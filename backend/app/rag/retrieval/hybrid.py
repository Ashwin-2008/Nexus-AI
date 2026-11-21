"""Hybrid retrieval: dense + sparse fused with RRF, with explicit degradation."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.rag.config import RagConfig
from app.rag.exceptions import EmbeddingUnavailableError, VectorStoreUnavailableError
from app.rag.retrieval.dense import DenseRetriever
from app.rag.retrieval.fusion import reciprocal_rank_fusion
from app.rag.retrieval.sparse import SparseRetriever
from app.rag.types import EvidenceChunk, RagScope, RetrievalFilters

logger = logging.getLogger(__name__)


class HybridRetriever:
    mode = "hybrid"

    def __init__(
        self,
        config: RagConfig | None = None,
        dense: DenseRetriever | None = None,
        sparse: SparseRetriever | None = None,
    ) -> None:
        self.config = config or RagConfig.from_settings()
        self.dense = dense or DenseRetriever(self.config)
        self.sparse = sparse or SparseRetriever(self.config)

    def retrieve(
        self,
        db: Session,
        scope: RagScope,
        query: str,
        filters: RetrievalFilters,
        top_k: int | None = None,
        *,
        warnings: list[str] | None = None,
    ) -> list[EvidenceChunk]:
        limit = top_k or self.config.hybrid_top_k
        sparse_hits = self.sparse.retrieve(db, scope, query, filters, limit)
        dense_hits: list[EvidenceChunk] = []
        try:
            dense_hits = self.dense.retrieve(db, scope, query, filters, limit)
        except (EmbeddingUnavailableError, VectorStoreUnavailableError) as exc:
            message = f"dense retrieval unavailable: {exc}"
            logger.warning("%s — hybrid degrades to lexical", message)
            if warnings is not None:
                warnings.append(message)
        fused = reciprocal_rank_fusion([dense_hits, sparse_hits], top_k=limit)
        for item in fused:
            item.mode = "hybrid"
        return fused
