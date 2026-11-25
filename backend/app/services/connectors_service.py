"""Connector sync: fetch external items and ingest them as Documents.

Items are stored through the same storage + ingestion pipeline as uploads
(Supabase/MinIO/local → extraction → chunking → embeddings → Qdrant), so connector
content lands in the same knowledge base, search and RAG paths.

Deduplication: documents are keyed by org + deterministic filename
"<type>/<external_id>.txt"; unchanged content (sha256) is skipped.

Robustness notes:
- Counters are committed incrementally, because a failed ingestion can trigger a
  session rollback that would otherwise erase the counters for earlier items.
- A sync can run in a Celery worker or in an in-process background task. Both
  paths go through the same code and persist terminal failures.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.connector import ConnectorSyncJob, DataSource
from app.models.document import Document, DocumentStatus
from app.services.connectors import (
    ConnectorContext,
    ConnectorError,
    ConnectorItem,
    get_connector,
    parse_config,
)
from app.services.credentials import decrypt_credentials
from app.services.ingestion_service import (
    create_ingestion_job,
    load_document_bytes,
    process_document_job,
    secure_store,
)

logger = logging.getLogger(__name__)

# Bounded per-source defaults (env-overridable via config fields on the source)
DEFAULT_MAX_ITEMS = 200
DEFAULT_STALE_MINUTES = 60


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return (slug or "item")[:180]


_MIME_EXTENSIONS = {
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "application/json": ".json",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}


def _item_extension(item: ConnectorItem) -> str:
    extension = _MIME_EXTENSIONS.get((item.mime or "").split(";")[0].strip().lower())
    if extension:
        return extension
    suffix = Path(item.uri or "").suffix.lower()
    return suffix if suffix in {".md", ".html", ".htm", ".json", ".csv", ".txt"} else ".txt"


def build_connector_filename(source_type: str, external_id: str, extension: str = ".txt") -> str:
    return f"connector/{source_type}/{_slug(external_id)}{extension}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _error_summary(errors: list[str], limit: int = 2000) -> str | None:
    if not errors:
        return None
    return "\n".join(errors)[:limit]


def _fail_sync(db: Session, job_id: uuid.UUID, source_id: uuid.UUID, message: str) -> dict[str, Any]:
    """Persist a terminal failure without letting a broken session mask it."""
    message = (message or "sync failed")[:2000]
    try:
        db.rollback()
        job = db.get(ConnectorSyncJob, job_id)
        source = db.get(DataSource, source_id)
        now = _utcnow()
        if job is not None:
            job.status = "failed"
            job.error = message
            job.finished_at = now
        if source is not None:
            source.status = "error"
            source.last_sync_status = "failed"
            source.last_error = message[:500]
        db.commit()
    except Exception:  # noqa: BLE001 — a DB outage must not hide the original error
        db.rollback()
        logger.exception("could not persist connector sync failure")
    return {"status": "failed", "error": message[:500]}


def sync_data_source(db: Session, source: DataSource, job: ConnectorSyncJob) -> dict[str, Any]:
    """Run one sync. Updates job counters/status in-place and commits."""
    source_id, job_id = source.id, job.id
    try:
        connector = get_connector(source.type)
        config = parse_config(source.config)
    except Exception as e:  # noqa: BLE001 — unknown type/bad config is a job failure
        return _fail_sync(db, job_id, source_id, f"Connector setup failed: {e}")

    try:
        credentials = decrypt_credentials(source.credentials_encrypted)
    except Exception as e:  # noqa: BLE001 — surfaced in job, not a 500
        return _fail_sync(db, job_id, source_id, f"Credential decryption failed: {e}")

    ctx = ConnectorContext(config=config, credentials=credentials)
    job = db.get(ConnectorSyncJob, job_id)
    if job is None:
        return {"status": "failed", "error": "Sync job not found"}
    job.status = "running"
    job.error = None
    db.commit()

    try:
        connector.validate(ctx)
        items = list(connector.fetch(ctx, max_items=int(config.get("max_items", DEFAULT_MAX_ITEMS))))
    except ConnectorError as e:
        return _fail_sync(db, job_id, source_id, str(e))
    except Exception as e:  # noqa: BLE001 — connector crashes are job failures
        logger.exception("connector fetch crashed (%s)", source.type)
        return _fail_sync(db, job_id, source_id, f"Connector fetch crashed: {e}")

    # Commit fetched early; per-item rollbacks must not erase progress.
    job = db.get(ConnectorSyncJob, job_id)
    job.fetched = len(items)
    db.commit()

    errors: list[str] = []
    source_type = source.type
    for item in items:
        if source is None:
            break
        doc: Document | None = None
        try:
            content = item.data if item.data is not None else (item.text or "").encode("utf-8")
            content_hash = item.content_hash()
            extension = _item_extension(item)
            filename = build_connector_filename(source.type, item.external_id, extension)
            content_type = item.mime or "text/plain"

            existing = (
                db.query(Document)
                .filter(
                    Document.organization_id == source.organization_id,
                    Document.filename == filename,
                )
                .first()
            )
            if (
                existing is not None
                and existing.status == DocumentStatus.completed
                and content_hash in (existing.doc_metadata or "{}")
            ):
                # Only a successfully indexed document with identical content
                # is a duplicate. A failed/pending row must be retried.
                job = db.get(ConnectorSyncJob, job_id)
                job.skipped += 1
                db.commit()
                continue

            storage_path, storage_backend = secure_store(
                source.organization_id, filename, content, content_type=content_type
            )
            metadata: dict[str, Any] = {
                "filename": filename,
                "content_type": content_type,
                "size_bytes": len(content),
                "extension": extension,
                "source": "connector",
                "connector_type": source.type,
                "external_id": item.external_id,
                "content_hash": content_hash,
                "uri": item.uri,
                "connector_metadata": item.metadata,
            }
            if existing is not None:
                # Re-ingest in place (same document row, fresh ingestion job)
                existing.status = DocumentStatus.pending
                existing.error_message = None
                existing.content_type = content_type
                existing.file_size = len(content)
                existing.storage_path = storage_path
                existing.storage_backend = storage_backend
                existing.content_hash = content_hash
                existing.source_id = source.id
                existing.access_scope = "organization"
                doc = existing
            else:
                doc = Document(
                    organization_id=source.organization_id,
                    uploaded_by=source.created_by,
                    filename=filename,
                    content_type=content_type,
                    file_size=len(content),
                    storage_path=storage_path,
                    storage_backend=storage_backend,
                    status=DocumentStatus.pending,
                    retry_count=0,
                    content_hash=content_hash,
                    source_id=source.id,
                    access_scope="organization",
                )
                db.add(doc)
            doc.doc_metadata = json.dumps(metadata, ensure_ascii=False)
            db.flush()
            ingestion = create_ingestion_job(db, doc, attempt=1)
            db.commit()
            process_document_job(db, doc.id, ingestion.id, worker_name=f"connector:{source.type}")
            job = db.get(ConnectorSyncJob, job_id)
            job.ingested += 1
            db.commit()
        except Exception as e:  # noqa: BLE001 — per-item failure must not kill the sync
            db.rollback()
            job = db.get(ConnectorSyncJob, job_id)
            source = db.get(DataSource, source_id)
            if job is not None:
                job.failed += 1
                errors.append(f"{item.external_id}: {type(e).__name__}: {e}")
                job.error = _error_summary(errors)
            if source is not None:
                source.last_error = _error_summary(errors, 500)
            db.commit()
            logger.warning(
                "connector item ingestion failed (%s/%s): %s", source_type, item.external_id, e, exc_info=True
            )

    job = db.get(ConnectorSyncJob, job_id)
    source = db.get(DataSource, source_id)
    if job is None or source is None:
        return {"status": "failed", "error": "Sync job or source disappeared"}

    now = _utcnow()
    job.finished_at = now
    if job.failed and not (job.ingested or job.skipped):
        job.status = "failed"
    elif job.failed:
        job.status = "partial"
    else:
        job.status = "succeeded"
    job.error = _error_summary(errors)
    source.status = "error" if job.status == "failed" else "active"
    source.last_sync_status = job.status
    source.last_error = _error_summary(errors, 500)
    if job.status in {"succeeded", "partial"}:
        source.last_synced_at = now
    db.commit()
    return {
        "status": job.status,
        "fetched": job.fetched,
        "ingested": job.ingested,
        "skipped": job.skipped,
        "failed": job.failed,
        "error": job.error,
    }


def run_sync_job_by_id(source_id: uuid.UUID, job_id: uuid.UUID) -> None:
    """Run a queued sync job in a fresh session (API background task/worker)."""
    from app.db import session as db_session

    db = db_session.SessionLocal()
    try:
        # Claim the job atomically: a Celery worker and the API fallback must
        # not run the same sync twice when both are available.
        claimed = (
            db.query(ConnectorSyncJob)
            .filter(
                ConnectorSyncJob.id == job_id,
                ConnectorSyncJob.status == "queued",
            )
            .update({"status": "running"}, synchronize_session=False)
        )
        db.commit()
        if not claimed:
            return
        source = db.get(DataSource, source_id)
        job = db.get(ConnectorSyncJob, job_id)
        if source is None or job is None:
            return
        sync_data_source(db, source, job)
    except Exception as e:  # noqa: BLE001 — last-resort guard so jobs never stay running
        logger.exception("connector sync crashed")
        _fail_sync(db, job_id, source_id, f"Sync crashed: {e}")
    finally:
        db.close()


def active_sync_job(
    db: Session, source_id: uuid.UUID, stale_minutes: int | None = None
) -> ConnectorSyncJob | None:
    """Return a recent queued/running job, or None when it should be superseded."""
    running_limit = int(
        stale_minutes or getattr(settings, "connector_sync_stale_minutes", DEFAULT_STALE_MINUTES)
    )
    queued_limit = int(
        getattr(settings, "connector_sync_queued_stale_minutes", 5) or 5
    )
    rows = (
        db.query(ConnectorSyncJob)
        .filter(
            ConnectorSyncJob.data_source_id == source_id,
            ConnectorSyncJob.status.in_(["queued", "running"]),
        )
        .order_by(ConnectorSyncJob.started_at.desc())
        .limit(5)
        .all()
    )
    now = _utcnow()
    for job in rows:
        started = _as_aware(job.started_at)
        if started is None:
            continue
        limit = queued_limit if job.status == "queued" else running_limit
        if (now - started) < timedelta(minutes=limit):
            return job
    return None


def reap_stale_sync_jobs(db: Session, source: DataSource) -> int:
    """Mark abandoned queued/running jobs as failed so the UI is never stuck."""
    running_limit = int(
        getattr(settings, "connector_sync_stale_minutes", DEFAULT_STALE_MINUTES)
    )
    queued_limit = int(
        getattr(settings, "connector_sync_queued_stale_minutes", 5) or 5
    )
    rows = (
        db.query(ConnectorSyncJob)
        .filter(
            ConnectorSyncJob.data_source_id == source.id,
            ConnectorSyncJob.status.in_(["queued", "running"]),
        )
        .all()
    )
    now = _utcnow()
    expired = 0
    for job in rows:
        started = _as_aware(job.started_at)
        limit = queued_limit if job.status == "queued" else running_limit
        if started is not None and (now - started) < timedelta(minutes=limit):
            continue
        job.status = "failed"
        job.error = (
            f"Sync did not start or finish within {limit} minutes. "
            "The background worker may be missing; trigger the sync again."
        )
        job.finished_at = now
        expired += 1
    if expired:
        if source.status != "disabled":
            source.status = "error"
        source.last_sync_status = "failed"
        source.last_error = f"{expired} sync job(s) timed out"
        db.commit()
    return expired


def run_sync_by_id(db: Session, source_id: uuid.UUID) -> dict[str, Any]:
    """Run a sync for a data source by id (used by scripts/tests)."""
    source = db.get(DataSource, source_id)
    if source is None:
        return {"status": "failed", "error": f"Data source {source_id} not found"}
    job = ConnectorSyncJob(
        data_source_id=source.id,
        organization_id=source.organization_id,
        status="queued",
    )
    db.add(job)
    db.commit()
    return sync_data_source(db, source, job)


def document_bytes_for(doc: Document) -> bytes:
    return load_document_bytes(doc.storage_path, doc.storage_backend)
