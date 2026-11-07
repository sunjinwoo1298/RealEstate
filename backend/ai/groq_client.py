from __future__ import annotations
import json
from dataclasses import dataclass
from typing import List, Type, TypeVar

from groq import AsyncGroq
from pydantic import BaseModel, ValidationError

from backend.core.config import settings

T = TypeVar("T", bound=BaseModel)

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    return _client


class LLMProviderError(Exception):
    """Raised when the LLM provider fails or returns an unusable response."""


@dataclass
class StructuredCompletion:
    data: BaseModel
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int


class GroqClient:
    """
    Isolates all Groq-specific provider details (model id, request shape,
    JSON-mode parsing) behind a single call that returns a validated
    Pydantic model, so business/orchestration code never depends on the
    LLM provider directly.
    """

    @staticmethod
    async def generate_structured(
        *,
        system_prompt: str,
        messages: List[dict],
        schema: Type[T],
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> StructuredCompletion:
        import time

        client = _get_client()
        start = time.monotonic()
        try:
            response = await client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[{"role": "system", "content": system_prompt}, *messages],
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:  # noqa: BLE001 - any provider/network failure is treated uniformly
            raise LLMProviderError(f"Groq request failed: {e}") from e

        latency_ms = (time.monotonic() - start) * 1000
        raw_content = response.choices[0].message.content or "{}"

        try:
            parsed = json.loads(raw_content)
            data = schema.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as e:
            raise LLMProviderError(f"Groq returned an unparseable structured response: {e}") from e

        usage = response.usage
        return StructuredCompletion(
            data=data,
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
