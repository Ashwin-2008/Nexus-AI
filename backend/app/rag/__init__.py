"""NEXUS AI modular RAG subsystem.

Public entry points:
- ``RagService`` / ``RagOrchestrator`` — canonical retrieval + grounded answer
  pipeline used by the chat API, RAG API and specialist agents.
- ``IngestionPipeline`` — validation → parsing → chunking → embeddings → index.
- typed request/response contracts in ``app.rag.types``.

Nothing in this package fabricates embeddings, evidence or citations; provider
and backend failures are raised explicitly and surfaced to callers.
"""
from app.rag.config import RagConfig, get_rag_config
from app.rag.exceptions import RagError
from app.rag.orchestration.rag_pipeline import RagOrchestrator
from app.rag.orchestration.service import RagService, get_rag_service
from app.rag.types import (
    Citation,
    EvidenceChunk,
    IngestionOutcome,
    QueryAnalysis,
    RagRequest,
    RagResponse,
    RagScope,
    RetrievalFilters,
    RetrievalResult,
    SpecialistRequest,
    SpecialistResponse,
    VerificationReport,
)

__all__ = [
    "Citation",
    "EvidenceChunk",
    "IngestionOutcome",
    "QueryAnalysis",
    "RagConfig",
    "RagError",
    "RagOrchestrator",
    "RagRequest",
    "RagResponse",
    "RagScope",
    "RagService",
    "RetrievalFilters",
    "RetrievalResult",
    "SpecialistRequest",
    "SpecialistResponse",
    "VerificationReport",
    "get_rag_config",
    "get_rag_service",
]
