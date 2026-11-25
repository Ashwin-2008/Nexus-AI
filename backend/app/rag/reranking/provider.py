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
        # Prefer a meaning-based LLM pass when a chat model is configured;
        # otherwise use the deterministic fallback. The retriever degrades
        # gracefully if the LLM call fails.
        from app.rag.generation.provider import llm_configured

        if llm_configured():
            return LLMReranker()
        return HeuristicReranker()
    return HeuristicReranker()


def reranker_metadata(config: RagConfig | None = None) -> dict:
    config = config or RagConfig.from_settings()
    name = (config.reranker or "auto").lower()
    effective = name
    if name == "auto":
        from app.rag.generation.provider import llm_configured

        effective = "llm" if llm_configured() else "heuristic"
    return {
        "configured": name,
        "effective": effective,
        "methods": list(RERANKER_METHODS),
        "note": "auto uses a meaning-based LLM pass when a chat model is configured; otherwise a deterministic fallback"
        if name == "auto"
        else ("heuristic is a deterministic fallback, not a trained cross-encoder" if name == "heuristic" else None),
    }
