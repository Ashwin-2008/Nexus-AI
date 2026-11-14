from __future__ import annotations

import io
import logging
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    from minio import Minio
    from minio.error import S3Error
except Exception:  # pragma: no cover
    Minio = None  # type: ignore
    S3Error = Exception  # type: ignore


class StorageError(Exception):
    pass


class StorageUnavailableError(StorageError):
    pass


class StorageBackend(ABC):
    name: str = "base"

    @abstractmethod
    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def exists(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> str:
        raise NotImplementedError


def _normalize_key(key: str) -> str:
    # Prevent traversal; keys are treated as relative object identifiers
    clean = key.replace("\\", "/").lstrip("/")
    parts = [p for p in clean.split("/") if p not in ("", ".", "..")]
    return "/".join(parts)


def build_document_key(org_id: uuid.UUID | str, filename: str) -> str:
    safe_name = Path(filename).name.replace("\\", "_").replace("/", "_") or "file"
    unique = f"{uuid.uuid4()}_{safe_name}"
    return _normalize_key(f"orgs/{org_id}/documents/{unique}")


class LocalStorageBackend(StorageBackend):
    name = "local"

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or settings.storage_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / _normalize_key(key)

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return _normalize_key(key)

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        # Backward compatibility: allow legacy absolute/relative paths stored before abstraction
        if not path.exists():
            legacy = Path(key)
            if legacy.exists() and legacy.is_file():
                return legacy.read_bytes()
            raise StorageError(f"Object not found: {key}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists() or (Path(key).exists() and Path(key).is_file())

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()
        else:
            legacy = Path(key)
            if legacy.exists() and legacy.is_file():
                legacy.unlink()

    def health_check(self) -> str:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            test = self.root / ".healthcheck"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
            return "healthy"
        except Exception:
            return "unhealthy"


class MinioStorageBackend(StorageBackend):
    name = "minio"

    def __init__(self):
        if Minio is None:
            raise StorageUnavailableError("minio client not installed")
        endpoint = settings.minio_endpoint
        # strip scheme if provided
        endpoint = endpoint.replace("http://", "").replace("https://", "")
        self.bucket = settings.minio_bucket
        self.client = Minio(
            endpoint,
            access_key=settings.minio_access_key or None,
            secret_key=settings.minio_secret_key or None,
            secure=settings.minio_secure,
        )

    def _ensure_bucket(self) -> None:
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except Exception as e:
            raise StorageUnavailableError(f"MinIO unavailable: {e}") from e

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        try:
            self._ensure_bucket()
            key = _normalize_key(key)
            self.client.put_object(
                self.bucket,
                key,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type or "application/octet-stream",
            )
            return key
        except Exception as e:
            raise StorageUnavailableError(f"MinIO put failed: {e}") from e

    def get_bytes(self, key: str) -> bytes:
        try:
            key = _normalize_key(key)
            resp = self.client.get_object(self.bucket, key)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()
        except Exception as e:
            # allow fallback to local legacy path if object not in minio
            legacy = Path(key)
            if legacy.exists() and legacy.is_file():
                return legacy.read_bytes()
            raise StorageError(f"MinIO get failed: {e}") from e

    def exists(self, key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, _normalize_key(key))
            return True
        except Exception:
            return Path(key).exists() and Path(key).is_file()

    def delete(self, key: str) -> None:
        try:
            self.client.remove_object(self.bucket, _normalize_key(key))
        except Exception:
            legacy = Path(key)
            if legacy.exists() and legacy.is_file():
                legacy.unlink()

    def health_check(self) -> str:
        try:
            self.client.bucket_exists(self.bucket)
            return "healthy"
        except Exception:
            return "unhealthy"


_backend: Optional[StorageBackend] = None


def get_storage_backend() -> StorageBackend:
    global _backend
    if _backend is not None:
        return _backend
    mode = (settings.storage_backend or "auto").lower()
    if mode == "local":
        _backend = LocalStorageBackend()
        return _backend
    if mode == "minio":
        _backend = MinioStorageBackend()
        return _backend
    # auto: prefer MinIO if credentials/endpoint configured, else local
    if settings.minio_endpoint and settings.minio_access_key and settings.minio_secret_key:
        try:
            _backend = MinioStorageBackend()
            # best-effort bucket ensure/check
            _backend.health_check()
            return _backend
        except Exception:
            logger.warning("MinIO unavailable, falling back to local storage")
    _backend = LocalStorageBackend()
    return _backend


def reset_storage_backend() -> None:
    global _backend
    _backend = None
