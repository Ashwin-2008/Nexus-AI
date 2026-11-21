"""Excel workbooks via openpyxl (sheet/row provenance)."""
from __future__ import annotations

from typing import ClassVar

from app.rag.loaders.base import ExtractorBackedLoader


class ExcelLoader(ExtractorBackedLoader):
    name: ClassVar[str] = "xlsx"
    extensions: ClassVar[tuple[str, ...]] = (".xlsx", ".xlsm")
    content_types: ClassVar[tuple[str, ...]] = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",)
