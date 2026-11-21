"""Read-only administration endpoints for the organization UI.

Only organization administrators can access these routes. Mutating user
management is intentionally not exposed here; the UI uses this surface for
truthful organization visibility instead of placeholder data.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.agent import AgentExecution
from app.models.chat import Conversation
from app.models.connector import DataSource
from app.models.document import Document, DocumentChunk
from app.models.rag import RagEvaluationRun, RagQueryLog
from app.models.report import Report
from app.models.user import AuditLog, Organization, User

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(user: User) -> None:
    role = user.role.name if getattr(user, "role", None) else "member"
    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Administrator role required"},
        )


def _org_counts(db: Session, organization_id: uuid.UUID) -> dict[str, int]:
    def count(model, *conditions) -> int:
        query = db.query(func.count(model.id)).filter(model.organization_id == organization_id)
        if conditions:
            query = query.filter(*conditions)
        return int(query.scalar() or 0)

    return {
        "users": count(User),
        "active_users": count(User, User.is_active.is_(True)),
        "documents": count(Document),
        "completed_documents": count(Document, Document.status == "completed"),
        "chunks": count(DocumentChunk),
        "sources": count(DataSource),
        "conversations": count(Conversation),
        "agent_executions": count(AgentExecution),
        "reports": count(Report),
        "rag_queries": count(RagQueryLog),
        "evaluations": count(RagEvaluationRun),
    }


@router.get("/overview")
def admin_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    organization = db.get(Organization, current_user.organization_id)
    return {
        "organization": {
            "id": str(current_user.organization_id),
            "name": organization.name if organization else None,
        },
        "counts": _org_counts(db, current_user.organization_id),
        "role": current_user.role.name if current_user.role else None,
    }


@router.get("/users")
def admin_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    rows = (
        db.query(User)
        .filter(User.organization_id == current_user.organization_id)
        .order_by(User.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": str(row.id),
                "email": row.email,
                "full_name": row.full_name,
                "role": row.role.name if row.role else None,
                "is_active": row.is_active,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@router.get("/audit-logs")
def admin_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.organization_id == current_user.organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": str(row.id),
                "user_id": str(row.user_id) if row.user_id else None,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "details": row.details,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }
