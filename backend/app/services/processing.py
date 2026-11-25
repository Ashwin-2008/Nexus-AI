"""Document processing pipeline: extraction, normalization, chunking.

Real content extraction per file type (PDF/DOCX/TXT/Markdown/CSV/XLSX/PPTX/
HTML/JSON/EML) with page/row/slide provenance, plus configurable chunking with
overlap. Embedding and vector indexing live in embeddings.py /
vector_index.py; the modular RAG pipeline builds on these primitives.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from app.core.config import settings

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


def _ocr_blobs(blobs: list[bytes], label: str, limit: int = 12) -> tuple[list[str], list[str]]:
    """OCR embedded images for formats that also contain normal text."""
    warnings: list[str] = []
    if not blobs or not settings.ocr_enabled:
        return [], warnings
    from app.rag.parsing.ocr import get_ocr_engine

    engine = get_ocr_engine()
    if not engine.available():
        warnings.append("OCR unavailable: embedded images were skipped (install Tesseract)")
        return [], warnings
    recovered: list[str] = []
    for index, blob in enumerate(blobs[:limit], start=1):
        try:
            text = engine.extract_text(blob)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{label} image {index} OCR failed: {exc}")
            continue
        if text.strip():
            recovered.append(text.strip())
    return recovered, warnings


class FileExtractor:
    """Content-type aware text extraction with provenance spans."""

    def extract(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        ext = _extension_of(ctx.filename)
        extractor = {
            ".pdf": self._extract_pdf,
            ".docx": self._extract_docx,
            ".txt": self._extract_text,
            ".md": self._extract_markdown,
            ".markdown": self._extract_markdown,
            ".csv": self._extract_csv,
            ".xlsx": self._extract_xlsx,
            ".pptx": self._extract_pptx,
            ".html": self._extract_html,
            ".htm": self._extract_html,
            ".json": self._extract_json,
            ".eml": self._extract_email,
            ".png": self._extract_image,
            ".jpg": self._extract_image,
            ".jpeg": self._extract_image,
            ".webp": self._extract_image,
            ".tif": self._extract_image,
            ".tiff": self._extract_image,
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

    def _extract_image(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        from app.rag.parsing.ocr import get_ocr_engine

        engine = get_ocr_engine()
        if not engine.available():
            raise ExtractionError(
                "Image OCR is unavailable. Install Tesseract OCR on the worker "
                "(or set OCR_TESSERACT_CMD) and retry."
            )
        try:
            text = engine.extract_text(data)
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError(f"Image OCR failed: {exc}") from exc
        if not text.strip():
            raise ExtractionError("OCR found no readable text in the image")
        return ExtractedContent(
            text=text,
            metadata={
                "filename": ctx.filename,
                "content_type": ctx.content_type,
                "ocr_engine": engine.name,
            },
            spans=[{"kind": "image", "start": 0, "end": len(text)}],
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
        ocr_pages = 0
        ocr_engine = None
        if settings.ocr_enabled:
            from app.rag.parsing.ocr import get_ocr_engine

            candidate = get_ocr_engine()
            ocr_engine = candidate if candidate.available() else None
        for i, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as e:  # noqa: BLE001
                warnings.append(f"page {i} extraction failed: {e}")
                page_text = ""
            ocr_text = ""
            if (
                ocr_engine is not None
                and len(page_text.strip()) < max(1, settings.ocr_min_text_chars)
                and ocr_pages < max(1, settings.ocr_max_pages)
            ):
                scanned: list[str] = []
                try:
                    images = list(page.images)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"page {i} image extraction failed: {exc}")
                    images = []
                for image in images[:4]:
                    try:
                        scanned.append(ocr_engine.extract_text(image.data))
                    except Exception as exc:  # noqa: BLE001
                        warnings.append(f"page {i} OCR failed: {exc}")
                ocr_text = "\n".join(part.strip() for part in scanned if part.strip())
                if ocr_text:
                    ocr_pages += 1
                    page_text = (page_text + "\n" + ocr_text).strip()
            if not page_text.strip():
                empty_pages += 1
            start = sum(len(p) for p in parts)
            parts.append(page_text)
            parts.append("\n\n")
            spans.append({"kind": "page", "number": i, "start": start, "end": start + len(page_text)})
        text = "".join(parts).strip()
        if not text:
            if ocr_engine is None:
                detail = (
                    " OCR is enabled but Tesseract is unavailable (install it or set OCR_TESSERACT_CMD)"
                    if settings.ocr_enabled
                    else " OCR is disabled (set OCR_ENABLED=true to read scans)"
                )
            else:
                detail = " OCR found no readable text in the embedded page images"
            raise ExtractionError(f"No extractable text in PDF;{detail}")
        if empty_pages:
            warnings.append(f"{empty_pages} of {len(reader.pages)} pages had no extractable text")
        if ocr_pages:
            warnings.append(f"OCR recovered text from {ocr_pages} page(s)")
        return ExtractedContent(
            text=text,
            metadata={
                "filename": ctx.filename,
                "content_type": ctx.content_type,
                "page_count": len(reader.pages),
                "ocr_pages": ocr_pages,
            },
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
        image_warnings: list[str] = []
        image_blobs: list[bytes] = []
        try:
            for part in d.part.package.iter_parts():
                if getattr(part, "content_type", "").startswith("image/") and hasattr(part, "blob"):
                    image_blobs.append(part.blob)
        except Exception as exc:  # noqa: BLE001
            image_warnings.append(f"DOCX image enumeration failed: {exc}")
        recovered, ocr_warnings = _ocr_blobs(image_blobs, "DOCX")
        ocr_warnings = image_warnings + ocr_warnings
        if recovered:
            parts.append("\n[Image text]\n")
            parts.extend(recovered)
            parts.append("\n")
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
                "ocr_images": len(recovered),
            },
            spans=spans,
            warnings=ocr_warnings,
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

    # -- added formats ---------------------------------------------------------

    def _extract_markdown(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        """Markdown text with ATX/Setext headings recorded as section spans."""
        text = _decode_best_effort(data)
        if not text.strip():
            raise ExtractionError("Markdown file is empty")
        lines = text.splitlines()
        spans: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
        offset = 0
        current_heading: str | None = None
        heading_start = 0
        for index, line in enumerate(lines):
            stripped = line.strip()
            heading = None
            level = 1
            if stripped.startswith("#"):
                match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
                if match:
                    heading = match.group(2).strip()
                    level = len(match.group(1))
            elif index + 1 < len(lines) and re.match(r"^\s*(=+|-{3,})\s*$", lines[index + 1]) and stripped:
                heading = stripped
            if heading:
                if current_heading is not None:
                    sections.append({"heading": current_heading, "level": level, "start": heading_start, "end": offset})
                current_heading = heading
                heading_start = offset
                spans.append({"kind": "heading", "title": heading, "level": level, "start": offset, "end": offset + len(line)})
            offset += len(line) + 1
        if current_heading is not None:
            sections.append({"heading": current_heading, "level": 1, "start": heading_start, "end": len(text)})
        spans.append({"kind": "file", "start": 0, "end": len(text)})
        return ExtractedContent(
            text=text,
            metadata={
                "filename": ctx.filename,
                "content_type": ctx.content_type,
                "format": "markdown",
                "line_count": len(lines),
                "heading_count": len(sections),
                "headings": [s["heading"] for s in sections[:50]],
            },
            spans=spans,
        )

    def _extract_html(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        """HTML text extraction (stdlib parser, no new dependency)."""
        html = _decode_best_effort(data)
        if not html.strip():
            raise ExtractionError("HTML file is empty")
        parser = _HtmlDocumentParser()
        try:
            parser.feed(html)
            parser.close()
        except Exception as e:  # noqa: BLE001
            raise ExtractionError(f"Malformed HTML: {e}") from e
        text = parser.text()
        if not text.strip():
            raise ExtractionError("HTML contains no extractable text")
        metadata = {
            "filename": ctx.filename,
            "content_type": ctx.content_type,
            "format": "html",
            "title": parser.title,
            "heading_count": len(parser.sections),
            "headings": [s["heading"] for s in parser.sections[:50]],
        }
        if parser.title:
            metadata["document_title"] = parser.title
        return ExtractedContent(
            text=text,
            metadata=metadata,
            spans=parser.spans or [{"kind": "file", "start": 0, "end": len(text)}],
        )

    def _extract_json(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        """Flatten JSON into readable key/value lines with per-field spans."""
        import json as json_lib

        raw = _decode_best_effort(data)
        try:
            payload = json_lib.loads(raw)
        except Exception as e:  # noqa: BLE001
            raise ExtractionError(f"Malformed JSON: {e}") from e
        parts: list[str] = []
        spans: list[dict[str, Any]] = []

        def walk(value: Any, path: str, depth: int = 0) -> None:
            if depth > 20:
                return
            if isinstance(value, dict):
                for key, item in value.items():
                    walk(item, f"{path}.{key}" if path else str(key), depth + 1)
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    walk(item, f"{path}[{index}]", depth + 1)
            else:
                line = f"{path}: {value}"
                start = sum(len(part) for part in parts)
                parts.append(line)
                parts.append("\n")
                spans.append({"kind": "json_field", "path": path, "start": start, "end": start + len(line)})

        walk(payload, "")
        text = "".join(parts).strip()
        if not text:
            raise ExtractionError("JSON contains no scalar values")
        return ExtractedContent(
            text=text,
            metadata={
                "filename": ctx.filename,
                "content_type": ctx.content_type,
                "format": "json",
                "field_count": len(spans),
                "top_level_type": type(payload).__name__,
            },
            spans=spans,
        )

    def _extract_pptx(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        """PPTX slide text via the OOXML zip container (no python-pptx dependency)."""
        import zipfile
        from xml.etree import ElementTree

        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except Exception as e:  # noqa: BLE001
            raise ExtractionError(f"Malformed PPTX: {e}") from e
        names = [name for name in archive.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", name)]
        if not names:
            raise ExtractionError("PPTX contains no slides")
        names.sort(key=lambda name: int(re.findall(r"(\d+)", name)[-1]))
        ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
        parts: list[str] = []
        spans: list[dict[str, Any]] = []
        warnings: list[str] = []
        try:
            for slide_number, name in enumerate(names, start=1):
                try:
                    root = ElementTree.fromstring(archive.read(name))
                except ElementTree.ParseError as e:
                    warnings.append(f"slide {slide_number} parse failed: {e}")
                    continue
                texts = [element.text for element in root.iter(f"{ns}t") if element.text]
                slide_text = "\n".join(part.strip() for part in texts if part.strip())
                start = sum(len(part) for part in parts)
                if slide_text:
                    parts.append(slide_text)
                    parts.append("\n\n")
                spans.append({"kind": "slide", "number": slide_number, "start": start, "end": start + len(slide_text)})
            media = [
                name
                for name in archive.namelist()
                if name.startswith("ppt/media/")
                and name.lower().rsplit(".", 1)[-1] in {"png", "jpg", "jpeg", "webp", "tif", "tiff"}
            ]
            recovered, ocr_warnings = _ocr_blobs([archive.read(name) for name in media], "PPTX")
            warnings.extend(ocr_warnings)
            if recovered:
                parts.append("\n[Image text]\n")
                parts.extend(recovered)
                parts.append("\n")
        finally:
            archive.close()
        text = "".join(parts).strip()
        if not text:
            raise ExtractionError("PPTX slides contain no extractable text")
        return ExtractedContent(
            text=text,
            metadata={
                "filename": ctx.filename,
                "content_type": ctx.content_type,
                "format": "pptx",
                "slide_count": len(names),
                "ocr_images": len(recovered),
            },
            spans=spans,
            warnings=warnings,
        )

    def _extract_email(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        """Email message (.eml) with headers, body, and attachment metadata."""
        import email as email_lib
        from email import policy as email_policy

        try:
            message = email_lib.message_from_bytes(data, policy=email_policy.default)
        except Exception as e:  # noqa: BLE001
            raise ExtractionError(f"Malformed email: {e}") from e
        bodies: list[str] = []
        attachments: list[str] = []
        parts = message.walk() if message.is_multipart() else [message]
        for part in parts:
            if part.is_multipart():
                continue
            filename = part.get_filename()
            if filename:
                attachments.append(filename)
                continue
            content_type = part.get_content_type()
            if content_type not in ("text/plain", "text/html"):
                continue
            try:
                body = part.get_content()
            except Exception:  # noqa: BLE001
                payload = part.get_payload(decode=True) or b""
                body = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
            if content_type == "text/html":
                parser = _HtmlDocumentParser()
                parser.feed(body or "")
                body = parser.text()
            if body and body.strip():
                bodies.append(body.strip())
        header_block = "\n".join(
            f"{name}: {message.get(name)}"
            for name in ("From", "To", "Cc", "Date", "Subject", "Message-ID")
            if message.get(name)
        )
        text = (header_block + "\n\n" + "\n\n".join(bodies)).strip()
        if not text:
            raise ExtractionError("Email contains no readable text body")
        return ExtractedContent(
            text=text,
            metadata={
                "filename": ctx.filename,
                "content_type": ctx.content_type,
                "format": "email",
                "subject": str(message.get("Subject") or ""),
                "sender": str(message.get("From") or ""),
                "date": str(message.get("Date") or ""),
                "message_id": str(message.get("Message-ID") or ""),
                "attachments": attachments[:50],
            },
            spans=[{"kind": "email", "start": 0, "end": len(text)}],
        )


def _extension_of(filename: str) -> str:
    import os

    return os.path.splitext(filename or "")[1].lower()


class _HtmlDocumentParser(HTMLParser):
    """Small HTML→text parser that keeps headings, paragraphs and titles.

    Deliberately stdlib-only: no new runtime dependency is introduced for a
    format the existing connector stack already needed.
    """

    SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "head", "nav", "footer"}
    BLOCK_TAGS = {"p", "div", "br", "li", "tr", "section", "article", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._heading_depth = 0
        self._heading_text: list[str] = []
        self._title_depth = 0
        self._title_text: list[str] = []
        self.title: str | None = None
        self.spans: list[dict[str, Any]] = []
        self.sections: list[dict[str, Any]] = []
        self._offset = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._title_depth += 1
        if re.fullmatch(r"h[1-6]", tag):
            self._heading_depth += 1
            self._heading_text = []
            self.spans.append({"kind": "heading", "level": int(tag[1]), "start": self._offset, "end": self._offset})
        if tag in self.BLOCK_TAGS:
            self._chunks.append("\n")
            self._offset += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
            self.title = " ".join(part.strip() for part in self._title_text).strip() or None
        if re.fullmatch(r"h[1-6]", tag) and self._heading_depth:
            self._heading_depth -= 1
            heading = " ".join(part.strip() for part in self._heading_text).strip()
            if heading:
                self.sections.append({"heading": heading, "level": int(tag[1]), "start": self._offset, "end": self._offset})
                if self.spans:
                    self.spans[-1]["end"] = self._offset
                    self.spans[-1]["title"] = heading
        if tag in self.BLOCK_TAGS:
            self._chunks.append("\n")
            self._offset += 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._title_depth:
            self._title_text.append(data)
            return
        value = data.strip()
        if not value:
            return
        if self._heading_depth:
            self._heading_text.append(value)
        self._chunks.append(value)
        self._chunks.append("\n")
        self._offset += len(value) + 1

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self._chunks)).strip()


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
