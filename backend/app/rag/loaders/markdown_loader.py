"""Markdown with heading-derived sections."""
from __future__ import annotations

from typing import ClassVar

from app.rag.loaders.base import ExtractorBackedLoader


class MarkdownLoader(ExtractorBackedLoader):
    name: ClassVar[str] = "markdown"
    extensions: ClassVar[tuple[str, ...]] = (".md", ".markdown")
    content_types: ClassVar[tuple[str, ...]] = ("text/markdown", "text/x-markdown")
