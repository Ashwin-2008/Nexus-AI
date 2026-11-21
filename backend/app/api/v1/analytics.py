"""Organization-scoped analytics derived from persisted telemetry.

Every number in this module comes from a real database aggregate. Fields the
system does not record (for example model cost) are intentionally absent rather
than fabricated.
"""
from __future__ import annotations

import json
import statistics
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.agent import AgentApprovalRequest, AgentExecution
from app.models.chat import Conversation
from app.models.connector import DataSource
from app.models.document import Document, DocumentChunk, IngestionJob
from app.models.report import Report
from app.models.rag import RagEvaluationRun, RagQueryLog
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


@router.get("/overview")
def analytics_overview(
    days: int = 14,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    days = max(7, min(90, days))
    organization_id: uuid.UUID = current_user.organization_id
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    # SQLite stores timezone-aware columns as naive local timestamps; match the
    # comparison shape so telemetry is not silently excluded in local dev.
    if getattr(getattr(db, "bind", None), "dialect", None) is not None and db.bind.dialect.name == "sqlite":
        since = since.replace(tzinfo=None)

    logs = (
        db.query(RagQueryLog)
        .filter(RagQueryLog.organization_id == organization_id, RagQueryLog.created_at >= since)
        .order_by(RagQueryLog.created_at.asc())
        .all()
    )
    total_queries = int(
        db.query(func.count(RagQueryLog.id)).filter(RagQueryLog.organization_id == organization_id).scalar() or 0
    )
    latencies = [log.total_latency_ms for log in logs if log.total_latency_ms is not None]
    retrieval_latencies = [log.retrieval_latency_ms for log in logs if log.retrieval_latency_ms is not None]

    series: dict[str, dict[str, float | int]] = {}
    for offset in range(days):
        day = (since + timedelta(days=offset)).date().isoformat()
        series[day] = {"queries": 0, "retrieval_ms": 0.0, "total_ms": 0.0, "no_evidence": 0}
    for log in logs:
        created = _aware(log.created_at)
        if created is None:
            continue
        key = created.date().isoformat()
        if key not in series:
            continue
        bucket = series[key]
        bucket["queries"] = int(bucket["queries"]) + 1
        bucket["retrieval_ms"] = float(bucket["retrieval_ms"]) + float(log.retrieval_latency_ms or 0)
        bucket["total_ms"] = float(bucket["total_ms"]) + float(log.total_latency_ms or 0)
        if log.answer_mode == "no_evidence" or (log.retrieved_count or 0) == 0:
            bucket["no_evidence"] = int(bucket["no_evidence"]) + 1
    query_series = [
        {
            "date": day,
            "queries": values["queries"],
            "avg_retrieval_ms": round(float(values["retrieval_ms"]) / values["queries"], 1) if values["queries"] else 0,
            "avg_total_ms": round(float(values["total_ms"]) / values["queries"], 1) if values["queries"] else 0,
            "no_evidence": values["no_evidence"],
        }
        for day, values in series.items()
    ]

    answer_modes = Counter(log.answer_mode or "unknown" for log in logs)
    verification = Counter(log.verification_status or "not_verified" for log in logs)
    modes = Counter(log.mode or "hybrid" for log in logs)
    no_evidence = sum(1 for log in logs if log.answer_mode == "no_evidence" or (log.retrieved_count or 0) == 0)
    successful = len(logs) - no_evidence

    agents = db.query(AgentExecution).filter(AgentExecution.organization_id == organization_id).all()
    agent_status = Counter(agent.status for agent in agents)
    agent_durations: list[float] = []
    for agent in agents:
        started, finished = _aware(agent.started_at), _aware(agent.finished_at)
        if started and finished:
            agent_durations.append((finished - started).total_seconds() * 1000)

    documents_by_status: dict[str, int] = {
        (key.value if hasattr(key, "value") else str(key)): int(value)
        for key, value in db.query(Document.status, func.count(Document.id))
        .filter(Document.organization_id == organization_id)
        .group_by(Document.status)
        .all()
    }
    chunk_count = int(
        db.query(func.count(DocumentChunk.id)).filter(DocumentChunk.organization_id == organization_id).scalar() or 0
    )
    source_count = int(
        db.query(func.count(DataSource.id)).filter(DataSource.organization_id == organization_id).scalar() or 0
    )
    active_sources = int(
        db.query(func.count(DataSource.id))
        .filter(DataSource.organization_id == organization_id, DataSource.status == "active")
        .scalar()
        or 0
    )

    conversation_count = int(
        db.query(func.count(Conversation.id))
        .filter(Conversation.organization_id == organization_id)
        .scalar()
        or 0
    )
    report_count = int(
        db.query(func.count(Report.id)).filter(Report.organization_id == organization_id).scalar() or 0
    )
    pending_approvals = int(
        db.query(func.count(AgentApprovalRequest.id))
        .filter(
            AgentApprovalRequest.organization_id == organization_id,
            AgentApprovalRequest.status == "pending",
        )
        .scalar()
        or 0
    )
    active_ingestions = int(
        db.query(func.count(IngestionJob.id))
        .filter(
            IngestionJob.organization_id == organization_id,
            IngestionJob.status.in_(["queued", "running", "retrying"]),
        )
        .scalar()
        or 0
    )

    latest_eval = (
        db.query(RagEvaluationRun)
        .filter(RagEvaluationRun.organization_id == organization_id)
        .order_by(RagEvaluationRun.created_at.desc())
        .first()
    )

    return {
        "window_days": days,
        "generated_at": now.isoformat(),
        "queries": {
            "total_all_time": total_queries,
            "window": len(logs),
            "successful": successful,
            "no_evidence": no_evidence,
            "success_rate": round((successful / len(logs)) * 100, 1) if logs else None,
            "avg_latency_ms": round(statistics.fmean(latencies), 1) if latencies else None,
            "p95_latency_ms": round(statistics.quantiles(latencies, n=20)[-1], 1) if len(latencies) >= 5 else None,
            "avg_retrieval_ms": round(statistics.fmean(retrieval_latencies), 1) if retrieval_latencies else None,
        },
        "series": query_series,
        "distribution": {
            "answer_modes": dict(answer_modes),
            "verification": dict(verification),
            "retrieval_modes": dict(modes),
        },
        "agents": {
            "total": len(agents),
            "by_status": dict(agent_status),
            "avg_duration_ms": round(statistics.fmean(agent_durations), 1) if agent_durations else None,
        },
        "knowledge": {
            "documents_by_status": documents_by_status,
            "documents_total": sum(documents_by_status.values()),
            "chunks": chunk_count,
            "sources": source_count,
            "active_sources": active_sources,
        },
        "activity": {
            "conversations": conversation_count,
            "reports": report_count,
            "pending_approvals": pending_approvals,
            "active_ingestions": active_ingestions,
        },
        "evaluation": {
            "run_id": str(latest_eval.id) if latest_eval else None,
            "name": latest_eval.name if latest_eval else None,
            "dataset": latest_eval.dataset_name if latest_eval else None,
            "item_count": latest_eval.item_count if latest_eval else None,
            "metrics": _json(latest_eval.metrics) if latest_eval else {},
            "created_at": latest_eval.created_at.isoformat() if latest_eval and latest_eval.created_at else None,
        },
    }
