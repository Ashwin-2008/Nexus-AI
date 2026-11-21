"""Observability for the RAG pipeline."""
from app.rag.observability.logging import get_rag_logger, log_event
from app.rag.observability.metrics import (
    record_citations,
    record_generation,
    record_ingestion,
    record_provider_error,
    record_query,
    record_retrieval,
    record_verification,
)
from app.rag.observability.performance import millis_since, timed
from app.rag.observability.tracing import Trace, new_trace_id

__all__ = [
    "Trace",
    "get_rag_logger",
    "log_event",
    "millis_since",
    "new_trace_id",
    "record_citations",
    "record_generation",
    "record_ingestion",
    "record_provider_error",
    "record_query",
    "record_retrieval",
    "record_verification",
    "timed",
]
