from __future__ import annotations

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

    # Object storage (MinIO / S3-compatible)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "nexus-documents"
    minio_secure: bool = False
    storage_backend: str = "auto"  # auto|minio|local
    storage_root: str = "storage"

    # Ingestion / worker
    ingestion_max_retries: int = 3
    ingestion_retry_backoff_seconds: int = 30
    ingestion_use_celery: bool = True

    # CORS
    cors_origins: str = "http://localhost,http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("debug", "minio_secure", mode="before")
    @classmethod
    def _coerce_bool(cls, v):
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "yes", "on", "debug"}
        return bool(v)

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
