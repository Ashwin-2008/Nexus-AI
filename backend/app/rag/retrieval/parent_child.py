"""Parent-child retrieval expansion.

Children are embedded for precise matching; when a child hits, the larger
parent passage is loaded as context. The citation still points at the child's
char span, and the child text is retained for evidence matching.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.document import DocumentChunk
from app.rag.types import EvidenceChunk, RagScope

MAX_EXPANDED_CHARS = 4000


def _org_uuid(scope: RagScope):
    return uuid.UUID(str(scope.organization_id))


def expand_parents(db: Session, scope: RagScope, evidence: list[EvidenceChunk]) -> int:
    parent_ids: list[uuid.UUID] = []
    for item in evidence:
        parent_id = (item.metadata or {}).get("parent_chunk_id")
        if parent_id:
            try:
                parent_ids.append(uuid.UUID(str(parent_id)))
            except ValueError:
                continue
    if not parent_ids:
        return 0
    rows = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.organization_id == _org_uuid(scope),
            DocumentChunk.id.in_(parent_ids),
        )
        .all()
    )
    parents = {str(row.id): row for row in rows}
    expanded = 0
    for item in evidence:
        parent_id = (item.metadata or {}).get("parent_chunk_id")
        parent = parents.get(str(parent_id))
        if parent is None or not parent.text:
            continue
        if len(parent.text) > MAX_EXPANDED_CHARS:
            continue
        item.metadata = {
            **(item.metadata or {}),
            "child_text": item.text,
            "child_char_span": [item.char_start, item.char_end],
            "expanded_parent": True,
            "parent_char_span": [parent.char_start, parent.char_end],
        }
        item.text = parent.text
        item.char_start = parent.char_start
        item.char_end = parent.char_end
        expanded += 1
    return expanded
