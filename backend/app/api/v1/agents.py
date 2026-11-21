from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.agent import AgentApprovalRequest, AgentExecution, AgentExecutionEvent, AgentExecutionStep
from app.models.user import AuditLog, User
from app.services.agent_service import create_execution as create_agent_execution, run_execution
from app.services.connectors import ConnectorContext, ConnectorError, parse_config
from app.services.credentials import decrypt_credentials
from app.services.safe_sql import validate_read_only_sql
from app.services.llm import LLMError
from app.services.sql_intelligence import generate_sql, schema_context
from app.services.intelligence import send_email

router = APIRouter(prefix="/agents", tags=["agents"])


class ExecutionCreate(BaseModel):
    request: str = Field(..., min_length=1, max_length=8000)
    source_id: uuid.UUID | None = None
    source_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    sql: str | None = Field(None, max_length=10000)
    max_rows: int = Field(100, ge=1, le=1000)
    background: bool = False


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_type: str
    status: str
    request: str
    plan: dict
    result: dict | None
    error: str | None
    created_at: object
    started_at: object | None
    finished_at: object | None


class StepRead(BaseModel):
    id: uuid.UUID
    agent_id: str
    step_key: str
    status: str
    description: str
    output_summary: dict | None
    error: str | None
    started_at: object | None
    finished_at: object | None


class EventRead(BaseModel):
    id: uuid.UUID
    step_id: uuid.UUID | None
    event_type: str
    payload: dict
    created_at: object


class ApprovalCreate(BaseModel):
    execution_id: uuid.UUID
    step_id: uuid.UUID | None = None
    agent_id: str = Field(..., max_length=64)
    action: str = Field(..., max_length=128)
    action_summary: str = Field(..., min_length=1, max_length=2000)
    risk_level: str = Field("high", pattern="^(low|medium|high|critical)$")
    requested_permissions: list[str] = []


class ApprovalDecision(BaseModel):
    rejection_reason: str | None = Field(None, max_length=1000)


class ApprovalRead(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    step_id: uuid.UUID | None
    agent_id: str
    action: str
    action_summary: str
    risk_level: str
    requested_permissions: list[str]
    status: str
    rejection_reason: str | None
    requested_at: object
    decided_at: object | None
    expires_at: object | None


class SqlRequest(BaseModel):
    source_id: uuid.UUID
    question: str = Field(..., min_length=1, max_length=4000)


class SqlValidateRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=10000)
    max_rows: int = Field(100, ge=1, le=1000)


def _read(execution: AgentExecution) -> ExecutionRead:
    def decode(value: str | None, default):
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default

    return ExecutionRead(
        id=execution.id,
        agent_type=execution.agent_type,
        status=execution.status,
        request=execution.request,
        plan=decode(execution.plan, {}),
        result=decode(execution.result, None),
        error=execution.error,
        created_at=execution.created_at,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
    )


