"""Tests for real extraction, normalization, and chunking."""
from __future__ import annotations

import io
import uuid

import pytest

from app.services.processing import (
    Chunker,
    ExtractionError,
    ExtractedContent,
    FileExtractor,
    ProcessingContext,
    TextNormalizer,
)


def _ctx(filename: str) -> ProcessingContext:
    return ProcessingContext(
        document_id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        filename=filename,
        content_type="application/octet-stream",
        storage_path="orgs/x/documents/y",
        storage_backend="local",
    )


def _minimal_pdf(*page_texts: str) -> bytes:
    """Build a tiny valid PDF with one page per provided text."""
    objects: list[bytes] = []
    page_ids = []
    n_pages = len(page_texts)
    kids = " ".join(f"{3 + i * 2} 0 R" for i in range(n_pages))
    objects.append(b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n")
    objects.append(f"2 0 obj<</Type/Pages/Kids[{kids}]/Count {n_pages}>>endobj\n".encode())
    for i, text in enumerate(page_texts):
        content = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode("latin-1", errors="ignore")
        page_id = 3 + i * 2
        content_id = page_id + 1
        page_ids.append(page_id)
        objects.append(
            f"{page_id} 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents {content_id} 0 R/Resources<</Font<</F1 {3 + n_pages * 2} 0 R>>>>>>endobj\n".encode()
        )
        objects.append(
            f"{content_id} 0 obj<</Length {len(content)}>>stream\n".encode()
            + content
            + b"\nendstream\nendobj\n"
        )
    font_id = 3 + n_pages * 2
    objects.append(f"{font_id} 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n".encode())

    parts = [b"%PDF-1.4\n"]
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(sum(len(p) for p in parts))
        parts.append(obj)
    xref_pos = sum(len(p) for p in parts)
    xref = b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        xref += ("%010d 00000 n \n" % off).encode()
    trailer = b"trailer<</Size " + str(len(objects) + 1).encode() + b"/Root 1 0 R>>\nstartxref\n" + str(xref_pos).encode() + b"\n%%EOF\n"
    return b"".join(parts) + xref + trailer


class TestExtraction:
    def test_txt_extracts_with_provenance(self):
        result = FileExtractor().extract(b"hello world\nsecond line", _ctx("a.txt"))
        assert "hello world" in result.text
        assert result.spans and result.spans[0]["kind"] == "file"

    def test_pdf_multi_page_with_page_provenance(self):
        data = _minimal_pdf("Revenue was 1.2 million dollars", "Risk: supplier concentration")
        result = FileExtractor().extract(data, _ctx("report.pdf"))
        assert "Revenue was 1.2 million dollars" in result.text
        assert "supplier concentration" in result.text
        pages = [s for s in result.spans if s["kind"] == "page"]
        assert len(pages) == 2
        assert {s["number"] for s in pages} == {1, 2}
        assert result.metadata["page_count"] == 2

    def test_pdf_garbage_raises(self):
        # Random bytes are not a valid PDF -> ExtractionError (not silent completion)
        with pytest.raises(ExtractionError):
            FileExtractor().extract(b"\x00\x01\x02not a pdf at all\x03", _ctx("junk.pdf"))

    def test_pdf_scanned_no_text_raises(self):
        # Valid PDF structure but no extractable text
        data = _minimal_pdf("")
        with pytest.raises(ExtractionError):
            FileExtractor().extract(data, _ctx("scan.pdf"))

    def test_csv_rows_and_header(self):
        data = b"item,qty\nwidget,5\ngadget,3\n"
        result = FileExtractor().extract(data, _ctx("data.csv"))
        assert result.metadata["row_count"] == 3
        assert result.metadata["column_count"] == 2
        assert result.metadata["header"] == ["item", "qty"]
        rows = [s for s in result.spans if s["kind"] == "row"]
        assert len(rows) == 3

    def test_csv_empty_raises(self):
        with pytest.raises(ExtractionError):
            FileExtractor().extract(b"", _ctx("empty.csv"))

    def test_unsupported_extension_raises(self):
        with pytest.raises(ExtractionError):
            FileExtractor().extract(b"data", _ctx("virus.exe"))

    def test_txt_encoding_fallback(self):
        result = FileExtractor().extract("caf\xe9 test".encode("latin-1"), _ctx("legacy.txt"))
        assert "caf" in result.text


class TestNormalization:
    def test_collapses_blank_lines_and_keeps_spans(self):
        content = ExtractedContent(
            text="line one\n\r\n\r\n\r\nline two\n",
            metadata={"filename": "x.txt"},
            spans=[{"kind": "file", "start": 0, "end": 25}],
        )
        normalized = TextNormalizer().normalize(content)
        assert "\n\n\n" not in normalized.text
        assert normalized.text.startswith("line one")
        assert normalized.spans


class TestChunking:
    def _content(self, text: str) -> ExtractedContent:
        spans = []
        pages = text.split("\f") if "\f" in text else [text]
        pos = 0
        for i, page in enumerate(pages, 1):
            spans.append({"kind": "page", "number": i, "start": pos, "end": pos + len(page)})
            pos += len(page)
        return ExtractedContent(text=text, metadata={"filename": "doc.pdf"}, spans=spans)

    def test_chunks_respect_size_and_overlap(self):
        text = " ".join(f"Sentence number {i} with some content." for i in range(200))
        chunker = Chunker(chunk_size=300, overlap=60)
        chunks = chunker.chunk(self._content(text), document_id="d1", organization_id="o1")
        assert len(chunks) > 1
        for c in chunks:
            assert len(c["text"]) <= 300
        # Overlap: consecutive chunks share text
        for prev, nxt in zip(chunks, chunks[1:]):
            assert prev["char_end"] > nxt["char_start"]

    def test_chunk_ids_deterministic(self):
        text = "Some document text that will be chunked deterministically."
        c1 = Chunker().chunk(self._content(text), document_id="doc-1", organization_id="o1")
        c2 = Chunker().chunk(self._content(text), document_id="doc-1", organization_id="o1")
        assert [c["chunk_id"] for c in c1] == [c["chunk_id"] for c in c2]
        # Different document -> different ids
        c3 = Chunker().chunk(self._content(text), document_id="doc-2", organization_id="o1")
        assert [c["chunk_id"] for c in c1] != [c["chunk_id"] for c in c3]

    def test_provenance_records_pages(self):
        text = "Page one content.\fPage two content.\fPage three content."
        chunks = Chunker(chunk_size=120, overlap=20).chunk(
            self._content(text), document_id="d", organization_id="o"
        )
        all_prov = [p for c in chunks for p in c["provenance"]]
        page_numbers = {p.get("number") for p in all_prov if p["kind"] == "page"}
        assert page_numbers == {1, 2, 3}

    def test_overlap_larger_than_size_rejected(self):
        with pytest.raises(ValueError):
            Chunker(chunk_size=100, overlap=150)

    def test_empty_text_returns_no_chunks(self):
        assert Chunker().chunk(self._content(""), document_id="d", organization_id="o") == []

    def test_round_trip_offsets(self):
        text = "First chunk of text here. Then more follows immediately after that."
        chunks = Chunker(chunk_size=100, overlap=20).chunk(
            self._content(text), document_id="d", organization_id="o"
        )
        for c in chunks:
            # char offsets map back into the original text
            original_slice = text[c["char_start"] : c["char_end"]]
            assert c["text"].strip() in original_slice
