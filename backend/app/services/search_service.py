"""Retrieval engine: semantic, lexical (BM25), and hybrid (RRF) search.

All modes are strictly organization-scoped. Semantic search goes through
Qdrant with an org filter; lexical search is BM25 over the organization's
persisted chunks in PostgreSQL/SQLite; hybrid fuses both rankings with
Reciprocal Rank Fusion.
"""
from __future__ import annotations

import json
import logging
import math
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk
from app.services.embeddings import EmbeddingError, get_embedding_provider
from app.services.vector_index import VectorIndexError, get_vector_index

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)


@dataclass
class SearchHit:
    chunk_id: str
    document_id: str
    document_filename: str
    chunk_index: int
    text: str
    provenance: list[dict[str, Any]]
    score: float
    mode: str
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_filename": self.document_filename,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "provenance": self.provenance,
            "score": round(self.score, 6),
            "mode": self.mode,
            "metadata": self.metadata or {},
        }


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _org_chunks(
    db: Session,
    organization_id,
    document_ids: list[str] | None,
    limit: int = 5000,
    *,
    source_ids: list[str] | None = None,
    source_types: list[str] | None = None,
    access_scopes: list[str] | None = None,
    document_version: int | None = None,
    include_parent_chunks: bool = False,
) -> list[tuple[DocumentChunk, Document]]:
    query = (
        db.query(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .filter(DocumentChunk.organization_id == organization_id)
    )
    if document_ids:
        uuids: list[Any] = []
        for d in document_ids:
            try:
                uuids.append(uuid.UUID(str(d)))
            except ValueError:
                continue  # invalid ids simply match nothing
        if uuids:
            query = query.filter(DocumentChunk.document_id.in_(uuids))
        else:
            return []
    if source_ids:
        source_uuids: list[Any] = []
        for source_id in source_ids:
            try:
                source_uuids.append(uuid.UUID(str(source_id)))
            except ValueError:
                continue
        if source_uuids:
            query = query.filter(Document.source_id.in_(source_uuids))
        else:
            return []
    if access_scopes:
        allowed = list(access_scopes)
        query = query.filter(
            or_(DocumentChunk.access_scope.is_(None), DocumentChunk.access_scope.in_(allowed))
        )
    if document_version is not None:
        query = query.filter(DocumentChunk.document_version == int(document_version))
    if not include_parent_chunks:
        # Parent-child parents are stored for context expansion only; children are indexed.
        query = query.filter(
            or_(DocumentChunk.chunk_strategy.is_(None), DocumentChunk.chunk_strategy != "parent_child_parent")
        )
    rows = query.order_by(DocumentChunk.document_id, DocumentChunk.chunk_index).limit(limit).all()
    if source_types:
        wanted = {value.lower() for value in source_types}
        filtered: list[tuple[DocumentChunk, Document]] = []
        for chunk, doc in rows:
            metadata: dict[str, Any] = {}
            if doc.doc_metadata:
                try:
                    metadata = json.loads(doc.doc_metadata) or {}
                except Exception:  # noqa: BLE001
                    metadata = {}
            source_type = str(metadata.get("connector_type") or metadata.get("source") or "upload").lower()
            if source_type in wanted:
                filtered.append((chunk, doc))
        rows = filtered
    return rows


def _chunk_context(chunk: DocumentChunk, doc: Document) -> str:
    parts: list[str] = []
    heading = getattr(chunk, "section_heading", None)
    if heading:
        parts.append(str(heading))
    try:
        metadata = json.loads(doc.doc_metadata) if doc.doc_metadata else {}
    except (TypeError, ValueError):
        metadata = {}
    if isinstance(metadata, dict):
        for key in ("document_title", "title", "subject", "summary", "semantic_profile", "keywords"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
            elif isinstance(value, list):
                parts.extend(str(item) for item in value if str(item).strip())
            elif isinstance(value, dict):
                parts.extend(str(item) for item in value.values() if str(item).strip())
    return " ".join(parts)


def lexical_search(
    db: Session,
    organization_id,
    query: str,
    top_k: int,
    document_ids: list[str] | None = None,
    *,
    source_ids: list[str] | None = None,
    source_types: list[str] | None = None,
    access_scopes: list[str] | None = None,
    document_version: int | None = None,
) -> list[SearchHit]:
    """BM25 ranking over the organization's chunks.

    Implementation note: BM25 is computed in Python over the org's chunk set
    (bounded by limit). At current scale this is correct and dependency-free;
    a Postgres tsvector/GIN index is the migration path for large corpora.
    """
    rows = _org_chunks(
        db,
        organization_id,
        document_ids,
        source_ids=source_ids,
        source_types=source_types,
        access_scopes=access_scopes,
        document_version=document_version,
    )
    if not rows:
        return []
    k1, b = 1.5, 0.75
    doc_tokens: list[list[str]] = []
    for chunk, doc in rows:
        # Include the section heading and document title/summary in the
        # lexical document. The cited text stays exactly the chunk text, but
        # a query that names the section or the document topic can now find
        # the passage even when the wording differs.
        context = _chunk_context(chunk, doc)
        doc_tokens.append(_tokenize(chunk.text) + (_tokenize(context) if context else []))
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []
    n_docs = len(doc_tokens)
    avgdl = sum(len(t) for t in doc_tokens) / n_docs if n_docs else 0.0
    # Document frequency per unique query term.
    df: dict[str, int] = {}
    for term in set(query_tokens):
        df[term] = sum(1 for tokens in doc_tokens if term in tokens)
    hits: list[SearchHit] = []
    for (chunk, doc), tokens in zip(rows, doc_tokens):
        if not tokens:
            continue
        score = 0.0
        tf: dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        dl = len(tokens)
        for term in set(query_tokens):
            f = tf.get(term, 0)
            if not f or df.get(term, 0) == 0:
                continue
            idf = math.log(1.0 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / (avgdl or 1.0)))
        if score > 0:
            hits.append(_hit_from_row(chunk, doc, score, "lexical"))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]


