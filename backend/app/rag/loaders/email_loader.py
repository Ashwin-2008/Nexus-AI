"""Email messages with sender/date/thread metadata."""
from __future__ import annotations

from typing import ClassVar

from app.rag.loaders.base import ExtractorBackedLoader


class EmailFileLoader(ExtractorBackedLoader):
    name: ClassVar[str] = "email"
    extensions: ClassVar[tuple[str, ...]] = (".eml",)
    content_types: ClassVar[tuple[str, ...]] = ("message/rfc822",)
