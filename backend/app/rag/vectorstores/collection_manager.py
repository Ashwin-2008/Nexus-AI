"""Collection lifecycle helpers."""
from __future__ import annotations

from typing import Any

from app.rag.config import RagConfig
from app.rag.vectorstores.qdrant_store import QdrantVectorStore, get_vector_store


class CollectionManager:
    def __init__(self, store: QdrantVectorStore | None = None, config: RagConfig | None = None) -> None:
        self.store = store or get_vector_store(config)

    def ensure(self, dimensions: int | None = None) -> dict[str, Any]:
        if dimensions:
            self.store.dimensions = int(dimensions)
        self.store.ensure_collection()
        return self.describe()

    def describe(self) -> dict[str, Any]:
        health = self.store.health()
        return {
            "backend": self.store.name,
            "collection": getattr(self.store.index, "collection", None),
            "dimensions": self.store.dimensions,
            "healthy": bool(health.get("healthy")),
            "points": health.get("points"),
        }

    def delete_document(self, organization_id: str, document_id: str) -> int:
        return self.store.delete_document(organization_id, document_id)
