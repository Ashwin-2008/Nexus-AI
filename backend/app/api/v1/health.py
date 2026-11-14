from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from app.core.config import settings
from app.db.session import engine

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
