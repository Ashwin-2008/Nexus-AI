"""Filter normalization for vector and lexical retrieval.

Filters can only narrow a query; they can never widen the caller's
organization or document authorization. Values are validated as UUIDs where
the backing column is a UUID.
"""
from __future__ import annotations

import uuid
from typing import Iterable

from app.rag.types import RetrievalFilters


def clean_uuid_list(values: Iterable[str] | None) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        try:
            cleaned.append(str(uuid.UUID(str(value))))
        except (ValueError, AttributeError, TypeError):
            continue
    return cleaned


def normalize_filters(filters: RetrievalFilters | None) -> RetrievalFilters:
    if filters is None:
        return RetrievalFilters()
    return RetrievalFilters(
        document_ids=tuple(clean_uuid_list(filters.document_ids)),
        source_ids=tuple(clean_uuid_list(filters.source_ids)),
        source_types=tuple(sorted({value.strip().lower() for value in filters.source_types if value.strip()})),
        document_version=filters.document_version,
        metadata=tuple(sorted(filters.metadata)),
    )


def describe_filters(filters: RetrievalFilters) -> dict:
    return filters.describe()
