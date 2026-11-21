"""Citation formatting helpers (markers and human-readable source lists)."""
from __future__ import annotations

from app.rag.types import Citation


def marker(index: int) -> str:
    return f"[{index}]"


def format_citation(citation: Citation) -> str:
    parts = [f"[{citation.index}] {citation.document_title}"]
    if citation.source_type:
        parts.append(f"({citation.source_type})")
    if citation.page_number:
        parts.append(f"p. {citation.page_number}")
    if citation.section_heading:
        parts.append(f"§ {citation.section_heading}")
    if citation.url:
        parts.append(citation.url)
    elif citation.file_reference:
        parts.append(citation.file_reference)
    if citation.document_version > 1:
        parts.append(f"v{citation.document_version}")
    return " · ".join(parts)


def format_source_list(citations: list[Citation]) -> str:
    if not citations:
        return "No sources cited."
    return "\n".join(format_citation(citation) for citation in sorted(citations, key=lambda item: item.index))
