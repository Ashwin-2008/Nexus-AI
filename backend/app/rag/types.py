"""Typed internal contracts shared by the RAG pipeline and agents.

These dataclasses are the stable interface between stages. API routers convert
them to Pydantic schemas at the boundary; specialist agents consume them
directly. Keeping them explicit avoids passing unvalidated dictionaries
through the retrieval/generation path.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


def _jsonable(value: Any) -> Any:
    if dataclass_is(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (uuid.UUID, datetime)):
        return str(value)
    return value


def dataclass_is(value: Any) -> bool:
    return hasattr(value, "__dataclass_fields__")


def to_dict(value: Any) -> Any:
    """Recursively convert dataclasses/IDs/datetimes into JSON-safe values."""
    return _jsonable(value)


# ---------------------------------------------------------------------------
# Authorization / retrieval scope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RagScope:
    """Authorization context for every retrieval and generation call.

    ``organization_id`` is always applied as a hard filter. ``access_scopes``
    describes document-level scopes the caller may read. ``allowed_document_ids``
    is a defensive intersection when a caller explicitly selects documents.
    """

    organization_id: str
    user_id: str | None = None
    role: str = "member"
    access_scopes: tuple[str, ...] = ("organization",)
    allowed_document_ids: tuple[str, ...] = ()
    allowed_source_ids: tuple[str, ...] = ()

    def describe(self) -> dict[str, Any]:
        return {
            "organization_id": self.organization_id,
            "user_id": self.user_id,
            "role": self.role,
            "access_scopes": list(self.access_scopes),
            "allowed_document_ids": list(self.allowed_document_ids),
            "allowed_source_ids": list(self.allowed_source_ids),
        }


@dataclass(frozen=True)
class RetrievalFilters:
    """Optional narrowing filters; never widen the caller's authorization."""

    document_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    document_version: int | None = None
    metadata: tuple[tuple[str, str], ...] = ()  # equality filters on document metadata

    def is_empty(self) -> bool:
        return not (
            self.document_ids
            or self.source_ids
            or self.source_types
            or self.document_version is not None
            or self.metadata
        )

    def describe(self) -> dict[str, Any]:
        return {
            "document_ids": list(self.document_ids),
            "source_ids": list(self.source_ids),
            "source_types": list(self.source_types),
            "document_version": self.document_version,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


@dataclass
class LoadedDocument:
    """Raw loader output before parsing/normalization."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    spans: list[dict[str, Any]] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    loader: str = "unknown"


@dataclass
class ParsedDocument:
    """Normalized document ready for chunking."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    spans: list[dict[str, Any]] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    loader: str = "unknown"
    title: str | None = None
    language: str | None = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256((self.text or "").encode("utf-8")).hexdigest()


@dataclass
class ChunkRecord:
    """Technical chunk representation persisted and indexed."""

    chunk_id: str
    document_id: str
    organization_id: str
    index: int
    text: str
    char_start: int
    char_end: int
    provenance: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    section_heading: str | None = None
    parent_chunk_id: str | None = None
    content_hash: str = ""
    token_count: int = 0
    strategy: str = "recursive"
    document_version: int = 1
    access_scope: str = "organization"
    source_id: str | None = None

    def to_vector_payload(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "organization_id": self.organization_id,
            "index": self.index,
            "text": self.text,
            "metadata": self.metadata,
            "provenance": self.provenance,
            "section_heading": self.section_heading,
            "parent_chunk_id": self.parent_chunk_id,
            "content_hash": self.content_hash,
            "token_count": self.token_count,
            "strategy": self.strategy,
            "document_version": self.document_version,
            "access_scope": self.access_scope,
            "source_id": self.source_id,
        }

    def to_db_fields(self) -> dict[str, Any]:
        return {
            "id": uuid.UUID(self.chunk_id),
            "document_id": uuid.UUID(self.document_id),
            "organization_id": uuid.UUID(self.organization_id),
            "chunk_index": self.index,
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "section_heading": self.section_heading,
            "parent_chunk_id": uuid.UUID(self.parent_chunk_id) if self.parent_chunk_id else None,
            "content_hash": self.content_hash,
            "token_count": self.token_count,
            "chunk_strategy": self.strategy,
            "document_version": self.document_version,
            "access_scope": self.access_scope,
        }


@dataclass
class IngestionOutcome:
    document_id: str
    organization_id: str
    status: str
    version: int
    chunks: int
    embeddings: int
    content_hash: str
    chunk_strategy: str
    embedding_provider: str
    embedding_model: str
    index_backend: str
    indexed: bool
    duplicate_of: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Query understanding
# ---------------------------------------------------------------------------


@dataclass
class QueryAnalysis:
    original: str
    normalized: str
    intent: str = "question"
    expected_answer_type: str = "unknown"
    entities: list[str] = field(default_factory=list)
    time_constraints: list[str] = field(default_factory=list)
    needs_retrieval: bool = True
    needs_multiple_retrieval: bool = False
    needs_specialists: bool = False
    suggested_agents: list[str] = field(default_factory=list)
    rewritten: str | None = None
    subqueries: list[str] = field(default_factory=list)
    expansion_terms: list[str] = field(default_factory=list)
    method: str = "deterministic"
    notes: list[str] = field(default_factory=list)

    @property
    def retrieval_queries(self) -> list[str]:
        queries = [self.rewritten or self.normalized]
        queries.extend(self.subqueries)
        # preserve order, drop blanks/duplicates
        seen: set[str] = set()
        result: list[str] = []
        for query in queries:
            key = query.strip().lower()
            if key and key not in seen:
                seen.add(key)
                result.append(query.strip())
        return result


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


@dataclass
class EvidenceChunk:
    chunk_id: str
    document_id: str
    organization_id: str
    document_filename: str
    text: str
    score: float
    mode: str = "hybrid"
    provenance: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    section_heading: str | None = None
    source_id: str | None = None
    source_type: str | None = None
    document_version: int = 1
    access_scope: str = "organization"
    char_start: int = 0
    char_end: int = 0
    content_hash: str = ""
    retrieval_rank: int = 0
    rerank_score: float | None = None
    rerank_method: str | None = None
    retrieval_scores: dict[str, float] = field(default_factory=dict)
    matched_queries: list[str] = field(default_factory=list)

    @property
    def page_number(self) -> int | None:
        for span in self.provenance:
            if span.get("kind") == "page" and span.get("number"):
                return int(span["number"])
        return None

    @property
    def citation_key(self) -> str:
        return self.chunk_id or f"{self.document_id}:{self.char_start}:{self.char_end}"

    def to_dict(self, include_text: bool = True) -> dict[str, Any]:
        payload = to_dict(self)
        if not include_text:
            payload.pop("text", None)
        return payload


@dataclass
class RetrievalResult:
    query: str
    mode: str
    evidence: list[EvidenceChunk] = field(default_factory=list)
    queries_used: list[str] = field(default_factory=list)
    reranker: str | None = None
    filtered_count: int = 0
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, int] = field(default_factory=dict)

    @property
    def top_score(self) -> float:
        return max((item.score for item in self.evidence), default=0.0)

    def to_dict(self, include_text: bool = True) -> dict[str, Any]:
        return {
            "query": self.query,
            "mode": self.mode,
            "evidence": [item.to_dict(include_text=include_text) for item in self.evidence],
            "queries_used": list(self.queries_used),
            "reranker": self.reranker,
            "filtered_count": self.filtered_count,
            "warnings": list(self.warnings),
            "timings": dict(self.timings),
        }


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


