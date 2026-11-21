"""Ingestion status persistence helpers.

Durable status lives in the existing ``documents``/``ingestion_jobs`` tables.
These helpers keep transitions consistent and record structured error details
without duplicating job state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentStatus, IngestionJob, IngestionJobStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def mark_running(db: Session, document: Document, job: IngestionJob, worker_name: str | None = None) -> None:
    job.status = IngestionJobStatus.running
    job.started_at = job.started_at or utcnow()
    job.worker = worker_name or job.worker
    document.status = DocumentStatus.processing
    document.error_message = None
    db.commit()


def mark_succeeded(db: Session, document: Document, job: IngestionJob, detail: dict[str, Any]) -> None:
    job.status = IngestionJobStatus.succeeded
    job.error_message = None
    job.error_details = None
    job.finished_at = utcnow()
    document.status = DocumentStatus.completed
    document.error_message = None
    db.commit()


def mark_failed(db: Session, document: Document, job: IngestionJob, exc: Exception) -> None:
    """Persist failure; keep retrying while attempts remain."""
    attempt = job.attempt or 1
    max_attempts = job.max_attempts or settings.ingestion_max_retries
    document.retry_count = max(0, attempt - 1)
    document.error_message = str(exc)[:1000]
    job.error_message = str(exc)[:1000]
    job.error_details = json.dumps(
        {"type": exc.__class__.__name__, "message": str(exc)[:2000]}, ensure_ascii=False
    )
    job.finished_at = utcnow()
    if attempt < max_attempts:
        job.status = IngestionJobStatus.retrying
        document.status = DocumentStatus.pending
    else:
        job.status = IngestionJobStatus.failed
        document.status = DocumentStatus.failed
    db.commit()
