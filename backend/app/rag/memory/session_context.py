"""Per-request session context (trace id, conversation, warnings, timings)."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionContext:
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    conversation_id: str | None = None
    organization_id: str | None = None
    user_id: str | None = None
    started_at: float = field(default_factory=time.monotonic)
    warnings: list[str] = field(default_factory=list)
    stages: dict[str, int] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=dict)

    def mark(self, stage: str, started: float) -> int:
        elapsed = int((time.monotonic() - started) * 1000)
        self.stages[stage] = elapsed
        return elapsed

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000)
