"""RAG API: query, streaming, ingestion, index operations, evaluation.

Retrieval/generation routes call the same ``RagService`` used by specialists and
chat; nothing here re-implements a pipeline. Existing ``/documents`` and
``/search`` endpoints remain the canonical upload and search surfaces.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.connector import DataSource
from app.models.document import Document, DocumentChunk, IngestionJob
from app.models.rag import RagEvaluationRun
from app.models.user import User
from app.rag.config import RagConfig
from app.rag.constants import PIPELINE_VERSION
from app.rag.evaluation.datasets import load_dataset, parse_items
from app.rag.evaluation.evaluator import Evaluator
from app.rag.evaluation.reports import list_reports, persist_report, read_report
from app.rag.exceptions import ConfigurationError, EvaluationError, RagError, ValidationError as RagValidationError
from app.rag.indexes.index_manager import IndexManager
from app.rag.ingestion.orchestrator import IngestionOrchestrator
from app.rag.orchestration.service import RagService
from app.rag.security import scope_from_user
from app.rag.types import RagRequest, RetrievalFilters
from app.schemas.rag import (
    RagEvaluationIn,
    RagFiltersIn,
    RagIngestTextIn,
    RagQueryIn,
    RagRetrievalIn,
)

router = APIRouter(prefix="/rag", tags=["rag"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)})
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail={"code": "forbidden", "message": str(exc)})
    if isinstance(exc, (RagValidationError, EvaluationError)):
        return HTTPException(status_code=422, detail={"code": "validation_error", "message": str(exc)})
    if isinstance(exc, ConfigurationError):
        return HTTPException(status_code=400, detail={"code": "configuration_error", "message": str(exc)})
    if isinstance(exc, RagError):
        return HTTPException(status_code=400, detail={"code": "rag_error", "message": str(exc)})
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=409, detail={"code": "conflict", "message": str(exc)[:300]})
    return HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)[:300]})


def _require_admin(user: User) -> None:
    role = user.role.name if getattr(user, "role", None) else "member"
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Administrator role required"},
        )


def _filters(payload: RagFiltersIn | None) -> RetrievalFilters:
    if payload is None:
        return RetrievalFilters()
    return RetrievalFilters(
        document_ids=tuple(payload.document_ids),
        source_ids=tuple(payload.source_ids),
        source_types=tuple(payload.source_types),
        document_version=payload.document_version,
        metadata=tuple(sorted(payload.metadata.items())),
    )


def _request(body: RagQueryIn, scope) -> RagRequest:
    return RagRequest(
        query=body.query,
        scope=scope,
        filters=_filters(body.filters),
        mode=body.mode,
        top_k=body.top_k,
        rerank=body.rerank,
        verify=body.verify,
        conversation_id=body.conversation_id,
        max_context_tokens=body.max_context_tokens,
        include_evidence=body.include_evidence,
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _document_summary(document: Document) -> dict[str, Any]:
    status_value = document.status.value if hasattr(document.status, "value") else str(document.status)
    return {
        "id": str(document.id),
        "filename": document.filename,
        "content_type": document.content_type,
        "file_size": document.file_size,
        "status": status_value,
        "version": document.version,
        "source_id": str(document.source_id) if document.source_id else None,
        "access_scope": document.access_scope,
        "uploaded_by": str(document.uploaded_by) if document.uploaded_by else None,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "error_message": document.error_message,
    }


@router.post("/query")
def rag_query(
    body: RagQueryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    scope = scope_from_user(current_user)
    try:
        response = RagService().orchestrator.answer(db, scope, _request(body, scope))
    except Exception as exc:  # noqa: BLE001 — translated to an HTTP error
        raise _http_error(exc) from exc
    return response.to_dict(include_evidence_text=body.include_evidence)


@router.post("/query/stream")
def rag_query_stream(
    body: RagQueryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    scope = scope_from_user(current_user)
    request = _request(body, scope)

    def event_stream():
        try:
            for event in RagService().orchestrator.stream(db, scope, request):
                yield _sse(event["event"], event["data"])
        except Exception as exc:  # noqa: BLE001 — stream must always terminate with an event
            yield _sse("error", {"code": "rag_stream_failed", "message": str(exc)[:300]})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/retrieval/test")
def rag_retrieval_test(
    body: RagRetrievalIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    scope = scope_from_user(current_user)
    try:
        result = RagService().retrieve(
            db,
            scope,
            body.query,
            filters=_filters(body.filters),
            mode=body.mode,
            top_k=body.top_k,
            rerank=body.rerank,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return {
        "query": result.query,
        "mode": result.mode,
        "queries_used": result.queries_used,
        "reranker": result.reranker,
        "timings": result.timings,
        "filtered_count": result.filtered_count,
        "warnings": result.warnings,
        "evidence": [item.to_dict(include_text=body.include_text) for item in result.evidence],
    }


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
def rag_ingest_text(
    body: RagIngestTextIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        document, job = IngestionOrchestrator().ingest_text(
            db,
            current_user,
            content=body.content,
            filename=body.filename,
            title=body.title,
            content_type=body.content_type,
            source_id=body.source_id,
            access_scope=body.access_scope,
            metadata=body.metadata,
            background_tasks=background_tasks,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return {
        "document": _document_summary(document),
        "job": IngestionOrchestrator.job_status(db, current_user, job.id),
    }


@router.post("/ingest/file", status_code=status.HTTP_202_ACCEPTED)
async def rag_ingest_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    source_id: uuid.UUID | None = Form(default=None),
    access_scope: str = Form(default="organization"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    config = RagConfig.from_settings()
    data = await file.read()
    if len(data) > config.max_document_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "file_too_large",
                "message": f"file exceeds the {config.max_document_bytes} byte limit",
            },
        )
    try:
        document, job = IngestionOrchestrator(config).ingest_file(
            db,
            current_user,
            filename=file.filename or "upload.bin",
            data=data,
            content_type=file.content_type,
            title=title,
            source_id=source_id,
            access_scope=access_scope,
            background_tasks=background_tasks,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return {
        "document": _document_summary(document),
        "job": IngestionOrchestrator.job_status(db, current_user, job.id),
    }


@router.get("/ingestions/{job_id}")
def rag_ingestion_status(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return IngestionOrchestrator.job_status(db, current_user, job_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.post("/documents/{document_id}/reindex", status_code=status.HTTP_202_ACCEPTED)
def rag_reindex_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        document, job = IngestionOrchestrator().reindex_document(
            db, current_user, document_id, background_tasks=background_tasks
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return {"document": _document_summary(document), "job": IngestionOrchestrator.job_status(db, current_user, job.id)}


@router.delete("/documents/{document_id}/index")
def rag_delete_document_index(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return IngestionOrchestrator().delete_document_index(db, current_user, document_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.delete("/documents/{document_id}")
def rag_delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return IngestionOrchestrator().delete_document(db, current_user, document_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.get("/documents/{document_id}/sync")
def rag_document_sync(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    document = db.get(Document, document_id)
    if document is None or document.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Document not found"})
    try:
        return IndexManager().document_sync(db, current_user.organization_id, document_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.get("/sources")
def rag_sources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    documents = (
        db.query(Document)
        .filter(Document.organization_id == current_user.organization_id)
        .order_by(Document.updated_at.desc())
        .all()
    )
    chunk_counts = dict(
        db.query(DocumentChunk.document_id, func.count(DocumentChunk.id))
        .filter(DocumentChunk.organization_id == current_user.organization_id)
        .group_by(DocumentChunk.document_id)
        .all()
    )
    connectors = (
        db.query(DataSource)
        .filter(DataSource.organization_id == current_user.organization_id)
        .order_by(DataSource.created_at.desc())
        .all()
    )
    return {
        "documents": [
            {**_document_summary(document), "chunk_count": int(chunk_counts.get(document.id, 0))}
            for document in documents
        ],
        "connectors": [
            {
                "id": str(source.id),
                "name": source.name,
                "type": source.type,
                "status": source.status,
                "last_synced_at": source.last_synced_at,
                "last_error": source.last_error,
            }
            for source in connectors
        ],
    }


@router.get("/status")
def rag_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    scope = scope_from_user(current_user)
    manager = IndexManager()
    try:
        index = manager.status(db, scope)
        sync = manager.organization_sync(db, current_user.organization_id, limit=25)
    except Exception as exc:  # noqa: BLE001 — report component failures truthfully
        index = {"error": str(exc)[:300]}
        sync = []
    by_status = dict(
        db.query(Document.status, func.count(Document.id))
        .filter(Document.organization_id == current_user.organization_id)
        .group_by(Document.status)
        .all()
    )
    chunk_count = (
        db.query(func.count(DocumentChunk.id))
        .filter(DocumentChunk.organization_id == current_user.organization_id)
        .scalar()
        or 0
    )
    config = RagConfig.from_settings()
    provider = (config.embedding_provider or "").strip().lower()
    semantic = provider not in {"hashing", "hash"}
    embedding_warning = None if semantic else (
        "EMBEDDING_PROVIDER=hashing stores non-semantic vectors. Retrieval is "
        "keyword-only, so paraphrased questions may return no evidence. Configure "
        "a real embeddings provider (and matching EMBEDDING_DIMENSIONS) for semantic search."
    )
    return {
        "organization_id": str(current_user.organization_id),
        "documents": {
            "total": sum(int(value) for value in by_status.values()),
            "by_status": {
                (key.value if hasattr(key, "value") else str(key)): int(value)
                for key, value in by_status.items()
            },
            "chunks": int(chunk_count),
        },
        "index": index,
        "sync": {
            "sampled_documents": len(sync),
            "out_of_sync": [item for item in sync if not item.get("in_sync")],
        },
        "pipeline_version": PIPELINE_VERSION,
        "embedding": {
            "provider": config.embedding_provider,
            "model": config.embedding_model or "(provider default)",
            "dimensions": config.embedding_dimensions or None,
            "semantic": semantic,
            "warning": embedding_warning,
        },
        "capabilities": {
            "modes": ["hybrid", "dense", "sparse"],
            "default_mode": config.retrieval_mode,
            "effective_mode": (
                "sparse"
                if not semantic and config.retrieval_mode in {"hybrid", "dense"}
                else config.retrieval_mode
            ),
            "verification": config.verification,
            "reranker": config.reranker,
        },
    }


@router.get("/config")
def rag_config(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    config = RagConfig.from_settings()
    return config.describe()


@router.get("/health")
def rag_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    scope = scope_from_user(current_user)
    try:
        return {"status": "ok", "index": IndexManager().status(db, scope)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "error": str(exc)[:300]}


@router.post("/evaluation/run")
def rag_evaluation_run(
    body: RagEvaluationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    scope = scope_from_user(current_user)
    try:
        if body.dataset:
            items = load_dataset(body.dataset)
        elif body.items:
            items = parse_items(body.items)
        else:
            raise EvaluationError("provide either a dataset fixture name or inline items")
        report = Evaluator().run(
            db, scope, items, name=body.name, mode=body.mode, k=body.k, generate=body.generate
        )
        payload = report.to_dict()
        if body.persist:
            row = persist_report(db, scope, report, dataset_name=body.dataset or "inline")
            payload["run_id"] = str(row.id)
        return payload
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.get("/evaluations")
def rag_evaluations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    rows = list_reports(db, current_user.organization_id)
    return {"items": [read_report(row) for row in rows]}


@router.get("/evaluations/{run_id}")
def rag_evaluation_detail(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    row = db.get(RagEvaluationRun, run_id)
    if row is None or row.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Evaluation run not found"})
    return read_report(row)
