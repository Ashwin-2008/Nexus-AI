"""RAG exception hierarchy.

Every error is explicit: the pipeline never silently degrades into fabricated
evidence. Callers can map these to HTTP responses without guessing.
"""
from __future__ import annotations


class RagError(RuntimeError):
    """Base class for all RAG subsystem errors."""


class ConfigurationError(RagError):
    """Invalid or missing RAG configuration."""


class ValidationError(RagError):
    """Input/source failed validation (size, type, structure)."""


class UnsupportedDocumentError(ValidationError):
    """No loader/parser for the supplied document type."""


class ParsingError(RagError):
    """Document could not be parsed into text."""


class OcrUnavailableError(ParsingError):
    """Scanned/image-only content requires OCR, which is not configured."""


class ChunkingError(RagError):
    """Chunking could not produce meaningful chunks."""


class EmbeddingUnavailableError(RagError):
    """The configured embedding provider is unavailable or misconfigured."""


class EmbeddingDimensionError(EmbeddingUnavailableError):
    """Provider returned vectors whose dimension does not match configuration."""


class VectorStoreUnavailableError(RagError):
    """The vector store (Qdrant) is unavailable."""


class LexicalIndexUnavailableError(RagError):
    """The lexical index could not be queried."""


class RetrievalError(RagError):
    """Retrieval failed irrecoverably."""


class RerankError(RagError):
    """A configured reranker failed."""


class RerankerUnavailableError(RerankError):
    """The requested reranker is not installed/configured."""


class GenerationError(RagError):
    """Answer generation failed and no grounded fallback applies."""


class CitationError(RagError):
    """A citation could not be resolved to authorized source material."""


class VerificationError(RagError):
    """Answer verification failed."""


class PermissionFilteredError(RagError):
    """A retrieved item was rejected by authorization checks."""


class IngestionError(RagError):
    """Ingestion failed; durable job state carries the details."""


class EvaluationError(RagError):
    """An evaluation run could not be completed."""
