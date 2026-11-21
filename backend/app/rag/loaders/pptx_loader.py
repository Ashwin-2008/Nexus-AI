"""PowerPoint slides via OOXML parsing."""
from __future__ import annotations

from typing import ClassVar

from app.rag.loaders.base import ExtractorBackedLoader


class PptxLoader(ExtractorBackedLoader):
    name: ClassVar[str] = "pptx"
    extensions: ClassVar[tuple[str, ...]] = (".pptx",)
    content_types: ClassVar[tuple[str, ...]] = ("application/vnd.openxmlformats-officedocument.presentationml.presentation",)
