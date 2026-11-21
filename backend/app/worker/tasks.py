from __future__ import annotations

import logging
import uuid

from app.core.config import settings
from app.db import session as db_session
from app.models.document import Document, IngestionJob, IngestionJobStatus
from app.services.ingestion_service import create_ingestion_job, process_document_job
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def enqueue_connector_sync(db, source, job) -> str | None:
    """Enqueue a connector sync task if Celery is available; else None."""
    if celery_app is None or not getattr(settings, "ingestion_use_celery", True):
        return None
    try:
        task = sync_connector_task.apply_async(
            kwargs={"source_id": str(source.id), "job_id": str(job.id)},
            queue="ingestion",
        )
        return task.id
    except Exception as e:  # broker unavailable, etc.
        logger.warning("Celery connector sync enqueue failed, using background fallback: %s", e)
        return None


def enqueue_agent_execution(execution_id: str) -> str | None:
    if celery_app is None or not getattr(settings, "ingestion_use_celery", True):
        return None
    try:
        task = run_agent_execution_task.apply_async(
            kwargs={"execution_id": execution_id},
            queue="agents",
        )
        return task.id
    except Exception as e:  # broker unavailable; caller can use synchronous fallback
        logger.warning("Celery agent execution enqueue failed: %s", e)
        return None
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


if celery_app is not None:

    @celery_app.task(name="app.worker.tasks.sync_connector", bind=True, acks_late=True, max_retries=1)
    def sync_connector_task(self, source_id: str, job_id: str):  # type: ignore[no-redef]
        SessionLocal = db_session.SessionLocal
        db = SessionLocal()
        try:
            from app.models.connector import ConnectorSyncJob, DataSource
            from app.services.connectors_service import sync_data_source

            source = db.get(DataSource, uuid.UUID(source_id))
            job = db.get(ConnectorSyncJob, uuid.UUID(job_id))
            if source is None or job is None:
                return {"status": "missing"}
            result = sync_data_source(db, source, job)
            return result
        finally:
            db.close()

else:

    def sync_connector_task(*args, **kwargs):  # type: ignore[no-redef]
        raise RuntimeError("Celery is not available")


if celery_app is not None:

    @celery_app.task(name="app.worker.tasks.run_agent_execution", bind=True, acks_late=True, max_retries=1)
    def run_agent_execution_task(self, execution_id: str):  # type: ignore[no-redef]
        from app.models.agent import AgentExecution
        from app.models.user import User
        from app.services.agent_service import run_execution

        db = db_session.SessionLocal()
        try:
            execution = db.get(AgentExecution, uuid.UUID(execution_id))
            if execution is None:
                return {"status": "missing"}
            user = db.get(User, execution.user_id)
            if user is None or execution.status in {"succeeded", "failed", "cancelled"}:
                return {"status": execution.status if user else "missing"}
            result = run_execution(db, user, execution.request, execution=execution, task_id=self.request.id)
            if result.status == "running":
                raise self.retry(countdown=min(60, 2 ** max(1, result.retry_count)), max_retries=settings.agent_max_retries)
            return {"status": "completed", "execution_id": execution_id}
        finally:
            db.close()

else:

    def run_agent_execution_task(*args, **kwargs):  # type: ignore[no-redef]
        raise RuntimeError("Celery is not available")
