"""Structured output parsing for generated answers.

Providers may return plain text or a JSON object. Both are accepted; JSON is
used when it validates, otherwise the text is preserved verbatim (never
invented or repaired into a different answer).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_FENCE_RE = re.compile(r"^```(?:json|markdown)?\s*|\s*```$", re.IGNORECASE)
# Some OpenAI-compatible providers occasionally decode a citation marker as
# "?1?" instead of "[1]" (observed with Groq gpt-oss). Restore the marker so
# citations resolve and verification can see them.
_QMARK_CITATION_RE = re.compile(r"[?？](\d{1,2})[?？]")
_CITATION_BRACKETS_RE = re.compile(r"[\[［【「]\s*(\d{1,2})\s*[\]］】」]")


@dataclass
class ParsedAnswer:
    answer: str
    claims: list[str] = field(default_factory=list)
    structured: bool = False
    warnings: list[str] = field(default_factory=list)


def parse_answer(raw: str) -> ParsedAnswer:
    text = (raw or "").replace("\u202f", " ").replace("\u00a0", " ").strip()
    text = _CITATION_BRACKETS_RE.sub(r"[\1]", text)
    text = _QMARK_CITATION_RE.sub(r"[\1]", text)
    if not text:
        return ParsedAnswer(answer="", warnings=["model returned an empty answer"])
    candidate = _FENCE_RE.sub("", text).strip()
    if candidate.startswith("{"):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            answer = payload.get("answer")
            claims = payload.get("claims") or []
            if isinstance(answer, str) and answer.strip():
                return ParsedAnswer(
                    answer=answer.strip(),
                    claims=[str(claim) for claim in claims if isinstance(claim, str)][:40],
                    structured=True,
                )
    return ParsedAnswer(answer=text)


def strip_citation_markers(text: str) -> str:
    return re.sub(r"\[\d{1,2}\]", "", text or "").strip()
