from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import engine
from app.models.user import User

router = APIRouter()

try:
    import redis as redis_lib
except Exception:  # pragma: no cover
    redis_lib = None

try:
    from qdrant_client import QdrantClient
except Exception:  # pragma: no cover
    QdrantClient = None


def _check_db() -> str:
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return "healthy"
    except Exception:
        return "unhealthy"


def _check_redis() -> str:
    if redis_lib is None:
        return "unavailable"
    try:
        client = redis_lib.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return "healthy"
    except Exception:
        return "unhealthy"


def _check_qdrant() -> str:
    if QdrantClient is None:
        return "unavailable"
    try:
        client = QdrantClient(url=settings.qdrant_url, timeout=1)
        client.get_collections()
        return "healthy"
    except Exception:
        return "unhealthy"


def _check_storage() -> str:
    try:
        from app.services.storage import get_storage_backend

        return get_storage_backend().health_check()
    except Exception:
        return "unhealthy"


def _check_worker() -> str:
    # Worker is healthy if at least one Celery worker responds, or if queueing infra is unavailable
    # we report degraded/unavailable rather than failing the API.
    try:
        from app.worker.celery_app import celery_app
    except Exception:
        celery_app = None  # type: ignore
    if celery_app is None:
        return "unavailable"
    try:
        insp = celery_app.control.inspect(timeout=0.5)
        if insp is None:
            return "unhealthy"
        pong = insp.ping() or {}
        return "healthy" if pong else "unhealthy"
    except Exception:
        # broker unreachable or no workers; treat as unhealthy signal but not API-fatal
        return "unhealthy"


@router.get("/health")
async def health() -> Dict[str, Any]:
    services = {
        "api": "healthy",
        "database": _check_db(),
        "redis": _check_redis(),
        "qdrant": _check_qdrant(),
        "storage": _check_storage(),
        "worker": _check_worker(),
    }
    # overall: unhealthy if DB down; degraded if critical up but optional components unhealthy
    overall = "healthy"
    if services["database"] != "healthy":
        overall = "unhealthy"
    elif any(v == "unhealthy" for k, v in services.items() if k != "api"):
        overall = "degraded"
    return {"status": overall, "services": services}


@router.get("/system/capabilities")
def system_capabilities(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Secret-free runtime capability inventory for operators and the UI.

    This is intentionally authenticated but not admin-only: every organization
    member needs to know which retrieval, generation and connector capabilities
    are actually configured for the deployment.
    """
    from app.rag.config import RagConfig

    config = RagConfig.from_settings()
    description = config.describe()
    try:
        from app.services.llm import llm_available

        llm_ok = llm_available()
    except Exception:
        llm_ok = False
    embedding_provider = str(settings.embedding_provider or "hashing")
    return {
        "providers": {
            "llm": {
                "provider": settings.llm_provider,
                "available": llm_ok,
                "extractive_fallback": True,
                "model": settings.llm_model or "(provider default)",
            },
            "embeddings": {
                "provider": embedding_provider,
                "model": settings.embedding_model or settings.embedding_local_model,
                "dimensions": settings.embedding_dimensions or None,
                "semantic": embedding_provider != "hashing",
            },
            "vector": {
                "backend": settings.vector_index_backend,
                "collection": settings.qdrant_collection,
            },
            "storage": {
                "backend": settings.storage_backend,
            },
        },
        "retrieval": description["retrieval"],
        "chunking": description["chunking"],
        "verification": description["verification"],
        "worker": {
            "celery_enabled": bool(settings.ingestion_use_celery),
            "max_ingestion_retries": settings.ingestion_max_retries,
        },
        "connectors": ["postgres", "mysql", "rest", "website", "github", "gdrive", "email"],
        "warnings": description["warnings"],
        "organization_id": str(current_user.organization_id),
    }
