"""Section/layout detection for documents that do not expose explicit headings.

PDF text rarely carries structural markup. This module provides a conservative
deterministic heuristic (numbered headings, Title Case lines, ALL CAPS lines)
that only labels sections when the signal is strong; it never rewrites text.
"""
from __future__ import annotations

import re
from typing import Any

_NUMBERED_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+[A-Z][A-Za-z0-9 ,&/'()\-]{2,80}$")
_CHAPTER_HEADING = re.compile(r"^\s*(chapter|section|article|part)\s+[0-9IVXLC]+\b", re.IGNORECASE)


def detect_sections(
    text: str,
    existing: list[dict[str, Any]] | None = None,
    *,
    max_sections: int = 200,
) -> list[dict[str, Any]]:
    """Return heading spans.

    Existing loader-provided sections win. Otherwise headings are inferred from
    short lines that match numbering or are ALL CAPS/Title Case and contain no
    terminal sentence punctuation.
    """
    if existing:
        return existing
    sections: list[dict[str, Any]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        content = stripped.rstrip("\n")
        if 3 <= len(content) <= 90 and not content.endswith((".", ",", ";", ":")):
            is_heading = bool(_NUMBERED_HEADING.match(content) or _CHAPTER_HEADING.match(content))
            if not is_heading:
                letters = [char for char in content if char.isalpha()]
                words = content.split()
                if len(letters) >= 4 and len(words) <= 12 and not any(ch.isdigit() for ch in content):
                    uppercase_ratio = sum(1 for ch in letters if ch.isupper()) / len(letters)
                    title_case_ratio = sum(1 for word in words if word[:1].isupper()) / len(words)
                    is_heading = uppercase_ratio >= 0.85 or title_case_ratio >= 0.8
            if is_heading:
                sections.append(
                    {
                        "heading": content[:200],
                        "level": 1,
                        "start": offset,
                        "end": offset + len(content),
                        "inferred": True,
                    }
                )
                if len(sections) >= max_sections:
                    break
        offset += len(line)
    return sections


def heading_at(sections: list[dict[str, Any]], position: int) -> str | None:
    """Return the nearest heading at/before ``position``."""
    current = None
    for section in sorted(sections, key=lambda item: int(item.get("start", 0))):
        if int(section.get("start", 0)) <= position:
            current = section.get("heading")
        else:
            break
    return current
