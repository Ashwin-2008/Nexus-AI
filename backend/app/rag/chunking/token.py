"""Token-window chunking.

Token counts are approximated (~4 chars/token) without adding a tokenizer
dependency. Windows never start inside a word, and overlap is expressed in
tokens. The approximation is recorded in chunk metadata for transparency.
"""
from __future__ import annotations

import re
from typing import Any

from app.rag.chunking.base import BaseChunker
from app.rag.chunking.chunk_metadata import estimate_tokens, make_chunk
from app.rag.types import ChunkRecord, ParsedDocument

_TOKEN_RE = re.compile(r"\S+")


class TokenChunker(BaseChunker):
    strategy = "token"

    def __init__(self, max_tokens: int = 220, overlap_tokens: int = 40) -> None:
        if max_tokens < 20:
            raise ValueError("max_tokens must be >= 20")
        if not 0 <= overlap_tokens < max_tokens:
            raise ValueError("overlap_tokens must be smaller than max_tokens")
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

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
        matches = list(_TOKEN_RE.finditer(parsed.text or ""))
        if not matches:
            return []
        merged = self.merged_metadata(parsed, metadata)
        chunks: list[ChunkRecord] = []
        step = max(1, self.max_tokens - self.overlap_tokens)
        index = 0
        position = 0
        while position < len(matches):
            window = matches[position : position + self.max_tokens]
            start = window[0].start()
            end = window[-1].end()
            chunks.append(
                make_chunk(
                    document_id=document_id,
                    organization_id=organization_id,
                    index=index,
                    text=parsed.text[start:end],
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
            if position + self.max_tokens >= len(matches):
                break
            position += step
        return chunks

    @staticmethod
    def tokens_for(chunk_size: int, overlap: int) -> tuple[int, int]:
        return max(20, estimate_tokens("x" * chunk_size)), max(0, estimate_tokens("x" * overlap) - 1)
