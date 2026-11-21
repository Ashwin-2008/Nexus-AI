"""Rank fusion utilities.

Reciprocal Rank Fusion (Cormack, Clarke & Buettcher, 2009) is used to combine
independent rankings (dense + lexical, or multiple query variants). It is
rank-based, so it does not require commensurable scores.
"""
from __future__ import annotations

from app.rag.constants import RRF_K
from app.rag.types import EvidenceChunk


def reciprocal_rank_fusion(
    rankings: list[list[EvidenceChunk]],
    *,
    k: int = RRF_K,
    top_k: int | None = None,
) -> list[EvidenceChunk]:
    scores: dict[str, float] = {}
    merged: dict[str, EvidenceChunk] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            key = item.citation_key
            if key not in merged:
                merged[key] = item
                merged[key].retrieval_rank = rank
                merged[key].retrieval_scores = dict(item.retrieval_scores or {})
            else:
                existing = merged[key]
                # Prefer records with richer text/metadata.
                if len(item.text) > len(existing.text):
                    merged[key] = item
                else:
                    merged[key].retrieval_scores.update(item.retrieval_scores or {})
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    ordered = sorted(merged.values(), key=lambda item: scores.get(item.citation_key, 0.0), reverse=True)
    for rank, item in enumerate(ordered, start=1):
        item.score = round(scores.get(item.citation_key, 0.0), 8)
        item.retrieval_scores["rrf"] = item.score
        item.retrieval_rank = rank
        if item.mode != "hybrid":
            item.mode = "hybrid"
    return ordered[:top_k] if top_k else ordered


def weighted_score_fusion(
    rankings: list[tuple[float, list[EvidenceChunk]]],
    *,
    top_k: int | None = None,
) -> list[EvidenceChunk]:
    """Normalize each ranking to 0..1 and combine with explicit weights."""
    scores: dict[str, float] = {}
    merged: dict[str, EvidenceChunk] = {}
    for weight, ranking in rankings:
        if not ranking:
            continue
        high = max(item.score for item in ranking) or 1.0
        low = min(item.score for item in ranking)
        span = (high - low) or 1.0
        for item in ranking:
            key = item.citation_key
            merged.setdefault(key, item)
            scores[key] = scores.get(key, 0.0) + weight * ((item.score - low) / span)
    ordered = sorted(merged.values(), key=lambda item: scores.get(item.citation_key, 0.0), reverse=True)
    for rank, item in enumerate(ordered, start=1):
        item.score = round(scores.get(item.citation_key, 0.0), 8)
        item.retrieval_rank = rank
    return ordered[:top_k] if top_k else ordered
