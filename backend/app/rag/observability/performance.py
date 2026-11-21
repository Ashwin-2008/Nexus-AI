"""Performance measurement helpers."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def timed(target: dict[str, int], key: str) -> Iterator[None]:
    started = time.monotonic()
    try:
        yield
    finally:
        target[key] = int((time.monotonic() - started) * 1000)


def millis_since(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
