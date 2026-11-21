"""JSON documents flattened to key/value text."""
from __future__ import annotations

from typing import ClassVar

from app.rag.loaders.base import ExtractorBackedLoader


class JsonLoader(ExtractorBackedLoader):
    name: ClassVar[str] = "json"
    extensions: ClassVar[tuple[str, ...]] = (".json",)
    content_types: ClassVar[tuple[str, ...]] = ("application/json",)
