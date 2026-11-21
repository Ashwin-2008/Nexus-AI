"""Vector/lexical index synchronization checks.

Vector upserts and relational chunk rows are written by the same ingestion
transaction path; this module verifies the result and can request a safe
re-index when counts diverge.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk
from app.rag.config import RagConfig
from app.rag.indexes.vector import VectorIndex


def document_sync_status(
    db: Session,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    config: RagConfig | None = None,
) -> dict[str, Any]:
    chunk_count = (
        db.query(func.count(DocumentChunk.id))
        .filter(
            DocumentChunk.organization_id == organization_id,
            DocumentChunk.document_id == document_id,
            (DocumentChunk.chunk_strategy.is_(None)) | (DocumentChunk.chunk_strategy != "parent_child_parent"),
        )
        .scalar()
        or 0
    )
    vector_count = None
    vector_error = None
    try:
        vector_count = VectorIndex(config).count_for_document(str(organization_id), str(document_id))
    except Exception as exc:  # noqa: BLE001
        vector_error = str(exc)
    return {
        "document_id": str(document_id),
        "lexical_chunks": int(chunk_count),
        "vector_points": vector_count,
        "in_sync": vector_count is not None and int(chunk_count) == int(vector_count),
        "vector_error": vector_error,
    }


def organization_sync_status(
    db: Session,
    organization_id: uuid.UUID,
    *,
    config: RagConfig | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    documents = (
        db.query(Document)
        .filter(Document.organization_id == organization_id)
        .order_by(Document.updated_at.desc())
        .limit(limit)
        .all()
    )
    return [
        document_sync_status(db, organization_id, document.id, config=config) for document in documents
    ]
