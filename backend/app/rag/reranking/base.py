"""Reranker contract."""
from __future__ import annotations

import abc

from app.rag.types import EvidenceChunk


class BaseReranker(abc.ABC):
    method: str = "base"

    @abc.abstractmethod
    def rerank(self, query: str, chunks: list[EvidenceChunk], top_k: int | None = None) -> list[EvidenceChunk]:
        raise NotImplementedError


class NoopReranker(BaseReranker):
    method = "none"

    def rerank(self, query: str, chunks: list[EvidenceChunk], top_k: int | None = None) -> list[EvidenceChunk]:
        return chunks[:top_k] if top_k else chunks
