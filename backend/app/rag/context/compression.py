"""Extractive context compression.

Compression selects the query-relevant sentences from a passage and keeps them
verbatim. It never paraphrases, so numbers/qualifiers cannot drift. An optional
LLM compression path exists for deployments that explicitly enable it, but the
deterministic path is the default.
"""
from __future__ import annotations

import re

from app.rag.query.expansion import query_terms
from app.rag.types import EvidenceChunk

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_RE.split(text or "") if part.strip()]


def compress_extractive(passage: str, query: str, max_sentences: int = 6) -> str:
    sentences = split_sentences(passage)
    if len(sentences) <= max_sentences:
        return passage
    terms = set(query_terms(query))
    if not terms:
        return " ".join(sentences[:max_sentences])
    scored: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(sentences):
        words = {word.lower() for word in re.findall(r"[A-Za-z0-9]+", sentence)}
        score = len(terms & words) / max(1, len(terms))
        scored.append((score, index, sentence))
    selected = sorted(scored, key=lambda item: (-item[0], item[1]))[:max_sentences]
    selected.sort(key=lambda item: item[1])
    return " ".join(item[2] for item in selected)


def compress_evidence(
    evidence: list[EvidenceChunk],
    query: str,
    *,
    max_sentences: int = 6,
) -> tuple[dict[str, str], list[str]]:
    """Return ``{chunk_id: compressed_text}`` and warnings."""
    compressed: dict[str, str] = {}
    warnings: list[str] = []
    for item in evidence:
        value = compress_extractive(item.text, query, max_sentences)
        if value != item.text:
            compressed[item.chunk_id] = value
            warnings.append(f"compressed context for chunk {item.chunk_id}")
    return compressed, warnings
