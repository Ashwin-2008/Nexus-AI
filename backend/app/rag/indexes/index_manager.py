"""Index manager: collection lifecycle and synchronization status."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.rag.config import RagConfig
from app.rag.indexes.lexical import LexicalIndex
from app.rag.indexes.synchronization import document_sync_status, organization_sync_status
from app.rag.indexes.vector import VectorIndex
from app.rag.types import RagScope


class IndexManager:
    def __init__(self, config: RagConfig | None = None) -> None:
        self.config = config or RagConfig.from_settings()

    def status(self, db: Session, scope: RagScope) -> dict[str, Any]:
        vector = VectorIndex(self.config)
        return {
            "vector": vector.health(),
            "lexical": LexicalIndex.stats(db, scope),
            "collection": getattr(vector.store.index, "collection", None),
        }

    def ensure_collection(self) -> dict[str, Any]:
        return VectorIndex(self.config).ensure()

    def document_sync(self, db: Session, organization_id: uuid.UUID, document_id: uuid.UUID) -> dict[str, Any]:
        return document_sync_status(db, organization_id, document_id, config=self.config)

    def organization_sync(self, db: Session, organization_id: uuid.UUID, limit: int = 100) -> list[dict[str, Any]]:
        return organization_sync_status(db, organization_id, config=self.config, limit=limit)


__all__ = ["IndexManager"]
