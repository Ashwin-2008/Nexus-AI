"""Word documents via python-docx (paragraphs and tables)."""
from __future__ import annotations

from typing import ClassVar

from app.rag.loaders.base import ExtractorBackedLoader


class DocxLoader(ExtractorBackedLoader):
    name: ClassVar[str] = "docx"
    extensions: ClassVar[tuple[str, ...]] = (".docx",)
    content_types: ClassVar[tuple[str, ...]] = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",)
