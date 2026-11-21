"""Document version tracking.

Each successful index build creates a ``document_versions`` row. Versions are
monotonic per document and store the embedding model/strategy that produced
them, so a model change is traceable and can trigger safe re-indexing.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.rag import DocumentVersion


def next_version(db: Session, document_id: uuid.UUID) -> int:
    current = (
        db.query(func.max(DocumentVersion.version))
        .filter(DocumentVersion.document_id == document_id)
        .scalar()
    )
    return int(current or 0) + 1


def record_version(
    db: Session,
    document: Document,
    *,
    version: int,
    content_hash: str,
    chunk_count: int,
    chunk_strategy: str,
    embedding_provider: str,
    embedding_model: str,
    embedding_dimensions: int | None,
    status: str = "indexed",
    detail: dict[str, Any] | None = None,
) -> DocumentVersion:
    row = DocumentVersion(
        id=uuid.uuid4(),
        document_id=document.id,
        organization_id=document.organization_id,
        version=version,
        content_hash=content_hash,
        chunk_count=chunk_count,
        chunk_strategy=chunk_strategy,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
        status=status,
        detail=json.dumps(detail or {}, ensure_ascii=False, default=str),
    )
    db.add(row)
    return row


def list_versions(db: Session, organization_id: uuid.UUID, document_id: uuid.UUID) -> list[DocumentVersion]:
    return (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.organization_id == organization_id,
            DocumentVersion.document_id == document_id,
        )
        .order_by(DocumentVersion.version.desc())
        .all()
    )


def latest_version(db: Session, document_id: uuid.UUID) -> DocumentVersion | None:
    return (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version.desc())
        .first()
    )
