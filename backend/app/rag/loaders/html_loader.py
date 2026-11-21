"""HTML pages with heading-derived sections."""
from __future__ import annotations

from typing import ClassVar

from app.rag.loaders.base import ExtractorBackedLoader


class HtmlLoader(ExtractorBackedLoader):
    name: ClassVar[str] = "html"
    extensions: ClassVar[tuple[str, ...]] = (".html", ".htm")
    content_types: ClassVar[tuple[str, ...]] = ("text/html", "application/xhtml+xml")
