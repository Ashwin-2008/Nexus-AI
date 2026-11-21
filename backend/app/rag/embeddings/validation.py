"""Embedding validation: no fake vectors, no silent dimension drift."""
from __future__ import annotations

import math

from app.rag.exceptions import EmbeddingDimensionError, EmbeddingUnavailableError


def validate_vectors(vectors: list[list[float]], expected_dimensions: int | None = None) -> None:
    if not vectors:
        raise EmbeddingUnavailableError("embedding provider returned no vectors")
    dimensions = expected_dimensions or len(vectors[0])
    for index, vector in enumerate(vectors):
        if not isinstance(vector, (list, tuple)) or not vector:
            raise EmbeddingUnavailableError(f"embedding {index} is empty")
        if len(vector) != dimensions:
            raise EmbeddingDimensionError(
                f"embedding {index} has dimension {len(vector)}, expected {dimensions}"
            )
        for value in vector:
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise EmbeddingUnavailableError(f"embedding {index} contains a non-finite value")
        norm = math.sqrt(sum(float(value) * float(value) for value in vector))
        if norm == 0.0:
            raise EmbeddingUnavailableError(
                f"embedding {index} is a zero vector; refusing to index meaningless evidence"
            )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return dot / (left_norm * right_norm)
