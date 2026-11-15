"""Tests for the embedding provider abstraction."""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.embeddings import (
    EmbeddingError,
    HashingEmbeddingProvider,
    get_embedding_provider,
    provider_info,
)


class TestHashingProvider:
    def test_deterministic(self):
        p = HashingEmbeddingProvider(dimensions=64)
        v1 = p.embed(["revenue risk supplier concentration"])
        v2 = p.embed(["revenue risk supplier concentration"])
        assert v1 == v2
        assert len(v1) == 1 and len(v1[0]) == 64

    def test_normalized(self):
        p = HashingEmbeddingProvider(dimensions=32)
        vec = p.embed(["some tokens here"])[0]
        norm = sum(x * x for x in vec) ** 0.5
        assert abs(norm - 1.0) < 1e-6

    def test_empty_text_handled(self):
        p = HashingEmbeddingProvider(dimensions=16)
        vecs = p.embed(["", "tokens"])
        assert len(vecs) == 2 and all(len(v) == 16 for v in vecs)

    def test_batch_count_preserved(self):
        p = HashingEmbeddingProvider(dimensions=16)
        texts = [f"text {i}" for i in range(10)]
        assert len(p.embed(texts)) == 10


class TestProviderSelection:
    def test_hashing_selected(self, monkeypatch):
        monkeypatch.setattr(settings, "embedding_provider", "hashing")
        p = get_embedding_provider()
        assert p.name == "hashing"

    def test_unknown_provider_fails_loudly(self, monkeypatch):
        monkeypatch.setattr(settings, "embedding_provider", "nonexistent")
        with pytest.raises(EmbeddingError):
            get_embedding_provider()

    def test_openai_without_key_fails_loudly(self, monkeypatch):
        monkeypatch.setattr(settings, "embedding_provider", "openai_compatible")
        monkeypatch.setattr(settings, "openai_api_key", "")
        with pytest.raises(EmbeddingError, match="no API key"):
            get_embedding_provider()

    def test_provider_info_shape(self, monkeypatch):
        monkeypatch.setattr(settings, "embedding_provider", "hashing")
        info = provider_info()
        assert set(info) == {"provider", "model", "dimensions"}
        assert info["provider"] == "hashing"
