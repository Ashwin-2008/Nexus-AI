"""Sparse/lexical retrieval leg (BM25 over organization chunk rows)."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.rag.config import RagConfig
from app.rag.types import EvidenceChunk, RagScope, RetrievalFilters
from app.services import search_service


def _org_uuid(scope: RagScope) -> uuid.UUID:
    return uuid.UUID(str(scope.organization_id))


class SparseRetriever:
    mode = "sparse"

    def __init__(self, config: RagConfig | None = None) -> None:
        self.config = config or RagConfig.from_settings()

    def retrieve(
        self,
        db: Session,
        scope: RagScope,
        query: str,
        filters: RetrievalFilters,
        top_k: int | None = None,
    ) -> list[EvidenceChunk]:
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


def _to_evidence(hit: search_service.SearchHit, query: str) -> EvidenceChunk:
    metadata = dict(hit.metadata or {})
    return EvidenceChunk(
        chunk_id=hit.chunk_id,
        document_id=hit.document_id,
        organization_id="",
        document_filename=hit.document_filename,
        text=hit.text,
        score=float(hit.score),
        mode="sparse",
        provenance=list(hit.provenance or []),
        metadata=metadata,
        section_heading=metadata.get("section_heading"),
        source_id=metadata.get("source_id"),
        document_version=int(metadata.get("document_version") or 1),
        access_scope=str(metadata.get("access_scope") or "organization"),
        content_hash=str(metadata.get("content_hash") or ""),
        retrieval_scores={"sparse": float(hit.score)},
        matched_queries=[query],
    )
