"""Deduplication helpers.

Document-level duplicates are detected by SHA-256 of stored bytes within an
organization. Duplicates are reported in metadata; ingestion still proceeds by
default so a re-upload behaves predictably. Connector sync performs its own
skip-if-unchanged check before calling the pipeline.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.document import Document


def find_duplicates(
    db: Session,
    organization_id: uuid.UUID | str,
    content_hash: str,
    *,
    exclude_document_id: uuid.UUID | str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if not content_hash:
        return []
    query = db.query(Document).filter(
        Document.organization_id == organization_id,
        Document.content_hash == content_hash,
    )
    if exclude_document_id is not None:
        query = query.filter(Document.id != exclude_document_id)
    rows = query.order_by(Document.created_at.desc()).limit(limit).all()
    return [
        {
            "document_id": str(row.id),
            "filename": row.filename,
            "version": row.version,
            "status": row.status.value if hasattr(row.status, "value") else str(row.status),
        }
        for row in rows
    ]


def chunk_content_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()
