"""Lightweight tracing helpers.

No external tracing backend is configured in this repository; traces are
structured records that can be logged or persisted by the caller. A trace id is
attached to every RAG query and remains stable across specialist steps.
"""
from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass
class Trace:
    trace_id: str = field(default_factory=new_trace_id)
    spans: list[dict[str, Any]] = field(default_factory=list)

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[dict[str, Any]]:
        started = time.monotonic()
        span: dict[str, Any] = {"name": name, "attributes": attributes}
        try:
            yield span
        finally:
            span["duration_ms"] = int((time.monotonic() - started) * 1000)
            self.spans.append(span)

    def summary(self) -> dict[str, Any]:
        return {"trace_id": self.trace_id, "spans": self.spans}
