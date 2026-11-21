"""Optional cross-encoder reranker.

Requires the optional ``sentence-transformers`` package (the same optional
extra as the local embedding provider). When it is not installed the adapter
reports an explicit availability error; it never pretends to rerank.
"""
from __future__ import annotations

import os
from typing import Any

from app.rag.exceptions import RerankerUnavailableError
from app.rag.reranking.base import BaseReranker
from app.rag.types import EvidenceChunk

DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker(BaseReranker):
    method = "cross_encoder"

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or os.getenv("RAG_CROSS_ENCODER_MODEL", DEFAULT_MODEL)
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
        except ImportError as exc:
            raise RerankerUnavailableError(
                "cross-encoder reranker requires sentence-transformers "
                "(install backend/requirements-embeddings.txt)"
            ) from exc
        self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(self, query: str, chunks: list[EvidenceChunk], top_k: int | None = None) -> list[EvidenceChunk]:
        if not chunks:
            return []
        model = self._load()
        pairs = [(query, item.text[:1200]) for item in chunks]
        try:
            scores = model.predict(pairs)
        except Exception as exc:  # noqa: BLE001
            raise RerankerUnavailableError(f"cross-encoder scoring failed: {exc}") from exc
        for item, score in zip(chunks, scores):
            item.rerank_score = float(score)
            item.rerank_method = "cross_encoder"
        ordered = sorted(chunks, key=lambda item: item.rerank_score or 0.0, reverse=True)
        return ordered[:top_k] if top_k else ordered
