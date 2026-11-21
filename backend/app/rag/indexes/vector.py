"""Vector index facade (reuses the Qdrant adapter)."""
from __future__ import annotations

from typing import Any

from app.rag.config import RagConfig
from app.rag.vectorstores.qdrant_store import QdrantVectorStore, get_vector_store


class VectorIndex:
    def __init__(self, config: RagConfig | None = None, dimensions: int | None = None) -> None:
        self.config = config or RagConfig.from_settings()
        self.store: QdrantVectorStore = get_vector_store(self.config, dimensions)

    @property
    def backend(self) -> str:
        return self.store.name

    def ensure(self) -> dict[str, Any]:
        self.store.ensure_collection()
        return self.store.health()

    def upsert(self, chunks: list[dict[str, Any]], vectors: list[list[float]]) -> int:
        return self.store.upsert(chunks, vectors)

    def delete_document(self, organization_id: str, document_id: str) -> int:
        return self.store.delete_document(organization_id, document_id)

    def count_for_document(self, organization_id: str, document_id: str) -> int:
        return self.store.count_for_document(organization_id, document_id)

    def health(self) -> dict[str, Any]:
        return self.store.health()


__all__ = ["VectorIndex"]
