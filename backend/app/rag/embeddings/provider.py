"""Embedding adapters on top of the existing provider registry.

The repository already has a provider abstraction in
``app.services.embeddings`` (openai_compatible / local / hashing). This package
adds RAG-specific batching, caching, validation and health reporting. It does
not create a second provider implementation and never generates random or
hardcoded vectors.
"""
from __future__ import annotations

from typing import Any, Protocol

from app.rag.config import RagConfig
from app.rag.exceptions import EmbeddingDimensionError, EmbeddingUnavailableError


class Embedder(Protocol):
    name: str
    model: str
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class RagEmbeddingProvider:
    """Configured embedding provider with validation and caching."""

    def __init__(self, config: RagConfig | None = None, provider: Embedder | None = None) -> None:
        self.config = config or RagConfig.from_settings()
        if provider is None:
            from app.services.embeddings import EmbeddingError, get_embedding_provider

            try:
                provider = get_embedding_provider()
            except EmbeddingError as exc:
                raise EmbeddingUnavailableError(str(exc)) from exc
        self.provider = provider
        self.name = getattr(provider, "name", "unknown")
        self.model = getattr(provider, "model", self.name)
        self.dimensions = int(getattr(provider, "dimensions", 0) or 0)

        from app.rag.embeddings.cache import EmbeddingCache

        self.cache = EmbeddingCache(max_entries=self.config.embedding_cache_size)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        vectors = self._embed([text])
        if not vectors:
            raise EmbeddingUnavailableError("embedding provider returned no vector for the query")
        return vectors[0]

    def info(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "dimensions": self.dimensions,
            "cache_entries": self.cache.size,
            "semantic": self.name != "hashing",
            "note": "hashing is deterministic but non-semantic (CI/dev only)"
            if self.name == "hashing"
            else None,
        }

    def health(self, probe: bool = False) -> dict[str, Any]:
        result = {"healthy": True, **self.info()}
        if probe:
            try:
                vector = self.embed_query("nexus rag embedding health probe")
                result["probe_dimensions"] = len(vector)
            except EmbeddingUnavailableError as exc:
                result.update({"healthy": False, "error": str(exc)})
        return result

    # -- internals -----------------------------------------------------------

    def _embed(self, texts: list[str]) -> list[list[float]]:
        from app.rag.embeddings.batcher import embed_batched
        from app.rag.embeddings.validation import validate_vectors

        cleaned = [(text or "").strip() for text in texts]
        if not cleaned:
            return []
        if any(not text for text in cleaned):
            raise EmbeddingUnavailableError("refusing to embed empty text")
        try:
            vectors = embed_batched(
                self.provider,
                cleaned,
                cache=self.cache,
                batch_size=max(1, min(128, int(getattr(self.config, "embedding_batch_size", 64) or 64))),
            )
        except EmbeddingUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 — provider errors are normalized
            raise EmbeddingUnavailableError(f"embedding generation failed: {exc}") from exc
        if self.dimensions and vectors and len(vectors[0]) != self.dimensions:
            raise EmbeddingDimensionError(
                f"embedding dimension mismatch: configured {self.dimensions}, returned {len(vectors[0])}"
            )
        validate_vectors(vectors, expected_dimensions=self.dimensions or None)
        if not self.dimensions:
            self.dimensions = len(vectors[0])
        return vectors


def get_rag_embedder(config: RagConfig | None = None) -> RagEmbeddingProvider:
    return RagEmbeddingProvider(config=config)
