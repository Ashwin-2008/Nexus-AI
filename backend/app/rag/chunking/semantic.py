"""Semantic-style chunking without an embedding dependency.

Sentences are grouped by lexical cohesion (content-word Jaccard similarity) and
a maximum size. This is a deterministic heuristic — explicitly *not* a
model-based semantic chunker. It avoids splitting closely related consecutive
sentences while keeping the pipeline dependency-free and reproducible.
"""
from __future__ import annotations

import re
from typing import Any

from app.rag.chunking.base import BaseChunker
from app.rag.chunking.chunk_metadata import make_chunk
from app.rag.chunking.sentence import sentence_spans
from app.rag.types import ChunkRecord, ParsedDocument

_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "that", "this", "these",
    "those", "is", "are", "was", "were", "be", "been", "being", "to", "of", "in", "on",
    "for", "with", "by", "as", "at", "from", "it", "its", "we", "you", "they", "he",
    "she", "not", "no", "do", "does", "did", "has", "have", "had", "will", "would",
}


def _terms(text: str) -> set[str]:
    return {word.lower() for word in _WORD_RE.findall(text) if word.lower() not in _STOPWORDS and len(word) > 2}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


class SemanticChunker(BaseChunker):
    strategy = "semantic"

    def __init__(self, chunk_size: int = 900, similarity_threshold: float = 0.08) -> None:
        self.chunk_size = chunk_size
        self.similarity_threshold = similarity_threshold

    def chunk(
        self,
        parsed: ParsedDocument,
        *,
        document_id: str,
        organization_id: str,
        document_version: int = 1,
        access_scope: str = "organization",
        source_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[ChunkRecord]:
        sentences = sentence_spans(parsed.text)
        if not sentences:
            return []
        merged = self.merged_metadata(parsed, metadata)
        chunks: list[ChunkRecord] = []
        index = 0
        group_start: int | None = None
        group_end = 0
        window_terms: set[str] = set()
        for start, end in sentences:
            sentence_text = parsed.text[start:end]
            terms = _terms(sentence_text)
            too_large = group_start is not None and end - group_start > self.chunk_size
            low_cohesion = (
                group_start is not None
                and window_terms
                and _jaccard(window_terms, terms) < self.similarity_threshold
                and end - group_start >= self.chunk_size // 3
            )
            if group_start is not None and (too_large or low_cohesion):
                text = parsed.text[group_start:group_end].strip()
                if text:
                    chunks.append(
                        make_chunk(
                            document_id=document_id,
                            organization_id=organization_id,
                            index=index,
                            text=text,
                            char_start=group_start,
                            char_end=group_end,
                            spans=parsed.spans,
                            sections=parsed.sections,
                            document_metadata=merged,
                            strategy=self.strategy,
                            document_version=document_version,
                            access_scope=access_scope,
                            source_id=source_id,
                        )
                    )
                    index += 1
                group_start = None
                window_terms = set()
            if group_start is None:
                group_start = start
                group_end = end
                window_terms = set(terms)
            else:
                group_end = end
                window_terms |= terms
        if group_start is not None:
            text = parsed.text[group_start:group_end].strip()
            if text:
                chunks.append(
                    make_chunk(
                        document_id=document_id,
                        organization_id=organization_id,
                        index=index,
                        text=text,
                        char_start=group_start,
                        char_end=group_end,
                        spans=parsed.spans,
                        sections=parsed.sections,
                        document_metadata=merged,
                        strategy=self.strategy,
                        document_version=document_version,
                        access_scope=access_scope,
                        source_id=source_id,
                    )
                )
        return chunks
