"""Table-aware extraction helpers.

Tables are preserved as pipe-delimited text by the file extractors; this module
identifies table regions so chunkers can avoid splitting rows mid-record and so
citations can point at a table/row.
"""
from __future__ import annotations

import re
from typing import Any

_PIPE_TABLE_RE = re.compile(r"^\s*\|?.+\|.+\|?\s*$")


def table_regions(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return contiguous table spans (docx table rows, sheet rows, CSV rows)."""
    regions: list[dict[str, Any]] = []
    for span in spans:
        if span.get("kind") not in {"table_row", "sheet_row"}:
            continue
        regions.append(
            {
                "kind": span.get("kind"),
                "table": span.get("table"),
                "sheet": span.get("sheet"),
                "start": int(span.get("start", 0)),
                "end": int(span.get("end", 0)),
            }
        )
    return regions


def extract_markdown_tables(text: str) -> list[dict[str, Any]]:
    """Detect Markdown pipe tables and return header/rows/offsets."""
    tables: list[dict[str, Any]] = []
    offset = 0
    current: dict[str, Any] | None = None
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if _PIPE_TABLE_RE.match(content):
            cells = [cell.strip() for cell in content.strip().strip("|").split("|")]
            if current is None:
                current = {"header": cells, "rows": [], "start": offset, "end": offset + len(content)}
            elif all(set(cell) <= {"-", ":", " "} for cell in cells):
                pass  # markdown separator row
            else:
                current["rows"].append(cells)
                current["end"] = offset + len(content)
        else:
            if current is not None:
                tables.append(current)
                current = None
        offset += len(line)
    if current is not None:
        tables.append(current)
    return tables


def table_summary(tables: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    return [
        {
            "header": table.get("header", [])[:20],
            "row_count": len(table.get("rows", [])),
            "start": table.get("start", 0),
            "end": table.get("end", 0),
        }
        for table in tables[:limit]
    ]