@dataclass
class Citation:
    citation_id: str
    index: int
    chunk_id: str
    document_id: str
    document_title: str
    source_type: str
    organization_id: str
    document_version: int = 1
    page_number: int | None = None
    section_heading: str | None = None
    source_span: dict[str, int] | None = None
    url: str | None = None
    file_reference: str | None = None
    source_id: str | None = None
    score: float = 0.0
    evidence_text: str = ""

    def to_dict(self, include_text: bool = True) -> dict[str, Any]:
        payload = to_dict(self)
        if not include_text:
            payload.pop("evidence_text", None)
        return payload


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


@dataclass
class ClaimVerification:
    claim: str
    status: str
    citation_indices: list[int] = field(default_factory=list)
    evidence_chunk_ids: list[str] = field(default_factory=list)
    support_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass
class VerificationReport:
    status: str
    claims: list[ClaimVerification] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    conflicting_claims: list[str] = field(default_factory=list)
    insufficient_claims: list[str] = field(default_factory=list)
    citation_errors: list[str] = field(default_factory=list)
    evidence_coverage: float = 0.0
    method: str = "deterministic_lexical_grounding"
    disclaimer: str = "Verification is a transparent heuristic, not a mathematical guarantee."
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)


# ---------------------------------------------------------------------------
# Pipeline request/response
# ---------------------------------------------------------------------------


