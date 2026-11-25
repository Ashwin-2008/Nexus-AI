from __future__ import annotations

import json
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NEXUS AI Backend"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"
    debug: bool = False

    # Auth / JWT (IC-003: docker-compose maps SECRET_KEY from JWT_SECRET)
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # Rate limiting
    rate_limit_enabled: bool = True
    auth_rate_limit: str = "20/minute"

    # Data stores (IC-004: postgresql+psycopg driver for psycopg v3)
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/nexus_ai"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    # Object storage — auto|supabase|minio|local
    # auto: Supabase Storage when SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY are
    # set, else MinIO when configured, else the local filesystem.
    storage_backend: str = "auto"
    storage_root: str = "storage"

    # Supabase Storage (managed document storage; REST API v1).
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "nexus-documents"

    # Self-hosted MinIO / S3-compatible storage (optional alternative)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "nexus-documents"
    minio_secure: bool = False

    # Ingestion / worker
    ingestion_max_retries: int = 3
    ingestion_retry_backoff_seconds: int = 30
    ingestion_use_celery: bool = True
    # A queued/running connector sync older than this is treated as abandoned
    # (e.g. the API restarted before its background task started).
    connector_sync_stale_minutes: int = 60
    # A queued job should start within seconds (Celery or API background task).
    # Recover it quickly so a missed task cannot block retries for an hour.
    connector_sync_queued_stale_minutes: int = 5
    agent_execution_timeout_seconds: int = 900
    agent_execution_recovery_seconds: int = 1800
    agent_max_retries: int = 3
    agent_approval_expiry_hours: int = 24

    # Chunking
    chunk_size: int = 900
    chunk_overlap: int = 150

    # --- RAG subsystem -------------------------------------------------------
    # Strategy: recursive | token | sentence | semantic | parent_child
    rag_chunk_strategy: str = "recursive"
    rag_parent_chunk_size: int = 1800
    rag_child_chunk_size: int = 450
    rag_child_overlap: int = 80
    # Retrieval: hybrid | dense | sparse
    rag_retrieval_mode: str = "hybrid"
    rag_dense_top_k: int = 12
    rag_sparse_top_k: int = 12
    rag_hybrid_top_k: int = 16
    rag_final_top_k: int = 8
    rag_min_relevance: float = 0.0
    # Reranker: heuristic | llm | cross_encoder | none | auto
    rag_reranker: str = "heuristic"
    rag_rerank_top_k: int = 8
    rag_query_rewrite: bool = True
    rag_multi_query: bool = True
    rag_max_subqueries: int = 3
    rag_context_compression: bool = False
    rag_context_compression_max_sentences: int = 6
    rag_verification: bool = True
    # Verification thresholds are lexical-support heuristics, not probabilities.
    rag_verification_support_threshold: float = 0.55
    rag_verification_partial_threshold: float = 0.30
    rag_embedding_cache_size: int = 2048
    rag_query_log_enabled: bool = True
    rag_max_document_bytes: int = 25 * 1024 * 1024
    rag_rate_limit_per_minute: int = 120
    rag_memory_max_turns: int = 4

    # Embeddings: provider = openai_compatible | local | hashing
    # - openai_compatible: OpenAI-compatible /v1/embeddings endpoint.
    #   EMBEDDING_BASE_URL/EMBEDDING_API_KEY allow a provider that is separate
    #   from the chat endpoint (e.g. OpenAI embeddings + Groq chat); when empty
    #   they fall back to OPENAI_BASE_URL/OPENAI_API_KEY.
    # - local: in-process sentence-transformers model (needs requirements-embeddings.txt)
    # - hashing: deterministic non-semantic vectors; CI/test machinery only
    embedding_provider: str = "hashing"
    embedding_model: str = ""
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_local_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 0  # 0 = provider default
    embedding_batch_size: int = 64

    # LLM (OpenAI-compatible; used by RAG/chat milestones)
    openai_api_key: str = ""
    openai_base_url: str = ""
    llm_model: str = ""
    # openai_compatible | extractive | auto (auto = openai_compatible when key present, else extractive)
    llm_provider: str = "auto"
    rag_context_token_budget: int = 6000
    rag_max_context_chunks: int = 8

    # Qdrant
    qdrant_api_key: str = ""
    qdrant_collection: str = "nexus_chunks"
    # qdrant = real Qdrant; memory = ephemeral in-process index (tests/offline dev only)
    vector_index_backend: str = "qdrant"
    search_top_k: int = 8

    # CORS
    cors_origins: str = "http://localhost,http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator(
        "debug",
        "minio_secure",
        "rag_query_rewrite",
        "rag_multi_query",
        "rag_context_compression",
        "rag_verification",
        "rag_query_log_enabled",
        mode="before",
    )
    @classmethod
    def _coerce_bool(cls, v):
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "yes", "on", "debug"}
        return bool(v)

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS tolerantly.

        Accepts a comma separated list, a JSON array, quoted entries and entries
        with a trailing slash, because every one of those has been pasted into a
        hosting dashboard at some point and silently disabled CORS.
        """
        raw = (self.cors_origins or "").strip()
        # Tolerate "CORS_ORIGINS=https://..." pasted into a dashboard value field.
        if raw.lower().startswith("cors_origins="):
            raw = raw.split("=", 1)[1].strip()
        if raw.startswith("[") and raw.endswith("]"):
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = None
            if isinstance(parsed, list):
                raw = ",".join(str(item) for item in parsed)
        origins: List[str] = []
        for item in raw.split(","):
            origin = item.strip().strip("'\"").strip().rstrip("/")
            if origin and origin not in origins:
                origins.append(origin)
        return origins


settings = Settings()
