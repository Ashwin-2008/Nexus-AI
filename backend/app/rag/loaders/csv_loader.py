"""CSV rows with row provenance."""
from __future__ import annotations

from typing import ClassVar

from app.rag.loaders.base import ExtractorBackedLoader


class CsvLoader(ExtractorBackedLoader):
    name: ClassVar[str] = "csv"
    extensions: ClassVar[tuple[str, ...]] = (".csv",)
    content_types: ClassVar[tuple[str, ...]] = ("text/csv", "application/csv")
