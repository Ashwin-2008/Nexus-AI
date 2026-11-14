from __future__ import annotations

import logging
import uuid

from app.core.config import settings
from app.db import session as db_session
from app.models.document import Document, IngestionJob, IngestionJobStatus
from app.services.ingestion_service import create_ingestion_job, process_document_job
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def enqueue_document_ingestion(db, document: Document, job: IngestionJob | None = None) -> str | None:
    """Enqueue Celery task if available; return task id or None."""
    if celery_app is None or not getattr(settings, "ingestion_use_celery", True):
        return None
    try:
        task = process_document_task.apply_async(  # type: ignore[attr-defined]
            kwargs={"document_id": str(document.id), "job_id": str(job.id) if job else None},
            queue="ingestion",
        )
        if job is not None:
            job.task_id = task.id
            db.add(job)
            db.commit()
        return task.id
    except Exception as e:  # broker unavailable, etc.
        logger.warning("Celery enqueue failed, will rely on fallback processing: %s", e)
        return None


if celery_app is not None:

    @celery_app.task(
        name="app.worker.tasks.process_document",
        bind=True,
        acks_late=True,
        max_retries=max(0, settings.ingestion_max_retries - 1),
    )
    def process_document_task(self, document_id: str, job_id: str | None = None):  # type: ignore[no-redef]
        SessionLocal = db_session.SessionLocal
        db = SessionLocal()
        doc_uuid = uuid.UUID(document_id)
        job_uuid = uuid.UUID(job_id) if job_id else None
        try:
            # ensure job exists and tracks this attempt/task
            job = db.get(IngestionJob, job_uuid) if job_uuid else None
            doc = db.get(Document, doc_uuid)
            if not doc:
                return {"status": "missing"}
            if job is None:
                job = create_ingestion_job(db, doc, attempt=(doc.retry_count or 0) + 1, task_id=self.request.id)
                db.commit()
                job_uuid = job.id
            else:
                job.task_id = self.request.id
                db.commit()
            process_document_job(db, doc_uuid, job_uuid, worker_name=getattr(self.request, "hostname", None))
            return {"status": "succeeded", "document_id": document_id}
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            # reload state persisted by process_document_job failure path
            db2 = SessionLocal()
            try:
                job = db2.get(IngestionJob, job_uuid) if job_uuid else None
                doc = db2.get(Document, doc_uuid)
                if job and job.status == IngestionJobStatus.retrying and doc:
                    # schedule next attempt with backoff; create next job record
                    next_attempt = (job.attempt or 1) + 1
                    next_job = create_ingestion_job(db2, doc, attempt=next_attempt)
                    db2.commit()
                    countdown = int(settings.ingestion_retry_backoff_seconds) * max(1, job.attempt or 1)
                    raise self.retry(exc=exc, countdown=countdown, kwargs={"document_id": document_id, "job_id": str(next_job.id)})
            finally:
                db2.close()
            raise
        finally:
            db.close()

else:

    def process_document_task(*args, **kwargs):  # type: ignore[no-redef]
        raise RuntimeError("Celery is not available")
