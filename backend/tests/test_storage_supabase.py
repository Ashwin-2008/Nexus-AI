from __future__ import annotations

import httpx
import pytest

from app.core.config import settings
from app.services.storage import (
    StorageError,
    StorageUnavailableError,
    SupabaseStorageBackend,
    get_storage_backend,
    reset_storage_backend,
)

BUCKET_PATH = "/storage/v1/bucket/nexus-documents"


@pytest.fixture()
def supabase_settings(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://demo.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-role-key")
    monkeypatch.setattr(settings, "supabase_storage_bucket", "nexus-documents")
    monkeypatch.setattr(settings, "storage_backend", "auto")
    reset_storage_backend()
    yield
    reset_storage_backend()


@pytest.fixture()
def backend(supabase_settings):
    instance = SupabaseStorageBackend()
    yield instance
    instance._client.close()


def _install(backend: SupabaseStorageBackend, handler) -> None:
    """Swap the real network client for an in-memory transport."""
    backend._client.close()
    backend._client = httpx.Client(
        base_url=backend.base_url,
        transport=httpx.MockTransport(handler),
        headers={
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
        },
    )
    backend._bucket_ready = False


def _bucket_ok(request: httpx.Request) -> httpx.Response | None:
    if request.method == "GET" and request.url.path == BUCKET_PATH:
        return httpx.Response(200, json={"id": "nexus-documents", "public": False})
    return None


def test_factory_prefers_supabase_when_configured(supabase_settings):
    assert get_storage_backend().name == "supabase"


def test_factory_falls_back_to_local_without_supabase(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_role_key", "")
    monkeypatch.setattr(settings, "storage_backend", "auto")
    reset_storage_backend()
    try:
        assert get_storage_backend().name in {"local", "minio"}
    finally:
        reset_storage_backend()


def test_missing_credentials_raise(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    with pytest.raises(StorageUnavailableError):
        SupabaseStorageBackend()


def test_object_url_encodes_path_segments(backend):
    url = backend._object_url("orgs/o1/documents/report final.pdf")
    assert url.endswith("/storage/v1/object/nexus-documents/orgs/o1/documents/report%20final.pdf")


def test_put_bytes_uploads_multipart_with_upsert(backend):
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        bucket = _bucket_ok(request)
        if bucket is not None:
            return bucket
        if request.method == "POST" and request.url.path.startswith("/storage/v1/object/"):
            # raw_path keeps the percent-encoding the client actually sent
            seen["path"] = request.url.raw_path.decode()
            seen["upsert"] = request.headers.get("x-upsert")
            seen["content_type"] = request.headers.get("content-type", "")
            seen["body"] = request.content
            return httpx.Response(200, json={"Key": "nexus-documents/x"})
        return httpx.Response(404)

    _install(backend, handler)
    key = backend.put_bytes("orgs/o1/documents/report final.pdf", b"%PDF-1.4 data", "application/pdf")

    assert key == "orgs/o1/documents/report final.pdf"
    assert seen["upsert"] == "true"
    assert seen["path"] == "/storage/v1/object/nexus-documents/orgs/o1/documents/report%20final.pdf"
    assert "multipart/form-data" in str(seen["content_type"])
    assert b"%PDF-1.4 data" in seen["body"]  # type: ignore[operator]


def test_put_bytes_creates_missing_bucket(backend):
    created: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == BUCKET_PATH:
            # Real Supabase shape: HTTP 400 carrying statusCode "404".
            return httpx.Response(
                400,
                json={"statusCode": "404", "error": "Bucket not found", "message": "Bucket not found"},
            )
        if request.method == "POST" and request.url.path == "/storage/v1/bucket":
            created["payload"] = request.content
            return httpx.Response(200, json={"name": "nexus-documents"})
        if request.method == "POST":
            return httpx.Response(200, json={"Key": "x"})
        return httpx.Response(404)

    _install(backend, handler)
    backend.put_bytes("orgs/o1/documents/a.txt", b"hello", "text/plain")
    assert b"nexus-documents" in created["payload"]  # type: ignore[operator]


def test_upload_error_is_reported_without_credentials(backend):
    def handler(request: httpx.Request) -> httpx.Response:
        bucket = _bucket_ok(request)
        if bucket is not None:
            return bucket
        return httpx.Response(413, json={"message": "Payload too large"})

    _install(backend, handler)
    with pytest.raises(StorageUnavailableError) as excinfo:
        backend.put_bytes("orgs/o1/documents/a.bin", b"x", "application/octet-stream")
    assert "413" in str(excinfo.value)
    assert "service-role-key" not in str(excinfo.value)


def test_get_bytes_returns_content(backend):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"stored bytes")

    _install(backend, handler)
    assert backend.get_bytes("orgs/o1/documents/a.txt") == b"stored bytes"


def test_get_bytes_missing_object_raises_storage_error(backend):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    _install(backend, handler)
    with pytest.raises(StorageError):
        backend.get_bytes("orgs/o1/documents/missing.txt")


def test_object_not_found_reported_as_400(backend):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"statusCode": "404", "error": "not_found", "message": "Object not found"},
        )

    _install(backend, handler)
    with pytest.raises(StorageError):
        backend.get_bytes("orgs/o1/documents/missing.txt")
    assert backend.exists("orgs/o1/documents/missing.txt") is False


def test_health_check_treats_missing_bucket_as_reachable(backend):
    _install(
        backend,
        lambda request: httpx.Response(
            400,
            json={"statusCode": "404", "error": "Bucket not found", "message": "Bucket not found"},
        ),
    )
    assert backend.health_check() == "healthy"


def test_exists_uses_head_then_falls_back(backend):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "HEAD":
            return httpx.Response(405)
        return httpx.Response(206, content=b"x")

    _install(backend, handler)
    assert backend.exists("orgs/o1/documents/a.txt") is True
    assert calls == ["HEAD", "GET"]


def test_exists_returns_false_for_missing_object(backend):
    _install(backend, lambda request: httpx.Response(404))
    assert backend.exists("orgs/o1/documents/missing.txt") is False


def test_delete_sends_prefix_payload(backend):
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = request.content
        return httpx.Response(200, json={"message": "Successfully deleted"})

    _install(backend, handler)
    backend.delete("orgs/o1/documents/a.txt")

    assert seen["method"] == "DELETE"
    assert seen["path"] == "/storage/v1/object/nexus-documents"
    assert b"orgs/o1/documents/a.txt" in seen["body"]  # type: ignore[operator]


def test_health_check_reports_bucket_state(backend):
    _install(backend, lambda request: httpx.Response(200, json={"id": "nexus-documents"}))
    assert backend.health_check() == "healthy"

    _install(backend, lambda request: httpx.Response(500))
    assert backend.health_check() == "unhealthy"


def test_health_check_reports_unreachable_host(backend):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    _install(backend, handler)
    assert backend.health_check() == "unhealthy"
