"""Lexical index facade.

The lexical index is the organization's ``document_chunks`` table queried with
BM25 in :mod:`app.services.search_service`. Parent-child parent rows are
excluded from lexical ranking; they exist for context expansion only.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.document import DocumentChunk
from app.rag.config import RagConfig
from app.rag.types import EvidenceChunk, RagScope, RetrievalFilters
from app.services import search_service


def _org_uuid(scope: RagScope) -> uuid.UUID:
    return uuid.UUID(str(scope.organization_id))


class LexicalIndex:
    backend = "postgres_chunk_rows_bm25"

    def __init__(self, config: RagConfig | None = None) -> None:
        self.config = config or RagConfig.from_settings()

    def search(
        self,
        db: Session,
        scope: RagScope,
        query: str,
        filters: RetrievalFilters,
        top_k: int | None = None,
    ) -> list[EvidenceChunk]:
        from app.rag.retrieval.sparse import _to_evidence

        hits = search_service.lexical_search(
            db,
            _org_uuid(scope),
            query,
            top_k or self.config.sparse_top_k,
            list(filters.document_ids) or None,
            source_ids=list(filters.source_ids) or None,
            source_types=list(filters.source_types) or None,
            access_scopes=list(scope.access_scopes),
            document_version=filters.document_version,
        )
        return [_to_evidence(hit, query) for hit in hits]

    @staticmethod
    def stats(db: Session, scope: RagScope) -> dict[str, Any]:
        org_id = uuid.UUID(str(scope.organization_id))
        query = db.query(func.count(DocumentChunk.id)).filter(
            DocumentChunk.organization_id == org_id
        )
        total = query.scalar() or 0
        indexed = (
            db.query(func.count(DocumentChunk.id))
            .filter(
                DocumentChunk.organization_id == org_id,
                DocumentChunk.embedding_model.isnot(None),
            )
            .scalar()
            or 0
        )
        return {"backend": LexicalIndex.backend, "chunks": int(total), "embedded_chunks": int(indexed)}


__all__ = ["LexicalIndex"]
