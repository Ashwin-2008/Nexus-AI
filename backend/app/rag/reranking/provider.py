"""Reranker provider selection with explicit, documented fallback."""
from __future__ import annotations

import logging

from app.rag.config import RagConfig
from app.rag.reranking.base import BaseReranker, NoopReranker
from app.rag.reranking.cross_encoder import CrossEncoderReranker
from app.rag.reranking.llm_reranker import LLMReranker
from app.rag.reranking.scoring import HeuristicReranker

logger = logging.getLogger(__name__)

RERANKER_METHODS = ("auto", "heuristic", "llm", "cross_encoder", "none")


def get_reranker(method: str | None = None, config: RagConfig | None = None) -> BaseReranker:
    config = config or RagConfig.from_settings()
    name = (method or config.reranker or "heuristic").strip().lower()
    if name == "none":
        return NoopReranker()
    if name == "llm":
        return LLMReranker()
    if name == "cross_encoder":
        return CrossEncoderReranker()
    if name == "auto":
        # `auto` deliberately means the deterministic fallback, not a hidden
        # network call or a first-use model download.
        return HeuristicReranker()
    return HeuristicReranker()


def reranker_metadata(config: RagConfig | None = None) -> dict:
    config = config or RagConfig.from_settings()
    name = (config.reranker or "heuristic").lower()
    return {
        "configured": name,
        "effective": "heuristic" if name == "auto" else name,
        "methods": list(RERANKER_METHODS),
        "note": "heuristic is a deterministic fallback, not a trained cross-encoder"
        if name in ("auto", "heuristic")
        else None,
    }
