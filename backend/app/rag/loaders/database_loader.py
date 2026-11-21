"""Database record loader.

The safe read-only SQL boundary (``app.services.safe_sql``) is the only place
that executes SQL. This loader formats already-returned rows into citable
text with table/column provenance. It never opens a connection itself.
"""
from __future__ import annotations

from typing import Any, ClassVar

from app.rag.exceptions import ValidationError
from app.rag.loaders.base import BaseLoader, LoaderContext
from app.rag.types import LoadedDocument


class DatabaseRowsLoader(BaseLoader):
    name: ClassVar[str] = "database"
    extensions: ClassVar[tuple[str, ...]] = ()

    def load_rows(
        self,
        rows: list[list[Any]],
        columns: list[str],
        ctx: LoaderContext,
        *,
        source_id: str | None = None,
        sql: str | None = None,
        max_rows: int = 500,
    ) -> LoadedDocument:
        if not columns:
            raise ValidationError("database loader requires column metadata")
        if len(rows) > max_rows:
            rows = rows[:max_rows]
        if not rows:
            raise ValidationError("database loader received no rows")
        parts: list[str] = [f"[database records: {len(rows)} rows, {len(columns)} columns]", ""]
        spans: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            cells = []
            for column, value in zip(columns, row):
                cells.append(f"{column}={value}")
            line = f"row {index}: " + " | ".join(cells)
            start = sum(len(part) for part in parts) + (1 if index > 1 else 0)
            parts.append(line)
            parts.append("\n")
            spans.append({"kind": "db_row", "row": index, "start": max(0, start - 1), "end": start - 1 + len(line)})
        text = "".join(parts).strip()
        return LoadedDocument(
            text=text,
            metadata={
                "filename": ctx.filename,
                "content_type": "text/plain",
                "format": "database",
                "columns": columns,
                "row_count": len(rows),
                "source_id": source_id,
                "sql": sql,
            },
            spans=spans,
            loader=self.name,
        )

    def load(self, data: bytes, ctx: LoaderContext) -> LoadedDocument:
        raise ValidationError(
            "database loader requires structured rows; use load_rows() with safe SQL results"
        )
