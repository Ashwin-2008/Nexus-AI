"""Text extraction facade.

Delegates to the existing ``FileExtractor`` so the repository has exactly one
file-format implementation. RAG-specific concerns (normalization, sections,
tables, metadata) live in :mod:`app.rag.parsing.parser`.
"""
from __future__ import annotations

from app.rag.loaders.base import LoaderContext
from app.rag.types import LoadedDocument
from app.services.processing import ExtractionError, FileExtractor


def extract_text(data: bytes, ctx: LoaderContext) -> LoadedDocument:
    extracted = FileExtractor().extract(data, ctx.to_processing_context())
    return LoadedDocument(
        text=extracted.text,
        metadata=dict(extracted.metadata),
        spans=list(extracted.spans),
        warnings=list(extracted.warnings),
        loader="file_extractor",
    )


__all__ = ["ExtractionError", "extract_text"]
