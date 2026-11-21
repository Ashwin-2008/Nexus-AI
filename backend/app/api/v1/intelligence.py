from __future__ import annotations

import json
import uuid
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.connector import DataSource
from app.models.agent import AgentApprovalRequest, AgentExecution, AgentExecutionEvent
from app.models.report import Report
from app.models.user import AuditLog, User
from app.services.connectors import ConnectorError
from app.services.intelligence import compare_documents, export_report, extract_document, search_email
from app.services.storage import StorageError, get_storage_backend

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


class EmailSearchRequest(BaseModel):
    source_id: uuid.UUID
    query: str = Field("", max_length=4000)
    max_items: int = Field(20, ge=1, le=100)


class EmailDraftRequest(BaseModel):
    source_id: uuid.UUID
    recipients: list[str] = Field(..., min_length=1, max_length=50)
    subject: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1, max_length=100000)
    attachments: list[dict[str, str]] = Field(default_factory=list, max_length=10)


class DocumentCompareRequest(BaseModel):
    document_ids: list[uuid.UUID] = Field(..., min_length=2, max_length=20)


class ReportExportRequest(BaseModel):
    report_id: str = Field(..., min_length=1, max_length=128)
    report: dict
    format: str = Field(..., pattern="^(pdf|docx|xlsx|csv)$")


@router.post("/email/search")
def email_search(body: EmailSearchRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return search_email(db, current_user.organization_id, body.source_id, body.query, body.max_items)
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail={"code": "email_search_failed", "message": str(exc)}) from exc


@router.post("/email/draft", status_code=201)
def email_draft(body: EmailDraftRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    source = db.get(DataSource, body.source_id)
    if source is None or source.organization_id != current_user.organization_id or source.type != "email":
        raise HTTPException(status_code=404, detail={"code": "email_source_not_found", "message": "Email source not found"})
    execution = AgentExecution(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        agent_type="email",
        status="waiting_for_approval",
        request=f"Send email: {body.subject}",
        plan=json.dumps({"agent": "email", "action": "email.send"}),
    )
    db.add(execution)
    db.flush()
    summary = json.dumps(body.model_dump(mode="json"), ensure_ascii=False)
    approval = AgentApprovalRequest(
        execution_id=execution.id,
        organization_id=current_user.organization_id,
        requested_by=current_user.id,
        agent_id="email",
        action="email.send",
        action_summary=summary,
        risk_level="high",
        requested_permissions=json.dumps(["connector.email.send"]),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.agent_approval_expiry_hours),
    )
    db.add(approval)
    db.add(AgentExecutionEvent(execution_id=execution.id, event_type="approval.required", payload=json.dumps({"action": "email.send"})))
    db.add(AuditLog(organization_id=current_user.organization_id, user_id=current_user.id, action="email_draft_created", resource_type="agent_execution", resource_id=str(execution.id)))
    db.commit()
    db.refresh(approval)
    return {"execution_id": execution.id, "approval_id": approval.id, "status": "waiting_for_approval", "recipients": body.recipients, "subject": body.subject}


@router.get("/documents/{document_id}/extract")
def document_extract(document_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return extract_document(db, current_user.organization_id, document_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=404, detail={"code": "document_not_found", "message": str(exc)}) from exc


@router.post("/documents/compare")
def document_compare(body: DocumentCompareRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return compare_documents(db, current_user.organization_id, body.document_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "document_compare_failed", "message": str(exc)}) from exc


@router.post("/reports/export")
def report_export(body: ReportExportRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        result = export_report(current_user.organization_id, body.report_id, body.report, body.format)
        record = Report(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            title=str(body.report.get("title") or body.report_id),
            report_type=str(body.report.get("type") or "generated"),
            file_format=body.format,
            status="completed",
            storage_key=result["storage_key"],
        )
        db.add(record)
        db.commit()
        return {**result, "report_metadata_id": str(record.id)}
    except (ValueError, OSError, ImportError) as exc:
        raise HTTPException(status_code=400, detail={"code": "report_export_failed", "message": str(exc)}) from exc


@router.get("/reports")
def list_reports(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Report).filter(Report.organization_id == current_user.organization_id).order_by(Report.created_at.desc()).limit(100).all()


@router.get("/reports/{report_id}")
def report_download(
    report_id: str,
    format: str,
    current_user: User = Depends(get_current_user),
):
    if format not in {"pdf", "docx", "xlsx", "csv"} or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", report_id):
        raise HTTPException(status_code=400, detail={"code": "invalid_report", "message": "Invalid report identifier or format"})
    try:
        content = get_storage_backend().get_bytes(f"orgs/{current_user.organization_id}/reports/{report_id}.{format}")
    except StorageError as exc:
        raise HTTPException(status_code=404, detail={"code": "report_not_found", "message": "Report export not found"}) from exc
    content_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
    }
    return Response(
        content=content,
        media_type=content_types[format],
        headers={"Content-Disposition": f'attachment; filename="{report_id}.{format}"'},
    )
