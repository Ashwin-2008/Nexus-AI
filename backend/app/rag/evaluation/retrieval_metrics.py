"""Information-retrieval metrics (implemented from definition)."""
from __future__ import annotations

import math
from typing import Iterable


def recall_at_k(ranked: Iterable[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    retrieved = list(ranked)[:k]
    return len(set(retrieved) & relevant_set) / len(relevant_set)


def precision_at_k(ranked: Iterable[str], relevant: Iterable[str], k: int) -> float:
    retrieved = list(ranked)[:k]
    if not retrieved:
        return 0.0
    relevant_set = set(relevant)
    return len(set(retrieved) & relevant_set) / len(retrieved)


def reciprocal_rank(ranked: Iterable[str], relevant: Iterable[str], k: int | None = None) -> float:
    relevant_set = set(relevant)
    items = list(ranked)
    if k is not None:
        items = items[:k]
    for index, item in enumerate(items, start=1):
        if item in relevant_set:
            return 1.0 / index
    return 0.0


def ndcg_at_k(ranked: Iterable[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    items = list(ranked)[:k]
    if not items or not relevant_set:
        return 0.0
    dcg = 0.0
    for index, item in enumerate(items, start=1):
        gain = 1.0 if item in relevant_set else 0.0
        dcg += gain / math.log2(index + 1)
    ideal = sum(1.0 / math.log2(index + 1) for index in range(1, min(len(relevant_set), k) + 1))
    return dcg / ideal if ideal else 0.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
