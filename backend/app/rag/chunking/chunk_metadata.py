"""Chunk construction and metadata preservation.

Every chunk carries the identifiers, provenance, hashes and access metadata
required by retrieval, citations and auditing. Chunk ids are deterministic so
re-indexing a document overwrites the same relational rows and vector points.
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Any

from app.rag.parsing.layout_extraction import heading_at
from app.rag.types import ChunkRecord

CHUNK_ID_NAMESPACE = uuid.NAMESPACE_URL


def estimate_tokens(text: str) -> int:
    """Approximate token count (~4 characters per token) for budgeting."""
    return max(1, len(text or "") // 4)


def chunk_id_for(
    document_id: str,
    index: int,
    *,
    strategy: str = "recursive",
    suffix: str | None = None,
) -> str:
    if strategy == "recursive" and not suffix:
        key = f"nexus-chunk:{document_id}:{index}"
    else:
        key = f"nexus-chunk:{strategy}:{document_id}:{suffix or index}"
    return str(uuid.uuid5(CHUNK_ID_NAMESPACE, key))


def provenance_for(spans: list[dict[str, Any]], start: int, end: int) -> list[dict[str, Any]]:
    """Human-readable provenance (page/slide/row/sheet/heading) a chunk overlaps."""
    result: dict[tuple, dict[str, Any]] = {}
    for span in spans:
        span_start, span_end = int(span.get("start", 0) or 0), int(span.get("end", 0) or 0)
        if span_end <= start or span_start >= end:
            continue
        kind = span.get("kind", "file")
        key = (
            kind,
            span.get("number"),
            span.get("page"),
            span.get("row"),
            span.get("sheet"),
            span.get("title"),
        )
        entry: dict[str, Any] = {"kind": kind}
        for field in ("number", "page", "row", "sheet", "table", "path"):
            if span.get(field) is not None:
                entry[field] = span[field]
        if span.get("title"):
            entry["title"] = span["title"]
        result.setdefault(key, entry)
    return list(result.values())


def chunk_metadata_fields(document_metadata: dict[str, Any], **extra: Any) -> dict[str, Any]:
    keys = (
        "document_title",
        "source",
        "connector_type",
        "external_id",
        "uri",
        "format",
        "language",
    )
    metadata = {key: document_metadata[key] for key in keys if document_metadata.get(key) is not None}
    metadata.update({key: value for key, value in extra.items() if value is not None})
    return metadata


def make_chunk(
    *,
    document_id: str,
    organization_id: str,
    index: int,
    text: str,
    char_start: int,
    char_end: int,
    spans: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    document_metadata: dict[str, Any],
    strategy: str,
    document_version: int = 1,
    access_scope: str = "organization",
    source_id: str | None = None,
    parent_chunk_id: str | None = None,
    suffix: str | None = None,
    role: str | None = None,
) -> ChunkRecord:
    clean = (text or "").strip()
    metadata = chunk_metadata_fields(document_metadata, chunk_role=role, access_scope=access_scope)
    return ChunkRecord(
        chunk_id=chunk_id_for(document_id, index, strategy=strategy, suffix=suffix),
        document_id=str(document_id),
        organization_id=str(organization_id),
        index=index,
        text=clean,
        char_start=max(0, char_start),
        char_end=max(char_start, char_end),
        provenance=provenance_for(spans, char_start, char_end),
        metadata=metadata,
        section_heading=heading_at(sections, char_start),
        parent_chunk_id=parent_chunk_id,
        content_hash=hashlib.sha256(clean.encode("utf-8")).hexdigest(),
        token_count=estimate_tokens(clean),
        strategy=strategy,
        document_version=document_version,
        access_scope=access_scope,
        source_id=source_id,
    )
