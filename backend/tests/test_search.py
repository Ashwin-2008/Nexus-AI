"""Tests for the search API: semantic, lexical, hybrid, and org isolation."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.test_authz_boundaries import auth_headers, login_token, register_user


def _upload_and_complete(client: TestClient, token: str, name: str, content: bytes, ctype: str = "text/plain") -> dict:
    """Upload a document and wait for in-process processing to finish."""
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": (name, content, ctype)},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    # In tests (INGESTION_USE_CELERY=false) processing runs via BackgroundTasks
    # synchronously after the response; fetch the final state.
    final = client.get(f"/api/v1/documents/{doc['id']}", headers=auth_headers(token)).json()
    assert final["status"] == "completed", f"expected completed, got {final['status']}: {final.get('error_message')}"
    return final


class TestLexicalSearch:
    def test_relevant_document_ranks_first(self, client: TestClient, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "s1"))
        register_user(client, "search1@example.com", "SearchOrg1")
        token = login_token(client, "search1@example.com")

        _upload_and_complete(client, token, "leave-policy.txt",
                             b"Employee leave policy: annual leave is 25 days, sick leave is 10 days per year.")
        _upload_and_complete(client, token, "revenue.txt",
                             b"Q1 revenue was 1,200,000 USD. Q2 revenue was 1,450,000 USD.")

        resp = client.get("/api/v1/search", params={"q": "annual leave days", "mode": "lexical"},
                          headers=auth_headers(token))
        assert resp.status_code == 200, resp.text
        hits = resp.json()["hits"]
        assert hits, "expected at least one hit"
        assert "leave policy" in hits[0]["text"].lower() or "leave" in hits[0]["text"].lower()

    def test_no_results_is_empty(self, client: TestClient, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "s2"))
        register_user(client, "search2@example.com", "SearchOrg2")
        token = login_token(client, "search2@example.com")
        _upload_and_complete(client, token, "a.txt", b"totally unrelated content about gardening")
        resp = client.get("/api/v1/search", params={"q": "quantum physics", "mode": "lexical"},
                          headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_requires_auth(self, client: TestClient):
        resp = client.get("/api/v1/search", params={"q": "anything", "mode": "lexical"})
        assert resp.status_code == 401

    def test_empty_query_rejected(self, client: TestClient):
        register_user(client, "search3@example.com", "SearchOrg3")
        token = login_token(client, "search3@example.com")
        resp = client.get("/api/v1/search", params={"q": "", "mode": "lexical"}, headers=auth_headers(token))
        assert resp.status_code == 422


class TestSemanticSearch:
    def test_semantic_requires_vector_backend(self, client: TestClient, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "s3"))
        register_user(client, "search4@example.com", "SearchOrg4")
        token = login_token(client, "search4@example.com")
        _upload_and_complete(client, token, "doc.txt", b"content about revenue projections for next year")
        # In-memory backend + hashing embeddings: identical machinery as production
        resp = client.get("/api/v1/search", params={"q": "revenue projections", "mode": "semantic"},
                          headers=auth_headers(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["mode"] == "semantic"
        for hit in body["hits"]:
            assert hit["document_filename"]  # attached from DB, org-scoped
            assert hit["metadata"]["document_status"] == "completed"

    def test_semantic_hits_have_provenance_structure(self, client: TestClient, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "s4"))
        register_user(client, "search5@example.com", "SearchOrg5")
        token = login_token(client, "search5@example.com")
        _upload_and_complete(client, token, "prov.txt", b"line one\nline two\nline three")
        resp = client.get("/api/v1/search", params={"q": "line", "mode": "semantic"},
                          headers=auth_headers(token))
        assert resp.status_code == 200
        for hit in resp.json()["hits"]:
            assert isinstance(hit["provenance"], list)


class TestHybridSearch:
    def test_hybrid_fuses_and_ranks(self, client: TestClient, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "s5"))
        register_user(client, "search6@example.com", "SearchOrg6")
        token = login_token(client, "search6@example.com")
        _upload_and_complete(client, token, "fin.txt", b"Financial risk report: supplier concentration is the main risk.")
        resp = client.get("/api/v1/search", params={"q": "supplier concentration risk", "mode": "hybrid"},
                          headers=auth_headers(token))
        assert resp.status_code == 200
        hits = resp.json()["hits"]
        assert hits
        assert all(h["mode"] == "hybrid" for h in hits)
        # scores sorted descending
        scores = [h["score"] for h in hits]
        assert scores == sorted(scores, reverse=True)


class TestOrgIsolation:
    def test_other_org_cannot_search_across_orgs(self, client: TestClient, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "s6"))
        # Org A uploads a distinctive document
        register_user(client, "orgA-search@example.com", "IsolationOrgA")
        token_a = login_token(client, "orgA-search@example.com")
        _upload_and_complete(client, token_a, "secret-a.txt",
                             b"Confidential: project Phoenix budget is 5,000,000 USD.")

        # Org B (different org) searches for the same content
        register_user(client, "orgB-search@example.com", "IsolationOrgB")
        token_b = login_token(client, "orgB-search@example.com")
        for mode in ("lexical", "semantic", "hybrid"):
            resp = client.get("/api/v1/search", params={"q": "project Phoenix budget", "mode": mode},
                              headers=auth_headers(token_b))
            assert resp.status_code == 200
            hits = resp.json()["hits"]
            assert hits == [], f"{mode} leaked another org's data"
            # ensure no document content/filename leakage (query echo excluded)
            assert "secret-a.txt" not in resp.text
            assert "5,000,000" not in resp.text

    def test_document_id_filter_cannot_cross_orgs(self, client: TestClient, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "s7"))
        register_user(client, "orgA-filter@example.com", "FilterOrgA")
        token_a = login_token(client, "orgA-filter@example.com")
        doc_a = _upload_and_complete(client, token_a, "a-doc.txt", b"unique content alpha bravo charlie")

        register_user(client, "orgB-filter@example.com", "FilterOrgB")
        token_b = login_token(client, "orgB-filter@example.com")
        # Org B explicitly names Org A's document id -> must return nothing
        resp = client.get(
            "/api/v1/search",
            params={"q": "alpha bravo", "mode": "lexical", "document_ids": doc_a["id"]},
            headers=auth_headers(token_b),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
