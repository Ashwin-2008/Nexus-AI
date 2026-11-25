"""Stable constants for the RAG subsystem.

Keep tunables in :mod:`app.rag.config` (environment-backed); only invariants
that other modules import belong here.
"""
from __future__ import annotations

PIPELINE_VERSION = "1.0.0"

# Finite, ordered verification states. Never imply mathematical certainty.
VERIFICATION_SUPPORTED = "supported"
VERIFICATION_PARTIALLY_SUPPORTED = "partially_supported"
VERIFICATION_UNSUPPORTED = "unsupported"
VERIFICATION_CONFLICTING = "conflicting_evidence"
VERIFICATION_INSUFFICIENT = "insufficient_evidence"

VERIFICATION_STATUSES = (
    VERIFICATION_SUPPORTED,
    VERIFICATION_PARTIALLY_SUPPORTED,
    VERIFICATION_UNSUPPORTED,
    VERIFICATION_CONFLICTING,
    VERIFICATION_INSUFFICIENT,
)

# Answer modes (mirrors the pre-existing chat contract).
ANSWER_MODE_LLM = "llm"
ANSWER_MODE_EXTRACTIVE = "extractive"
ANSWER_MODE_NO_EVIDENCE = "no_evidence"

RETRIEVAL_MODES = ("hybrid", "dense", "sparse")

CHUNK_STRATEGIES = ("recursive", "token", "sentence", "semantic", "parent_child")

# Extensions the ingestion pipeline can parse. Kept in sync with
# app.services.processing.FileExtractor and ingestion validation.
SUPPORTED_EXTENSIONS = (
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".xlsx",
    ".pptx",
    ".html",
    ".htm",
    ".json",
    ".eml",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".tif",
    ".tiff",
)

# Content types accepted by upload validation when the extension is supported.
SUPPORTED_CONTENT_TYPES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/html",
    "application/json",
    "message/rfc822",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/octet-stream",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/tiff",
)

# Prompt-injection defence: retrieved documents are untrusted data. These
# markers are stripped from content before it is embedded in a prompt.
PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard previous instructions",
    "system prompt",
    "you are now",
    "reveal your instructions",
)

DEFAULT_CONTEXT_DELIMITERS = ("\n\n", ". ", "\n", " ")

# Minimum evidence required before generation is attempted.
MIN_EVIDENCE_SCORE = 0.0

# Heuristic reranker weights (documented fallback, not a trained model).
HEURISTIC_RERANK_RETRIEVAL_WEIGHT = 0.55
HEURISTIC_RERANK_COVERAGE_WEIGHT = 0.35
HEURISTIC_RERANK_PHRASE_WEIGHT = 0.10

# Reciprocal Rank Fusion constant (Cormack et al. 2009).
RRF_K = 60
