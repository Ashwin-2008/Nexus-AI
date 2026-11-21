"""Metadata extraction/enrichment for ingested documents.

Structural metadata comes from the loader/extractor; this module adds
deterministic, conservative fields (hashes, dates, entities, document title).
It never invents facts and never calls an LLM, so ingestion stays cheap and
reproducible.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from app.rag.types import ParsedDocument

_DATE_PATTERNS = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b", re.IGNORECASE),
)
_ENTITY_RE = re.compile(r"\b(?:[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,3})\b")
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*\b")


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def enrich_metadata(parsed: ParsedDocument, *, file_digest: str, filename: str, content_type: str) -> dict[str, Any]:
    text = parsed.text or ""
    metadata = dict(parsed.metadata)
    dates = []
    for pattern in _DATE_PATTERNS:
        dates.extend(match.group(0) for match in pattern.finditer(text[:200_000]))
    entities = []
    seen: set[str] = set()
    for match in _ENTITY_RE.finditer(text[:200_000]):
        candidate = match.group(0).strip()
        if candidate.lower() not in seen:
            seen.add(candidate.lower())
            entities.append(candidate)
        if len(entities) >= 25:
            break
    metadata.update(
        {
            "filename": filename,
            "content_type": content_type,
            "file_hash": file_digest,
            "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "word_count": len(text.split()),
            "char_count": len(text),
            "dates": dates[:10],
            "entities": entities,
            "number_count": len(_NUMBER_RE.findall(text[:200_000])),
            "enriched_at": datetime.now(timezone.utc).isoformat(),
            "metadata_method": "deterministic",
        }
    )
    return metadata
