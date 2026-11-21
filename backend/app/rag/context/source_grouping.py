"""Group evidence by source document for context presentation."""
from __future__ import annotations

from typing import Any

from app.rag.types import EvidenceChunk


def group_by_document(evidence: list[EvidenceChunk]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in evidence:
        key = item.document_id
        if key not in groups:
            groups[key] = {
                "document_id": item.document_id,
                "document_title": (item.metadata or {}).get("document_title") or item.document_filename,
                "source_type": item.source_type or "upload",
                "chunks": [],
            }
            order.append(key)
        groups[key]["chunks"].append(item.chunk_id)
    return [groups[key] for key in order]


def group_by_source_type(evidence: list[EvidenceChunk]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in evidence:
        key = item.source_type or "upload"
        counts[key] = counts.get(key, 0) + 1
    return counts
