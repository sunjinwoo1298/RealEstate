from __future__ import annotations
import asyncio
import threading
from typing import List, Optional

from backend.core.config import settings
from backend.core.logging import logger

_model = None
_model_lock = threading.Lock()


def _load_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                logger.info(f"Loading embedding model {settings.EMBEDDING_MODEL_NAME}...")
                _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    return _model


class EmbeddingService:
    """
    Provider-independent text embedding wrapper. Uses a local multilingual
    sentence-transformers model rather than an LLM-provider embedding API, so
    knowledge embeddings never depend on (or are billed through) the LLM
    provider used for chat orchestration (Groq).
    """

    @staticmethod
    async def embed_texts(texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        def _encode() -> List[List[float]]:
            model = _load_model()
            vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
            return [v.tolist() for v in vectors]

        return await asyncio.to_thread(_encode)

    @staticmethod
    async def embed_text(text: str) -> List[float]:
        vectors = await EmbeddingService.embed_texts([text])
        return vectors[0]
