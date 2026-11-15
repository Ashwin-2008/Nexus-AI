"""Embedding provider abstraction.

Providers:
- openai_compatible: any OpenAI-compatible /v1/embeddings endpoint
  (OpenAI, Azure OpenAI, vLLM, Ollama, LM Studio, ...).
- local: sentence-transformers model, executed in-process. Genuinely semantic;
  no API key required. Requires the optional `sentence-transformers` package.
- hashing: deterministic feature-hashing vectors. NOT semantic. Intended only
  for CI/unit tests so the indexing/retrieval machinery can run without any
  model or network. Must never be used as a production retrieval provider.

The active provider is selected via settings.embedding_provider.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import time
from typing import Any, Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_LOCAL_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_OPENAI_MODEL = "text-embedding-3-small"


class EmbeddingError(RuntimeError):
    """Raised when embedding generation fails irrecoverably."""


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAICompatibleEmbeddingProvider:
    """Embeddings via an OpenAI-compatible HTTP API."""

    name = "openai_compatible"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url = (base_url or settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or settings.openai_api_key or ""
        self.model = model or settings.embedding_model or DEFAULT_OPENAI_MODEL
        self.dimensions = dimensions or settings.embedding_dimensions or 1536
        self.timeout = timeout
        self.max_retries = max_retries
        if not self.api_key:
            raise EmbeddingError(
                "OpenAI-compatible embedding provider selected but no API key configured "
                "(set OPENAI_API_KEY / OPENAI_BASE_URL)."
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        url = f"{self.base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        out: list[list[float]] = []
        # Batch to keep request sizes bounded.
        batch_size = settings.embedding_batch_size or 64
        last_error: Exception | None = None
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            payload: dict[str, Any] = {"model": self.model, "input": batch}
            # Some providers reject the dimensions parameter (e.g. legacy models).
            if settings.embedding_dimensions:
                payload["dimensions"] = self.dimensions
            for attempt in range(1, self.max_retries + 1):
                try:
                    resp = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
                    if resp.status_code in (429, 500, 502, 503, 504):
                        raise EmbeddingError(f"embedding API transient error HTTP {resp.status_code}")
                    resp.raise_for_status()
                    body = resp.json()
                    data = body.get("data", [])
                    if len(data) != len(batch):
                        raise EmbeddingError(
                            f"embedding API returned {len(data)} vectors for {len(batch)} inputs"
                        )
                    # API may return data out of order when index present; sort defensively.
                    if all("index" in item for item in data):
                        data = sorted(data, key=lambda item: item["index"])
                    vectors = [item["embedding"] for item in data]
                    if any(len(v) != self.dimensions for v in vectors):
                        raise EmbeddingError(
                            f"embedding dimension mismatch: expected {self.dimensions}, "
                            f"got {sorted({len(v) for v in vectors})}"
                        )
                    out.extend(vectors)
                    last_error = None
                    break
                except EmbeddingError:
                    raise
                except Exception as e:  # noqa: BLE001
                    last_error = e
                    if attempt == self.max_retries:
                        break
                    # Exponential backoff: 0.5s, 1s, 2s ...
                    time.sleep(0.5 * (2 ** (attempt - 1)))
            if last_error is not None:
                raise EmbeddingError(f"embedding API failed after {self.max_retries} attempts: {last_error}")
        return out


class LocalSentenceTransformerEmbeddingProvider:
    """Embeddings via an in-process sentence-transformers model.

    Genuinely semantic; requires the optional `sentence-transformers` package
    (extras: pip install -r requirements-embeddings.txt). The model is loaded
    lazily and cached per process.
    """

    name = "local"
    _model_cache: dict[str, Any] = {}

    def __init__(self, model: str | None = None, dimensions: int | None = None) -> None:
        self.model = model or settings.embedding_local_model or DEFAULT_LOCAL_MODEL
        self.dimensions = dimensions or 384  # all-MiniLM-L6-v2 default
        self._model: Any = None

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as e:
            raise EmbeddingError(
                "Local embedding provider selected but sentence-transformers is not installed. "
                "Install backend/requirements-embeddings.txt or choose another provider."
            ) from e
        model = SentenceTransformer(self.model)
        self.dimensions = int(model.get_sentence_embedding_dimension())
        self._model = model
        LocalSentenceTransformerEmbeddingProvider._model_cache[self.model] = model
        return model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load_model()
        batch_size = settings.embedding_batch_size or 64
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            vectors = model.encode(
                batch,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            embeddings.extend(v.tolist() for v in vectors)
        return embeddings


class HashingEmbeddingProvider:
    """Deterministic feature-hashing vectors.

    NOT semantic: identical texts map to identical vectors, but related texts
    do NOT map to nearby vectors. Useful only to exercise the storage/index/
    retrieval machinery in CI. Do not use for real retrieval quality.
    """

    name = "hashing"

    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions or settings.embedding_dimensions or 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self.dimensions
            tokens = (text or "").lower().split()
            if not tokens:
                vectors.append(vec)
                continue
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8", errors="ignore")).digest()
                idx = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vec[idx] += sign
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


_PROVIDERS = {
    "openai_compatible": OpenAICompatibleEmbeddingProvider,
    "local": LocalSentenceTransformerEmbeddingProvider,
    "hashing": HashingEmbeddingProvider,
}


def get_embedding_provider() -> EmbeddingProvider:
    """Build the configured embedding provider. Fails loudly on bad config."""
    provider_name = (settings.embedding_provider or "hashing").strip().lower()
    if provider_name not in _PROVIDERS:
        raise EmbeddingError(
            f"Unknown embedding_provider '{provider_name}'. Valid: {sorted(_PROVIDERS)}"
        )
    return _PROVIDERS[provider_name]()


def provider_info() -> dict[str, Any]:
    """Metadata persisted alongside chunks for model-version tracking."""
    p = get_embedding_provider()
    return {
        "provider": p.name,
        "model": getattr(p, "model", p.name),
        "dimensions": p.dimensions,
    }
