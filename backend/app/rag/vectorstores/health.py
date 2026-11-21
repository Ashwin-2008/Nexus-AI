"""Dependency health reporting for the RAG stack."""
from __future__ import annotations

from typing import Any

from app.rag.config import RagConfig
from app.rag.vectorstores.qdrant_store import get_vector_store


def rag_dependency_health(config: RagConfig | None = None) -> dict[str, Any]:
    config = config or RagConfig.from_settings()
    result: dict[str, Any] = {}

    try:
        from app.rag.embeddings.provider import get_rag_embedder

        embedder = get_rag_embedder(config)
        result["embeddings"] = embedder.health()
    except Exception as exc:  # noqa: BLE001
        result["embeddings"] = {"healthy": False, "error": str(exc), "provider": config.embedding_provider}

    try:
        result["vector_store"] = get_vector_store(config).health()
    except Exception as exc:  # noqa: BLE001
        result["vector_store"] = {"healthy": False, "error": str(exc)}

    try:
        from app.services.llm import llm_available

        result["llm"] = {
            "configured": llm_available(),
            "provider": config.llm_provider,
        }
    except Exception as exc:  # noqa: BLE001
        result["llm"] = {"configured": False, "error": str(exc)}

    result["lexical"] = {"backend": "postgres_chunk_rows_bm25", "healthy": True}
    result["reranker"] = {"configured": config.reranker}
    return result
