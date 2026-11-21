"""Structured specialist handlers built on the shared RAG service and tools.

Every specialist that needs knowledge retrieval calls ``app.rag.RagService``;
none implements its own retrieval pipeline. Evidence retrieved by one step is
passed to later steps so the supervisor can reuse it instead of querying the
indexes again.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.connector import DataSource
from app.rag.orchestration.service import RagService
from app.rag.types import EvidenceChunk, RagScope, RetrievalFilters
from app.services.connectors import ConnectorContext, ConnectorError, parse_config
from app.services.credentials import decrypt_credentials
from app.services.intelligence import search_email
from app.services.safe_sql import execute_read_only_sql
from app.services.sql_intelligence import generate_sql
from app.services.storage import get_storage_backend

_RETRIEVAL_INTENT = ("document", "policy", "report", "knowledge", "summarize", "what", "which", "how", "find", "compare")


def _scope(organization_id: uuid.UUID | str) -> RagScope:
    return RagScope(
        organization_id=str(organization_id),
        role="member",
        access_scopes=("organization", "member"),
    )


def _database_context(db: Session, organization_id: uuid.UUID, source_id: str) -> ConnectorContext:
    source = db.get(DataSource, uuid.UUID(str(source_id)))
    if source is None or source.organization_id != organization_id or source.type not in {"postgres", "mysql"}:
        raise ConnectorError("Database source not found or not permitted")
    return ConnectorContext(
        config={**parse_config(source.config), "type": source.type},
        credentials=decrypt_credentials(source.credentials_encrypted),
    )


def _citation_payload(citation) -> dict[str, Any]:
    payload = citation.to_dict()
    payload["document_filename"] = citation.file_reference or citation.document_title
    payload["text"] = citation.evidence_text
    payload["provenance"] = (
        [{"kind": "page", "number": citation.page_number}] if citation.page_number else []
    )
    return payload


def _citations(response) -> list[dict[str, Any]]:
    return [_citation_payload(citation) for citation in response.citations]


def _evidence_payload(evidence: list[EvidenceChunk]) -> list[dict[str, Any]]:
    return [item.to_dict(include_text=True) for item in evidence]


def _evidence_from_inputs(inputs: list[dict[str, Any]]) -> list[EvidenceChunk]:
    for item in reversed(inputs or []):
        if not isinstance(item, dict):
            continue
        raw = item.get("evidence")
        if isinstance(raw, list) and raw:
            evidence: list[EvidenceChunk] = []
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                fields = {
                    key: value
                    for key, value in entry.items()
                    if key in EvidenceChunk.__dataclass_fields__  # type: ignore[attr-defined]
                }
                try:
                    evidence.append(EvidenceChunk(**fields))
                except TypeError:
                    continue
            if evidence:
                return evidence
        if isinstance(item.get("context_evidence"), list):
            return _evidence_from_inputs([{"evidence": item["context_evidence"]}])
    return []


def _effective_scope(organization_id: uuid.UUID | str, scope: RagScope | None) -> RagScope:
    if scope is not None and str(scope.organization_id) != str(organization_id):
        raise PermissionError("retrieval scope does not match the requesting organization")
    return scope or _scope(organization_id)


def retrieval_agent(
    db: Session,
    organization_id: uuid.UUID,
    request: str,
    scope: RagScope | None = None,
) -> dict[str, Any]:
    response = RagService().answer(db, _effective_scope(organization_id, scope), request)
    return {
        "answer": response.answer,
        "answer_mode": response.answer_mode,
        "citations": _citations(response),
        "grounded": not response.insufficient_evidence,
        "verification": response.verification.to_dict() if response.verification else None,
        "evidence": _evidence_payload(response.evidence),
        "retrieval_latency_ms": response.timings.retrieval_ms,
        "generation_latency_ms": response.timings.generation_ms,
        "retrieval_mode": response.retrieval_mode,
        "reranker": response.reranker,
        "trace_id": response.trace_id,
        "warnings": response.warnings,
    }


def document_agent(
    db: Session,
    organization_id: uuid.UUID,
    request: str,
    inputs: list[dict[str, Any]] | None = None,
    scope: RagScope | None = None,
) -> dict[str, Any]:
    scope = _effective_scope(organization_id, scope)
    service = RagService()
    prior = _evidence_from_inputs(inputs or [])
    if prior:
        response = service.answer_with_evidence(db, scope, request, prior)
        reused = True
    else:
        retrieval = service.retrieve(db, scope, request)
        reused = False
        if not retrieval.evidence:
            return {
                "findings": [],
                "missing_information": ["No permitted document evidence matched the request"],
                "citations": [],
                "evidence": [],
                "reused_retrieval": reused,
            }
        response = service.answer_with_evidence(db, scope, request, retrieval.evidence)
    return {
        "operation": "compare" if "compare" in request.lower() else "summarize",
        "answer": response.answer,
        "findings": [
            {
                "text": response.answer,
                "evidence_quality": response.verification.status if response.verification else "unverified",
                "citations": [citation["index"] for citation in _citations(response)],
            }
        ],
        "citations": _citations(response),
        "verification": response.verification.to_dict() if response.verification else None,
        "evidence": _evidence_payload(response.evidence),
        "missing_information": [] if response.citations else ["Additional documents are required"],
        "contradictions": response.verification.conflicting_claims if response.verification else [],
        "reused_retrieval": reused,
        "trace_id": response.trace_id,
    }


def database_agent(
    db: Session,
    organization_id: uuid.UUID,
    source_id: str,
    request: str,
    sql: str | None = None,
    max_rows: int = 100,
    scope: RagScope | None = None,
) -> dict[str, Any]:
    context = _database_context(db, organization_id, source_id)
    generated: dict[str, Any] | None = None
    if not sql:
        generated = generate_sql(context, request)
        sql = generated["sql"]
    started = time.monotonic()
    result = execute_read_only_sql(context, sql, max_rows)
    documentation: dict[str, Any] | None = None
    if any(word in request.lower() for word in ("documentation", "definition", "policy", "meaning", "glossary")):
        documentation = retrieval_agent(
            db, organization_id, f"database definitions and documentation: {request}", scope=scope
        )
    return {
        **result,
        "sql": sql,
        "explanation": (generated or {}).get("explanation", "Executed the supplied validated read-only query"),
        "source_id": str(source_id),
        "execution_time_ms": int((time.monotonic() - started) * 1000),
        "documentation_context": documentation,
        "warnings": ["Results are bounded by the configured row limit"] if result["truncated"] else [],
    }


def _citations_from_inputs(inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: dict[str, dict[str, Any]] = {}
    for item in inputs or []:
        if not isinstance(item, dict):
            continue
        for citation in item.get("citations") or []:
            if isinstance(citation, dict) and citation.get("chunk_id"):
                citations.setdefault(str(citation["chunk_id"]), citation)
    return list(citations.values())


def analytics_agent(
    dataset: dict[str, Any],
    inputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = dataset.get("rows", [])
    columns = dataset.get("columns", [])
    numeric = {}
    for index, column in enumerate(columns):
        values = [row[index] for row in rows if isinstance(row[index], (int, float))]
        if values:
            numeric[column] = {
                "count": len(values),
                "sum": sum(values),
                "min": min(values),
                "max": max(values),
                "average": sum(values) / len(values),
            }
    labels = [str(row[0]) for row in rows] if rows and columns else []
    values = [row[1] for row in rows] if rows and len(columns) > 1 else []
    chart = {
        "type": "line" if labels and all(isinstance(value, (int, float)) for value in values) else "table",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": columns[1] if len(columns) > 1 else "value", "data": values}
            ],
        },
    }
    return {
        "metrics": numeric,
        "row_count": len(rows),
        "chart": chart,
        "method": "descriptive statistics over returned database rows",
        "source_id": dataset.get("source_id"),
        "sql": dataset.get("sql"),
        "citations": _citations_from_inputs(inputs or []),
        "evidence": _evidence_payload(_evidence_from_inputs(inputs or [])),
        "document_context_used": bool(inputs),
    }


def verification_agent(
    result: dict[str, Any],
    *,
    organization_id: uuid.UUID | str | None = None,
    inputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    citations = result.get("citations", []) or []
    evidence = _evidence_from_inputs(inputs or [])
    if not evidence and isinstance(result.get("evidence"), list):
        evidence = _evidence_from_inputs([{"evidence": result["evidence"]}])
    existing = result.get("verification")
    if isinstance(existing, dict):
        return {
            "status": existing.get("status", "insufficient_evidence"),
            "verified_claims": [
                claim.get("claim")
                for claim in existing.get("claims", [])
                if claim.get("status") in {"supported", "partially_supported"}
            ],
            "unsupported_claims": existing.get("unsupported_claims", []),
            "conflicting_claims": existing.get("conflicting_claims", []),
            "insufficient_claims": existing.get("insufficient_claims", []),
            "citation_errors": len(existing.get("citation_errors", [])),
            "evidence_coverage": existing.get("evidence_coverage", 0.0),
            "method": existing.get("method"),
            "disclaimer": existing.get("disclaimer"),
            "verification": existing,
        }
    answer = result.get("answer") or ""
    valid_citations = [item for item in citations if item.get("document_id") and item.get("chunk_id")]
    if organization_id is not None and answer and evidence:
        report = RagService().verify(answer, evidence, scope=_scope(organization_id))
        return {
            "status": report.status,
            "verified_claims": [
                claim.claim
                for claim in report.claims
                if claim.status in {"supported", "partially_supported"}
            ],
            "unsupported_claims": report.unsupported_claims,
            "conflicting_claims": report.conflicting_claims,
            "insufficient_claims": report.insufficient_claims,
            "citation_errors": len(report.citation_errors),
            "evidence_coverage": report.evidence_coverage,
            "method": report.method,
            "disclaimer": report.disclaimer,
            "verification": report.to_dict(),
        }
    unsupported = []
    if answer and not valid_citations and result.get("grounded") is not False:
        unsupported.append("Answer has no valid source citation")
    return {
        "status": "verified" if not unsupported else "needs_review",
        "verified_claims": [] if unsupported else ["Returned claims have source references"],
        "unsupported_claims": unsupported,
        "conflicting_claims": [],
        "insufficient_claims": [] if valid_citations else ["No evidence was available to verify"],
        "citation_errors": len(citations) - len(valid_citations),
        "evidence_coverage": 0.0,
        "method": "citation_presence_only",
        "disclaimer": "No evidence text was available; only citation presence was checked.",
    }


def research_agent(
    db: Session,
    organization_id: uuid.UUID,
    request: str,
    inputs: list[dict[str, Any]] | None = None,
    scope: RagScope | None = None,
) -> dict[str, Any]:
    scope = _effective_scope(organization_id, scope)
    service = RagService()
    prior = _evidence_from_inputs(inputs or [])
    if prior:
        response = service.answer_with_evidence(db, scope, request, prior)
        reused = True
    else:
        retrieval = service.retrieve(db, scope, request)
        reused = False
        response = service.answer_with_evidence(db, scope, request, retrieval.evidence)
    return {
        "question": request,
        "answer": response.answer,
        "findings": [
            {
                "text": response.answer,
                "source_type": "internal_knowledge",
                "citations": [citation["index"] for citation in _citations(response)],
            }
        ],
        "citations": _citations(response),
        "verification": response.verification.to_dict() if response.verification else None,
        "evidence": _evidence_payload(response.evidence),
        "external_research": {
            "status": "not_configured",
            "message": "No external research provider is configured; only internal knowledge was used.",
        },
        "missing_information": [] if response.citations else ["No sufficient internal evidence"],
        "contradictions": response.verification.conflicting_claims if response.verification else [],
        "reused_retrieval": reused,
        "trace_id": response.trace_id,
    }


def report_agent(
    organization_id: uuid.UUID,
    request: str,
    inputs: list[dict[str, Any]],
    execution_id: str,
) -> dict[str, Any]:
    citations: dict[str, dict[str, Any]] = {}
    findings: list[str] = []
    verification_status = "unverified"
    for index, item in enumerate(inputs, 1):
        findings.append(f"## Finding {index}\n{json.dumps(item, ensure_ascii=False, default=str)}")
        for citation in item.get("citations", []) if isinstance(item, dict) else []:
            if isinstance(citation, dict) and citation.get("chunk_id"):
                citations[citation["chunk_id"]] = citation
        if isinstance(item, dict) and isinstance(item.get("verification"), dict):
            verification_status = item["verification"].get("status", verification_status)
    lines = [
        "# NEXUS AI Report",
        "",
        f"Request: {request}",
        f"Verification status: {verification_status}",
        "",
        *findings,
    ]
    if citations:
        lines.extend(["", "## Sources"])
        for citation in citations.values():
            title = citation.get("document_title") or citation.get("document_filename")
            page = citation.get("page_number")
            lines.append(
                f"- [{citation.get('index')}] {title}"
                + (f" (p. {page})" if page else "")
                + f" — chunk {citation.get('chunk_id')}"
            )
    content = "\n".join(lines).encode("utf-8")
    key = f"orgs/{organization_id}/reports/{execution_id}.md"
    stored_key = get_storage_backend().put_bytes(key, content, "text/markdown")
    return {
        "format": "markdown",
        "storage_key": stored_key,
        "preview": content.decode("utf-8"),
        "citations": list(citations.values()),
        "verification_status": verification_status,
    }


def email_agent(
    request: str,
    *,
    db: Session | None = None,
    organization_id: uuid.UUID | None = None,
    source_id: str | None = None,
) -> dict[str, Any]:
    if db is not None and organization_id is not None and source_id:
        try:
            result = search_email(db, organization_id, uuid.UUID(str(source_id)), request, 20)
            knowledge = None
            try:
                retrieval = RagService().retrieve(
                    db, _scope(organization_id), request, top_k=5
                )
                knowledge = {
                    "citations": _evidence_payload(retrieval.evidence),
                    "evidence": _evidence_payload(retrieval.evidence),
                }
            except Exception as exc:  # noqa: BLE001 — email results remain usable without docs
                knowledge = {"citations": [], "evidence": [], "error": str(exc)[:200]}
            return {
                "available": True,
                "status": "succeeded",
                "request": request,
                "count": result["count"],
                "messages": result["messages"],
                "citations": (knowledge or {}).get("citations", []),
                "evidence": (knowledge or {}).get("evidence", []),
                "knowledge_context": knowledge,
            }
        except (ConnectorError, ValueError) as exc:
            return {
                "available": False,
                "status": "failed",
                "request": request,
                "message": str(exc)[:300],
                "messages": [],
                "citations": [],
            }
    return {
        "available": False,
        "status": "unavailable",
        "message": "No authorized email connector is configured; no email results were generated.",
        "request": request,
        "messages": [],
        "citations": [],
    }


def workflow_agent(
    db: Session,
    organization_id: uuid.UUID,
    request: str,
    source_ids: list[str],
    prior_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Correlate authorized source capabilities without fabricating evidence."""
    sources = []
    evidence = list(prior_results)
    for raw_id in source_ids:
        source = db.get(DataSource, uuid.UUID(str(raw_id)))
        if source is None or source.organization_id != organization_id:
            sources.append({"source_id": str(raw_id), "status": "unavailable", "reason": "not found or not permitted"})
            continue
        if source.status != "active":
            sources.append(
                {
                    "source_id": str(source.id),
                    "type": source.type,
                    "status": "unavailable",
                    "reason": source.last_error or "source is not active",
                }
            )
            continue
        if source.type == "email":
            try:
                result = search_email(db, organization_id, source.id, request, 20)
                evidence.append({"source_id": str(source.id), "type": "email", "messages": result["messages"]})
                sources.append({"source_id": str(source.id), "type": "email", "status": "succeeded", "count": result["count"]})
            except ConnectorError as exc:
                sources.append({"source_id": str(source.id), "type": "email", "status": "failed", "reason": str(exc)})
        elif source.type in {"postgres", "mysql"}:
            sources.append(
                {
                    "source_id": str(source.id),
                    "type": source.type,
                    "status": "available",
                    "note": "Database requires a safe SQL plan or configured LLM generation",
                }
            )
        else:
            sources.append(
                {
                    "source_id": str(source.id),
                    "type": source.type,
                    "status": "available",
                    "note": "Indexed content is searched through the retrieval step",
                }
            )
    category = (
        "contract"
        if "contract" in request.casefold() or "obligation" in request.casefold()
        else ("organization" if "organization" in request.casefold() or "organizational" in request.casefold() else "project")
    )
    return {
        "workflow": category,
        "request": request,
        "source_status": sources,
        "evidence": evidence,
        "limitations": [item for item in sources if item["status"] in {"unavailable", "failed"}],
        "grounded": bool(evidence),
    }


