"""Citation validation: fabricated indices never survive."""
from __future__ import annotations

import re

from app.rag.types import Citation, EvidenceChunk

_CITATION_RE = re.compile(r"\[(\d{1,2})\]")


def cited_indices(answer: str) -> set[int]:
    return {int(match.group(1)) for match in _CITATION_RE.finditer(answer or "")}


def validate_citations(
    answer: str,
    evidence: list[EvidenceChunk],
    citations: list[Citation],
) -> tuple[list[Citation], list[str], set[int]]:
    """Return ``(valid_citations, errors, used_indices)``.

    Only indices that map to retrieved evidence are valid. Duplicate chunk
    citations are collapsed. Missing citations are not errors (some answers,
    e.g. the insufficient-evidence message, legitimately cite nothing).
    """
    errors: list[str] = []
    valid_indices = {index for index, _item in enumerate(evidence, start=1)}
    used = cited_indices(answer)
    fabricated = sorted(used - valid_indices)
    if fabricated:
        errors.append(f"answer cited non-existent passages: {fabricated}")
    by_index = {citation.index: citation for citation in citations}
    seen_chunks: set[str] = set()
    result: list[Citation] = []
    for index in sorted(used & valid_indices):
        citation = by_index.get(index)
        if citation is None:
            errors.append(f"citation for passage {index} could not be resolved")
            continue
        if citation.chunk_id in seen_chunks:
            continue
        seen_chunks.add(citation.chunk_id)
        result.append(citation)
    return result, errors, used & valid_indices


def dedupe_citations(citations: list[Citation]) -> list[Citation]:
    seen: set[str] = set()
    result: list[Citation] = []
    for citation in citations:
        key = citation.chunk_id or citation.citation_id
        if key in seen:
            continue
        seen.add(key)
        result.append(citation)
    return result
