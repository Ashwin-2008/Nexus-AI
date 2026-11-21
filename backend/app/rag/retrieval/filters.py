"""Retrieval filters and post-retrieval authorization revalidation.

Defence in depth:
1. requested document/source ids are validated against the caller's org;
2. vector/lexical backends receive organization + document filters;
3. every candidate is revalidated against the relational database and the
   caller's access scopes before it can reach the context builder or LLM.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from app.models.connector import DataSource
from app.models.document import Document, DocumentChunk
from app.rag.security import allowed_for_scope
from app.rag.types import EvidenceChunk, RagScope, RetrievalFilters
from app.rag.vectorstores.filters import clean_uuid_list, normalize_filters


def _org_uuid(scope: RagScope) -> uuid.UUID:
    return uuid.UUID(str(scope.organization_id))


def effective_filters(
    db: Session,
    scope: RagScope,
    filters: RetrievalFilters | None,
) -> tuple[RetrievalFilters, bool, list[str]]:
    """Intersect requested filters with authorization.

    Returns ``(filters, deny_all, warnings)``. ``deny_all`` means the caller
    requested something outside their authorization; the pipeline must return
    an empty, non-leaking result rather than broaden the search.
    """
    requested = normalize_filters(filters)
    warnings: list[str] = []
    deny_all = False
    document_ids = list(requested.document_ids)
    source_ids = list(requested.source_ids)

    if document_ids:
        rows = (
            db.query(Document)
            .filter(
                Document.organization_id == _org_uuid(scope),
                Document.id.in_([uuid.UUID(item) for item in document_ids]),
            )
            .all()
        )
        allowed = [
            str(row.id)
            for row in rows
            if allowed_for_scope(row.access_scope, scope)
            and (not scope.allowed_document_ids or str(row.id) in scope.allowed_document_ids)
        ]
        if len(allowed) != len(document_ids):
            warnings.append("some requested documents are not accessible and were excluded")
        if not allowed:
            deny_all = True
        document_ids = allowed

    if source_ids:
        rows = (
            db.query(DataSource)
            .filter(
                DataSource.organization_id == _org_uuid(scope),
                DataSource.id.in_([uuid.UUID(item) for item in source_ids]),
            )
            .all()
        )
        allowed_sources = [
            str(row.id)
            for row in rows
            if not scope.allowed_source_ids or str(row.id) in scope.allowed_source_ids
        ]
        if len(allowed_sources) != len(source_ids):
            warnings.append("some requested sources are not accessible and were excluded")
        if not allowed_sources:
            deny_all = True
        source_ids = allowed_sources

    return (
        replace(requested, document_ids=tuple(document_ids), source_ids=tuple(source_ids)),
        deny_all,
        warnings,
    )


def _doc_metadata(document: Document) -> dict[str, Any]:
    if not document.doc_metadata:
        return {}
    try:
        value = json.loads(document.doc_metadata)
        return value if isinstance(value, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _source_type(document: Document, metadata: dict[str, Any]) -> str:
    return str(metadata.get("connector_type") or metadata.get("source") or "upload").lower()


def revalidate_evidence(
    db: Session,
    scope: RagScope,
    filters: RetrievalFilters,
    evidence: list[EvidenceChunk],
) -> tuple[list[EvidenceChunk], int]:
    """Hydrate candidates from the database and drop anything unauthorized."""
    if not evidence:
        return [], 0
    document_ids = {uuid.UUID(item.document_id) for item in evidence if _is_uuid(item.document_id)}
    chunk_ids = {uuid.UUID(item.chunk_id) for item in evidence if _is_uuid(item.chunk_id)}
    if not document_ids:
        return [], len(evidence)
    documents = (
        db.query(Document)
        .filter(
            Document.organization_id == _org_uuid(scope),
            Document.id.in_(document_ids),
        )
        .all()
    )
    doc_map = {str(row.id): row for row in documents}
    chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.organization_id == _org_uuid(scope),
            DocumentChunk.id.in_(chunk_ids),
        )
        .all()
        if chunk_ids
        else []
    )
    chunk_map = {str(row.id): row for row in chunks}
    metadata_filters = dict(filters.metadata) if filters.metadata else {}

    allowed: list[EvidenceChunk] = []
    rejected = 0
    for item in evidence:
        document = doc_map.get(str(item.document_id))
        chunk = chunk_map.get(str(item.chunk_id))
        if document is None or chunk is None or str(chunk.document_id) != str(document.id):
            rejected += 1
            continue
        if not allowed_for_scope(getattr(document, "access_scope", None), scope):
            rejected += 1
            continue
        if not allowed_for_scope(getattr(chunk, "access_scope", None), scope):
            rejected += 1
            continue
        metadata = _doc_metadata(document)
        source_type = _source_type(document, metadata)
        if filters.source_types and source_type not in set(filters.source_types):
            rejected += 1
            continue
        if filters.source_ids and str(getattr(document, "source_id", "")) not in set(filters.source_ids):
            rejected += 1
            continue
        if filters.document_version is not None and int(chunk.document_version or 1) != int(filters.document_version):
            rejected += 1
            continue
        if metadata_filters and any(str(metadata.get(key)) != value for key, value in metadata_filters.items()):
            rejected += 1
            continue

        provenance = _provenance(chunk)
        item.organization_id = str(document.organization_id)
        item.document_filename = document.filename
        item.document_version = int(chunk.document_version or document.version or 1)
        item.access_scope = chunk.access_scope or getattr(document, "access_scope", "organization")
        item.source_id = str(document.source_id) if getattr(document, "source_id", None) else None
        item.source_type = source_type
        item.section_heading = chunk.section_heading
        item.content_hash = chunk.content_hash or item.content_hash
        item.char_start = int(chunk.char_start or 0)
        item.char_end = int(chunk.char_end or 0)
        item.text = chunk.text
        item.provenance = provenance or item.provenance
        item.metadata = {
            **(item.metadata or {}),
            "document_title": metadata.get("document_title") or document.filename,
            "uri": metadata.get("uri"),
            "connector_type": metadata.get("connector_type"),
            "external_id": metadata.get("external_id"),
            "document_status": _status(document),
            "section_heading": chunk.section_heading,
            "parent_chunk_id": str(chunk.parent_chunk_id) if chunk.parent_chunk_id else None,
            "document_version": int(chunk.document_version or document.version or 1),
            "access_scope": chunk.access_scope or "organization",
            "source_type": source_type,
        }
        allowed.append(item)
    return allowed, rejected


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


def _provenance(chunk: DocumentChunk) -> list[dict[str, Any]]:
    if not chunk.provenance:
        return []
    try:
        value = json.loads(chunk.provenance)
        return value if isinstance(value, list) else []
    except Exception:  # noqa: BLE001
        return []


def _status(document: Document) -> str:
    return document.status.value if hasattr(document.status, "value") else str(document.status)
