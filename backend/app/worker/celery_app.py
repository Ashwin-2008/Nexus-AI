"""Celery worker application and task registration."""
from __future__ import annotations

import os

try:
    from celery import Celery
except Exception:  # pragma: no cover - celery optional in local dev
    Celery = None  # type: ignore


def _make_app():
    if Celery is None:
        return None
    broker = os.getenv("REDIS_URL", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
    backend = os.getenv("CELERY_RESULT_BACKEND", broker)
    app = Celery("nexus_ai", broker=broker, backend=backend, include=["app.worker.tasks"])
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_default_queue="default",
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_routes={
            "app.worker.tasks.*": {"queue": "ingestion"},
        },
    )
    if broker.startswith("rediss://"):
        # Managed Redis endpoints (e.g. Upstash) use TLS. Celery requires the
        # SSL parameters to be given explicitly for rediss:// URLs; Upstash
        # serves a certificate signed by a public CA, so verification settings
        # are left at defaults and only cert-reqs is relaxed.
        ssl_options = {"ssl_cert_reqs": None}
        app.conf.broker_use_ssl = ssl_options
        app.conf.redis_backend_use_ssl = ssl_options
    return app


celery_app = _make_app()
