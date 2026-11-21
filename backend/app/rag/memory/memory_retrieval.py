"""Prior-evidence memory for follow-up questions.

Previously cited chunks are re-read from the database and re-authorized before
reuse. Stale or unauthorized citations are silently dropped; nothing from
memory can bypass current permissions.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage
from app.rag.retrieval.filters import revalidate_evidence
from app.rag.types import EvidenceChunk, RagScope, RetrievalFilters


def prior_evidence(
    db: Session,
    scope: RagScope,
    conversation_id: str | None,
    *,
    limit: int = 3,
) -> list[EvidenceChunk]:
    if not conversation_id:
        return []
    message = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id, ChatMessage.role == "assistant")
        .order_by(ChatMessage.created_at.desc())
        .first()
    )
    if message is None or not message.citations:
        return []
    try:
        citations = json.loads(message.citations)
    except Exception:  # noqa: BLE001
        return []
    candidates: list[EvidenceChunk] = []
    for citation in citations[: max(limit, 1) * 3]:
        if not isinstance(citation, dict):
            continue
        chunk_id = citation.get("chunk_id")
        document_id = citation.get("document_id")
        if not chunk_id or not document_id:
            continue
        candidates.append(
            EvidenceChunk(
                chunk_id=str(chunk_id),
                document_id=str(document_id),
                organization_id=scope.organization_id,
                document_filename=str(citation.get("document_title") or citation.get("document_filename") or ""),
                text=str(citation.get("evidence_text") or citation.get("text") or ""),
                score=0.0,
                mode="memory",
                retrieval_scores={"memory": 0.0},
            )
        )
    allowed, _rejected = revalidate_evidence(db, scope, RetrievalFilters(), candidates)
    return allowed[:limit]
