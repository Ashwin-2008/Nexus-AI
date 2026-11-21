"""Contextual retrieval: bounded neighbour context around a hit.

Neighbour text is attached as ``metadata["neighbor_context"]`` instead of
replacing the hit text, so citations and verification continue to target the
matched chunk while the context builder may include adjacent sentences when the
token budget allows.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.document import DocumentChunk
from app.rag.types import EvidenceChunk, RagScope

MAX_NEIGHBOURS = 2
MAX_NEIGHBOUR_CHARS = 1200


def _org_uuid(scope: RagScope):
    return uuid.UUID(str(scope.organization_id))


def attach_neighbour_context(
    db: Session,
    scope: RagScope,
    evidence: list[EvidenceChunk],
    *,
    window: int = 1,
) -> int:
    if window <= 0 or not evidence:
        return 0
    window = min(window, MAX_NEIGHBOURS)
    document_ids = {
        uuid.UUID(item.document_id) for item in evidence if _uuid_ok(item.document_id)
    }
    if not document_ids:
        return 0
    rows = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.organization_id == _org_uuid(scope),
            DocumentChunk.document_id.in_(document_ids),
        )
        .all()
    )
    by_document: dict[tuple[str, int], DocumentChunk] = {
        (str(row.document_id), int(row.chunk_index)): row for row in rows
    }
    attached = 0
    for item in evidence:
        neighbours: list[str] = []
        index = None
        for (document_id, chunk_index), row in by_document.items():
            if document_id == str(item.document_id) and str(row.id) == str(item.chunk_id):
                index = chunk_index
                break
        if index is None:
            continue
        for offset in range(-window, window + 1):
            if offset == 0:
                continue
            row = by_document.get((str(item.document_id), index + offset))
            if row is not None and row.text:
                neighbours.append(row.text[:MAX_NEIGHBOUR_CHARS])
        if neighbours:
            item.metadata = {**(item.metadata or {}), "neighbor_context": neighbours}
            attached += 1
    return attached


def _uuid_ok(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False
