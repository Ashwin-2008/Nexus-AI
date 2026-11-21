"""Prometheus metrics for RAG (uses the existing prometheus_client dependency)."""
from __future__ import annotations

from typing import Any

try:
    from prometheus_client import Counter, Histogram
except Exception:  # pragma: no cover - prometheus optional in minimal envs
    Counter = None  # type: ignore[assignment]
    Histogram = None  # type: ignore[assignment]


_METRICS: dict[str, Any] = {}
if Counter is not None and Histogram is not None:  # pragma: no branch
    _METRICS = {
        "queries": Counter("nexus_rag_queries_total", "RAG queries", ["mode", "answer_mode"]),
        "retrieval_seconds": Histogram("nexus_rag_retrieval_seconds", "Retrieval duration", ["mode"]),
        "generation_seconds": Histogram("nexus_rag_generation_seconds", "Generation duration", ["answer_mode"]),
        "ingestion_seconds": Histogram("nexus_rag_ingestion_seconds", "Ingestion duration"),
        "citations": Histogram("nexus_rag_citations", "Citations per answer"),
        "verification": Counter("nexus_rag_verification_total", "Verification outcomes", ["status"]),
        "provider_errors": Counter("nexus_rag_provider_errors_total", "Provider errors", ["component"]),
    }


def record_query(mode: str, answer_mode: str) -> None:
    if "queries" in _METRICS:
        _METRICS["queries"].labels(mode=mode, answer_mode=answer_mode).inc()


def record_retrieval(mode: str, seconds: float) -> None:
    if "retrieval_seconds" in _METRICS:
        _METRICS["retrieval_seconds"].labels(mode=mode).observe(max(0.0, seconds))


def record_generation(answer_mode: str, seconds: float) -> None:
    if "generation_seconds" in _METRICS:
        _METRICS["generation_seconds"].labels(answer_mode=answer_mode).observe(max(0.0, seconds))


def record_ingestion(seconds: float) -> None:
    if "ingestion_seconds" in _METRICS:
        _METRICS["ingestion_seconds"].observe(max(0.0, seconds))


def record_citations(count: int) -> None:
    if "citations" in _METRICS:
        _METRICS["citations"].observe(max(0, count))


def record_verification(status: str) -> None:
    if "verification" in _METRICS:
        _METRICS["verification"].labels(status=status).inc()


def record_provider_error(component: str) -> None:
    if "provider_errors" in _METRICS:
        _METRICS["provider_errors"].labels(component=component).inc()
