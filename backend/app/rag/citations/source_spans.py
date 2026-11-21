"""Source span helpers for citations."""
from __future__ import annotations

import re
from typing import Any


def page_number(provenance: list[dict[str, Any]]) -> int | None:
    for span in provenance or []:
        if span.get("kind") == "page" and span.get("number"):
            try:
                return int(span["number"])
            except (TypeError, ValueError):
                continue
    return None


def slide_number(provenance: list[dict[str, Any]]) -> int | None:
    for span in provenance or []:
        if span.get("kind") == "slide" and span.get("number"):
            try:
                return int(span["number"])
            except (TypeError, ValueError):
                continue
    return None


def span_within(text: str, quote: str) -> dict[str, int] | None:
    """Locate a quote inside chunk text (character offsets, half-open)."""
    if not text or not quote:
        return None
    needle = re.sub(r"\s+", " ", quote.strip())
    haystack = re.sub(r"\s+", " ", text)
    position = haystack.find(needle)
    if position < 0:
        # Fall back to the first 40 characters of the quote.
        position = haystack.find(needle[:40])
    if position < 0:
        return None
    return {"start": position, "end": position + len(needle)}


def source_span_for(evidence: Any) -> dict[str, int]:
    metadata = getattr(evidence, "metadata", None) or {}
    child_span = metadata.get("child_char_span")
    if metadata.get("expanded_parent") and isinstance(child_span, list) and len(child_span) == 2:
        return {"start": int(child_span[0]), "end": int(child_span[1])}
    return {"start": int(getattr(evidence, "char_start", 0) or 0), "end": int(getattr(evidence, "char_end", 0) or 0)}
