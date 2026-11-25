"""Data source (connector) API: CRUD + test + sync, strictly org-scoped.

Credentials are accepted on create/update, encrypted at rest, and never
returned by the API (masked shapes only). Sync jobs run through the standard
ingestion pipeline so connector content is searchable/answerable like uploads.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.connector import ConnectorSyncJob, DataSource
from app.models.user import User
from app.services.connectors import (
    CONNECTOR_TYPES,
    ConnectorContext,
    ConnectorError,
    get_connector,
    parse_config,
)
from app.services.connector_presets import (
    GuidedConfigError,
    build_guided_connection,
    guided_schema,
)
from app.services.connectors_service import (
    active_sync_job,
    reap_stale_sync_jobs,
    run_sync_job_by_id,
)
from app.services.credentials import (
    CredentialError,
    decrypt_credentials,
    encrypt_credentials,
    mask_credentials,
)

router = APIRouter(prefix="/sources", tags=["sources"])


# -- schemas -----------------------------------------------------------------


class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., min_length=1, max_length=32)
    config: dict = {}
    credentials: dict = {}


class SourceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    config: dict | None = None
    credentials: dict | None = None
    status: str | None = Field(None, pattern="^(active|disabled)$")


class GuidedSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., min_length=1, max_length=32)
    values: dict = {}


class SourceRead(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    status: str
    config: dict
    credentials_masked: dict | None
    last_synced_at: object | None
    last_sync_status: str | None
    last_error: str | None
    created_at: object
    updated_at: object


class SyncJobRead(BaseModel):
    id: uuid.UUID
    data_source_id: uuid.UUID
    status: str
    fetched: int
    ingested: int
    skipped: int
    failed: int
    error: str | None
    started_at: object
    finished_at: object | None


# -- helpers -----------------------------------------------------------------


def _get_owned_source(db: Session, source_id: uuid.UUID, user: User) -> DataSource:
    source = db.get(DataSource, source_id)
    if source is None or source.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Data source not found"})
    return source


def _source_to_read(source: DataSource) -> SourceRead:
    try:
        masked = mask_credentials(decrypt_credentials(source.credentials_encrypted))
    except CredentialError:
        masked = None
    return SourceRead(
        id=source.id,
        name=source.name,
        type=source.type,
        status=source.status,
        config=parse_config(source.config),
        credentials_masked=masked,
        last_synced_at=source.last_synced_at,
        last_sync_status=source.last_sync_status,
        last_error=source.last_error,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def _job_to_read(job: ConnectorSyncJob) -> SyncJobRead:
    return SyncJobRead(
        id=job.id,
        data_source_id=job.data_source_id,
        status=job.status,
        fetched=job.fetched,
        ingested=job.ingested,
        skipped=job.skipped,
        failed=job.failed,
        error=job.error,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )



def _new_job(db: Session, source: DataSource) -> ConnectorSyncJob:
    job = ConnectorSyncJob(data_source_id=source.id, organization_id=source.organization_id, status="queued")
    db.add(job)
    db.commit()
    return job


# -- endpoints -----------------------------------------------------------------


@router.post("", response_model=SourceRead, status_code=201)
def create_source(
    body: SourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.type not in CONNECTOR_TYPES:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_type", "message": f"Unknown connector type '{body.type}' (valid: {', '.join(CONNECTOR_TYPES)})"},
        )
    connector = get_connector(body.type)
    ctx = ConnectorContext(config=body.config, credentials=body.credentials)
    try:
        connector.validate(ctx)
    except ConnectorError as e:
        raise HTTPException(status_code=400, detail={"code": "invalid_config", "message": str(e)})

    source = DataSource(
        organization_id=current_user.organization_id,
        created_by=current_user.id,
        name=body.name,
        type=body.type,
        status="active",
        config=json.dumps(body.config, ensure_ascii=False),
        credentials_encrypted=encrypt_credentials(body.credentials) if body.credentials else None,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _source_to_read(source)


@router.get("", response_model=list[SourceRead])
def list_sources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(DataSource)
        .filter(DataSource.organization_id == current_user.organization_id)
        .order_by(DataSource.created_at.desc())
        .all()
    )
    return [_source_to_read(s) for s in rows]


@router.get("/guided/schema")
def guided_source_schema(current_user: User = Depends(get_current_user)):
    """Form definition for provider-aware source creation (no secrets)."""
    return guided_schema()


@router.post("/guided", response_model=SourceRead, status_code=201)
def create_guided_source(
    body: GuidedSourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a source from only the questions a user can answer."""
    try:
        connector_type, config, credentials = build_guided_connection(body.type, body.values)
    except GuidedConfigError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_config", "message": str(exc)})
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_config", "message": str(exc)})

    source = DataSource(
        organization_id=current_user.organization_id,
        created_by=current_user.id,
        name=body.name.strip(),
        type=connector_type,
        status="active",
        config=json.dumps(config, ensure_ascii=False),
        credentials_encrypted=encrypt_credentials(credentials) if credentials else None,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _source_to_read(source)


@router.get("/{source_id}", response_model=SourceRead)
def get_source(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _source_to_read(_get_owned_source(db, source_id, current_user))


@router.patch("/{source_id}", response_model=SourceRead)
def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = _get_owned_source(db, source_id, current_user)
    if body.name is not None:
        source.name = body.name
    if body.status is not None:
        source.status = body.status
    if body.config is not None or body.credentials is not None:
        merged_config = body.config if body.config is not None else parse_config(source.config)
        merged_creds = (
            body.credentials
            if body.credentials is not None
            else decrypt_credentials(source.credentials_encrypted)
        )
        try:
            get_connector(source.type).validate(
                ConnectorContext(config=merged_config, credentials=merged_creds)
            )
        except (ConnectorError, CredentialError) as e:
            raise HTTPException(status_code=400, detail={"code": "invalid_config", "message": str(e)})
        source.config = json.dumps(merged_config, ensure_ascii=False)
        if body.credentials is not None:
            source.credentials_encrypted = encrypt_credentials(body.credentials)
    db.commit()
    db.refresh(source)
    return _source_to_read(source)


@router.delete("/{source_id}", status_code=204)
def delete_source(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = _get_owned_source(db, source_id, current_user)
    # Delete exactly the documents this source created. A filename prefix is
    # not safe: two sources of the same type can share an external id.
    from app.models.document import Document
    from app.services.vector_index import get_vector_index

    docs = (
        db.query(Document)
        .filter(
            Document.organization_id == current_user.organization_id,
            Document.source_id == source.id,
        )
        .all()
    )
    try:
        index = get_vector_index()
        for doc in docs:
            try:
                index.delete_document(str(current_user.organization_id), str(doc.id))
            except Exception:  # noqa: BLE001 — vector cleanup best-effort, rows still removed
                pass
        for doc in docs:
            db.delete(doc)
    except Exception:  # noqa: BLE001 — DB cleanup must proceed even if vector backend unavailable
        for doc in docs:
            db.delete(doc)
    db.delete(source)
    db.commit()
    return None


@router.post("/{source_id}/test")
def test_source(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = _get_owned_source(db, source_id, current_user)
    connector = get_connector(source.type)
    ctx = ConnectorContext(
        config=parse_config(source.config),
        credentials=decrypt_credentials_safe(source.credentials_encrypted),
    )
    try:
        result = connector.test_connection(ctx)
    except ConnectorError as e:
        source.status = "error"
        source.last_error = str(e)[:2000]
        db.commit()
        return {"ok": False, "error": str(e)}
    if not result.get("ok"):
        message = str(result.get("error") or "Connection test returned no readable data")
        source.status = "error"
        source.last_error = message[:2000]
        db.commit()
        return {"ok": False, "error": message}
    source.status = "active"
    source.last_error = None
    db.commit()
    return {"ok": True, "type": source.type, "sample": result.get("sample")}


def decrypt_credentials_safe(token: str | None) -> dict:
    if not token:
        return {}
    try:
        return decrypt_credentials(token)
    except CredentialError:
        return {}


@router.post("/{source_id}/sync", response_model=SyncJobRead, status_code=202)
def trigger_sync(
    source_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = _get_owned_source(db, source_id, current_user)
    if source.status == "disabled":
        raise HTTPException(status_code=409, detail={"code": "disabled", "message": "Data source is disabled"})

    # Recover jobs abandoned by an earlier API restart before deciding whether
    # this click is a duplicate of a genuinely running sync.
    reap_stale_sync_jobs(db, source)
    existing = active_sync_job(db, source.id)
    if existing is not None:
        return _job_to_read(existing)

    job = _new_job(db, source)
    # Prefer a real Celery worker. If none is consuming the queue, run the sync
    # as an in-process background task so the job never sits queued forever.
    from app.worker.tasks import enqueue_connector_sync

    try:
        task_id = enqueue_connector_sync(db, source, job)
    except Exception:  # noqa: BLE001 — queue probing must never fail the request
        task_id = None
    if not task_id:
        background_tasks.add_task(run_sync_job_by_id, source.id, job.id)
    db.refresh(job)
    return _job_to_read(job)


@router.get("/{source_id}/syncs", response_model=list[SyncJobRead])
def list_syncs(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = _get_owned_source(db, source_id, current_user)
    reap_stale_sync_jobs(db, source)
    rows = (
        db.query(ConnectorSyncJob)
        .filter(ConnectorSyncJob.data_source_id == source.id)
        .order_by(ConnectorSyncJob.started_at.desc())
        .limit(20)
        .all()
    )
    return [_job_to_read(j) for j in rows]
