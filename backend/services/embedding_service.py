from __future__ import annotations
import asyncio
import math
import threading
from typing import Any, List, Optional

import httpx

from backend.core.config import settings
from backend.core.logging import logger

_model = None
_model_lock = threading.Lock()


def _normalize_vector(vec: List[float]) -> List[float]:
    """Normalizes a vector to unit length (L2 norm = 1)."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def _load_local_model():
    """Lazy loader for local sentence-transformers model (used when HF_TOKEN is unset)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError:
                    raise RuntimeError(
                        "Local embedding model requested but 'sentence-transformers' is not installed. "
                        "Please set HF_TOKEN in your environment to use the Hugging Face Serverless API, "
                        "or install: pip install sentence-transformers torch"
                    )

                logger.info(f"Loading local embedding model {settings.EMBEDDING_MODEL_NAME}...")
                _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    return _model


class EmbeddingService:
    """
    Provider-independent text embedding service.

    When `HF_TOKEN` is configured, embeddings are requested remotely from the
    Hugging Face Inference API. This avoids downloading the model or keeping PyTorch
    in memory on the host, dramatically lowering memory usage (~150 MB instead of ~2 GB)
    and allowing the backend to run on smaller plans (e.g. Render Starter or Free tier).

    If `HF_TOKEN` is not set, it falls back to the local sentence-transformers model.
    """

    @classmethod
    def get_hf_endpoints(cls) -> List[str]:
        if settings.HF_API_URL:
            return [settings.HF_API_URL]
        model_id = settings.EMBEDDING_MODEL_NAME
        return [
            f"https://router.huggingface.co/hf-inference/models/{model_id}/pipeline/feature-extraction",
            f"https://router.huggingface.co/hf-inference/models/{model_id}",
        ]

    @classmethod
    def _parse_hf_response(cls, data: Any, expected_count: int) -> List[List[float]]:
        # Single vector: [float, float, ...]
        if isinstance(data, list) and data and isinstance(data[0], (int, float)):
            vec = [float(x) for x in data]
            return [_normalize_vector(vec)]

        # List of items:
        if isinstance(data, list) and data and isinstance(data[0], list):
            # 3D tensor: token-level [batch, seq_len, dim] -> perform mean pooling
            if data[0] and isinstance(data[0][0], list):
                pooled = []
                for token_matrix in data:
                    dim = len(token_matrix[0])
                    num_tokens = len(token_matrix)
                    avg = [
                        sum(token_matrix[t][d] for t in range(num_tokens)) / num_tokens
                        for d in range(dim)
                    ]
                    pooled.append(_normalize_vector(avg))
                return pooled

            # 2D list of vectors: [[float, ...], [float, ...]]
            return [_normalize_vector([float(x) for x in item]) for item in data]

        raise ValueError(f"Unexpected Hugging Face embedding response format: {type(data)} -> {data}")

    @classmethod
    async def _embed_via_hf(cls, texts: List[str]) -> List[List[float]]:
        token = settings.HF_TOKEN.strip()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": texts,
            "options": {"wait_for_model": True},
        }

        urls = cls.get_hf_endpoints()
        last_error = None

        async with httpx.AsyncClient(timeout=settings.HF_EMBEDDING_TIMEOUT_SECONDS) as client:
            for url in urls:
                try:
                    response = await client.post(url, headers=headers, json=payload)

                    if response.status_code == 200:
                        data = response.json()
                        return cls._parse_hf_response(data, expected_count=len(texts))

                    if response.status_code == 403:
                        msg = (
                            "Hugging Face token returned 403 Forbidden. "
                            "Please ensure your token in https://huggingface.co/settings/tokens "
                            "has 'Make calls to Inference Providers' permission enabled."
                        )
                        logger.error(msg)
                        raise RuntimeError(msg)

                    error_body = response.text
                    logger.warning(
                        f"HF embedding request to {url} returned status {response.status_code}: {error_body[:200]}"
                    )
                    last_error = RuntimeError(
                        f"Hugging Face returned status {response.status_code}: {error_body}"
                    )
                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    logger.warning(f"HF embedding connection failed for {url}: {exc}")
                    last_error = exc

        raise RuntimeError(f"Failed to generate embeddings via Hugging Face API: {last_error}")

    @staticmethod
    async def embed_texts(texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        if settings.HF_TOKEN and settings.HF_TOKEN.strip():
            return await EmbeddingService._embed_via_hf(texts)

        # Fallback to local sentence-transformers model
        def _encode() -> List[List[float]]:
            model = _load_local_model()
            vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
            return [v.tolist() for v in vectors]

        return await asyncio.to_thread(_encode)

    @staticmethod
    async def embed_text(text: str) -> List[float]:
        vectors = await EmbeddingService.embed_texts([text])
        return vectors[0]
