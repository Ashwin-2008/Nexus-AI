"""Recursive character chunking.

Delegates the boundary-aware splitting to the existing, tested
``app.services.processing.Chunker`` (sentence/paragraph breaks, overlap) and
maps its output into typed chunks with deterministic ids and full metadata.
"""
from __future__ import annotations

from typing import Any

from app.rag.chunking.base import BaseChunker
from app.rag.chunking.chunk_metadata import make_chunk
from app.rag.types import ChunkRecord, ParsedDocument
from app.services.processing import Chunker, ExtractedContent


class RecursiveChunker(BaseChunker):
    strategy = "recursive"

    def __init__(self, chunk_size: int = 900, overlap: int = 150) -> None:
        self.chunker = Chunker(chunk_size=chunk_size, overlap=overlap)
        self.chunk_size = chunk_size
        self.overlap = overlap

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
        extracted = ExtractedContent(
            text=parsed.text,
            metadata=parsed.metadata,
            spans=parsed.spans,
            warnings=parsed.warnings,
        )
        raw_chunks = self.chunker.chunk(extracted, document_id=document_id, organization_id=organization_id)
        merged = self.merged_metadata(parsed, metadata)
        chunks: list[ChunkRecord] = []
        for index, raw in enumerate(raw_chunks):
            chunks.append(
                make_chunk(
                    document_id=document_id,
                    organization_id=organization_id,
                    index=index,
                    text=raw["text"],
                    char_start=int(raw.get("char_start", 0)),
                    char_end=int(raw.get("char_end", 0)),
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
