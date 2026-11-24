from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentChunk, DocumentStatus, IngestionJob, IngestionJobStatus
from app.services.embeddings import EmbeddingError, get_embedding_provider, provider_info
from app.services.processing import Chunker, ExtractionError, FileExtractor, ProcessingContext, TextNormalizer
from app.services.storage import StorageError, StorageUnavailableError, build_document_key, get_storage_backend
from app.services.vector_index import VectorIndexError, get_vector_index

from app.rag.constants import SUPPORTED_CONTENT_TYPES, SUPPORTED_EXTENSIONS
from app.rag.exceptions import UnsupportedDocumentError as RagUnsupportedDocumentError
from app.rag.exceptions import ValidationError as RagValidationError
from app.rag.ingestion.validators import validate_document as _validate_rag_document

ALLOWED_EXTENSIONS = set(SUPPORTED_EXTENSIONS)
ALLOWED_CONTENT_TYPES = set(SUPPORTED_CONTENT_TYPES)
MAX_FILE_SIZE_BYTES = settings.rag_max_document_bytes


class FileValidationError(ValueError):
    pass


def get_storage_root() -> Path:
    # Backward-compat helper
    root = Path(os.getenv("STORAGE_ROOT", settings.storage_root))
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_upload(filename: str, content_type: str | None, size: int, data: bytes | None = None) -> str:
    """Validate an upload (extension, size, magic bytes, archive safety).

    ``size`` is kept for the existing API signature; when ``data`` is supplied
    the RAG validator also checks magic-byte consistency and archive safety.
    """
    ext = Path(filename).suffix.lower()
    if data is None:
        if ext not in ALLOWED_EXTENSIONS:
            raise FileValidationError(f"Unsupported file type: {ext or 'unknown'}")
        if size <= 0:
            raise FileValidationError("Empty file")
        if size > MAX_FILE_SIZE_BYTES:
            raise FileValidationError("File too large")
        return ext
    try:
        return _validate_rag_document(filename, content_type, data)
    except (RagUnsupportedDocumentError, RagValidationError) as exc:
        raise FileValidationError(str(exc)) from exc


def secure_store(org_id: uuid.UUID, filename: str, data: bytes, content_type: str | None = None) -> tuple[str, str]:
    """Store file via configured storage backend. Returns (storage_path/key, backend_name)."""
    backend = get_storage_backend()
    key = build_document_key(org_id, filename)
    try:
        stored = backend.put_bytes(key, data, content_type=content_type)
        return stored, backend.name
    except StorageUnavailableError:
        # Graceful fallback to local if primary (e.g. MinIO) unavailable
        from app.services.storage import LocalStorageBackend

        local = LocalStorageBackend()
        stored = local.put_bytes(key, data, content_type=content_type)
        return stored, local.name


def load_document_bytes(storage_path: str, storage_backend: str | None = None) -> bytes:
    # Try hinted backend first, then fallbacks for migration/compat
    from app.services.storage import (
        LocalStorageBackend,
        MinioStorageBackend,
        SupabaseStorageBackend,
        get_storage_backend,
    )

    errors = []
    candidates = []
    if storage_backend == "supabase":
        try:
            candidates.append(SupabaseStorageBackend())
        except Exception:
            pass
        candidates.append(LocalStorageBackend())
    elif storage_backend == "minio":
        try:
            candidates.append(MinioStorageBackend())
        except Exception:
            pass
        candidates.append(LocalStorageBackend())
    elif storage_backend == "local":
        candidates.append(LocalStorageBackend())
    else:
        candidates.append(get_storage_backend())
        candidates.append(LocalStorageBackend())
    seen = set()
    for b in candidates:
        if b.name in seen:
            continue
        seen.add(b.name)
        try:
            return b.get_bytes(storage_path)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
            continue
    # final direct path fallback
    p = Path(storage_path)
    if p.exists() and p.is_file():
        return p.read_bytes()
    raise StorageError("; ".join(errors) or f"Unable to load object: {storage_path}")


