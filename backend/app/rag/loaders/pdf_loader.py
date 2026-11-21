"""PDF documents via pypdf page extraction."""
from __future__ import annotations

from typing import ClassVar

from app.rag.loaders.base import ExtractorBackedLoader


class PdfLoader(ExtractorBackedLoader):
    name: ClassVar[str] = "pdf"
    extensions: ClassVar[tuple[str, ...]] = (".pdf",)
    content_types: ClassVar[tuple[str, ...]] = ("application/pdf",)
