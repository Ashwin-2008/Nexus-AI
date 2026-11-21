"""Vector store contract."""
from __future__ import annotations

from typing import Any, Protocol


class VectorStore(Protocol):
    name: str
    dimensions: int

    def ensure_collection(self) -> None: ...

    def upsert(self, chunks: list[dict[str, Any]], vectors: list[list[float]]) -> int: ...

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
    ) -> list[dict[str, Any]]: ...

    def delete_document(self, organization_id: str, document_id: str) -> int: ...

    def count_for_document(self, organization_id: str, document_id: str) -> int: ...

    def health(self) -> dict[str, Any]: ...
