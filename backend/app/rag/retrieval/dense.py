"""Dense (vector) retrieval leg.

Reuses the existing embedding provider and organization-scoped vector index via
``app.services.search_service.semantic_search``; filters are passed through to
both the vector payload filter and the relational revalidation layer.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.rag.config import RagConfig
from app.rag.exceptions import EmbeddingUnavailableError, VectorStoreUnavailableError
from app.rag.types import EvidenceChunk, RagScope, RetrievalFilters
from app.services import search_service
from app.services.embeddings import EmbeddingError
from app.services.vector_index import VectorIndexError


class DenseRetriever:
    mode = "dense"

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
        try:
            hits = search_service.semantic_search(
                scope.organization_id,
                query,
                top_k or self.config.dense_top_k,
                list(filters.document_ids) or None,
                source_ids=list(filters.source_ids) or None,
                access_scopes=list(scope.access_scopes),
                document_version=filters.document_version,
            )
        except EmbeddingError as exc:
            raise EmbeddingUnavailableError(str(exc)) from exc
        except VectorIndexError as exc:
            raise VectorStoreUnavailableError(str(exc)) from exc
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
        mode="dense",
        provenance=list(hit.provenance or []),
        metadata=metadata,
        section_heading=metadata.get("section_heading"),
        source_id=metadata.get("source_id"),
        document_version=int(metadata.get("document_version") or 1),
        access_scope=str(metadata.get("access_scope") or "organization"),
        content_hash=str(metadata.get("content_hash") or ""),
        retrieval_scores={"dense": float(hit.score)},
        matched_queries=[query],
    )


__all__: list[Any] = ["DenseRetriever"]
