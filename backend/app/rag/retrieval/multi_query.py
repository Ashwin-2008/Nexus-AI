"""Multi-query retrieval and query fusion."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.rag.config import RagConfig
from app.rag.retrieval.fusion import reciprocal_rank_fusion
from app.rag.retrieval.hybrid import HybridRetriever
from app.rag.types import EvidenceChunk, RagScope, RetrievalFilters


class MultiQueryRetriever:
    def __init__(self, config: RagConfig | None = None, base: HybridRetriever | None = None) -> None:
        self.config = config or RagConfig.from_settings()
        self.base = base or HybridRetriever(self.config)

    def retrieve(
        self,
        db: Session,
        scope: RagScope,
        queries: list[str],
        filters: RetrievalFilters,
        top_k: int | None = None,
        *,
        warnings: list[str] | None = None,
    ) -> list[EvidenceChunk]:
        unique: list[str] = []
        seen: set[str] = set()
        for query in queries:
            key = (query or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(query.strip())
        if not unique:
            return []
        rankings: list[list[EvidenceChunk]] = []
        per_query = top_k or self.config.hybrid_top_k
        for query in unique[: max(1, self.config.max_subqueries + 1)]:
            ranking = self.base.retrieve(db, scope, query, filters, per_query, warnings=warnings)
            for item in ranking:
                item.matched_queries = list({*item.matched_queries, query})
            rankings.append(ranking)
        if len(rankings) == 1:
            for rank, item in enumerate(rankings[0], start=1):
                item.retrieval_rank = rank
            return rankings[0]
        fused = reciprocal_rank_fusion(rankings, top_k=per_query)
        return fused
