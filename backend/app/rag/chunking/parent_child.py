"""Parent-child chunking.

Parent chunks (larger context) are persisted for retrieval expansion; child
chunks (smaller, precise) are embedded and indexed. Child chunks reference their
parent with ``parent_chunk_id`` so the retriever can return broader context
without losing the precise citation span.
"""
from __future__ import annotations

from typing import Any

from app.rag.chunking.base import BaseChunker
from app.rag.chunking.chunk_metadata import make_chunk
from app.rag.chunking.recursive import RecursiveChunker
from app.rag.chunking.sentence import SentenceChunker
from app.rag.types import ChunkRecord, ParsedDocument

PARENT_STRATEGY = "parent_child_parent"
CHILD_STRATEGY = "parent_child"


class ParentChildChunker(BaseChunker):
    strategy = CHILD_STRATEGY

    def __init__(
        self,
        parent_size: int = 1800,
        parent_overlap: int = 150,
        child_size: int = 450,
        child_overlap: int = 80,
    ) -> None:
        if child_size >= parent_size:
            raise ValueError("child_size must be smaller than parent_size")
        self.parents = RecursiveChunker(chunk_size=parent_size, overlap=parent_overlap)
        self.children = SentenceChunker(chunk_size=child_size, overlap_chars=child_overlap)

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
        merged = self.merged_metadata(parsed, metadata)
        parent_chunks = self.parents.chunk(
            parsed,
            document_id=document_id,
            organization_id=organization_id,
            document_version=document_version,
            access_scope=access_scope,
            source_id=source_id,
            metadata=merged,
        )
        result: list[ChunkRecord] = []
        for parent_index, parent in enumerate(parent_chunks):
            parent.strategy = PARENT_STRATEGY
            parent.metadata["chunk_role"] = "parent"
            result.append(parent)
            # Chunk the exact parent slice so child offsets stay correct.
            parent_parsed = ParsedDocument(
                text=parent.text,
                metadata=parsed.metadata,
                spans=parsed.spans,
                sections=parsed.sections,
                warnings=parsed.warnings,
                loader=parsed.loader,
                title=parsed.title,
                language=parsed.language,
            )
            child_chunks = self.children.chunk(
                parent_parsed,
                document_id=document_id,
                organization_id=organization_id,
                document_version=document_version,
                access_scope=access_scope,
                source_id=source_id,
                metadata=merged,
            )
            for child_index, child in enumerate(child_chunks):
                start = parent.char_start + child.char_start
                end = parent.char_start + child.char_end
                record = make_chunk(
                    document_id=document_id,
                    organization_id=organization_id,
                    index=parent_index,
                    text=child.text,
                    char_start=start,
                    char_end=end,
                    spans=parsed.spans,
                    sections=parsed.sections,
                    document_metadata=merged,
                    strategy=CHILD_STRATEGY,
                    document_version=document_version,
                    access_scope=access_scope,
                    source_id=source_id,
                    parent_chunk_id=parent.chunk_id,
                    suffix=f"{parent_index}:{child_index}",
                    role="child",
                )
                result.append(record)
        return result


def is_parent_chunk(chunk: ChunkRecord | Any) -> bool:
    strategy = getattr(chunk, "strategy", None) or ""
    if strategy == PARENT_STRATEGY:
        return True
    metadata = getattr(chunk, "metadata", None) or {}
    return isinstance(metadata, dict) and metadata.get("chunk_role") == "parent"
