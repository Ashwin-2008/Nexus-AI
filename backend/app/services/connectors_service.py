"""Connector sync: fetch external items and ingest them as Documents.

Items are stored through the same storage + ingestion pipeline as uploads
(Supabase/MinIO/local → extraction → chunking → embeddings → Qdrant), so connector
content lands in the same knowledge base, search and RAG paths.

Deduplication: documents are keyed by org + deterministic filename
"<type>/<external_id>.txt"; unchanged content (sha256) is skipped.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

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


def sync_data_source(db: Session, source: DataSource, job: ConnectorSyncJob) -> dict[str, Any]:
    """Run one sync. Updates job counters/status in-place and commits."""
    connector = get_connector(source.type)
    config = parse_config(source.config)
    try:
        credentials = decrypt_credentials(source.credentials_encrypted)
    except Exception as e:  # noqa: BLE001 — surfaced in job, not a 500
        job.status = "failed"
        job.error = f"Credential decryption failed: {e}"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        source.status = "error"
        source.last_sync_status = "failed"
        source.last_error = job.error
        db.commit()
        return {"status": "failed", "error": job.error}

    ctx = ConnectorContext(config=config, credentials=credentials)
    job.status = "running"
    db.commit()

    try:
        connector.validate(ctx)
        items = list(connector.fetch(ctx, max_items=int(config.get("max_items", DEFAULT_MAX_ITEMS))))
    except ConnectorError as e:
        job.status = "failed"
        job.error = str(e)[:500]
        job.finished_at = datetime.now(timezone.utc)
        source.status = "error"
        source.last_sync_status = "failed"
        source.last_error = job.error
        db.commit()
        return {"status": "failed", "error": job.error}

    job.fetched = len(items)
    for item in items:
        try:
            content = item.data if item.data is not None else (item.text or "").encode("utf-8")
            content_hash = item.content_hash()
            extension = _item_extension(item)
            filename = build_connector_filename(source.type, item.external_id, extension)
            title = item.title or Path(filename).stem
            content_type = item.mime or "text/plain"

            existing = (
                db.query(Document)
                .filter(
                    Document.organization_id == source.organization_id,
                    Document.filename == filename,
                )
                .first()
            )
            if existing is not None:
                meta_existing = existing.doc_metadata or "{}"
                if content_hash in meta_existing:
                    job.skipped += 1
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
            job.ingested += 1
        except Exception as e:  # noqa: BLE001 — per-item failure must not kill the sync
            db.rollback()
            job.failed += 1
            logger.warning("connector item ingestion failed (%s/%s): %s", source.type, item.external_id, e)

    job.status = "succeeded"
    job.finished_at = datetime.now(timezone.utc)
    source.status = "error" if job.failed and not job.ingested and not job.skipped else "active"
    source.last_synced_at = datetime.now(timezone.utc)
    source.last_sync_status = "succeeded" if not job.failed else "partial"
    source.last_error = None if not job.failed else f"{job.failed} item(s) failed"
    db.commit()
    return {
        "status": "succeeded",
        "fetched": job.fetched,
        "ingested": job.ingested,
        "skipped": job.skipped,
        "failed": job.failed,
    }


def run_sync_by_id(db: Session, source_id: uuid.UUID) -> dict[str, Any]:
    """Run a sync for a data source by id (used by worker task / background path)."""
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
