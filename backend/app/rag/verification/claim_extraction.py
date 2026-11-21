"""Claim extraction from generated answers (deterministic)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_CITATION_RE = re.compile(r"\[(\d{1,2})\]")
_BOILERPLATE = (
    "could not find enough",
    "do not contain enough evidence",
    "no relevant information",
    "here is what the retrieved sources say",
)


@dataclass
class Claim:
    text: str
    citation_indices: list[int] = field(default_factory=list)


def extract_claims(answer: str, max_claims: int = 40) -> list[Claim]:
    claims: list[Claim] = []
    for raw in _SENTENCE_RE.split(answer or ""):
        sentence = raw.strip()
        if not sentence:
            continue
        lowered = sentence.lower()
        if any(marker in lowered for marker in _BOILERPLATE):
            continue
        indices = sorted({int(match.group(1)) for match in _CITATION_RE.finditer(sentence)})
        text = _CITATION_RE.sub("", sentence).strip(" -*•\t")
        if len(text) < 8 or not re.search(r"[A-Za-zÀ-ÿ]", text):
            continue
        claims.append(Claim(text=text, citation_indices=indices))
        if len(claims) >= max_claims:
            break
    return claims
