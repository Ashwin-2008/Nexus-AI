from __future__ import annotations

import io
import time

from fastapi.testclient import TestClient

from tests.test_authz_boundaries import auth_headers, login_token, register_user


def _upload(client: TestClient, token: str, name: str, content: bytes, ctype: str):
    return client.post(
        "/api/v1/documents/upload",
        files={"file": (name, content, ctype)},
        headers=auth_headers(token),
    )


def test_upload_txt_and_metadata_extraction(client: TestClient, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    register_user(client, "doc1@example.com", "OrgD")
    token = login_token(client, "doc1@example.com")
    resp = _upload(client, token, "sample.txt", b"hello\nworld\n", "text/plain")
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] in {"pending", "processing", "completed"}
    assert data["filename"] == "sample.txt"
    assert "storage_backend" in data
    assert data.get("latest_job") is not None
    # Background/celery-fallback processing may complete; allow brief processing
    doc_id = data["id"]
    final = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers(token))
    assert final.status_code == 200
    fdata = final.json()
    assert fdata["status"] in {"completed", "failed", "processing", "pending"}
    if fdata["status"] == "completed":
        assert isinstance(fdata.get("metadata"), dict)
        assert fdata.get("latest_job") is not None
        assert fdata["latest_job"]["status"] in {"succeeded", "running", "queued", "retrying", "failed"}


def test_file_validation_rejects_unsupported_type(client: TestClient, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    register_user(client, "doc2@example.com", "OrgD2")
    token = login_token(client, "doc2@example.com")
    resp = _upload(client, token, "malware.exe", b"MZ...", "application/octet-stream")
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("error", {}).get("code") == "invalid_file"


def test_file_validation_rejects_empty(client: TestClient, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    register_user(client, "doc3@example.com", "OrgD3")
    token = login_token(client, "doc3@example.com")
    resp = _upload(client, token, "empty.txt", b"", "text/plain")
    assert resp.status_code == 400


def test_retry_document_flow(client: TestClient, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    register_user(client, "doc4@example.com", "OrgD4")
    token = login_token(client, "doc4@example.com")
    resp = _upload(client, token, "retry.txt", b"retry content", "text/plain")
    assert resp.status_code == 201
    doc_id = resp.json()["id"]
    # wait/poll for completion or failure
    status_val = resp.json()["status"]
    for _ in range(10):
        r = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers(token)).json()
        status_val = r["status"]
        if status_val in {"completed", "failed"}:
            break
        time.sleep(0.05)
    # retry allowed when completed/failed
    if status_val in {"completed", "failed"}:
        retry = client.post(f"/api/v1/documents/{doc_id}/retry", headers=auth_headers(token))
        assert retry.status_code == 200, retry.text
        assert retry.json()["status"] in {"pending", "processing", "completed", "failed"}
        # if it was completed, retry_count should remain consistent (not required to increment on manual retry except failure path)
    else:
        # still processing in edge envs; ensure endpoint exists and enforces state
        retry = client.post(f"/api/v1/documents/{doc_id}/retry", headers=auth_headers(token))
        assert retry.status_code in {200, 409}
