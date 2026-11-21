"""Content normalization with exact provenance remapping.

The legacy ``TextNormalizer`` clamps spans after whitespace collapsing. The RAG
pipeline instead builds a character→normalized-index map so page/row/slide
spans stay accurate after normalization. Spans are remapped in
:mod:`app.rag.ingestion.normalizer`.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TRAILING_SPACE_RE = re.compile(r"[ \t]+\n")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_SPACE_RUN_RE = re.compile(r"[ \t]{2,}")


class NormalizationResult:
    __slots__ = ("text", "index_map", "warnings")

    def __init__(self, text: str, index_map: list[int], warnings: list[str]) -> None:
        self.text = text
        self.index_map = index_map
        self.warnings = warnings


def normalize_text(raw: str, *, max_chars: int | None = None) -> NormalizationResult:
    """Normalize text and return a map from original index → normalized index.

    ``index_map`` has ``len(raw) + 1`` entries. For an original span
    ``[start, end)`` the normalized span is
    ``[index_map[start], index_map[min(end, len(raw))])``.
    """
    warnings: list[str] = []
    if max_chars is not None and len(raw) > max_chars:
        warnings.append(f"truncated extraction to {max_chars} chars")
        raw = raw[:max_chars]

    chars: list[str] = []
    index_map: list[int] = [0] * (len(raw) + 1)
    pending_space = False
    newline_run = 0
    last_was_newline = True  # suppress leading newlines
    length = 0

    def emit(value: str) -> None:
        nonlocal length
        chars.append(value)
        length += len(value)

    for position, original in enumerate(raw):
        index_map[position] = length
        if original == "\r":
            # CRLF is handled on the following LF; a lone CR becomes a newline.
            continue
        if original == "\n":
            if newline_run >= 2:
                continue
            pending_space = False
            emit("\n")
            newline_run += 1
            last_was_newline = True
            continue
        newline_run = 0
        normalized_char = unicodedata.normalize("NFKC", original)
        if normalized_char == "":
            continue
        if normalized_char in (" ", "\t") or normalized_char.isspace():
            if last_was_newline:
                continue
            pending_space = True
            continue
        if _CONTROL_RE.match(normalized_char):
            continue
        if pending_space:
            emit(" ")
            pending_space = False
        emit(normalized_char)
        last_was_newline = False
    index_map[len(raw)] = length

    text = "".join(chars).strip()
    # Map targets can only be clamped, never shifted: spans earlier in the text
    # must keep their positions when trailing whitespace is removed.
    if len(text) != length:
        index_map = [min(value, len(text)) for value in index_map]
    return NormalizationResult(text=text, index_map=index_map, warnings=warnings)


def remap_spans(spans: list[dict[str, Any]], index_map: list[int], text_length: int) -> list[dict[str, Any]]:
    remapped: list[dict[str, Any]] = []
    original_length = len(index_map) - 1
    for span in spans:
        start = max(0, min(int(span.get("start", 0) or 0), original_length))
        end = max(start, min(int(span.get("end", 0) or 0), original_length))
        new_start = min(index_map[start], text_length)
        new_end = min(max(index_map[end], new_start), text_length)
        item = {**span, "start": new_start, "end": new_end}
        remapped.append(item)
    return remapped