def _decode(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _approval_read(row: AgentApprovalRequest) -> ApprovalRead:
    return ApprovalRead(
        id=row.id,
        execution_id=row.execution_id,
        step_id=row.step_id,
        agent_id=row.agent_id,
        action=row.action,
        action_summary=row.action_summary,
        risk_level=row.risk_level,
        requested_permissions=_decode(row.requested_permissions, []),
        status=row.status,
        rejection_reason=row.rejection_reason,
        requested_at=row.requested_at,
        decided_at=row.decided_at,
        expires_at=row.expires_at,
    )


@router.post("/executions", response_model=ExecutionRead, status_code=201)
def create_execution(
    body: ExecutionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.background:
        source_ids = [str(source_id) for source_id in body.source_ids]
        if body.source_id and str(body.source_id) not in source_ids:
            source_ids.insert(0, str(body.source_id))
        execution = create_agent_execution(db, current_user, body.request, str(body.source_id) if body.source_id else None, body.sql, source_ids)
        from app.worker.tasks import enqueue_agent_execution

        task_id = enqueue_agent_execution(str(execution.id))
        if task_id is None:
            execution = run_execution(
                db,
                current_user,
                body.request,
                str(body.source_id) if body.source_id else None,
                body.sql,
                body.max_rows,
                execution=execution,
                source_ids=source_ids,
            )
        else:
            execution.status = "queued"
            db.commit()
    else:
        source_ids = [str(source_id) for source_id in body.source_ids]
        if body.source_id and str(body.source_id) not in source_ids:
            source_ids.insert(0, str(body.source_id))
        execution = run_execution(
            db,
            current_user,
            body.request,
            str(body.source_id) if body.source_id else None,
            body.sql,
            body.max_rows,
            source_ids=source_ids,
        )
    if execution.status == "failed":
        raise HTTPException(status_code=400, detail={"code": "execution_failed", "message": execution.error})
    return _read(execution)


@router.get("/executions", response_model=list[ExecutionRead])
def list_executions(
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AgentExecution)
        .filter(
            AgentExecution.organization_id == current_user.organization_id,
            AgentExecution.user_id == current_user.id,
        )
        .order_by(AgentExecution.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_read(row) for row in rows]


@router.get("/executions/{execution_id}", response_model=ExecutionRead)
def get_execution(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(AgentExecution, execution_id)
    if row is None or row.organization_id != current_user.organization_id or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Execution not found"})
    return _read(row)


@router.get("/catalog")
def agent_catalog():
    from app.agents.registry import list_agents

    return [
        {
            "id": item.agent_id,
            "name": item.name,
            "description": item.description,
            "capabilities": sorted(item.capabilities),
            "required_permissions": sorted(item.required_permissions),
            "tools": list(item.tools),
        }
        for item in list_agents()
    ]


def _database_context(source_id: uuid.UUID, current_user: User, db: Session) -> ConnectorContext:
    from app.models.connector import DataSource

    source = db.get(DataSource, source_id)
    if source is None or source.organization_id != current_user.organization_id or source.type not in {"postgres", "mysql"}:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Database source not found"})
    return ConnectorContext(
        config={**parse_config(source.config), "type": source.type},
        credentials=decrypt_credentials(source.credentials_encrypted),
    )


@router.post("/sql/schema")
def sql_schema(source_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return schema_context(_database_context(source_id, current_user, db))
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail={"code": "schema_discovery_failed", "message": str(exc)}) from exc


@router.post("/sql/validate")
def sql_validate(body: SqlValidateRequest, current_user: User = Depends(get_current_user)):
    try:
        return {"valid": True, "sql": validate_read_only_sql(body.sql, body.max_rows)}
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail={"code": "unsafe_sql", "message": str(exc)}) from exc


@router.post("/sql/generate")
def sql_generate(body: SqlRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return generate_sql(_database_context(body.source_id, current_user, db), body.question)
    except (ConnectorError, LLMError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "sql_generation_failed", "message": str(exc)}) from exc


@router.get("/executions/{execution_id}/steps", response_model=list[StepRead])
def list_steps(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    execution = db.get(AgentExecution, execution_id)
    if execution is None or execution.organization_id != current_user.organization_id or execution.user_id != current_user.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Execution not found"})
    rows = db.query(AgentExecutionStep).filter(AgentExecutionStep.execution_id == execution.id).all()
    return [
        StepRead(
            id=row.id,
            agent_id=row.agent_id,
            step_key=row.step_key,
            status=row.status,
            description=row.description,
            output_summary=_decode(row.output_summary, None),
            error=row.error,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )
        for row in rows
    ]


@router.get("/executions/{execution_id}/events", response_model=list[EventRead])
def list_events(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    execution = db.get(AgentExecution, execution_id)
    if execution is None or execution.organization_id != current_user.organization_id or execution.user_id != current_user.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Execution not found"})
    rows = db.query(AgentExecutionEvent).filter(AgentExecutionEvent.execution_id == execution.id).order_by(AgentExecutionEvent.created_at).all()
    return [
        EventRead(id=row.id, step_id=row.step_id, event_type=row.event_type, payload=_decode(row.payload, {}), created_at=row.created_at)
        for row in rows
    ]


@router.post("/approvals", response_model=ApprovalRead, status_code=201)
def create_approval(
    body: ApprovalCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    execution = db.get(AgentExecution, body.execution_id)
    if execution is None or execution.organization_id != current_user.organization_id or execution.user_id != current_user.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Execution not found"})
    row = AgentApprovalRequest(
        execution_id=execution.id,
        step_id=body.step_id,
        organization_id=current_user.organization_id,
        requested_by=current_user.id,
        agent_id=body.agent_id,
        action=body.action,
        action_summary=body.action_summary,
        risk_level=body.risk_level,
        requested_permissions=json.dumps(body.requested_permissions),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.agent_approval_expiry_hours),
    )
    execution.status = "waiting_for_approval"
    db.add(row)
    db.add(AgentExecutionEvent(execution_id=execution.id, step_id=body.step_id, event_type="approval.required", payload=body.action_summary))
    db.commit()
    db.refresh(row)
    return _approval_read(row)


@router.get("/approvals", response_model=list[ApprovalRead])
def list_approvals(
    pending_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(AgentApprovalRequest).filter(AgentApprovalRequest.organization_id == current_user.organization_id)
    if pending_only:
        query = query.filter(AgentApprovalRequest.status == "pending")
    return [_approval_read(row) for row in query.order_by(AgentApprovalRequest.requested_at.desc()).limit(100).all()]


def _decide_approval(
    approval_id: uuid.UUID,
    approved: bool,
    body: ApprovalDecision,
    current_user: User,
    db: Session,
) -> ApprovalRead:
    row = db.get(AgentApprovalRequest, approval_id)
    if row is None or row.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Approval not found"})
    now = datetime.now(timezone.utc)
    if row.status == "pending" and row.expires_at and row.expires_at <= now:
        row.status = "expired"
        row.decided_at = now
        execution = db.get(AgentExecution, row.execution_id)
        if execution and execution.status == "waiting_for_approval":
            execution.status = "failed"
            execution.error = "Approval expired"
            execution.finished_at = now
        db.commit()
    if row.status != "pending":
        raise HTTPException(status_code=409, detail={"code": "already_decided", "message": "Approval is no longer pending"})
    if row.requested_by == current_user.id and current_user.role.name != "admin":
        raise HTTPException(status_code=403, detail={"code": "self_approval_denied", "message": "The requester cannot approve this action"})
    row.status = "approved" if approved else "rejected"
    row.approver_id = current_user.id
    row.rejection_reason = body.rejection_reason if not approved else None
    row.decided_at = datetime.now(timezone.utc)
    execution = db.get(AgentExecution, row.execution_id)
    if execution:
        execution.status = "queued" if approved else "failed"
        if not approved:
            execution.error = row.rejection_reason or "Approval rejected"
            execution.finished_at = row.decided_at
        db.add(AgentExecutionEvent(execution_id=execution.id, step_id=row.step_id, event_type=f"approval.{row.status}", payload=json.dumps({"approval_id": str(row.id)})))
    db.add(AuditLog(organization_id=row.organization_id, user_id=current_user.id, action=f"approval_{row.status}", resource_type="approval", resource_id=str(row.id)))
    db.commit()
    email_sent = False
    if approved and row.action == "email.send" and execution:
        try:
            payload = json.loads(row.action_summary)
            result = send_email(
                db,
                row.organization_id,
                uuid.UUID(str(payload["source_id"])),
                payload["recipients"],
                payload["subject"],
                payload["body"],
                payload.get("attachments", []),
            )
            row.result = json.dumps(result, ensure_ascii=False)
            execution.status = "succeeded"
            execution.result = json.dumps(result, ensure_ascii=False)
            execution.finished_at = row.decided_at
            db.add(AgentExecutionEvent(execution_id=execution.id, event_type="email.sent", payload=json.dumps(result)))
            db.add(AuditLog(organization_id=row.organization_id, user_id=current_user.id, action="email_sent", resource_type="agent_execution", resource_id=str(execution.id)))
            db.commit()
            email_sent = True
        except (ConnectorError, KeyError, ValueError, json.JSONDecodeError) as exc:
            execution.status = "failed"
            execution.error = str(exc)[:1000]
            execution.finished_at = row.decided_at
            row.result = json.dumps({"status": "failed", "error": str(exc)[:500]})
            db.add(AgentExecutionEvent(execution_id=execution.id, event_type="email.failed", payload=json.dumps({"error": str(exc)[:500]})))
            db.commit()
    if approved and execution:
        if email_sent:
            db.refresh(row)
            return _approval_read(row)
        from app.worker.tasks import enqueue_agent_execution

        task_id = enqueue_agent_execution(str(execution.id))
        if task_id:
            execution.task_id = task_id
            db.commit()
        else:
            owner = db.get(User, execution.user_id)
            if owner:
                run_execution(db, owner, execution.request, execution=execution, task_id=None)
    db.refresh(row)
    return _approval_read(row)


@router.post("/executions/{execution_id}/cancel", response_model=ExecutionRead)
def cancel_execution(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(AgentExecution, execution_id)
    if row is None or row.organization_id != current_user.organization_id or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Execution not found"})
    if row.status in {"succeeded", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail={"code": "not_cancellable", "message": "Execution is already final"})
    row.status = "cancelled"
    row.error = "Cancelled by user"
    row.finished_at = datetime.now(timezone.utc)
    db.query(AgentExecutionStep).filter(
        AgentExecutionStep.execution_id == row.id,
        AgentExecutionStep.status.in_(["pending", "running"]),
    ).update({"status": "cancelled", "error": "Execution cancelled"}, synchronize_session=False)
    db.add(AgentExecutionEvent(execution_id=row.id, event_type="execution.cancelled", payload=json.dumps({"user_id": str(current_user.id)})))
    db.add(AuditLog(organization_id=row.organization_id, user_id=current_user.id, action="agent_execution_cancelled", resource_type="agent_execution", resource_id=str(row.id)))
    db.commit()
    db.refresh(row)
    return _read(row)


@router.post("/executions/{execution_id}/retry", response_model=ExecutionRead)
def retry_execution(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(AgentExecution, execution_id)
    if row is None or row.organization_id != current_user.organization_id or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Execution not found"})
    if row.status != "failed" or row.retry_count >= settings.agent_max_retries:
        raise HTTPException(status_code=409, detail={"code": "not_retryable", "message": "Execution is not eligible for retry"})
    for step in db.query(AgentExecutionStep).filter(AgentExecutionStep.execution_id == row.id).all():
        if step.status in {"failed", "cancelled"}:
            step.status = "pending"
            step.error = None
            step.last_error = None
            step.finished_at = None
            step.claimed_at = None
    row.status = "queued"
    row.error = None
    row.finished_at = None
    row.retry_count += 1
    db.add(AgentExecutionEvent(execution_id=row.id, event_type="execution.retry_requested", payload=json.dumps({"retry_count": row.retry_count})))
    db.commit()
    result = run_execution(db, current_user, row.request, execution=row)
    if result.status == "failed":
        raise HTTPException(status_code=400, detail={"code": "execution_failed", "message": result.error})
    return _read(result)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRead)
def approve_approval(approval_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _decide_approval(approval_id, True, ApprovalDecision(), current_user, db)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRead)
def reject_approval(approval_id: uuid.UUID, body: ApprovalDecision, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _decide_approval(approval_id, False, body, current_user, db)