def execute_specialist(
    db: Session,
    organization_id: uuid.UUID,
    agent_id: str,
    request: str,
    source_id: str | None = None,
    sql: str | None = None,
    max_rows: int = 100,
    inputs: list[dict[str, Any]] | None = None,
    execution_id: str | None = None,
    source_ids: list[str] | None = None,
    scope: RagScope | None = None,
) -> dict[str, Any]:
    if agent_id == "retrieval":
        return retrieval_agent(db, organization_id, request, scope)
    if agent_id == "document":
        return document_agent(db, organization_id, request, inputs, scope)
    if agent_id == "database":
        if not source_id:
            raise ConnectorError("source_id is required for database intelligence")
        return database_agent(db, organization_id, source_id, request, sql, max_rows, scope)
    if agent_id == "analytics":
        return analytics_agent((inputs or [{}])[-1], inputs)
    if agent_id == "verification":
        return verification_agent(
            (inputs or [{}])[-1], organization_id=organization_id, inputs=inputs
        )
    if agent_id == "research":
        return research_agent(db, organization_id, request, inputs, scope)
    if agent_id == "report":
        if not execution_id:
            raise ValueError("execution_id is required for report generation")
        return report_agent(organization_id, request, inputs or [], execution_id)
    if agent_id == "email":
        return email_agent(request, db=db, organization_id=organization_id, source_id=source_id)
    if agent_id == "workflow":
        return workflow_agent(db, organization_id, request, source_ids or [], inputs or [])
    raise ValueError(f"Unsupported specialist agent: {agent_id}")
