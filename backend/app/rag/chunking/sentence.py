"""Sentence-grouped chunking with optional sentence overlap."""
from __future__ import annotations

import re
from typing import Any

from app.rag.chunking.base import BaseChunker
from app.rag.chunking.chunk_metadata import make_chunk
from app.rag.types import ChunkRecord, ParsedDocument

_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]?|\n+")


def sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in _SENTENCE_RE.finditer(text or ""):
        value = match.group(0)
        if not value.strip() or value.strip() == "":
            continue
        spans.append((match.start(), match.end()))
    return spans


class SentenceChunker(BaseChunker):
    strategy = "sentence"

    def __init__(self, chunk_size: int = 900, overlap_chars: int = 150) -> None:
        self.chunk_size = chunk_size
        self.overlap_chars = overlap_chars

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
        cursor = 0
        while cursor < len(sentences):
            start = sentences[cursor][0]
            end = sentences[cursor][1]
            next_cursor = cursor + 1
            while next_cursor < len(sentences) and sentences[next_cursor][1] - start <= self.chunk_size:
                end = sentences[next_cursor][1]
                next_cursor += 1
            text = parsed.text[start:end].strip()
            if text:
                chunks.append(
                    make_chunk(
                        document_id=document_id,
                        organization_id=organization_id,
                        index=index,
                        text=text,
                        char_start=start,
                        char_end=end,
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
            if next_cursor >= len(sentences):
                break
            if self.overlap_chars <= 0:
                cursor = next_cursor
                continue
            # Walk back to include overlapping sentences.
            overlap_start = end - self.overlap_chars
            rewind = next_cursor
            while rewind > cursor and sentences[rewind - 1][0] >= overlap_start:
                rewind -= 1
            cursor = max(cursor + 1, rewind)
        return chunks
