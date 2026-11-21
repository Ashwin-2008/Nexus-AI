"""Supervisor execution service with durable state and explicit tool boundaries."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.agents.registry import route_request
from app.core.config import settings
from app.models.agent import AgentExecution, AgentExecutionEvent, AgentExecutionStep
from app.models.connector import DataSource
from app.models.user import AuditLog, User
from app.rag.security import scope_from_user
from app.services.connectors import ConnectorContext, ConnectorError, parse_config
from app.services.credentials import CredentialError, decrypt_credentials
from app.services.safe_sql import execute_read_only_sql
from app.services.specialists import execute_specialist


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _plan(request: str, source_id: str | None, sql: str | None, source_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "agent": "supervisor",
        "source_id": source_id,
        "source_ids": source_ids or ([source_id] if source_id else []),
        "sql": sql,
        "steps": route_request(request, bool(sql), bool(source_id)),
    }


def create_execution(
    db: Session,
    user: User,
    request: str,
    source_id: str | None = None,
    sql: str | None = None,
    source_ids: list[str] | None = None,
) -> AgentExecution:
    execution = AgentExecution(
        organization_id=user.organization_id,
        user_id=user.id,
        request=request,
        plan=json.dumps(_plan(request, source_id, sql, source_ids)),
        status="queued",
    )
    db.add(execution)
    db.flush()
    for spec in json.loads(execution.plan)["steps"]:
        db.add(
            AgentExecutionStep(
                execution_id=execution.id,
                agent_id=spec["agent_id"],
                step_key=spec["key"],
                description=spec["description"],
                dependencies=json.dumps(spec.get("dependencies", [])),
            )
        )
    db.add(AgentExecutionEvent(execution_id=execution.id, event_type="execution.queued", payload=execution.plan))
    db.commit()
    db.refresh(execution)
    return execution


def _event(db: Session, execution: AgentExecution, event_type: str, step: AgentExecutionStep | None = None, payload: dict | None = None) -> None:
    db.add(
        AgentExecutionEvent(
            execution_id=execution.id,
            step_id=step.id if step else None,
            event_type=event_type,
            payload=json.dumps(payload or {}, ensure_ascii=False, default=str),
        )
    )


def _merge_execution_result(
    result: dict[str, Any], step_results: list[dict[str, Any]]
) -> dict[str, Any]:
    """Merge evidence/citations produced by multiple specialists without duplicates."""
    merged = dict(result) if isinstance(result, dict) else {}
    citations: dict[str, dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    verification = merged.get("verification") if isinstance(merged.get("verification"), dict) else None
    warnings: list[str] = list(merged.get("warnings") or [])
    for item in step_results:
        if not isinstance(item, dict):
            continue
        for citation in item.get("citations") or []:
            if not isinstance(citation, dict):
                continue
            key = str(citation.get("chunk_id") or citation.get("citation_id") or citation.get("index"))
            citations.setdefault(key, citation)
        for chunk in item.get("evidence") or []:
            if not isinstance(chunk, dict):
                continue
            key = str(chunk.get("chunk_id") or chunk.get("text", "")[:64])
            evidence.setdefault(key, chunk)
        if verification is None and isinstance(item.get("verification"), dict):
            verification = item["verification"]
        for warning in item.get("warnings") or []:
            if warning not in warnings:
                warnings.append(warning)
        if not merged.get("answer") and item.get("answer"):
            merged["answer"] = item["answer"]
        if item.get("insufficient_evidence") is True:
            merged["insufficient_evidence"] = True
    if citations:
        ordered = sorted(
            citations.values(),
            key=lambda citation: (
                citation.get("index") if isinstance(citation.get("index"), int) else 9999
            ),
        )
        merged["citations"] = ordered
    if evidence:
        merged["evidence"] = list(evidence.values())
    if verification is not None:
        merged["verification"] = verification
        merged["verification_status"] = verification.get("status")
    if warnings:
        merged["warnings"] = warnings
    return merged


def run_execution(
    db: Session,
    user: User,
    request: str,
    source_id: str | None = None,
    sql: str | None = None,
    max_rows: int = 100,
    execution: AgentExecution | None = None,
    task_id: str | None = None,
    source_ids: list[str] | None = None,
) -> AgentExecution:
    if execution is None:
        execution = create_execution(db, user, request, source_id, sql)
    else:
        plan = json.loads(execution.plan or "{}")
        source_id = source_id or plan.get("source_id")
        source_ids = source_ids or plan.get("source_ids", [])
        sql = sql or plan.get("sql")
    locked = (
        db.query(AgentExecution)
        .filter(AgentExecution.id == execution.id)
        .with_for_update()
        .one()
    )
    if locked.status in {"succeeded", "failed", "cancelled"}:
        return locked
    if (
        locked.status == "running"
        and locked.claimed_at
        and _now() - locked.claimed_at < timedelta(seconds=settings.agent_execution_recovery_seconds)
    ):
        return locked
    execution = locked
    scope = scope_from_user(user)
    if execution.status == "running":
        for stale_step in db.query(AgentExecutionStep).filter(
            AgentExecutionStep.execution_id == execution.id,
            AgentExecutionStep.status == "running",
        ):
            stale_step.status = "pending"
            stale_step.claimed_at = None
        _event(db, execution, "execution.recovered", payload={"retry_count": execution.retry_count})
    execution.status = "running"
    execution.task_id = task_id or execution.task_id
    execution.claimed_at = _now()
    execution.started_at = execution.started_at or _now()
    _event(db, execution, "execution.started")
    db.commit()
    steps = db.query(AgentExecutionStep).filter(AgentExecutionStep.execution_id == execution.id).order_by(AgentExecutionStep.id).all()
    plan_order = {
        item.get("key"): index
        for index, item in enumerate(json.loads(execution.plan or "{}").get("steps", []))
    }
    steps.sort(key=lambda item: plan_order.get(item.step_key, len(plan_order)))
    try:
        for step in steps:
            if step.status == "completed":
                continue
            step.status = "running"
            step.started_at = _now()
            step.claimed_at = _now()
            step.input_summary = request[:500]
            _event(db, execution, "step.started", step, {"agent_id": step.agent_id})
            db.commit()
        if sql:
            if not source_id:
                raise ConnectorError("source_id is required for database queries")
            source = db.get(DataSource, source_id)
            if source is None or source.organization_id != user.organization_id or source.type not in {"postgres", "mysql"}:
                raise ConnectorError("Database source not found or not permitted")
            context = ConnectorContext(
                config={**parse_config(source.config), "type": source.type},
                credentials=decrypt_credentials(source.credentials_encrypted),
            )
            database_result = execute_read_only_sql(context, sql, max_rows)
            result = {"database": database_result}
            step_results = [database_result]
            execution.agent_type = "database"
            for step in steps:
                if step.agent_id == "database":
                    step.output_summary = json.dumps({"row_count": database_result["row_count"]})
                    step.status = "completed"
                    step.finished_at = _now()
                    step.claimed_at = None
                elif step.agent_id == "analytics":
                    specialist_result = execute_specialist(
                        db,
                        user.organization_id,
                        "analytics",
                        request,
                        inputs=step_results,
                        execution_id=str(execution.id),
                        scope=scope,
                    )
                    step.output_summary = json.dumps(specialist_result, ensure_ascii=False, default=str)[:10000]
                    step.status = "completed"
                    step.finished_at = _now()
                    step.claimed_at = None
                    step_results.append(specialist_result)
                    result["analytics"] = specialist_result
                elif step.agent_id == "verification":
                    specialist_result = execute_specialist(
                        db,
                        user.organization_id,
                        "verification",
                        request,
                        inputs=step_results,
                        execution_id=str(execution.id),
                        scope=scope,
                    )
                    step.output_summary = json.dumps(specialist_result, ensure_ascii=False, default=str)[:10000]
                    step.status = "completed"
                    step.finished_at = _now()
                    step.claimed_at = None
                    step_results.append(specialist_result)
                    result["verification"] = specialist_result
        else:
            step_results: list[dict[str, Any]] = []
            result: dict[str, Any] = {}
            execution.agent_type = steps[0].agent_id if steps else "supervisor"
            for step in steps:
                if step.agent_id in {"analytics", "verification"} and not step_results:
                    step.status = "skipped"
                    step.output_summary = json.dumps({"reason": "No specialist dataset was available"})
                    step.finished_at = _now()
                    continue
                specialist_result = execute_specialist(
                    db,
                    user.organization_id,
                    step.agent_id,
                    request,
                    source_id,
                    sql,
                    max_rows,
                    step_results,
                    str(execution.id),
                    source_ids,
                    scope,
                )
                step_results.append(specialist_result)
                step.output_summary = json.dumps(specialist_result, ensure_ascii=False, default=str)[:10000]
                step.status = "completed"
                step.finished_at = _now()
                step.claimed_at = None
                result = specialist_result if step.agent_id in {"retrieval", "document", "research", "report"} else {"specialists": step_results}
        for step in steps:
            if step.status == "running":
                step.status = "completed"
                step.finished_at = _now()
            step.claimed_at = None
            _event(db, execution, "step.completed", step, {"status": step.status})
        result = _merge_execution_result(result, step_results)
        execution.result = json.dumps(result, ensure_ascii=False, default=str)
        execution.status = "succeeded"
        execution.finished_at = _now()
        execution.claimed_at = None
        _event(db, execution, "execution.completed", payload={"agent_type": execution.agent_type})
        db.add(
            AuditLog(
                organization_id=user.organization_id,
                user_id=user.id,
                action="agent_execution_succeeded",
                resource_type="agent_execution",
                resource_id=str(execution.id),
                details=json.dumps({"agent_type": execution.agent_type}),
            )
        )
    except (ConnectorError, CredentialError, ValueError) as exc:
        for step in steps:
            if step.status == "running":
                step.status = "failed"
                step.error = str(exc)[:500]
                step.finished_at = _now()
                _event(db, execution, "step.failed", step, {"error": str(exc)[:500]})
        execution.status = "failed"
        execution.error = str(exc)[:1000]
        execution.finished_at = _now()
        execution.claimed_at = None
        _event(db, execution, "execution.failed", payload={"error": str(exc)[:500]})
        db.add(
            AuditLog(
                organization_id=user.organization_id,
                user_id=user.id,
                action="agent_execution_failed",
                resource_type="agent_execution",
                resource_id=str(execution.id),
                details=json.dumps({"error": str(exc)[:500]}),
            )
        )
    db.commit()
    db.refresh(execution)
    return execution
