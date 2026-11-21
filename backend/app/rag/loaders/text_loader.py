"""Plain text with encoding fallback."""
from __future__ import annotations

from typing import ClassVar

from app.rag.loaders.base import ExtractorBackedLoader


class TextLoader(ExtractorBackedLoader):
    name: ClassVar[str] = "text"
    extensions: ClassVar[tuple[str, ...]] = (".txt",)
    content_types: ClassVar[tuple[str, ...]] = ("text/plain",)
