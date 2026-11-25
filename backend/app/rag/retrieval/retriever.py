"""Retrieval orchestration: query variants → legs → fusion → authorization →
reranking → parent expansion → final evidence set.

The retriever is the only place that turns backend results into
``EvidenceChunk`` objects, so authorization revalidation happens exactly once
per stage and cannot be bypassed by a specialist agent.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from sqlalchemy.orm import Session

from app.rag.config import RagConfig
from app.rag.exceptions import RerankError, RerankerUnavailableError
from app.rag.query.analyzer import QueryAnalyzer
from app.rag.reranking.provider import get_reranker
from app.rag.retrieval.dense import DenseRetriever
from app.rag.retrieval.fusion import reciprocal_rank_fusion
from app.rag.retrieval.hybrid import HybridRetriever
from app.rag.retrieval.multi_query import MultiQueryRetriever
from app.rag.retrieval.parent_child import expand_parents
from app.rag.retrieval.contextual import attach_neighbour_context
from app.rag.retrieval.sparse import SparseRetriever
from app.rag.retrieval.filters import effective_filters, revalidate_evidence
from app.rag.types import EvidenceChunk, QueryAnalysis, RagScope, RetrievalFilters, RetrievalResult

logger = logging.getLogger(__name__)


class Retriever:
    def __init__(
        self,
        config: RagConfig | None = None,
        *,
        dense: DenseRetriever | None = None,
        sparse: SparseRetriever | None = None,
        hybrid: HybridRetriever | None = None,
        multi_query: MultiQueryRetriever | None = None,
    ) -> None:
        self.config = config or RagConfig.from_settings()
        self.dense = dense or DenseRetriever(self.config)
        self.sparse = sparse or SparseRetriever(self.config)
        self.hybrid = hybrid or HybridRetriever(self.config, self.dense, self.sparse)
        self.multi_query = multi_query or MultiQueryRetriever(self.config, self.hybrid)
        self.analyzer = QueryAnalyzer(self.config)

    def retrieve(
        self,
        db: Session,
        scope: RagScope,
        query: str,
        *,
        filters: RetrievalFilters | None = None,
        mode: str | None = None,
        top_k: int | None = None,
        rerank: bool | None = None,
        analysis: QueryAnalysis | None = None,
        warnings: list[str] | None = None,
    ) -> RetrievalResult:
        started = time.monotonic()
        warnings = warnings if warnings is not None else []
        mode = (mode or self.config.retrieval_mode or "hybrid").strip().lower()
        if mode not in {"hybrid", "dense", "sparse"}:
            warnings.append(f"unknown retrieval mode '{mode}', using hybrid")
            mode = "hybrid"

        # Hashing vectors encode no meaning: a dense leg would add near-random
        # neighbours and drown the lexical matches in RRF. Use BM25 alone and
        # say so, rather than returning irrelevant context.
        non_semantic = (self.config.embedding_provider or "").strip().lower() in {"hashing", "hash"}
        if non_semantic and mode in {"hybrid", "dense"}:
            warnings.append(
                "keyword-only retrieval: EMBEDDING_PROVIDER=hashing is not semantic; "
                "configure a real embeddings provider for paraphrase search"
            )
            mode = "sparse"

        effective, deny_all, filter_warnings = effective_filters(db, scope, filters)
        warnings.extend(filter_warnings)
        if deny_all:
            return RetrievalResult(
                query=query,
                mode=mode,
                evidence=[],
                warnings=warnings,
                filtered_count=0,
                timings={"retrieval_ms": _ms(started)},
            )

        analysis = analysis or self.analyzer.analyze(query)
        queries = analysis.retrieval_queries if self.config.multi_query else analysis.retrieval_queries[:1]
        if not queries:
            return RetrievalResult(query=query, mode=mode, warnings=warnings)

        leg_started = time.monotonic()
        candidates = self._retrieve_queries(db, scope, queries, effective, mode, warnings)
        timings = {"retrieval_ms": _ms(leg_started)}

        coverage_query = query
        query_expanded = False
        if (
            non_semantic
            and mode == "sparse"
            and analysis.intent not in {"summarize", "report", "conversational"}
        ):
            from app.rag.reranking.scoring import query_coverage

            best = max(
                (
                    query_coverage(
                        query,
                        item.text,
                        f"{item.document_filename} {item.section_heading or ''}",
                    )
                    for item in candidates
                ),
                default=0.0,
            )
            if best < 0.25:
                extra_query = self._expand_query(query)
                if extra_query:
                    extra = self._retrieve_queries(
                        db, scope, [extra_query], effective, mode, warnings
                    )
                    merged = {item.chunk_id or item.citation_key: item for item in candidates}
                    for item in extra:
                        key = item.chunk_id or item.citation_key
                        current = merged.get(key)
                        if current is None or item.score > current.score:
                            merged[key] = item
                    candidates = list(merged.values())
                    queries = [*queries, extra_query]
                    query_expanded = True
                    # The expansion is document-like; scoring the original
                    # question as well would dilute every long expansion.
                    coverage_query = extra_query

        candidates, filtered_count = revalidate_evidence(db, scope, effective, candidates)
        candidates = _dedupe(candidates)
        if self.config.min_relevance > 0:
            candidates = [item for item in candidates if item.score >= self.config.min_relevance]

        reranker_label = "none"
        rerank_ms = 0
        if rerank is not False and self.config.reranker != "none" and candidates:
            rerank_started = time.monotonic()
            reranker = get_reranker(self.config.reranker, self.config)
            try:
                candidates = reranker.rerank(query, candidates, self.config.rerank_top_k)
                reranker_label = getattr(reranker, "method", self.config.reranker)
            except (RerankerUnavailableError, RerankError) as exc:
                logger.warning("configured reranker failed (%s); falling back to heuristic", exc)
                warnings.append(f"configured reranker unavailable: {str(exc)[:200]}")
                from app.rag.reranking.scoring import rerank_heuristic

                candidates = rerank_heuristic(query, candidates, self.config.rerank_top_k)
                reranker_label = "heuristic_fallback"
            rerank_ms = _ms(rerank_started)
            candidates, filtered_after = revalidate_evidence(db, scope, effective, candidates)
            filtered_count += filtered_after

        if non_semantic and candidates and analysis.intent not in {"summarize", "report", "conversational"}:
            from app.rag.reranking.scoring import query_coverage

            scored = [
                (
                    item,
                    query_coverage(
                        coverage_query,
                        item.text,
                        f"{item.document_filename} {item.section_heading or ''}",
                    ),
                )
                for item in candidates
            ]
            best = max((value for _item, value in scored), default=0.0)
            if query_expanded:
                # Expansion keywords are diverse, so fractional coverage is
                # low by construction; keep every passage that matched any of
                # them and let the LLM discard the rest.
                kept = [item for item, value in scored if value > 0]
                if kept:
                    candidates = kept
            elif best <= 0:
                from app.rag.generation.provider import llm_configured

                if llm_configured() and candidates:
                    # Nothing overlaps lexically, but a real LLM can still use
                    # these passages (they were ranked by BM25). Dropping them
                    # would turn a paraphrase into a false "no evidence".
                    warnings.append(
                        "no retrieved chunk shares a term with the question; "
                        "passing the best keyword-ranked passages to the LLM"
                    )
                else:
                    warnings.append(
                        "no retrieved chunk shares a term with the question; "
                        "semantic search needs a real embeddings provider"
                    )
                    candidates = []
            else:
                threshold = max(0.25, best * 0.5)
                kept = [item for item, value in scored if value >= threshold]
                candidates = kept

        expanded = expand_parents(db, scope, candidates)
        attach_neighbour_context(db, scope, candidates, window=0)
        final_limit = int(top_k or self.config.final_top_k)
        evidence = candidates[:final_limit]
        for rank, item in enumerate(evidence, start=1):
            item.retrieval_rank = rank

        timings["total_retrieval_ms"] = _ms(started)
        timings["rerank_ms"] = rerank_ms
        return RetrievalResult(
            query=query,
            mode=mode,
            evidence=evidence,
            queries_used=queries,
            reranker=reranker_label,
            filtered_count=filtered_count,
            warnings=warnings,
            timings=timings,
        )

    # -- internals -----------------------------------------------------------

    def _expand_query(self, query: str) -> str:
        """Turn a paraphrase into document-like keywords with the configured LLM.

        Only used for non-semantic embeddings, where BM25 is the sole retriever:
        a question that shares no terms with the source otherwise returns no
        evidence even though the answer is present. Failure is non-fatal.
        """
        if not self.config.query_rewrite:
            return ""
        try:
            from app.rag.generation.provider import chat, llm_configured

            if not llm_configured():
                return ""
            result = chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You rewrite a question into a short keyword search query for an "
                            "enterprise document index. Output only keywords or synonyms likely "
                            "to appear in the answer, 6 to 15 words, one line, no quotes, no "
                            "explanation."
                        ),
                    },
                    {"role": "user", "content": query},
                ],
                temperature=0.0,
                # gpt-oss spends part of the budget on reasoning before it
                # emits the keyword line; 300 tokens can leave the answer empty.
                max_tokens=600,
            )
            line = " ".join((result.text or "").split())
            line = re.sub(r"^[\"'`]+|[\"'`]+$", "", line).strip()
            if not line or len(line) > 240:
                return ""
            return line
        except Exception as exc:  # noqa: BLE001 — expansion is best-effort
            logger.warning("lexical query expansion failed: %s", exc)
            return ""

    def _retrieve_queries(
        self,
        db: Session,
        scope: RagScope,
        queries: list[str],
        filters: RetrievalFilters,
        mode: str,
        warnings: list[str],
    ) -> list[EvidenceChunk]:
        if len(queries) > 1 and self.config.multi_query:
            if mode == "hybrid":
                return self.multi_query.retrieve(
                    db,
                    scope,
                    queries,
                    filters,
                    self.config.hybrid_top_k,
                    warnings=warnings,
                )
            rankings = [
                self._single(db, scope, query, filters, mode, warnings) for query in queries
            ]
            fused = reciprocal_rank_fusion(rankings, top_k=self.config.hybrid_top_k)
            for item in fused:
                item.mode = mode
            return fused
        return self._single(db, scope, queries[0], filters, mode, warnings)

    def _single(
        self,
        db: Session,
        scope: RagScope,
        query: str,
        filters: RetrievalFilters,
        mode: str,
        warnings: list[str],
    ) -> list[EvidenceChunk]:
        if mode == "dense":
            try:
                return self.dense.retrieve(db, scope, query, filters, self.config.dense_top_k)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"dense retrieval unavailable: {str(exc)[:200]}")
                return []
        if mode == "sparse":
            return self.sparse.retrieve(db, scope, query, filters, self.config.sparse_top_k)
        return self.hybrid.retrieve(
            db, scope, query, filters, self.config.hybrid_top_k, warnings=warnings
        )


def _dedupe(items: list[EvidenceChunk]) -> list[EvidenceChunk]:
    """Remove identical and near-identical chunks, preserving richer text."""
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    kept: list[EvidenceChunk] = []
    token_cache: list[set[str]] = []
    for item in items:
        key = item.chunk_id or item.citation_key
        if key in seen_ids:
            continue
        if item.content_hash and item.content_hash in seen_hashes:
            continue
        tokens = set((item.text or "").lower().split()[:400])
        duplicate = False
        for existing in token_cache:
            if not tokens or not existing:
                continue
            overlap = len(tokens & existing) / len(tokens | existing)
            if overlap >= 0.92:
                duplicate = True
                break
        if duplicate:
            continue
        seen_ids.add(key)
        if item.content_hash:
            seen_hashes.add(item.content_hash)
        token_cache.append(tokens)
        kept.append(item)
    return kept


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


__all__: list[Any] = ["Retriever"]
