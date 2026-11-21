"""Structured RAG logging with secret redaction.

Document content is never logged. Only identifiers, counts, timings and
provider error summaries are emitted.
"""
from __future__ import annotations

import logging
from typing import Any

from app.rag.parsing.cleaning import redact_secrets

LOGGER_NAME = "nexus.rag"


def get_rag_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def log_event(event: str, **fields: Any) -> None:
    safe = {key: redact_secrets(value) if isinstance(value, str) else value for key, value in fields.items()}
    get_rag_logger().info(event, extra={"rag": safe})
