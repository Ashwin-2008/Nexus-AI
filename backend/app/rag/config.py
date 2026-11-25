"""RAG configuration resolution.

The single source of truth for runtime configuration remains
``app.core.config.settings`` (environment/.env). This module snapshots those
values into an immutable-ish object so pipeline components receive
configuration by injection instead of importing globals, and so tests can
construct isolated configurations.

``RagConfig.describe()`` is safe to expose over the API: it never contains
secrets.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any

from app.core.config import settings
from app.rag.constants import CHUNK_STRATEGIES, PIPELINE_VERSION, RETRIEVAL_MODES, SUPPORTED_EXTENSIONS
from app.rag.exceptions import ConfigurationError


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RagConfig:
    # Chunking
    chunk_strategy: str = "recursive"
    chunk_size: int = 900
    chunk_overlap: int = 150
    parent_chunk_size: int = 1800
    child_chunk_size: int = 450
    child_overlap: int = 80

    # Retrieval
    retrieval_mode: str = "hybrid"
    dense_top_k: int = 12
    sparse_top_k: int = 12
    hybrid_top_k: int = 16
    final_top_k: int = 8
    min_relevance: float = 0.0
    reranker: str = "auto"
    llm_verification: bool = True
    rerank_top_k: int = 8
    query_rewrite: bool = True
    multi_query: bool = True
    max_subqueries: int = 3

    # Context / generation
    context_token_budget: int = 6000
    max_context_chunks: int = 8
    context_compression: bool = False
    context_compression_max_sentences: int = 6

    # Verification
    verification: bool = True
    support_threshold: float = 0.55
    partial_threshold: float = 0.30

    # Ingestion / safety
    max_document_bytes: int = 25 * 1024 * 1024
    allowed_extensions: tuple[str, ...] = SUPPORTED_EXTENSIONS

    # Observability / memory
    query_log_enabled: bool = True
    embedding_cache_size: int = 2048
    memory_max_turns: int = 4

    # Provider identifiers (informational, no secrets)
    embedding_provider: str = "hashing"
    embedding_model: str = ""
    embedding_dimensions: int = 0
    embedding_batch_size: int = 64
    llm_provider: str = "auto"

    warnings: tuple[str, ...] = field(default_factory=tuple)

    # -- constructors --------------------------------------------------------

    @classmethod
    def from_settings(cls) -> "RagConfig":
        warnings: list[str] = []
        strategy = (settings.rag_chunk_strategy or "recursive").strip().lower()
        if strategy not in CHUNK_STRATEGIES:
            warnings.append(f"unknown rag_chunk_strategy '{strategy}', using recursive")
            strategy = "recursive"
        mode = (settings.rag_retrieval_mode or "hybrid").strip().lower()
        if mode not in RETRIEVAL_MODES:
            warnings.append(f"unknown rag_retrieval_mode '{mode}', using hybrid")
            mode = "hybrid"
        reranker = (settings.rag_reranker or "auto").strip().lower()

        config = cls(
            chunk_strategy=strategy,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            parent_chunk_size=settings.rag_parent_chunk_size,
            child_chunk_size=settings.rag_child_chunk_size,
            child_overlap=settings.rag_child_overlap,
            retrieval_mode=mode,
            dense_top_k=settings.rag_dense_top_k,
            sparse_top_k=settings.rag_sparse_top_k,
            hybrid_top_k=settings.rag_hybrid_top_k,
            final_top_k=settings.rag_final_top_k or settings.rag_max_context_chunks,
            min_relevance=settings.rag_min_relevance,
            reranker=reranker,
            llm_verification=settings.llm_verification,
            rerank_top_k=settings.rag_rerank_top_k,
            query_rewrite=settings.rag_query_rewrite,
            multi_query=settings.rag_multi_query,
            max_subqueries=settings.rag_max_subqueries,
            context_token_budget=settings.rag_context_token_budget,
            max_context_chunks=settings.rag_max_context_chunks,
            context_compression=settings.rag_context_compression,
            context_compression_max_sentences=settings.rag_context_compression_max_sentences,
            verification=settings.rag_verification,
            support_threshold=settings.rag_verification_support_threshold,
            partial_threshold=settings.rag_verification_partial_threshold,
            max_document_bytes=settings.rag_max_document_bytes,
            query_log_enabled=settings.rag_query_log_enabled,
            embedding_cache_size=settings.rag_embedding_cache_size,
            memory_max_turns=settings.rag_memory_max_turns,
            embedding_provider=settings.embedding_provider,
            embedding_model=settings.embedding_model,
            embedding_dimensions=settings.embedding_dimensions,
            embedding_batch_size=settings.embedding_batch_size,
            llm_provider=settings.llm_provider,
            warnings=tuple(warnings),
        )
        config.validate()
        return config

    # -- validation ----------------------------------------------------------

    def validate(self) -> None:
        if self.chunk_size < 100:
            raise ConfigurationError("chunk_size must be >= 100 characters")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ConfigurationError("chunk_overlap must be >= 0 and smaller than chunk_size")
        if self.child_chunk_size >= self.parent_chunk_size:
            raise ConfigurationError("child_chunk_size must be smaller than parent_chunk_size")
        if not 0 <= self.child_overlap < self.child_chunk_size:
            raise ConfigurationError("child_overlap must be smaller than child_chunk_size")
        if self.final_top_k < 1 or self.final_top_k > 100:
            raise ConfigurationError("final_top_k must be between 1 and 100")
        for name in ("dense_top_k", "sparse_top_k", "hybrid_top_k", "rerank_top_k"):
            value = getattr(self, name)
            if value < 1 or value > 200:
                raise ConfigurationError(f"{name} must be between 1 and 200")
        if not 0.0 <= self.partial_threshold <= self.support_threshold <= 1.0:
            raise ConfigurationError(
                "verification thresholds must satisfy 0 <= partial_threshold <= support_threshold <= 1"
            )
        if self.context_token_budget < 500:
            raise ConfigurationError("context_token_budget must be >= 500")
        if self.max_document_bytes <= 0:
            raise ConfigurationError("max_document_bytes must be positive")

    # -- helpers -------------------------------------------------------------

    def with_overrides(self, **overrides: Any) -> "RagConfig":
        return replace(self, **overrides)

    def describe(self) -> dict[str, Any]:
        """Secret-free configuration description for diagnostics."""
        return {
            "pipeline_version": PIPELINE_VERSION,
            "chunking": {
                "strategy": self.chunk_strategy,
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
                "parent_chunk_size": self.parent_chunk_size,
                "child_chunk_size": self.child_chunk_size,
                "child_overlap": self.child_overlap,
            },
            "retrieval": {
                "mode": self.retrieval_mode,
                "dense_top_k": self.dense_top_k,
                "sparse_top_k": self.sparse_top_k,
                "hybrid_top_k": self.hybrid_top_k,
                "final_top_k": self.final_top_k,
                "min_relevance": self.min_relevance,
                "reranker": self.reranker,
                "rerank_top_k": self.rerank_top_k,
                "query_rewrite": self.query_rewrite,
                "multi_query": self.multi_query,
                "max_subqueries": self.max_subqueries,
                "fusion": "reciprocal_rank_fusion",
            },
            "context": {
                "token_budget": self.context_token_budget,
                "max_chunks": self.max_context_chunks,
                "compression": self.context_compression,
            },
            "verification": {
                "enabled": self.verification,
                "support_threshold": self.support_threshold,
                "partial_threshold": self.partial_threshold,
                "llm_entailment": self.llm_verification,
                "method": "deterministic lexical grounding + optional LLM entailment (not a certainty guarantee)",
            },
            "ingestion": {
                "max_document_bytes": self.max_document_bytes,
                "allowed_extensions": list(self.allowed_extensions),
            },
            "providers": {
                "embedding_provider": self.embedding_provider,
                "embedding_model": self.embedding_model or "(provider default)",
                "llm_provider": self.llm_provider,
            },
            "warnings": list(self.warnings),
        }


def get_rag_config() -> RagConfig:
    """Resolve configuration from the environment exactly once per call."""
    return RagConfig.from_settings()