@dataclass
class RagRequest:
    query: str
    scope: RagScope
    filters: RetrievalFilters = field(default_factory=RetrievalFilters)
    mode: str | None = None
    top_k: int | None = None
    rerank: bool | None = None
    verify: bool | None = None
    conversation_id: str | None = None
    max_context_tokens: int | None = None
    include_evidence: bool = True
    trace_id: str | None = None


@dataclass
class RagTimings:
    analysis_ms: int = 0
    rewrite_ms: int = 0
    retrieval_ms: int = 0
    rerank_ms: int = 0
    context_ms: int = 0
    generation_ms: int = 0
    verification_ms: int = 0
    total_ms: int = 0

    def to_dict(self) -> dict[str, int]:
        return to_dict(self)


@dataclass
class RagResponse:
    answer: str
    answer_mode: str
    model: str
    citations: list[Citation]
    evidence: list[EvidenceChunk]
    verification: VerificationReport | None
    query_analysis: QueryAnalysis
    timings: RagTimings
    trace_id: str
    insufficient_evidence: bool = False
    warnings: list[str] = field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    retrieval_mode: str = "hybrid"
    reranker: str | None = None
    degraded_from: str | None = None
    context_chunk_count: int = 0

    def to_dict(self, include_evidence_text: bool = True) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "answer_mode": self.answer_mode,
            "model": self.model,
            "citations": [c.to_dict(include_text=include_evidence_text) for c in self.citations],
            "evidence": [e.to_dict(include_text=include_evidence_text) for e in self.evidence]
            if include_evidence_text
            else [],
            "verification": self.verification.to_dict() if self.verification else None,
            "query_analysis": to_dict(self.query_analysis),
            "timings": self.timings.to_dict(),
            "trace_id": self.trace_id,
            "insufficient_evidence": self.insufficient_evidence,
            "warnings": list(self.warnings),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "retrieval_mode": self.retrieval_mode,
            "reranker": self.reranker,
            "degraded_from": self.degraded_from,
            "context_chunk_count": self.context_chunk_count,
        }


# ---------------------------------------------------------------------------
# Specialist agent contracts
# ---------------------------------------------------------------------------


@dataclass
class SpecialistRequest:
    request: str
    scope: RagScope
    source_id: str | None = None
    source_ids: list[str] = field(default_factory=list)
    sql: str | None = None
    max_rows: int = 100
    inputs: list[dict[str, Any]] = field(default_factory=list)
    execution_id: str | None = None
    filters: RetrievalFilters = field(default_factory=RetrievalFilters)


@dataclass
class SpecialistResponse:
    agent_id: str
    status: str
    answer: str | None = None
    findings: list[dict[str, Any]] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    evidence: list[EvidenceChunk] = field(default_factory=list)
    verification: VerificationReport | None = None
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    grounded: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = to_dict(self)
        payload.pop("evidence", None)  # evidence is transported separately to avoid duplication
        return payload
