"""Loader contracts for the RAG ingestion pipeline.

Loaders convert raw bytes (or already-fetched external records) into a
:class:`app.rag.types.LoadedDocument`. File-format loading delegates to the
existing, tested ``app.services.processing.FileExtractor`` — this package adds
typed contracts, section metadata, and external-source adapters rather than a
second parser.

External loaders (web/database) never bypass authorization: they receive
already-authorized configuration from the connector layer, and the database
loader only formats rows that the safe read-only SQL boundary returned.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, ClassVar

from app.rag.exceptions import UnsupportedDocumentError
from app.rag.types import LoadedDocument
from app.services.processing import ExtractedContent, FileExtractor, ProcessingContext


@dataclass
class LoaderContext:
    document_id: str
    organization_id: str
    filename: str
    content_type: str
    storage_path: str = ""
    storage_backend: str = "local"
    max_bytes: int = 25 * 1024 * 1024

    def to_processing_context(self) -> ProcessingContext:
        return ProcessingContext(
            document_id=self.document_id,
            organization_id=self.organization_id,
            filename=self.filename,
            content_type=self.content_type,
            storage_path=self.storage_path,
            storage_backend=self.storage_backend,
        )


class BaseLoader(abc.ABC):
    """One document format/source."""

    name: ClassVar[str] = "base"
    extensions: ClassVar[tuple[str, ...]] = ()
    content_types: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def supports(cls, filename: str, content_type: str | None = None) -> bool:
        lowered = (filename or "").lower()
        if cls.extensions and any(lowered.endswith(ext) for ext in cls.extensions):
            return True
        if content_type and cls.content_types and content_type.split(";")[0].strip().lower() in cls.content_types:
            return True
        return False

    @abc.abstractmethod
    def load(self, data: bytes, ctx: LoaderContext) -> LoadedDocument:
        raise NotImplementedError

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def from_extracted(extracted: ExtractedContent, loader: str) -> LoadedDocument:
        sections: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        for span in extracted.spans:
            if span.get("kind") == "heading" and span.get("title"):
                sections.append(
                    {
                        "heading": span["title"],
                        "level": span.get("level", 1),
                        "start": span.get("start", 0),
                        "end": span.get("end", 0),
                    }
                )
            if span.get("kind") in {"table_row", "sheet_row", "row"}:
                tables.append(dict(span))
        return LoadedDocument(
            text=extracted.text,
            metadata=dict(extracted.metadata),
            spans=list(extracted.spans),
            sections=sections,
            tables=tables,
            warnings=list(extracted.warnings),
            loader=loader,
        )


class ExtractorBackedLoader(BaseLoader):
    """Loader for a file format handled by ``FileExtractor``."""

    def load(self, data: bytes, ctx: LoaderContext) -> LoadedDocument:
        if not data:
            raise UnsupportedDocumentError(f"{self.name} file is empty")
        extracted = FileExtractor().extract(data, ctx.to_processing_context())
        return self.from_extracted(extracted, self.name)


def ensure_supported(filename: str, content_type: str | None = None) -> None:
    from app.rag.loaders.registry import get_loader

    try:
        get_loader(filename, content_type)
    except UnsupportedDocumentError:
        raise
