"""Batched embedding with cache reuse.

If the provider rejects a batch (e.g. provider input-size limit), the batch is
split in half and retried once per half. Provider-level retries/backoff remain
in ``app.services.embeddings``.
"""
from __future__ import annotations

from typing import Any

from app.rag.embeddings.cache import EmbeddingCache, cache_key
from app.rag.exceptions import EmbeddingUnavailableError


def _batch_embed(provider: Any, texts: list[str]) -> list[list[float]]:
    try:
        return provider.embed(texts)
    except Exception as exc:  # noqa: BLE001
        if len(texts) > 1:
            midpoint = len(texts) // 2
            return _batch_embed(provider, texts[:midpoint]) + _batch_embed(provider, texts[midpoint:])
        raise EmbeddingUnavailableError(f"embedding provider rejected input: {exc}") from exc


def embed_batched(
    provider: Any,
    texts: list[str],
    *,
    cache: EmbeddingCache | None = None,
    batch_size: int = 64,
) -> list[list[float]]:
    if not texts:
        return []
    name = getattr(provider, "name", "unknown")
    model = getattr(provider, "model", name)
    dimensions = int(getattr(provider, "dimensions", 0) or 0)
    vectors: list[list[float] | None] = [None] * len(texts)
    pending: list[tuple[int, str, tuple[str, str, int, str]]] = []

    for index, text in enumerate(texts):
        key = cache_key(name, model, dimensions, text)
        cached = cache.get(key) if cache else None
        if cached is not None:
            vectors[index] = cached
        else:
            pending.append((index, text, key))

    for start in range(0, len(pending), max(1, batch_size)):
        window = pending[start : start + max(1, batch_size)]
        results = _batch_embed(provider, [text for _index, text, _key in window])
        if len(results) != len(window):
            raise EmbeddingUnavailableError(
                f"embedding provider returned {len(results)} vectors for {len(window)} inputs"
            )
        for (index, _text, key), vector in zip(window, results):
            vectors[index] = list(vector)
            if cache:
                cache.put(key, vector)

    missing = [index for index, vector in enumerate(vectors) if vector is None]
    if missing:
        raise EmbeddingUnavailableError(f"embedding provider returned no vectors for {len(missing)} inputs")
    return [vector for vector in vectors if vector is not None]  # type: ignore[misc]
