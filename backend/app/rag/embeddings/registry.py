"""Embedding provider registry facade (reuses app.services.embeddings)."""
from __future__ import annotations

from typing import Any

from app.rag.config import RagConfig
from app.rag.embeddings.provider import RagEmbeddingProvider, get_rag_embedder
from app.services.embeddings import _PROVIDERS, EmbeddingError

AVAILABLE_PROVIDERS = tuple(sorted(_PROVIDERS))


def build_embedder(config: RagConfig | None = None) -> RagEmbeddingProvider:
    return get_rag_embedder(config)


def provider_names() -> list[str]:
    return list(AVAILABLE_PROVIDERS)


def provider_metadata(config: RagConfig | None = None) -> dict[str, Any]:
    config = config or RagConfig.from_settings()
    try:
        return get_rag_embedder(config).info()
    except EmbeddingError as exc:
        return {"provider": config.embedding_provider, "available": False, "error": str(exc)}


__all__ = ["AVAILABLE_PROVIDERS", "build_embedder", "provider_metadata", "provider_names"]
