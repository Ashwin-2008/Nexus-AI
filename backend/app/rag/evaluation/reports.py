"""Persistence and retrieval of evaluation runs."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.rag import RagEvaluationRun
from app.rag.evaluation.evaluator import EvaluationReport
from app.rag.types import RagScope


def persist_report(
    db: Session,
    scope: RagScope,
    report: EvaluationReport,
    *,
    dataset_name: str = "inline",
) -> RagEvaluationRun:
    row = RagEvaluationRun(
        organization_id=uuid.UUID(scope.organization_id),
        user_id=uuid.UUID(scope.user_id) if scope.user_id else None,
        name=report.name[:255],
        dataset_name=dataset_name[:255],
        status="completed" if not report.errors else "completed_with_errors",
        item_count=report.item_count,
        metrics=json.dumps(report.metrics, ensure_ascii=False),
        detail=json.dumps(
            {
                "mode": report.mode,
                "generated": report.generated,
                "duration_ms": report.duration_ms,
                "errors": report.errors,
                "items": report.items,
            },
            ensure_ascii=False,
            default=str,
        )[:1_000_000],
        finished_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_reports(db: Session, organization_id: uuid.UUID, limit: int = 50) -> list[RagEvaluationRun]:
    return (
        db.query(RagEvaluationRun)
        .filter(RagEvaluationRun.organization_id == organization_id)
        .order_by(RagEvaluationRun.created_at.desc())
        .limit(limit)
        .all()
    )


def read_report(row: RagEvaluationRun) -> dict:
    def decode(value: str | None, default):
        if not value:
            return default
        try:
            return json.loads(value)
        except Exception:  # noqa: BLE001
            return default

    return {
        "id": str(row.id),
        "name": row.name,
        "dataset_name": row.dataset_name,
        "status": row.status,
        "item_count": row.item_count,
        "metrics": decode(row.metrics, {}),
        "detail": decode(row.detail, {}),
        "error": row.error,
        "created_at": row.created_at,
        "finished_at": row.finished_at,
    }
