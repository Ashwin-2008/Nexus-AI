"""Document parser: loader → normalization → sections/tables → metadata.

This is the single entry point used by the ingestion pipeline. It returns a
``ParsedDocument`` with accurate provenance spans; it never writes to the
database.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from app.rag.exceptions import ParsingError, UnsupportedDocumentError
from app.rag.ingestion.normalizer import normalize_text, remap_spans
from app.rag.loaders import LoaderContext, get_loader
from app.rag.parsing.cleaning import strip_control_characters, summarize_metadata
from app.rag.parsing.layout_extraction import detect_sections
from app.rag.parsing.table_extraction import extract_markdown_tables
from app.rag.types import ParsedDocument
from app.services.processing import MAX_EXTRACT_CHARS

MAX_PARSED_CHARS = MAX_EXTRACT_CHARS


class DocumentParser:
    def parse(
        self,
        data: bytes,
        ctx: LoaderContext,
        *,
        content_type: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> ParsedDocument:
        loader = get_loader(ctx.filename, content_type or ctx.content_type)
        try:
            loaded = loader.load(data, ctx)
        except UnsupportedDocumentError:
            raise
        except Exception as exc:  # noqa: BLE001 — parser errors are pipeline errors
            raise ParsingError(f"{loader.name} loader failed for '{ctx.filename}': {exc}") from exc

        cleaned_raw = strip_control_characters(loaded.text or "")
        normalization = normalize_text(cleaned_raw, max_chars=MAX_PARSED_CHARS)
        text = normalization.text
        if not text.strip():
            raise ParsingError(f"'{ctx.filename}' produced no extractable text")
        spans = remap_spans(loaded.spans, normalization.index_map, len(text))
        if not spans:
            spans = [{"kind": "file", "start": 0, "end": len(text)}]
        else:
            spans.append({"kind": "file", "start": 0, "end": len(text)})

        sections = [
            {
                **section,
                "start": _clamp(int(section.get("start", 0)), len(text)),
                "end": _clamp(int(section.get("end", 0)), len(text)),
            }
            for section in loaded.sections
        ]
        if not sections:
            sections = detect_sections(text)

        markdown_tables = extract_markdown_tables(text) if text.count("|") >= 2 else []
        metadata = dict(loaded.metadata)
        if extra_metadata:
            metadata.update(extra_metadata)
        metadata.update(
            {
                "content_hash": hashlib.sha256((loaded.text or "").encode("utf-8")).hexdigest(),
                "char_count": len(text),
                "loader": loader.name,
                "section_count": len(sections),
                "table_count": len(loaded.tables) + len(markdown_tables),
            }
        )
        if markdown_tables:
            metadata["markdown_tables"] = [
                {"columns": table["header"][:20], "row_count": len(table["rows"])}
                for table in markdown_tables[:10]
            ]
        title = _title_for(metadata, sections, ctx.filename)
        metadata["document_title"] = title
        metadata["language"] = _language_hint(text)

        warnings = list(loaded.warnings) + list(normalization.warnings)
        if loading := metadata.get("extraction_warnings"):
            if isinstance(loading, list):
                warnings.extend(str(item) for item in loading)
        metadata = summarize_metadata(metadata, max_keys=60)
        return ParsedDocument(
            text=text,
            metadata=metadata,
            spans=spans,
            sections=sections,
            tables=loaded.tables + markdown_tables,
            warnings=_dedupe(warnings),
            loader=loader.name,
            title=title,
            language=metadata.get("language"),
        )


def _clamp(value: int, limit: int) -> int:
    return max(0, min(int(value or 0), limit))


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _title_for(metadata: dict[str, Any], sections: list[dict[str, Any]], filename: str) -> str:
    for key in ("document_title", "title", "subject"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:255]
    if sections:
        heading = str(sections[0].get("heading") or "").strip()
        if heading:
            return heading[:255]
    return Path(filename or "document").stem[:255]


_STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "are", "was", "were",
    "have", "has", "not", "但是", "und", "der", "die", "das", "les", "des",
    "que", "por", "para", "con", "una", "uno", "del",
}
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]+")


def _language_hint(text: str) -> str:
    """Cheap language hint for metadata only (never used for filtering)."""
    words = [word.lower() for word in _WORD_RE.findall(text[:5000])]
    if not words:
        return "unknown"
    english = sum(1 for word in words if word in {"the", "and", "of", "to", "in", "is", "for", "that", "with"})
    if english / max(1, len(words)) > 0.05:
        return "en"
    return "und"
