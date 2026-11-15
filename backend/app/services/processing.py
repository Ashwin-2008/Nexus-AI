"""Document processing pipeline: extraction, normalization, chunking.

Real content extraction per file type (PDF/DOCX/TXT/CSV/XLSX) with page/row
provenance, plus configurable chunking with overlap. Embedding and vector
indexing live in embeddings.py / vector_index.py.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MAX_EXTRACT_CHARS = 2_000_000  # hard cap on extracted text per document


@dataclass
class ProcessingContext:
    document_id: str
    organization_id: str
    filename: str
    content_type: str
    storage_path: str
    storage_backend: str


@dataclass
class ExtractedContent:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    # provenance spans (start/end char offsets into text) for page/row/sheet
    spans: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ExtractionError(ValueError):
    """Raised when a file cannot be parsed at all (malformed, corrupt, empty)."""


class FileExtractor:
    """Content-type aware text extraction with provenance spans."""

    def extract(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        ext = _extension_of(ctx.filename)
        extractor = {
            ".pdf": self._extract_pdf,
            ".docx": self._extract_docx,
            ".txt": self._extract_text,
            ".csv": self._extract_csv,
            ".xlsx": self._extract_xlsx,
        }.get(ext)
        if extractor is None:
            raise ExtractionError(f"Unsupported file type: {ext or 'unknown'}")
        result = extractor(data, ctx)
        if len(result.text) > MAX_EXTRACT_CHARS:
            result.text = result.text[:MAX_EXTRACT_CHARS]
            result.warnings.append(f"truncated extraction to {MAX_EXTRACT_CHARS} chars")
        return result

    # -- per-type extractors ---------------------------------------------------

    def _extract_text(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        text = _decode_best_effort(data)
        return ExtractedContent(
            text=text,
            metadata={"filename": ctx.filename, "content_type": ctx.content_type},
            spans=[{"kind": "file", "start": 0, "end": len(text)}] if text else [],
        )

    def _extract_pdf(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
        except Exception as e:  # noqa: BLE001
            raise ExtractionError(f"Malformed PDF: {e}") from e
        if reader.is_encrypted:
            try:
                reader.decrypt("")  # empty-password owner unlock; raises if real password
            except Exception as e:  # noqa: BLE001
                raise ExtractionError("Encrypted PDF: password required") from e
        parts: list[str] = []
        spans: list[dict[str, Any]] = []
        warnings: list[str] = []
        empty_pages = 0
        for i, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as e:  # noqa: BLE001
                warnings.append(f"page {i} extraction failed: {e}")
                page_text = ""
            if not page_text.strip():
                empty_pages += 1
            start = sum(len(p) for p in parts)
            parts.append(page_text)
            parts.append("\n\n")
            spans.append({"kind": "page", "number": i, "start": start, "end": start + len(page_text)})
        text = "".join(parts).strip()
        if not text:
            raise ExtractionError(
                "No extractable text in PDF (scanned/image-only content requires OCR, "
                "which is not enabled)"
            )
        if empty_pages:
            warnings.append(f"{empty_pages} of {len(reader.pages)} pages had no extractable text")
        return ExtractedContent(
            text=text,
            metadata={"filename": ctx.filename, "content_type": ctx.content_type, "page_count": len(reader.pages)},
            spans=spans,
            warnings=warnings,
        )

    def _extract_docx(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        import docx

        try:
            d = docx.Document(io.BytesIO(data))
        except Exception as e:  # noqa: BLE001
            raise ExtractionError(f"Malformed DOCX: {e}") from e
        parts: list[str] = []
        spans: list[dict[str, Any]] = []
        for i, para in enumerate(d.paragraphs):
            t = para.text or ""
            start = sum(len(p) for p in parts)
            parts.append(t)
            parts.append("\n")
            spans.append({"kind": "paragraph", "number": i, "start": start, "end": start + len(t)})
        # Tables: flatten rows to pipe-delimited lines (table-aware where feasible)
        table_rows: list[str] = []
        for t_idx, table in enumerate(d.tables):
            for r_idx, row in enumerate(table.rows):
                cells = [c.text.strip() for c in row.cells]
                line = " | ".join(cells)
                start = sum(len(p) for p in parts)
                parts.append(line)
                parts.append("\n")
                spans.append({"kind": "table_row", "table": t_idx, "row": r_idx, "start": start, "end": start + len(line)})
                table_rows.append(line)
        text = "".join(parts).strip()
        if not text:
            raise ExtractionError("DOCX contains no extractable text")
        return ExtractedContent(
            text=text,
            metadata={
                "filename": ctx.filename,
                "content_type": ctx.content_type,
                "paragraph_count": len(d.paragraphs),
                "table_count": len(d.tables),
            },
            spans=spans,
        )

    def _extract_csv(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        text = _decode_best_effort(data)
        if not text.strip():
            raise ExtractionError("CSV is empty")
        reader = csv.reader(io.StringIO(text))
        rows: list[list[str]] = [row for row in reader if row]
        if not rows:
            raise ExtractionError("CSV contains no rows")
        parts: list[str] = []
        spans: list[dict[str, Any]] = []
        for i, row in enumerate(rows):
            line = " | ".join(str(c) for c in row)
            start = sum(len(p) for p in parts)
            parts.append(line)
            parts.append("\n")
            spans.append({"kind": "row", "number": i, "start": start, "end": start + len(line)})
        return ExtractedContent(
            text="".join(parts).strip(),
            metadata={
                "filename": ctx.filename,
                "content_type": ctx.content_type,
                "row_count": len(rows),
                "column_count": max(len(r) for r in rows),
                "header": rows[0] if rows else [],
            },
            spans=spans,
        )

    def _extract_xlsx(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        import openpyxl

        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            raise ExtractionError(f"Malformed XLSX: {e}") from e
        parts: list[str] = []
        spans: list[dict[str, Any]] = []
        try:
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                parts.append(f"[sheet: {sheet_name}]\n")
                row_count = 0
                for row in ws.iter_rows(values_only=True):
                    if row is None:
                        continue
                    cells = ["" if c is None else str(c) for c in row]
                    if not any(c.strip() for c in cells):
                        continue
                    line = " | ".join(cells)
                    start = sum(len(p) for p in parts)
                    parts.append(line)
                    parts.append("\n")
                    spans.append({"kind": "sheet_row", "sheet": sheet_name, "row": row_count + 1, "start": start, "end": start + len(line)})
                    row_count += 1
                if row_count == 0:
                    spans.append({"kind": "sheet", "sheet": sheet_name, "start": 0, "end": 0})
        finally:
            wb.close()
        text = "".join(parts).strip()
        if not text:
            raise ExtractionError("XLSX contains no cell data")
        return ExtractedContent(
            text=text,
            metadata={
                "filename": ctx.filename,
                "content_type": ctx.content_type,
                "sheet_count": len(wb.sheetnames),
                "sheet_names": wb.sheetnames[:20],
            },
            spans=spans,
        )


def _extension_of(filename: str) -> str:
    import os

    return os.path.splitext(filename or "")[1].lower()


def _decode_best_effort(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


class TextNormalizer:
    """Whitespace normalization that preserves provenance offsets."""

    def normalize(self, content: ExtractedContent) -> ExtractedContent:
        text = content.text or ""
        # Collapse 3+ newlines to 2, CRLF to LF, strip trailing spaces per line.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        # Recompute spans against the normalized text conservatively:
        # spans remain valid by clamping to the new length and dropping empty ones.
        spans = []
        for span in content.spans:
            start = min(span.get("start", 0), len(text))
            end = min(span.get("end", 0), len(text))
            if end > start or span.get("end", 0) == 0:
                spans.append({**span, "start": start, "end": end})
        return ExtractedContent(
            text=text,
            metadata=dict(content.metadata),
            spans=spans,
            warnings=list(content.warnings),
        )


class Chunker:
    """Configurable, provenance-aware chunking with overlap.

    Chunks respect sentence boundaries where possible; each chunk records
    which page/row/sheet spans it overlaps so citations can carry provenance.
    """

    def __init__(self, chunk_size: int | None = None, overlap: int | None = None) -> None:
        self.chunk_size = chunk_size or 900
        self.overlap = overlap or 150
        if self.overlap >= self.chunk_size:
            raise ValueError("chunk overlap must be smaller than chunk size")
        if self.chunk_size < 100:
            raise ValueError("chunk size too small")

    def chunk(self, content: ExtractedContent, document_id: str | None = None, organization_id: str | None = None) -> list[dict[str, Any]]:
        text = content.text or ""
        if not text:
            return []
        spans = content.spans or [{"kind": "file", "start": 0, "end": len(text)}]
        chunks: list[dict[str, Any]] = []
        step = self.chunk_size - self.overlap
        idx = 0
        pos = 0
        n = len(text)
        while pos < n:
            end = min(pos + self.chunk_size, n)
            # Prefer breaking at a sentence/paragraph boundary near the end.
            if end < n:
                window = text[pos:end]
                for sep in ("\n\n", ". ", "\n", " "):
                    cut = window.rfind(sep)
                    if cut > self.chunk_size // 2:
                        end = pos + cut + len(sep)
                        break
            chunk_text = text[pos:end].strip()
            if chunk_text:
                # Deterministic chunk id (document_id + index) so re-indexing
                # overwrites the same Qdrant points instead of orphaning them.
                chunk_id = str(
                    uuid.uuid5(uuid.NAMESPACE_URL, f"nexus-chunk:{document_id}:{idx}")
                )
                provenance = self._provenance_for(spans, pos, end)
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "document_id": document_id,
                        "organization_id": organization_id,
                        "index": idx,
                        "text": chunk_text,
                        "char_start": pos,
                        "char_end": end,
                        "provenance": provenance,
                        "metadata": dict(content.metadata),
                    }
                )
                idx += 1
            if end >= n:
                break
            pos = end - self.overlap
        return chunks

    @staticmethod
    def _provenance_for(spans: list[dict[str, Any]], start: int, end: int) -> list[dict[str, Any]]:
        """Return the human-readable provenance (pages/rows/sheets) a chunk overlaps."""
        result: dict[tuple, dict[str, Any]] = {}
        for span in spans:
            s_start, s_end = span.get("start", 0), span.get("end", 0)
            if s_end <= start or s_start >= end:
                continue  # no overlap
            kind = span.get("kind", "file")
            key = (kind, span.get("number"), span.get("page"), span.get("row"), span.get("sheet"))
            entry = {"kind": kind}
            if span.get("number") is not None:
                entry["number"] = span["number"]
            if span.get("row") is not None:
                entry["row"] = span["row"]
            if span.get("sheet") is not None:
                entry["sheet"] = span["sheet"]
            result.setdefault(key, entry)
        return list(result.values())