def semantic_search(
    organization_id,
    query: str,
    top_k: int,
    document_ids: list[str] | None = None,
    *,
    source_ids: list[str] | None = None,
    access_scopes: list[str] | None = None,
    document_version: int | None = None,
) -> list[SearchHit]:
    provider = get_embedding_provider()
    vectors = provider.embed([query])
    if not vectors:
        return []
    index = get_vector_index(dimensions=provider.dimensions)
    results = index.search(
        vector=vectors[0],
        organization_id=str(organization_id),
        top_k=top_k,
        document_ids=document_ids,
        source_ids=source_ids,
        access_scopes=access_scopes,
        document_version=document_version,
    )
    return [
        SearchHit(
            chunk_id=r["chunk_id"] or "",
            document_id=r["document_id"] or "",
            document_filename="",  # joined by caller
            chunk_index=r.get("chunk_index") or 0,
            text=r.get("text", ""),
            provenance=(r.get("metadata") or {}).get("provenance", []) if isinstance(r.get("metadata"), dict) else [],
            score=r.get("score", 0.0),
            mode="semantic",
            metadata={
                "semantic_score": r.get("score", 0.0),
                "section_heading": r.get("section_heading"),
                "parent_chunk_id": r.get("parent_chunk_id"),
                "content_hash": r.get("content_hash"),
                "document_version": r.get("document_version"),
                "access_scope": r.get("access_scope"),
                "source_id": r.get("source_id"),
            },
        )
        for r in results
    ]


def hybrid_search(
    db: Session,
    organization_id,
    query: str,
    top_k: int,
    document_ids: list[str] | None = None,
    *,
    source_ids: list[str] | None = None,
    source_types: list[str] | None = None,
    access_scopes: list[str] | None = None,
    document_version: int | None = None,
) -> list[SearchHit]:
    """Reciprocal Rank Fusion of semantic and lexical rankings."""
    k = 60
    lexical = {
        h.chunk_id: h
        for h in lexical_search(
            db,
            organization_id,
            query,
            top_k,
            document_ids,
            source_ids=source_ids,
            source_types=source_types,
            access_scopes=access_scopes,
            document_version=document_version,
        )
    }
    try:
        semantic_rows = semantic_search(
            organization_id,
            query,
            top_k,
            document_ids,
            source_ids=source_ids,
            access_scopes=access_scopes,
            document_version=document_version,
        )
    except EmbeddingError as e:
        logger.warning("semantic leg unavailable (%s); hybrid degrades to lexical", e)
        semantic_rows = []
    except VectorIndexError as e:
        logger.warning("vector index unavailable (%s); hybrid degrades to lexical", e)
        semantic_rows = []

    scores: dict[str, float] = {}
    hits: dict[str, SearchHit] = dict(lexical)
    for rank, hit in enumerate(semantic_rows, start=1):
        hits.setdefault(hit.chunk_id, hit)
        scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
    for rank, hit in enumerate(lexical.values(), start=1):
        scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
    ordered = sorted(hits.values(), key=lambda h: scores.get(h.chunk_id, 0.0), reverse=True)
    for h in ordered:
        h.score = scores.get(h.chunk_id, 0.0)
        h.mode = "hybrid"
    return ordered[:top_k]


def _hit_from_row(chunk: DocumentChunk, doc: Document, score: float, mode: str) -> SearchHit:
    provenance: list[dict[str, Any]] = []
    if chunk.provenance:
        try:
            provenance = json.loads(chunk.provenance)
        except Exception:  # noqa: BLE001
            provenance = []
    return SearchHit(
        chunk_id=str(chunk.id),
        document_id=str(chunk.document_id),
        document_filename=doc.filename,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        provenance=provenance,
        score=score,
        mode=mode,
        metadata={
            "embedding_model": chunk.embedding_model,
            "embedding_provider": chunk.embedding_provider,
            "section_heading": chunk.section_heading,
            "parent_chunk_id": str(chunk.parent_chunk_id) if chunk.parent_chunk_id else None,
            "content_hash": chunk.content_hash,
            "document_version": chunk.document_version,
            "access_scope": chunk.access_scope,
            "chunk_strategy": chunk.chunk_strategy,
        },
    )


def attach_document_info(db: Session, organization_id, hits: list[SearchHit]) -> list[SearchHit]:
    """Fill in document filenames/metadata for hits that came from Qdrant.

    Strictly org-scoped: only documents owned by organization_id are attached.
    """
    if not hits:
        return hits
    document_ids: list[uuid.UUID] = []
    for hit in hits:
        try:
            document_ids.append(uuid.UUID(str(hit.document_id)))
        except (ValueError, TypeError):
            continue
    if not document_ids:
        return []
    docs = (
        db.query(Document)
        .filter(
            Document.id.in_(document_ids),
            Document.organization_id == organization_id,
        )
        .all()
    )
    by_id = {str(d.id): d for d in docs}
    attached: list[SearchHit] = []
    for hit in hits:
        doc = by_id.get(str(hit.document_id))
        if doc is None:
            # Stale or unauthorized index point: never surface content without
            # a live, organization-owned document row.
            continue
        hit.document_filename = doc.filename
        if not hit.metadata:
            hit.metadata = {}
        hit.metadata.setdefault(
            "document_status",
            doc.status.value if hasattr(doc.status, "value") else str(doc.status),
        )
        attached.append(hit)
    return attached
