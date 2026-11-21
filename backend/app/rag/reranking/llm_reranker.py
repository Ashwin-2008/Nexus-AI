"""LLM-based reranking via the configured chat provider.

Only invoked when explicitly configured (`RAG_RERANKER=llm`). Scores are
parsed defensively; malformed output raises ``RerankError`` so the caller can
fall back to the heuristic reranker and label the degradation.
"""
from __future__ import annotations

import json
import re

from app.rag.exceptions import RerankError, RerankerUnavailableError
from app.rag.reranking.base import BaseReranker
from app.rag.types import EvidenceChunk


class LLMReranker(BaseReranker):
    method = "llm"

    def __init__(self, max_passage_chars: int = 700) -> None:
        self.max_passage_chars = max_passage_chars

    def rerank(self, query: str, chunks: list[EvidenceChunk], top_k: int | None = None) -> list[EvidenceChunk]:
        if not chunks:
            return []
        from app.prompts import load_prompt
        from app.services.llm import ChatMessageData, LLMError, get_llm_provider, llm_available

        if not llm_available():
            raise RerankerUnavailableError("LLM reranker requested but no LLM provider is configured")
        passages = "\n\n".join(
            f"[{index}] {item.text[: self.max_passage_chars]}"
            for index, item in enumerate(chunks)
        )
        prompt = load_prompt("rag/llm_rerank.md", question=query, passages=passages)
        try:
            result = get_llm_provider().chat(
                [
                    ChatMessageData(role="system", content="Return only the requested JSON array."),
                    ChatMessageData(role="user", content=prompt),
                ],
                temperature=0,
                max_tokens=min(800, 40 + len(chunks) * 20),
            )
        except LLMError as exc:
            raise RerankError(str(exc)) from exc
        scores = _parse_scores(result.text, len(chunks))
        if not scores:
            raise RerankError("LLM reranker returned no parseable scores")
        for index, item in enumerate(chunks):
            item.rerank_score = round(float(scores.get(index, 0.0)) / 10.0, 8)
            item.rerank_method = "llm"
            item.metadata = {**(item.metadata or {}), "llm_rerank_score": scores.get(index, 0.0)}
        ordered = sorted(chunks, key=lambda item: item.rerank_score or 0.0, reverse=True)
        return ordered[:top_k] if top_k else ordered


def _parse_scores(raw: str, count: int) -> dict[int, float]:
    value = (raw or "").strip()
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.IGNORECASE).strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, list):
        return {}
    scores: dict[int, float] = {}
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        try:
            index = int(entry.get("id"))
            score = float(entry.get("score"))
        except (TypeError, ValueError):
            continue
        if 0 <= index < count:
            scores[index] = max(0.0, min(10.0, score))
    return scores