def extract_metadata_from_bytes(data: bytes, path_hint: str, filename: str, content_type: str) -> dict[str, Any]:
    p = Path(path_hint or filename)
    meta: dict[str, Any] = {
        "filename": filename,
        "content_type": content_type,
        "size_bytes": len(data),
        "extension": p.suffix.lower(),
    }
    ext = (p.suffix or Path(filename).suffix).lower()
    try:
        if ext == ".txt":
            text = data.decode("utf-8", errors="ignore")
            meta.update({"char_count": len(text), "line_count": text.count("\n") + 1 if text else 0})
        elif ext == ".csv":
            import csv
            import io

            text = data.decode("utf-8", errors="ignore")
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            meta.update({"row_count": len(rows), "column_count": len(rows[0]) if rows else 0})
        elif ext == ".pdf":
            try:
                import io
                from pypdf import PdfReader  # type: ignore

                reader = PdfReader(io.BytesIO(data))
                meta.update({"page_count": len(reader.pages)})
            except Exception:
                meta.update({"page_count": None})
        elif ext == ".docx":
            try:
                import io
                import docx  # type: ignore

                d = docx.Document(io.BytesIO(data))
                meta.update({"paragraph_count": len(d.paragraphs)})
            except Exception:
                meta.update({"paragraph_count": None})
        elif ext == ".xlsx":
            try:
                import io
                import openpyxl  # type: ignore

                wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
                meta.update({"sheet_count": len(wb.sheetnames), "sheet_names": wb.sheetnames[:20]})
                wb.close()
            except Exception:
                meta.update({"sheet_count": None})
    except Exception as e:
        meta["extraction_warning"] = str(e)
    return meta


def extract_metadata(path: str, filename: str, content_type: str) -> dict[str, Any]:
    # Backward-compatible wrapper
    p = Path(path)
    if p.exists() and p.is_file():
        data = p.read_bytes()
    else:
        data = load_document_bytes(path)
    return extract_metadata_from_bytes(data, path, filename, content_type)


def metadata_to_json(meta: dict[str, Any]) -> str:
    return json.dumps(meta, ensure_ascii=False)


def metadata_from_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def create_ingestion_job(db: Session, document: Document, attempt: int = 1, task_id: str | None = None) -> IngestionJob:
    job = IngestionJob(
        document_id=document.id,
        organization_id=document.organization_id,
        status=IngestionJobStatus.queued,
        attempt=attempt,
        max_attempts=settings.ingestion_max_retries,
        task_id=task_id,
    )
    db.add(job)
    db.flush()
    return job


def _error_details(exc: Exception) -> str:
    return json.dumps({"type": exc.__class__.__name__, "message": str(exc)[:2000]}, ensure_ascii=False)


def process_document_job(db: Session, document_id: uuid.UUID, job_id: uuid.UUID | None = None, worker_name: str | None = None) -> Document:
    """Run the full ingestion pipeline and persist durable job status.

    Heavy lifting lives in ``app.rag.ingestion.pipeline.IngestionPipeline``
    (validation -> parsing -> normalization -> metadata -> dedupe/version ->
    chunking -> real embeddings -> Qdrant -> lexical rows -> version record).
    """
    doc = db.get(Document, document_id)
    if not doc:
        raise ValueError("Document not found")

    job: Optional[IngestionJob] = db.get(IngestionJob, job_id) if job_id else None
    if job is None:
        job = (
            db.query(IngestionJob)
            .filter(IngestionJob.document_id == document_id)
            .order_by(IngestionJob.created_at.desc())
            .first()
        )
    if job is None:
        job = create_ingestion_job(db, doc, attempt=(doc.retry_count or 0) + 1)

    job_id = job.id
    now = datetime.now(timezone.utc)
    job.status = IngestionJobStatus.running
    job.started_at = job.started_at or now
    job.worker = worker_name or job.worker
    doc.status = DocumentStatus.processing
    doc.error_message = None
    db.commit()

    try:
        from app.rag.config import RagConfig
        from app.rag.ingestion.pipeline import IngestionPipeline

        outcome = IngestionPipeline(RagConfig.from_settings()).run(db, doc)
        doc.doc_metadata = metadata_to_json(outcome.metadata)
        doc.status = DocumentStatus.completed
        doc.error_message = None
        job.status = IngestionJobStatus.succeeded
        job.error_message = None
        job.error_details = None
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(doc)
        return doc
    except Exception as e:  # noqa: BLE001
        db.rollback()
        doc = db.get(Document, document_id)
        job = db.get(IngestionJob, job_id)
        if doc is None or job is None:
            raise
        attempt = job.attempt or 1
        max_attempts = job.max_attempts or settings.ingestion_max_retries
        doc.retry_count = max(0, attempt - 1)
        doc.error_message = str(e)[:1000]
        job.error_message = str(e)[:1000]
        job.error_details = _error_details(e)
        job.finished_at = datetime.now(timezone.utc)
        if attempt < max_attempts:
            job.status = IngestionJobStatus.retrying
            doc.status = DocumentStatus.pending
        else:
            job.status = IngestionJobStatus.failed
            doc.status = DocumentStatus.failed
        db.commit()
        raise
