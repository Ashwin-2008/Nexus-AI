"""Targeted hallucination checks used by the verification report."""
from __future__ import annotations

import re

from app.rag.types import EvidenceChunk

_NUMBER_RE = re.compile(r"(?<!\w)(\d[\d,.]*)(?!\w)")


def unsupported_numbers(claim: str, evidence: list[EvidenceChunk]) -> list[str]:
    claim_numbers = {value.replace(",", "").rstrip(".") for value in _NUMBER_RE.findall(claim)}
    evidence_text = "\n".join(item.text or "" for item in evidence)
    evidence_numbers = {value.replace(",", "").rstrip(".") for value in _NUMBER_RE.findall(evidence_text)}
    return sorted(claim_numbers - evidence_numbers)


def fabricated_citations(cited: set[int], evidence_count: int) -> list[int]:
    return sorted(index for index in cited if index < 1 or index > evidence_count)


def uncited_claims(claims) -> list[str]:
    return [claim.text for claim in claims if not claim.citation_indices]


def contradictory_pairs(evidence: list[EvidenceChunk]) -> list[dict[str, str]]:
    """Detect exact numeric contradictions between evidence passages.

    Conservative by design: only flags the same label with two different
    numeric values in the same document, which is a useful review signal but
    not proof of an error.
    """
    values: dict[str, dict[str, str]] = {}
    conflicts: list[dict[str, str]] = []
    for item in evidence:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", item.text or ""):
            match = re.search(r"([A-Za-z][A-Za-z ]{2,40}?)\s*(?:is|was|:|=)\s*(\d[\d,.]*)", sentence)
            if not match:
                continue
            label = re.sub(r"\s+", " ", match.group(1).strip().lower())
            value = match.group(2).replace(",", "").rstrip(".")
            previous = values.get(label)
            if previous and previous["value"] != value:
                conflicts.append(
                    {
                        "label": label,
                        "first_value": previous["value"],
                        "second_value": value,
                        "first_chunk": previous["chunk"],
                        "second_chunk": item.chunk_id,
                    }
                )
            else:
                values[label] = {"value": value, "chunk": item.chunk_id}
    return conflicts[:10]
