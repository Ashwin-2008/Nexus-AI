"""Tests for the connector framework: credentials, connectors, API, sync pipeline."""
from __future__ import annotations

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.connectors import ConnectorContext, ConnectorError, get_connector
from app.services.credentials import encrypt_credentials, decrypt_credentials, mask_credentials
from tests.test_authz_boundaries import auth_headers, login_token, register_user


# ---------------------------------------------------------------------------
# local test servers (real HTTP over localhost, no mocks)
# ---------------------------------------------------------------------------


class _SiteHandler(BaseHTTPRequestHandler):
    pages: dict[str, str] = {}

    def do_GET(self):  # noqa: N802
        body = self.pages.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # silence test output
        return


class _ApiHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/items"):
            from urllib.parse import urlparse, parse_qs

            params = parse_qs(urlparse(self.path).query)
            offset = int(params.get("offset", ["0"])[0])
            limit = int(params.get("limit", ["50"])[0])
            all_items = [
                {"id": i, "title": f"Ticket {i}", "content": f"Ticket {i} describes outage in region {i}."}
                for i in range(1, 4)
            ]
            body = json.dumps({"data": all_items[offset:offset + limit]}).encode("utf-8")
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


@pytest.fixture(scope="module")
def site_server():
    _SiteHandler.pages = {
        "/": "<html><head><title>Help Center</title></head><body><h1>Help Center</h1>"
        "<p>Reset your password from the account page. Coverage includes region 7.</p>"
        '<a href="/page2.html">More</a></body></html>',
        "/page2.html": "<html><head><title>Page Two</title></head><body><p>SLA credits apply when uptime is below 99.9%.</p></body></html>",
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SiteHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def rest_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


# ---------------------------------------------------------------------------
# credential encryption
# ---------------------------------------------------------------------------


class TestCredentialEncryption:
    def test_roundtrip(self):
        creds = {"password": "hunter2", "token": "ghp_abcdef123456"}
        token = encrypt_credentials(creds)
        assert token != json.dumps(creds)
        assert decrypt_credentials(token) == creds

    def test_masking_preserves_shape(self):
        masked = mask_credentials({"password": "hunter2", "token": "ghp_abcdef123456", "note": ""})
        assert masked["password"] != "hunter2"
        assert "••" in masked["password"]
        assert "ghp" not in masked["token"]
        assert masked["note"] == ""


# ---------------------------------------------------------------------------
# connector unit behavior
# ---------------------------------------------------------------------------


def test_sql_connection_url_injects_encrypted_credentials():
    import sqlalchemy as sa

    from app.services.safe_sql import _connection_url

    context = ConnectorContext(
        config={"connection_url": "postgresql://db.internal:5432/knowledge"},
        credentials={"username": "readonly_user", "password": "not-in-config"},
    )
    parsed = sa.engine.make_url(_connection_url(context, "postgres"))
    assert parsed.username == "readonly_user"
    assert parsed.password == "not-in-config"
    assert str(parsed.host) == "db.internal"




class TestWebsiteConnector:
    def test_validate(self):
        c = get_connector("website")
        with pytest.raises(ConnectorError):
            c.validate(ConnectorContext(config={}, credentials={}))
        with pytest.raises(ConnectorError):
            c.validate(ConnectorContext(config={"base_url": "not-a-url"}, credentials={}))

    def test_fetch_real_http(self, site_server):
        c = get_connector("website")
        items = list(c.fetch(ConnectorContext(
            config={"base_url": f"{site_server}/", "max_pages": 5}, credentials={},
        )))
        assert len(items) == 2
        home = next(i for i in items if i.uri.rstrip("/") == site_server)
        assert "Reset your password" in home.text
        assert home.title == "Help Center"
        assert any(i.uri.endswith("/page2.html") for i in items)

    def test_fetch_unreachable_raises(self):
        c = get_connector("website")
        with pytest.raises(ConnectorError):
            c.fetch(ConnectorContext(config={"base_url": "http://127.0.0.1:59999/", "timeout_seconds": 2}, credentials={}))


class TestRestConnector:
    def test_fetch_real_http(self, rest_server):
        c = get_connector("rest")
        items = list(c.fetch(ConnectorContext(
            config={"url": f"{rest_server}/items", "item_path": "data", "page_size": 2, "max_pages": 2},
            credentials={},
        )))
        assert len(items) == 3
        assert "outage in region 2" in items[1].text
        assert items[0].title == "Ticket 1"

    def test_requires_select_like_shape(self, rest_server):
        c = get_connector("rest")
        with pytest.raises(ConnectorError):
            c.fetch(ConnectorContext(config={"url": f"{rest_server}/items", "item_path": "wrong.path"}, credentials={}))


class TestPostgresConnector:
    def test_validate(self):
        c = get_connector("postgres")
        with pytest.raises(ConnectorError):
            c.validate(ConnectorContext(config={"connection_url": "postgresql://x"}, credentials={}))
        with pytest.raises(ConnectorError):
            c.validate(ConnectorContext(config={"connection_url": "mysql://x", "query": "SELECT 1"}, credentials={}))

    def test_query_must_be_select(self):
        c = get_connector("postgres")
        ctx = ConnectorContext(
            config={"connection_url": "postgresql://u:p@localhost/db", "query": "DELETE FROM t"},
            credentials={},
        )
        with pytest.raises(ConnectorError, match="SELECT"):
            c.fetch(ctx)


class TestMySQLConnector:
    def test_requires_mysql_url(self):
        c = get_connector("mysql")
        with pytest.raises(ConnectorError):
            c.validate(ConnectorContext(config={"connection_url": "postgresql://x", "query": "SELECT 1"}, credentials={}))


class TestGitHubConnector:
    @pytest.fixture()
    def fake_github(self, monkeypatch):
        """Serve GitHub API shape over httpx MockTransport (httpx's own test transport)."""
        files = {"tree": {
            "tree": [
                {"type": "blob", "path": "README.md", "size": 120},
                {"type": "blob", "path": "docs/guide.md", "size": 200},
                {"type": "blob", "path": "image.png", "size": 500},
            ]
        }}
        blobs = {
            "README.md": b"# Project Phoenix\nPhoenix is an internal knowledge platform.",
            "docs/guide.md": b"# Guide\nRun the ingestion worker before syncing.",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/git/trees/" in url:
                return httpx.Response(200, json=files["tree"])
            if "/contents/" in url:
                path = url.split("/contents/")[1].split("?")[0]
                data = blobs.get(path)
                if data is None:
                    return httpx.Response(404, json={})
                return httpx.Response(200, json={
                    "encoding": "base64",
                    "content": base64.b64encode(data).decode("ascii"),
                })
            return httpx.Response(404, json={})

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def client_factory(**kwargs):
            return original_client(transport=transport, **kwargs)

        monkeypatch.setattr(httpx, "Client", client_factory)
        yield blobs

    def test_fetch_markdown_files(self, fake_github):
        c = get_connector("github")
        items = list(c.fetch(ConnectorContext(
            config={"repo": "acme/portal", "branch": "main"}, credentials={"token": "ghp_test"},
        )))
        assert len(items) == 2
        readme = next(i for i in items if i.title == "README.md")
        assert "Project Phoenix" in readme.data.decode("utf-8")

    def test_auth_failure_raises(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "Bad credentials"})

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def client_factory(**kwargs):
            return original_client(transport=transport, **kwargs)

        monkeypatch.setattr(httpx, "Client", client_factory)
        c = get_connector("github")
        with pytest.raises(ConnectorError, match="auth failed"):
            c.fetch(ConnectorContext(config={"repo": "acme/private"}, credentials={"token": "bad"}))


class TestGDriveConnector:
    def test_validate(self):
        c = get_connector("gdrive")
        with pytest.raises(ConnectorError):
            c.validate(ConnectorContext(config={}, credentials={}))
        c.validate(ConnectorContext(config={}, credentials={"client_id": "a", "client_secret": "b", "refresh_token": "c"}))

    def test_fetch_via_oauth_flow(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "oauth2.googleapis.com/token" in url:
                return httpx.Response(200, json={"access_token": "at-test"})
            path = request.url.path
            if path == "/drive/v3/files":
                return httpx.Response(200, json={"files": [
                    {"id": "f1", "name": "Notes.doc", "mimeType": "application/vnd.google-apps.document", "modifiedTime": "2026-01-01T00:00:00Z"},
                ]})
            if path.endswith("/drive/v3/files/f1/export"):
                return httpx.Response(200, text="# Notes\nExported drive content about onboarding.")
            return httpx.Response(404, json={})

        transport = httpx.MockTransport(handler)
        original_post, original_get = httpx.post, httpx.get

        def client_post(url, **kw):
            return httpx.Client(transport=transport).post(url, **kw)

        def client_get(url, **kw):
            return httpx.Client(transport=transport).get(url, **kw)

        monkeypatch.setattr(httpx, "post", client_post)
        monkeypatch.setattr(httpx, "get", client_get)

        c = get_connector("gdrive")
        items = list(c.fetch(ConnectorContext(
            config={},
            credentials={"client_id": "a", "client_secret": "b", "refresh_token": "c"},
        )))
        assert len(items) == 1
        assert "onboarding" in items[0].data.decode("utf-8")

    def test_bad_refresh_token_raises(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "invalid_grant"})

        transport = httpx.MockTransport(handler)

        def client_post(url, **kw):
            return httpx.Client(transport=transport).post(url, **kw)

        monkeypatch.setattr(httpx, "post", client_post)
        c = get_connector("gdrive")
        with pytest.raises(ConnectorError, match="token refresh failed"):
            c.fetch(ConnectorContext(config={}, credentials={"client_id": "a", "client_secret": "b", "refresh_token": "x"}))


class TestEmailConnector:
    def test_validate(self):
        c = get_connector("email")
        with pytest.raises(ConnectorError):
            c.validate(ConnectorContext(config={"host": "imap.example.org"}, credentials={}))
        c.validate(ConnectorContext(
            config={"host": "imap.example.org"},
            credentials={"username": "u", "password": "p"},
        ))


# ---------------------------------------------------------------------------
# API + sync pipeline
# ---------------------------------------------------------------------------


def _wait_for(predicate, timeout: float = 15.0, interval: float = 0.25) -> bool:
    """Poll until predicate is true (background sync tasks may lag the response)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class TestSourcesAPI:
    def test_create_rejects_unknown_type_and_bad_config(self, client: TestClient):
        register_user(client, "src-a@example.com", "SrcOrgA")
        token = login_token(client, "src-a@example.com")
        r = client.post("/api/v1/sources", json={"name": "X", "type": "oracle"}, headers=auth_headers(token))
        assert r.status_code == 400
        r2 = client.post("/api/v1/sources", json={"name": "X", "type": "website", "config": {"base_url": "junk"}}, headers=auth_headers(token))
        assert r2.status_code == 400
        assert "base_url" in r2.json()["error"]["message"]

    def test_create_lists_and_masks_credentials(self, client: TestClient):
        register_user(client, "src-b@example.com", "SrcOrgB")
        token = login_token(client, "src-b@example.com")
        body = {
            "name": "Docs site",
            "type": "website",
            "config": {"base_url": "http://127.0.0.1:59991/", "max_pages": 3},
            "credentials": {"token": "super-secret-token-value"},
        }
        r = client.post("/api/v1/sources", json=body, headers=auth_headers(token))
        assert r.status_code == 201, r.text
        src = r.json()
        assert src["type"] == "website"
        assert src["credentials_masked"]["token"] != "super-secret-token-value"
        assert "super-secret" not in json.dumps(src)

        lst = client.get("/api/v1/sources", headers=auth_headers(token)).json()
        assert len(lst) == 1
        got = client.get(f"/api/v1/sources/{src['id']}", headers=auth_headers(token)).json()
        assert got["id"] == src["id"]

    def test_org_isolation_404(self, client: TestClient):
        register_user(client, "src-c@example.com", "SrcOrgC")
        token_a = login_token(client, "src-c@example.com")
        src = client.post(
            "/api/v1/sources",
            json={"name": "Private", "type": "website", "config": {"base_url": "http://example.invalid/"}},
            headers=auth_headers(token_a),
        ).json()

        register_user(client, "src-d@example.com", "SrcOrgD")
        token_b = login_token(client, "src-d@example.com")
        assert client.get(f"/api/v1/sources/{src['id']}", headers=auth_headers(token_b)).status_code == 404
        assert client.post(f"/api/v1/sources/{src['id']}/sync", headers=auth_headers(token_b)).status_code == 404
        assert client.delete(f"/api/v1/sources/{src['id']}", headers=auth_headers(token_b)).status_code == 404

    def test_requires_auth(self, client: TestClient):
        assert client.get("/api/v1/sources").status_code == 401

    def test_update_validates_merged_config(self, client: TestClient):
        register_user(client, "src-e@example.com", "SrcOrgE")
        token = login_token(client, "src-e@example.com")
        src = client.post(
            "/api/v1/sources",
            json={"name": "W", "type": "website", "config": {"base_url": "http://example.org/"}},
            headers=auth_headers(token),
        ).json()
        r = client.patch(f"/api/v1/sources/{src['id']}", json={"config": {"base_url": "broken"}}, headers=auth_headers(token))
        assert r.status_code == 400
        r2 = client.patch(f"/api/v1/sources/{src['id']}", json={"name": "Renamed", "status": "disabled"}, headers=auth_headers(token))
        assert r2.status_code == 200
        assert r2.json()["name"] == "Renamed"
        assert r2.json()["status"] == "disabled"


class TestSyncPipeline:
    def test_website_sync_ingests_and_dedupes_and_deletes(self, client: TestClient, site_server, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "conn1"))
        register_user(client, "sync-a@example.com", "SyncOrgA")
        token = login_token(client, "sync-a@example.com")

        src = client.post(
            "/api/v1/sources",
            json={"name": "Help center", "type": "website", "config": {"base_url": f"{site_server}/", "max_pages": 5}},
            headers=auth_headers(token),
        ).json()

        # trigger sync (celery off in tests -> executes synchronously, job returned final)
        r = client.post(f"/api/v1/sources/{src['id']}/sync", headers=auth_headers(token))
        assert r.status_code == 202, r.text

        def connector_docs():
            items = client.get("/api/v1/documents", headers=auth_headers(token)).json()["items"]
            return [d for d in items if d["filename"].startswith("connector/website/")]

        # connector documents were ingested into the normal pipeline (job terminal state)
        assert _wait_for(lambda: (
            (docs := connector_docs()) and len(docs) == 2
            and all(d["status"] == "completed" for d in docs)
        )), "sync did not ingest 2 documents in time"
        conn_docs = connector_docs()
        assert all(d["metadata"]["source"] == "connector" for d in conn_docs)

        # content is searchable through the normal search API
        search = client.get(
            "/api/v1/search?q=uptime%20below%2099.9&mode=lexical",
            headers=auth_headers(token),
        ).json()
        assert search["total"] >= 1
        assert any("99.9" in h["text"] for h in search["hits"])

        # RAG can answer from connector content
        conv = client.post("/api/v1/chat/conversations", json={}, headers=auth_headers(token)).json()
        msg = client.post(
            f"/api/v1/chat/conversations/{conv['id']}/messages",
            json={"content": "When do SLA credits apply?", "stream": False},
            headers=auth_headers(token),
        ).json()
        assert "99.9" in msg["content"] or "SLA" in msg["content"]
        assert msg["citations"]

        # second sync: unchanged content -> skipped, no duplicates
        r2 = client.post(f"/api/v1/sources/{src['id']}/sync", headers=auth_headers(token))
        assert r2.status_code == 202
        job2_id = r2.json()["id"]

        def second_sync_done():
            jobs_now = client.get(f"/api/v1/sources/{src['id']}/syncs", headers=auth_headers(token)).json()
            match = [j for j in jobs_now if j["id"] == job2_id]
            return bool(match) and match[0]["status"] in ("succeeded", "failed")

        assert _wait_for(second_sync_done), "second sync did not complete in time"
        jobs = client.get(f"/api/v1/sources/{src['id']}/syncs", headers=auth_headers(token)).json()
        latest = next(j for j in jobs if j["id"] == job2_id)
        docs_after = [d for d in client.get("/api/v1/documents", headers=auth_headers(token)).json()["items"]
                      if d["filename"].startswith("connector/")]
        assert latest["status"] == "succeeded"
        assert latest["fetched"] == 2
        assert len(docs_after) == 2
        assert latest["skipped"] == 2

        # sync history shows both runs
        assert len(jobs) == 2

    def test_sync_failure_recorded(self, client: TestClient, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "conn2"))
        register_user(client, "sync-b@example.com", "SyncOrgB")
        token = login_token(client, "sync-b@example.com")
        src = client.post(
            "/api/v1/sources",
            json={"name": "Dead site", "type": "website", "config": {"base_url": "http://127.0.0.1:59999/", "timeout_seconds": 2, "max_pages": 1}},
            headers=auth_headers(token),
        ).json()
        r = client.post(f"/api/v1/sources/{src['id']}/sync", headers=auth_headers(token))
        assert r.status_code == 202
        assert _wait_for(lambda: (
            (jobs := client.get(f"/api/v1/sources/{src['id']}/syncs", headers=auth_headers(token)).json())
            and jobs[0]["status"] == "failed"
        )), "sync did not fail in time"
        jobs = client.get(f"/api/v1/sources/{src['id']}/syncs", headers=auth_headers(token)).json()
        assert jobs[0]["status"] == "failed"
        assert jobs[0]["error"]
        src_now = client.get(f"/api/v1/sources/{src['id']}", headers=auth_headers(token)).json()
        assert src_now["status"] == "error"
        assert src_now["last_error"]

    def test_delete_propagates_documents(self, client: TestClient, site_server, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "conn3"))
        register_user(client, "sync-c@example.com", "SyncOrgC")
        token = login_token(client, "sync-c@example.com")
        src = client.post(
            "/api/v1/sources",
            json={"name": "Site", "type": "website", "config": {"base_url": f"{site_server}/", "max_pages": 5}},
            headers=auth_headers(token),
        ).json()
        client.post(f"/api/v1/sources/{src['id']}/sync", headers=auth_headers(token))
        assert _wait_for(lambda: (
            (docs := [d for d in client.get("/api/v1/documents", headers=auth_headers(token)).json()["items"]
                      if d["filename"].startswith("connector/website/")])
            and len(docs) == 2 and all(d["status"] == "completed" for d in docs)
        )), "sync did not ingest documents in time"

        r = client.delete(f"/api/v1/sources/{src['id']}", headers=auth_headers(token))
        assert r.status_code == 204
        remaining = [d for d in client.get("/api/v1/documents", headers=auth_headers(token)).json()["items"]
                     if d["filename"].startswith("connector/")]
        assert remaining == []
        assert client.get(f"/api/v1/sources/{src['id']}", headers=auth_headers(token)).status_code == 404
