"""Chunker contracts."""
from __future__ import annotations

import abc
from typing import Any

from app.rag.types import ChunkRecord, ParsedDocument


class BaseChunker(abc.ABC):
    strategy: str = "base"

    @abc.abstractmethod
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
        raise NotImplementedError

    @staticmethod
    def merged_metadata(parsed: ParsedDocument, extra: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(parsed.metadata)
        if extra:
            merged.update(extra)
        return merged
