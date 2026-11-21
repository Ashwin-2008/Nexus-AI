"""Named pipeline stages used in timings, logs and traces."""
from __future__ import annotations

from enum import StrEnum


class PipelineStep(StrEnum):
    ANALYZE = "analyze"
    RETRIEVE = "retrieve"
    RERANK = "rerank"
    CONTEXT = "context"
    GENERATE = "generate"
    CITE = "cite"
    VERIFY = "verify"
    PERSIST = "persist"


STEP_ORDER = (
    PipelineStep.ANALYZE,
    PipelineStep.RETRIEVE,
    PipelineStep.RERANK,
    PipelineStep.CONTEXT,
    PipelineStep.GENERATE,
    PipelineStep.CITE,
    PipelineStep.VERIFY,
    PipelineStep.PERSIST,
)
