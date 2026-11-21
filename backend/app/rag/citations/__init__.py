"""Citation resolution, formatting and validation."""
from app.rag.citations.formatter import format_citation, format_source_list, marker
from app.rag.citations.models import Citation
from app.rag.citations.resolver import CitationResolver, resolve_citations
from app.rag.citations.source_spans import page_number, source_span_for, span_within
from app.rag.citations.validation import cited_indices, dedupe_citations, validate_citations

__all__ = [
    "Citation",
    "CitationResolver",
    "cited_indices",
    "dedupe_citations",
    "format_citation",
    "format_source_list",
    "marker",
    "page_number",
    "resolve_citations",
    "source_span_for",
    "span_within",
    "validate_citations",
]
