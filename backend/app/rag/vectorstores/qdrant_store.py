"""Qdrant adapter for the RAG vector index.

Reuses the existing, organization-scoped ``app.services.vector_index`` client.
No second Qdrant client or collection is created.
"""
from __future__ import annotations

from typing import Any

from app.rag.config import RagConfig
from app.rag.exceptions import VectorStoreUnavailableError
from app.rag.vectorstores.base import VectorStore
from app.services.vector_index import VectorIndexError, get_vector_index


class QdrantVectorStore:
    def __init__(self, config: RagConfig | None = None, dimensions: int | None = None) -> None:
        self.config = config or RagConfig.from_settings()
        self.dimensions = int(dimensions or self.config.embedding_dimensions or 0)
        try:
            self.index = get_vector_index(dimensions=self.dimensions or None)
        except VectorIndexError as exc:
            raise VectorStoreUnavailableError(str(exc)) from exc
        self.name = getattr(self.index, "name", "qdrant")
        self.dimensions = int(getattr(self.index, "dimensions", self.dimensions) or self.dimensions)

    def ensure_collection(self) -> None:
        try:
            self.index.ensure_collection()
        except VectorIndexError as exc:
            raise VectorStoreUnavailableError(str(exc)) from exc

    def upsert(self, chunks: list[dict[str, Any]], vectors: list[list[float]]) -> int:
        try:
            return int(self.index.upsert_chunks(chunks, vectors))
        except VectorIndexError as exc:
            raise VectorStoreUnavailableError(str(exc)) from exc

    def search(
        self,
        vector: list[float],
        organization_id: str,
        top_k: int = 8,
        *,
        document_ids: list[str] | None = None,
        source_ids: list[str] | None = None,
        access_scopes: list[str] | None = None,
        document_version: int | None = None,
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "document_ids": document_ids,
            "source_ids": source_ids,
            "access_scopes": access_scopes,
            "document_version": document_version,
        }
        try:
            return self.index.search(vector=vector, organization_id=organization_id, top_k=top_k, **kwargs)
        except VectorIndexError as exc:
            raise VectorStoreUnavailableError(str(exc)) from exc

    def delete_document(self, organization_id: str, document_id: str) -> int:
        try:
            return int(self.index.delete_document(organization_id, document_id))
        except VectorIndexError as exc:
            raise VectorStoreUnavailableError(str(exc)) from exc

    def count_for_document(self, organization_id: str, document_id: str) -> int:
        try:
            return int(self.index.count_for_document(organization_id, document_id))
        except VectorIndexError as exc:
            raise VectorStoreUnavailableError(str(exc)) from exc

    def health(self) -> dict[str, Any]:
        try:
            return {
                "backend": self.name,
                "dimensions": self.dimensions,
                **self.index.health(),
            }
        except Exception as exc:  # noqa: BLE001
            return {"backend": self.name, "healthy": False, "error": str(exc)}


def get_vector_store(config: RagConfig | None = None, dimensions: int | None = None) -> QdrantVectorStore:
    return QdrantVectorStore(config, dimensions)


__all__ = ["QdrantVectorStore", "VectorStore", "get_vector_store"]
