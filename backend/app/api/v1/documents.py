from __future__ import annotations

from pathlib import Path
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.document import Document, DocumentStatus, IngestionJob
from app.models.user import User
from app.schemas.document import DocumentList, DocumentRead, IngestionJobRead
from app.services.ingestion_service import (
    FileValidationError,
    create_ingestion_job,
    metadata_from_json,
    process_document_job,
    secure_store,
    validate_upload,
)

router = APIRouter(prefix="/documents", tags=["documents"])
compat_router = APIRouter(tags=["documents"])


def _latest_job(db: Session, doc_id: uuid.UUID) -> IngestionJob | None:
    return (
        db.query(IngestionJob)
        .filter(IngestionJob.document_id == doc_id)
        .order_by(IngestionJob.created_at.desc())
        .first()
    )


def _doc_to_read(doc: Document, db: Session | None = None) -> DocumentRead:
    latest = None
    job = None
    if db is not None:
        job = _latest_job(db, doc.id)
    elif getattr(doc, "ingestion_jobs", None):
        job = doc.ingestion_jobs[0] if doc.ingestion_jobs else None
    if job is not None:
        latest = IngestionJobRead(
            id=job.id,
            status=job.status.value if hasattr(job.status, "value") else str(job.status),
            attempt=job.attempt,
            max_attempts=job.max_attempts,
            task_id=job.task_id,
            worker=job.worker,
            error_message=job.error_message,
            started_at=job.started_at,
            finished_at=job.finished_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
    return DocumentRead(
        id=doc.id,
        organization_id=doc.organization_id,
        uploaded_by=doc.uploaded_by,
        filename=doc.filename,
        content_type=doc.content_type,
        file_size=doc.file_size,
        storage_backend=getattr(doc, "storage_backend", None),
        status=doc.status.value if hasattr(doc.status, "value") else str(doc.status),
        error_message=doc.error_message,
        retry_count=doc.retry_count or 0,
        metadata=metadata_from_json(doc.doc_metadata),
        latest_job=latest,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _dispatch_ingestion(background_tasks: BackgroundTasks, db: Session, doc: Document, job: IngestionJob) -> None:
    # Prefer Celery/Redis when available; fall back to in-process background execution.
    try:
        from app.worker.tasks import enqueue_document_ingestion

        task_id = enqueue_document_ingestion(db, doc, job)
        if task_id:
            return
    except Exception:
        pass
    # Fallback: run in background task (status/job persisted in DB by process_document_job)
    background_tasks.add_task(_run_ingestion_sync, str(doc.id), str(job.id))


def _run_ingestion_sync(document_id: str, job_id: str) -> None:
    from app.db import session as db_session

    SessionLocal = db_session.SessionLocal
    db = SessionLocal()
    try:
        try:
            process_document_job(db, uuid.UUID(document_id), uuid.UUID(job_id), worker_name="background")
        except Exception:
            # failure state is persisted inside process_document_job when possible
            db.rollback()
    finally:
        db.close()


async def _handle_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    db: Session,
    current_user: User,
):
    filename = file.filename or "upload"
    content_type = file.content_type or "application/octet-stream"
    data = await file.read()
    try:
        validate_upload(filename, content_type, len(data))
    except FileValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_file", "message": str(e)})

    try:
        storage_path, storage_backend = secure_store(current_user.organization_id, filename, data, content_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "storage_unavailable", "message": f"Storage unavailable: {e}"})

    doc = Document(
        organization_id=current_user.organization_id,
        uploaded_by=current_user.id,
        filename=Path(filename).name,
        content_type=content_type,
        file_size=len(data),
        storage_path=storage_path,
        storage_backend=storage_backend,
        status=DocumentStatus.pending,
        retry_count=0,
    )
    db.add(doc)
    db.flush()
    job = create_ingestion_job(db, doc, attempt=1)
    db.commit()
    db.refresh(doc)

    _dispatch_ingestion(background_tasks, db, doc, job)
    db.refresh(doc)
    return _doc_to_read(doc, db)


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _handle_upload(background_tasks, file, db, current_user)


@compat_router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document_compat(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compatibility alias for /api/v1/upload (see integration-spec)."""
    return await _handle_upload(background_tasks, file, db, current_user)


@router.get("", response_model=DocumentList)
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    docs = (
        db.query(Document)
        .filter(Document.organization_id == current_user.organization_id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return DocumentList(items=[_doc_to_read(d, db) for d in docs])


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.get(Document, document_id)
    if not doc or doc.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Document not found"})
    return _doc_to_read(doc, db)


@router.post("/{document_id}/retry", response_model=DocumentRead)
def retry_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.get(Document, document_id)
    if not doc or doc.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Document not found"})
    if doc.status not in {DocumentStatus.failed, DocumentStatus.completed}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "conflict", "message": "Document is not retryable in current state"})
    next_attempt = (doc.retry_count or 0) + 1
    doc.status = DocumentStatus.pending
    doc.error_message = None
    job = create_ingestion_job(db, doc, attempt=next_attempt)
    db.commit()
    db.refresh(doc)
    _dispatch_ingestion(background_tasks, db, doc, job)
    db.refresh(doc)
    return _doc_to_read(doc, db)
