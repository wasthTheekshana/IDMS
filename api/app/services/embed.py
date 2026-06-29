"""Embedding provider protocol + Mistral implementation."""

from typing import Protocol, runtime_checkable

from app.core.config import settings


@runtime_checkable
class EmbedProvider(Protocol):
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class MistralEmbed:
    """Embed texts via Mistral mistral-embed (1024-dim)."""

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        from mistralai.client.sdk import Mistral

        client = Mistral(
            api_key=settings.MISTRAL_API_KEY,
            timeout_ms=60_000,
        )
        response = await client.embeddings.create_async(
            model=settings.EMBED_MODEL,
            inputs=texts,
        )
        return [e.embedding for e in response.data]


class StubEmbed:
    """Fallback — returns zero vectors when no API key is configured."""

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * settings.EMBED_DIM for _ in texts]
