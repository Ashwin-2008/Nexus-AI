"""Citation resolution.

Every citation maps to a chunk that was retrieved and revalidated for the
calling organization. Citations are deduplicated by chunk id and expose all
available provenance (document, page, section, span, URL, version).
"""
from __future__ import annotations

import uuid

from app.rag.citations.source_spans import page_number, source_span_for
from app.rag.exceptions import CitationError
from app.rag.types import Citation, EvidenceChunk, RagScope


class CitationResolver:
    def resolve(
        self,
        scope: RagScope,
        evidence: list[EvidenceChunk],
        indices: set[int] | None = None,
    ) -> list[Citation]:
        citations: list[Citation] = []
        seen_chunks: set[str] = set()
        for index, item in enumerate(evidence, start=1):
            if indices is not None and index not in indices:
                continue
            if item.chunk_id in seen_chunks:
                continue
            _validate_ids(item, scope)
            metadata = item.metadata or {}
            evidence_text = metadata.get("child_text") if metadata.get("expanded_parent") else item.text
            source_type = item.source_type or metadata.get("source_type") or "upload"
            document_title = (
                metadata.get("document_title")
                or item.document_filename
                or metadata.get("external_id")
                or "untitled document"
            )
            citations.append(
                Citation(
                    citation_id=f"cit-{item.chunk_id}",
                    index=index,
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    document_title=str(document_title),
                    source_type=str(source_type),
                    organization_id=item.organization_id,
                    document_version=item.document_version,
                    page_number=page_number(item.provenance),
                    section_heading=item.section_heading,
                    source_span=source_span_for(item),
                    url=metadata.get("uri") or metadata.get("url"),
                    file_reference=item.document_filename,
                    source_id=item.source_id,
                    score=round(float(item.score), 6),
                    evidence_text=evidence_text or item.text,
                )
            )
            seen_chunks.add(item.chunk_id)
        return citations


def _validate_ids(item: EvidenceChunk, scope: RagScope) -> None:
    if not item.chunk_id or not item.document_id:
        raise CitationError("evidence chunk is missing chunk/document identifiers")
    try:
        uuid.UUID(str(item.chunk_id))
        uuid.UUID(str(item.document_id))
    except (ValueError, TypeError) as exc:
        raise CitationError("evidence chunk identifiers are not valid UUIDs") from exc
    if item.organization_id and item.organization_id != scope.organization_id:
        raise CitationError("citation references a chunk outside the caller's organization")


def resolve_citations(
    scope: RagScope,
    evidence: list[EvidenceChunk],
    indices: set[int] | None = None,
) -> list[Citation]:
    return CitationResolver().resolve(scope, evidence, indices)
