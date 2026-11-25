"""Standalone images (scans, screenshots) via OCR."""
from __future__ import annotations

from typing import ClassVar

from app.rag.loaders.base import ExtractorBackedLoader


class ImageLoader(ExtractorBackedLoader):
    name: ClassVar[str] = "image"
    extensions: ClassVar[tuple[str, ...]] = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")
    content_types: ClassVar[tuple[str, ...]] = (
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/tiff",
    )