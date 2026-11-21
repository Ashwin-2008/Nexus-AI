"""Thread-safe in-process embedding cache.

Safe to cache because embeddings are deterministic per (provider, model,
dimension, text). The cache is process-local and bounded; it is not a
correctness mechanism, only a latency/cost optimization.
"""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict

CacheKey = tuple[str, str, int, str]


def cache_key(provider_name: str, model: str, dimensions: int, text: str) -> CacheKey:
    digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    return (provider_name, model, int(dimensions or 0), digest)


class EmbeddingCache:
    def __init__(self, max_entries: int = 2048) -> None:
        self.max_entries = max(0, max_entries)
        self._data: OrderedDict[CacheKey, list[float]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._data)

    def get(self, key: CacheKey) -> list[float] | None:
        if self.max_entries == 0:
            return None
        with self._lock:
            value = self._data.get(key)
            if value is None:
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return list(value)

    def put(self, key: CacheKey, vector: list[float]) -> None:
        if self.max_entries == 0:
            return
        with self._lock:
            self._data[key] = list(vector)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = 0
            self.misses = 0

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"entries": len(self._data), "hits": self.hits, "misses": self.misses}
