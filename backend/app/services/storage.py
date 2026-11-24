from __future__ import annotations

import io
import logging
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from urllib.parse import quote

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


class SupabaseStorageBackend(StorageBackend):
    """Supabase Storage backend (Storage API v1, service-role key).

    Supabase's S3 gateway lives below a path prefix (``/storage/v1/s3``) that
    ``minio-py`` cannot express, and the REST API needs no extra dependency
    (``httpx`` is already required). The service-role key is used server-side
    only and is never logged.
    """

    name = "supabase"

    def __init__(self):
        try:
            import httpx
        except Exception as exc:  # pragma: no cover - httpx is a hard dependency
            raise StorageUnavailableError("httpx client not installed") from exc

        base_url = (settings.supabase_url or "").strip().rstrip("/")
        if not base_url:
            raise StorageUnavailableError("SUPABASE_URL is not configured")
        if not settings.supabase_service_role_key:
            raise StorageUnavailableError("SUPABASE_SERVICE_ROLE_KEY is not configured")

        self._httpx = httpx
        self.base_url = base_url
        self.bucket = (settings.supabase_storage_bucket or "nexus-documents").strip("/")
        self._bucket_ready = False
        service_key = settings.supabase_service_role_key
        self._client = httpx.Client(
            timeout=httpx.Timeout(60.0, connect=10.0),
            headers={"Authorization": f"Bearer {service_key}", "apikey": service_key},
        )

    # -- helpers -------------------------------------------------------------
    @property
    def _bucket_url(self) -> str:
        return f"{self.base_url}/storage/v1/bucket/{quote(self.bucket, safe='')}"

    def _object_url(self, key: str) -> str:
        segments = [quote(seg, safe="") for seg in _normalize_key(key).split("/") if seg]
        bucket = quote(self.bucket, safe="")
        return f"{self.base_url}/storage/v1/object/{bucket}/" + "/".join(segments)

    @staticmethod
    def _is_not_found(resp) -> bool:
        """Supabase reports missing buckets/objects as 404, or as 400 + statusCode 404."""
        if resp.status_code == 404:
            return True
        if resp.status_code != 400:
            return False
        try:
            payload = resp.json()
        except Exception:  # noqa: BLE001 - non-JSON error body
            return False
        if not isinstance(payload, dict):
            return False
        code = str(payload.get("statusCode", ""))
        if code == "404":
            return True
        message = f"{payload.get('error', '')} {payload.get('message', '')}".lower()
        return "not found" in message or "nosuchbucket" in message

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            resp = self._client.get(self._bucket_url)
        except self._httpx.HTTPError as exc:
            raise StorageUnavailableError(f"Supabase storage unreachable: {exc}") from exc
        if resp.status_code == 200:
            self._bucket_ready = True
            return
        if self._is_not_found(resp):
            try:
                created = self._client.post(
                    f"{self.base_url}/storage/v1/bucket",
                    json={"id": self.bucket, "name": self.bucket, "public": False},
                )
            except self._httpx.HTTPError as exc:
                raise StorageUnavailableError(f"Supabase storage unreachable: {exc}") from exc
            if created.status_code in (200, 201):
                self._bucket_ready = True
                return
            raise StorageUnavailableError(
                f"Supabase bucket {self.bucket!r} could not be created (HTTP {created.status_code})"
            )
        raise StorageUnavailableError(
            "Supabase storage rejected the request "
            f"(HTTP {resp.status_code}); check SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY"
        )

    @staticmethod
    def _error_detail(resp) -> str:
        """Short, non-sensitive error detail (never includes credentials)."""
        try:
            payload = resp.json()
            message = payload.get("message") or payload.get("error") or ""
        except Exception:  # noqa: BLE001 - non-JSON error body
            message = (resp.text or "").strip()
        return str(message)[:200]

    # -- StorageBackend ------------------------------------------------------
    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        self._ensure_bucket()
        key = _normalize_key(key)
        filename = Path(key).name or "document"
        try:
            resp = self._client.post(
                self._object_url(key),
                files={"file": (filename, data, content_type or "application/octet-stream")},
                headers={"x-upsert": "true"},
            )
        except self._httpx.HTTPError as exc:
            raise StorageUnavailableError(f"Supabase storage unreachable: {exc}") from exc
        if resp.status_code not in (200, 201):
            raise StorageUnavailableError(
                f"Supabase upload failed (HTTP {resp.status_code}): {self._error_detail(resp)}"
            )
        return key

    def get_bytes(self, key: str) -> bytes:
        try:
            resp = self._client.get(self._object_url(key))
        except self._httpx.HTTPError as exc:
            raise StorageUnavailableError(f"Supabase storage unreachable: {exc}") from exc
        if resp.status_code == 200:
            return resp.content
        if self._is_not_found(resp):
            raise StorageError(f"Object not found: {key}")
        raise StorageError(
            f"Supabase download failed (HTTP {resp.status_code}): {self._error_detail(resp)}"
        )

    def exists(self, key: str) -> bool:
        try:
            resp = self._client.head(self._object_url(key))
        except self._httpx.HTTPError:
            return False
        if resp.status_code == 200:
            return True
        if self._is_not_found(resp):
            return False
        # Some Storage API deployments/proxies do not expose HEAD on objects.
        try:
            probe = self._client.get(self._object_url(key), headers={"Range": "bytes=0-0"})
        except self._httpx.HTTPError:
            return False
        if self._is_not_found(probe):
            return False
        return probe.status_code in (200, 206)

    def delete(self, key: str) -> None:
        # Storage API removes objects by prefix (single-object delete route).
        try:
            resp = self._client.request(
                "DELETE",
                f"{self.base_url}/storage/v1/object/{quote(self.bucket, safe='')}",
                json={"prefixes": [_normalize_key(key)]},
            )
        except self._httpx.HTTPError as exc:
            raise StorageUnavailableError(f"Supabase storage unreachable: {exc}") from exc
        if resp.status_code in (200, 204) or self._is_not_found(resp):
            return
        raise StorageError(
            f"Supabase delete failed (HTTP {resp.status_code}): {self._error_detail(resp)}"
        )

    def health_check(self) -> str:
        try:
            resp = self._client.get(self._bucket_url)
        except self._httpx.HTTPError:
            return "unhealthy"
        # A missing bucket is created on first upload, so it is not a failure.
        if resp.status_code == 200 or self._is_not_found(resp):
            return "healthy"
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
    if mode == "supabase":
        _backend = SupabaseStorageBackend()
        return _backend
    if mode == "minio":
        _backend = MinioStorageBackend()
        return _backend
    # auto: Supabase Storage if configured, then MinIO, then the local filesystem.
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            _backend = SupabaseStorageBackend()
            return _backend
        except Exception:
            logger.warning("Supabase storage unavailable, trying next backend")
    if settings.minio_endpoint and settings.minio_access_key and settings.minio_secret_key:
        try:
            _backend = MinioStorageBackend()
            return _backend
        except Exception:
            logger.warning("MinIO unavailable, falling back to local storage")
    _backend = LocalStorageBackend()
    return _backend


def reset_storage_backend() -> None:
    global _backend
    _backend = None
