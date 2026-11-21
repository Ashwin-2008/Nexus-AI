"""Ingestion pipeline components.

Kept import-light to avoid a cycle: ``app.services.ingestion_service`` imports
validators, and the pipeline imports storage helpers from that service.
"""
from typing import Any

__all__ = ["IngestionPipeline", "chunk_content_hash"]


def __getattr__(name: str) -> Any:  # pragma: no cover - import shim
    if name == "IngestionPipeline":
        from app.rag.ingestion.pipeline import IngestionPipeline

        return IngestionPipeline
    if name == "chunk_content_hash":
        from app.rag.ingestion.deduplication import chunk_content_hash

        return chunk_content_hash
    raise AttributeError(name)
