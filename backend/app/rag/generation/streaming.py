"""Streaming helper (SSE-ready events)."""
from typing import Any, Iterator

from app.rag.generation.generator import Generator

__all__ = ["stream_answer"]


def stream_answer(generator: Generator, query: str, bundle, analysis=None) -> Iterator[dict[str, Any]]:
    yield from generator.stream(query, bundle, analysis)
