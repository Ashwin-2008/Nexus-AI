"""Heuristic reranking (documented fallback, no model required).

Score = retrieval-weight * normalized first-stage score
      + coverage-weight * query-term coverage
      + phrase-weight * exact-phrase bonus

It is deterministic and cheap, but it is *not* a learned reranker. The method
label is recorded on every chunk and in the API response.
"""
from __future__ import annotations

import re

from app.rag.constants import (
    HEURISTIC_RERANK_COVERAGE_WEIGHT,
    HEURISTIC_RERANK_PHRASE_WEIGHT,
    HEURISTIC_RERANK_RETRIEVAL_WEIGHT,
)
from app.rag.query.expansion import query_terms, stem_variants
from app.rag.reranking.base import BaseReranker
from app.rag.types import EvidenceChunk

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9]+")


def _terms(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text or "") if len(token) > 2}


def query_coverage(query: str, text: str, extra: str = "") -> float:
    """Fraction of meaningful query terms present in a passage.

    Used only for non-semantic embedding providers: when vectors carry no
    meaning, a passage that shares no terms with the question cannot be
    relevant, and keeping it makes the answer look ungrounded.
    """
    wanted: set[str] = set()
    for term in query_terms(query):
        wanted |= stem_variants(term)
    if not wanted:
        return 0.0
    return len(wanted & _terms(f"{text} {extra}")) / len(wanted)


def rerank_heuristic(query: str, chunks: list[EvidenceChunk], top_k: int | None = None) -> list[EvidenceChunk]:
    if not chunks:
        return []
    base_terms: list[str] = []
    for term in query_terms(query):
        base_terms.extend(sorted(stem_variants(term)))
    wanted = set(base_terms)
    highest = max((item.score for item in chunks), default=0.0) or 1.0
    phrase = re.sub(r"\s+", " ", (query or "").strip().lower())
    for item in chunks:
        terms = _terms(item.text)
        coverage = len(wanted & terms) / len(wanted) if wanted else 0.0
        phrase_bonus = 1.0 if phrase and len(phrase) >= 8 and phrase in (item.text or "").lower() else 0.0
        normalized_retrieval = max(0.0, min(1.0, item.score / highest))
        item.rerank_score = round(
            HEURISTIC_RERANK_RETRIEVAL_WEIGHT * normalized_retrieval
            + HEURISTIC_RERANK_COVERAGE_WEIGHT * coverage
            + HEURISTIC_RERANK_PHRASE_WEIGHT * phrase_bonus,
            8,
        )
        item.rerank_method = "heuristic"
    ordered = sorted(chunks, key=lambda item: (item.rerank_score or 0.0, item.score), reverse=True)
    return ordered[:top_k] if top_k else ordered


class HeuristicReranker(BaseReranker):
    method = "heuristic"

    def rerank(self, query: str, chunks: list[EvidenceChunk], top_k: int | None = None) -> list[EvidenceChunk]:
        return rerank_heuristic(query, chunks, top_k)
