"""Ingestion orchestration for the RAG API: submit/re-index/delete/status.

File uploads continue to use the existing ``/documents/upload`` endpoint.
This module adds the operations the RAG surface needs while reusing the same
storage, validation, Celery dispatch and ingestion pipeline.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentStatus, IngestionJob
from app.models.rag import DocumentVersion
from app.models.user import AuditLog, User
from app.rag.config import RagConfig
from app.rag.exceptions import ValidationError
from app.rag.ingestion.validators import validate_document
from app.rag.security import can_manage_document
from app.services.ingestion_service import create_ingestion_job, secure_store
from app.services.storage import get_storage_backend


class IngestionOrchestrator:
    def __init__(self, config: RagConfig | None = None) -> None:
        self.config = config or RagConfig.from_settings()

    # -- submission ----------------------------------------------------------

    def ingest_text(
        self,
        db: Session,
        user: User,
        *,
        content: str,
        filename: str,
        title: str | None = None,
        content_type: str = "text/plain",
        source_id: uuid.UUID | None = None,
        access_scope: str = "organization",
        metadata: dict[str, Any] | None = None,
        background_tasks: Any | None = None,
    ) -> tuple[Document, IngestionJob]:
        data = (content or "").encode("utf-8")
        safe_name = Path(filename or "text.txt").name
        if not Path(safe_name).suffix:
            safe_name = f"{safe_name}.txt"
        return self.ingest_file(
            db,
            user,
            filename=safe_name,
            data=data,
            content_type=content_type,
            title=title,
            source_id=source_id,
            access_scope=access_scope,
            metadata=metadata,
            background_tasks=background_tasks,
        )

    def ingest_file(
        self,
        db: Session,
        user: User,
        *,
        filename: str,
        data: bytes,
        content_type: str | None = None,
        title: str | None = None,
        source_id: uuid.UUID | None = None,
        access_scope: str = "organization",
        metadata: dict[str, Any] | None = None,
        background_tasks: Any | None = None,
    ) -> tuple[Document, IngestionJob]:
        content_type = content_type or "application/octet-stream"
        safe_name = Path(filename or "upload.bin").name
        if access_scope != "organization":
            role = user.role.name if getattr(user, "role", None) else "member"
            if role != "admin":
                raise ValidationError("only admins may set a non-organization document access scope")
        validate_document(safe_name, content_type, data, self.config)
        storage_path, storage_backend = secure_store(
            user.organization_id, safe_name, data, content_type=content_type
        )
        doc = Document(
            organization_id=user.organization_id,
            uploaded_by=user.id,
            filename=safe_name,
            content_type=content_type,
            file_size=len(data),
            storage_path=storage_path,
            storage_backend=storage_backend,
            status=DocumentStatus.pending,
            retry_count=0,
            source_id=source_id,
            access_scope=access_scope,
            doc_metadata=json.dumps(
                {"document_title": title or Path(safe_name).stem, **(metadata or {})},
                ensure_ascii=False,
            ),
        )
        db.add(doc)
        db.flush()
        job = create_ingestion_job(db, doc, attempt=1)
        db.add(
            AuditLog(
                organization_id=user.organization_id,
                user_id=user.id,
                action="rag_ingestion_submitted",
                resource_type="document",
                resource_id=str(doc.id),
                details=json.dumps({"filename": safe_name}),
            )
        )
        db.commit()
        db.refresh(doc)
        db.refresh(job)
        self.dispatch(db, doc, job, background_tasks=background_tasks)
        return doc, job

    def reindex_document(
        self,
        db: Session,
        user: User,
        document_id: uuid.UUID,
        *,
        background_tasks: Any | None = None,
    ) -> tuple[Document, IngestionJob]:
        document = db.get(Document, document_id)
        if document is None or document.organization_id != user.organization_id:
            raise LookupError("Document not found")
        if not can_manage_document(user, document):
            raise PermissionError("Only the uploader or an admin may re-index this document")
        if document.status == DocumentStatus.processing:
            raise RuntimeError("Document is already being processed")
        document.status = DocumentStatus.pending
        document.error_message = None
        job = create_ingestion_job(db, document, attempt=(document.retry_count or 0) + 1)
        db.add(
            AuditLog(
                organization_id=user.organization_id,
                user_id=user.id,
                action="rag_reindex_requested",
                resource_type="document",
                resource_id=str(document.id),
            )
        )
        db.commit()
        db.refresh(document)
        db.refresh(job)
        self.dispatch(db, document, job, background_tasks=background_tasks)
        return document, job

    def delete_document_index(self, db: Session, user: User, document_id: uuid.UUID) -> dict[str, Any]:
        document = db.get(Document, document_id)
        if document is None or document.organization_id != user.organization_id:
            raise LookupError("Document not found")
        if not can_manage_document(user, document):
            raise PermissionError("Only the uploader or an admin may delete this document's index")

        deleted_points = 0
        vector_error = None
        try:
            from app.rag.indexes.vector import VectorIndex

            deleted_points = VectorIndex(self.config).delete_document(
                str(user.organization_id), str(document.id)
            )
        except Exception as exc:  # noqa: BLE001 — index may be unavailable; report truthfully
            vector_error = str(exc)[:300]

        from app.models.document import DocumentChunk

        deleted_chunks = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.organization_id == user.organization_id,
                DocumentChunk.document_id == document.id,
            )
            .delete(synchronize_session=False)
        )
        metadata = _metadata(document)
        processing = metadata.get("processing")
        if isinstance(processing, dict):
            processing["indexed"] = False
            processing["index_deleted_at"] = True
            metadata["processing"] = processing
        document.doc_metadata = json.dumps(metadata, ensure_ascii=False)
        latest = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version.desc())
            .first()
        )
        if latest is not None:
            latest.status = "deleted"
        db.add(
            AuditLog(
                organization_id=user.organization_id,
                user_id=user.id,
                action="rag_index_deleted",
                resource_type="document",
                resource_id=str(document.id),
                details=json.dumps({"deleted_chunks": int(deleted_chunks), "deleted_points": deleted_points}),
            )
        )
        db.commit()
        return {
            "document_id": str(document.id),
            "deleted_chunks": int(deleted_chunks),
            "deleted_points": deleted_points,
            "vector_error": vector_error,
        }

    def delete_document(self, db: Session, user: User, document_id: uuid.UUID) -> dict[str, Any]:
        document = db.get(Document, document_id)
        if document is None or document.organization_id != user.organization_id:
            raise LookupError("Document not found")
        if not can_manage_document(user, document):
            raise PermissionError("Only the uploader or an admin may delete this document")
        index_result = self.delete_document_index(db, user, document.id)
        storage_key = document.storage_path
        storage_backend = getattr(document, "storage_backend", None)
        storage_deleted = False
        try:
            if storage_backend == "minio":
                from app.services.storage import MinioStorageBackend

                MinioStorageBackend().delete(storage_key)
                storage_deleted = True
            else:
                get_storage_backend().delete(storage_key)
                storage_deleted = True
        except Exception:  # noqa: BLE001 — object may already be absent
            storage_deleted = False
        db.delete(document)
        db.add(
            AuditLog(
                organization_id=user.organization_id,
                user_id=user.id,
                action="rag_document_deleted",
                resource_type="document",
                resource_id=str(document_id),
                details=json.dumps({"storage_deleted": storage_deleted}),
            )
        )
        db.commit()
        return {**index_result, "storage_deleted": storage_deleted, "document_deleted": True}

    # -- status --------------------------------------------------------------

    @staticmethod
    def job_status(db: Session, user: User, job_id: uuid.UUID) -> dict[str, Any]:
        job = db.get(IngestionJob, job_id)
        if job is None or job.organization_id != user.organization_id:
            raise LookupError("Ingestion job not found")
        document = db.get(Document, job.document_id)
        return {
            "job_id": str(job.id),
            "document_id": str(job.document_id),
            "status": job.status.value if hasattr(job.status, "value") else str(job.status),
            "attempt": job.attempt,
            "max_attempts": job.max_attempts,
            "worker": job.worker,
            "error": job.error_message,
            "error_details": _decode(job.error_details),
            "document_status": (
                document.status.value if document and hasattr(document.status, "value") else None
            ),
            "document_version": document.version if document else None,
            "metadata": _metadata(document) if document else {},
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "created_at": job.created_at,
        }

    # -- dispatch ------------------------------------------------------------

    def dispatch(self, db: Session, document: Document, job: IngestionJob, background_tasks: Any | None = None) -> str:
        try:
            from app.worker.tasks import enqueue_document_ingestion

            task_id = enqueue_document_ingestion(db, document, job)
            if task_id:
                return "celery"
        except Exception:  # noqa: BLE001 — broker unavailable; fall back
            pass
        if background_tasks is not None:
            background_tasks.add_task(_process_in_new_session, str(document.id), str(job.id))
            return "background"
        _process_in_new_session(str(document.id), str(job.id))
        return "inline"


def _process_in_new_session(document_id: str, job_id: str) -> None:
    from app.db import session as db_session
    from app.services.ingestion_service import process_document_job

    db = db_session.SessionLocal()
    try:
        try:
            process_document_job(db, uuid.UUID(document_id), uuid.UUID(job_id), worker_name="rag-inline")
        except Exception:  # noqa: BLE001 — failure is persisted in job state
            db.rollback()
    finally:
        db.close()


def _metadata(document: Document | None) -> dict[str, Any]:
    if document is None or not document.doc_metadata:
        return {}
    try:
        value = json.loads(document.doc_metadata)
        return value if isinstance(value, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _decode(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return raw


__all__ = ["IngestionOrchestrator"]
