"""Integration tests for the modular RAG API and shared pipeline."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.test_authz_boundaries import auth_headers, login_token, register_user


def _register(client: TestClient, email: str, org: str) -> str:
    register_user(client, email, org)
    return login_token(client, email)


def _upload(client: TestClient, token: str, name: str, content: bytes, ctype: str = "text/plain") -> dict:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (name, content, ctype)},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    document = response.json()
    final = client.get(f"/api/v1/documents/{document['id']}", headers=auth_headers(token)).json()
    assert final["status"] == "completed", final.get("error_message")
    return final


def _parse_sse(raw: str) -> dict[str, list[dict]]:
    events: dict[str, list[dict]] = {}
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        name = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                name = line[7:].strip()
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name:
            events.setdefault(name, []).append(data or {})
    return events


POLICY = (
    b"Employee leave policy: annual leave is 25 days per year. "
    b"Sick leave is 10 days. Parental leave is 90 days. "
    b"Remote work is allowed up to three days per week with manager approval."
)


def test_rag_query_returns_grounded_answer_with_verified_citations(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag-query"))
    token = _register(client, "ragq@example.com", "RagQueryOrg")
    _upload(client, token, "policy.txt", POLICY)

    response = client.post(
        "/api/v1/rag/query",
        json={"query": "How many annual leave days do employees get?"},
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_mode"] in {"extractive", "llm", "no_evidence"}
    assert "25 days" in body["answer"]
    assert body["insufficient_evidence"] is False
    assert body["citations"], body
    citation = body["citations"][0]
    assert citation["chunk_id"]
    assert citation["document_id"]
    assert citation["document_title"]
    assert body["verification"]["status"] in {"supported", "partially_supported"}
    assert body["verification"]["disclaimer"]
    assert body["trace_id"]
    assert body["query_analysis"]["intent"]


def test_rag_query_stream_emits_context_tokens_and_final_payload(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag-stream"))
    token = _register(client, "rags@example.com", "RagStreamOrg")
    _upload(client, token, "policy.txt", POLICY)

    response = client.post(
        "/api/v1/rag/query/stream",
        json={"query": "How many sick leave days are allowed?"},
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    events = _parse_sse(response.text)
    assert "context" in events
    assert "token" in events
    assert "verification" in events
    final = events["rag_end"][-1]
    assert "10 days" in final["answer"]
    assert final["citations"]
    assert final["trace_id"]
    assert final["verification"]["status"] in {"supported", "partially_supported"}


def test_rag_query_without_evidence_is_explicit_not_fabricated(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag-empty"))
    token = _register(client, "rage@example.com", "RagEmptyOrg")
    _upload(client, token, "policy.txt", POLICY)

    response = client.post(
        "/api/v1/rag/query",
        json={"query": "What is the orbital period of Neptune's moon Triton?"},
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_mode"] == "no_evidence"
    assert body["insufficient_evidence"] is True
    assert body["citations"] == []
    assert body["verification"] is None


def test_rag_query_filters_and_organization_isolation(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag-filter"))
    token_a = _register(client, "fga@example.com", "FilterOrgA")
    token_b = _register(client, "fgb@example.com", "FilterOrgB")
    doc_one = _upload(client, token_a, "policy.txt", POLICY)
    _upload(client, token_a, "other.txt", b"The office address is 10 Market Street.")

    response = client.post(
        "/api/v1/rag/retrieval/test",
        json={"query": "What is the office address?", "filters": {"document_ids": [doc_one["id"]]}},
        headers=auth_headers(token_a),
    )
    assert response.status_code == 200, response.text
    evidence = response.json()["evidence"]
    assert all(item["document_id"] == doc_one["id"] for item in evidence)

    cross_org = client.post(
        "/api/v1/rag/query",
        json={"query": "What is the annual leave policy?"},
        headers=auth_headers(token_b),
    )
    assert cross_org.status_code == 200
    assert cross_org.json()["citations"] == []
    assert cross_org.json()["insufficient_evidence"] is True


def test_rag_text_ingestion_job_is_pollable_and_searchable(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag-ingest"))
    token = _register(client, "ragi@example.com", "RagIngestOrg")

    response = client.post(
        "/api/v1/rag/ingest",
        json={
            "content": "Disaster recovery policy: backups are taken every six hours and retained for 35 days.",
            "filename": "dr.md",
            "title": "Disaster Recovery Policy",
            "content_type": "text/markdown",
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 202, response.text
    body = response.json()
    job_id = body["job"]["job_id"]
    document_id = body["document"]["id"]

    polled = client.get(f"/api/v1/rag/ingestions/{job_id}", headers=auth_headers(token))
    assert polled.status_code == 200, polled.text
    assert polled.json()["status"] == "succeeded", polled.json()
    assert polled.json()["document_status"] == "completed"

    query = client.post(
        "/api/v1/rag/query",
        json={"query": "How long are backups retained?", "filters": {"document_ids": [document_id]}},
        headers=auth_headers(token),
    )
    assert query.status_code == 200, query.text
    assert "35 days" in query.json()["answer"]
    assert query.json()["citations"]


def test_rag_file_ingestion_rejects_unsupported_extension(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag-bad"))
    token = _register(client, "ragb@example.com", "RagBadOrg")
    response = client.post(
        "/api/v1/rag/ingest/file",
        files={"file": ("malware.exe", b"MZ\x90\x00binary", "application/octet-stream")},
        headers=auth_headers(token),
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error", response.text


def test_rag_reindex_and_index_deletion_keep_indexes_in_sync(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag-sync"))
    token = _register(client, "ragd@example.com", "RagDeleteOrg")
    document = _upload(client, token, "policy.txt", POLICY)

    sync = client.get(f"/api/v1/rag/documents/{document['id']}/sync", headers=auth_headers(token))
    assert sync.status_code == 200, sync.text
    assert sync.json()["lexical_chunks"] > 0
    assert sync.json()["in_sync"] is True, sync.json()

    deleted = client.delete(f"/api/v1/rag/documents/{document['id']}/index", headers=auth_headers(token))
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_chunks"] > 0
    after = client.get(f"/api/v1/rag/documents/{document['id']}/sync", headers=auth_headers(token)).json()
    assert after["lexical_chunks"] == 0
    assert after["in_sync"] is True

    reindexed = client.post(f"/api/v1/rag/documents/{document['id']}/reindex", headers=auth_headers(token))
    assert reindexed.status_code == 202, reindexed.text
    status_body = client.get(f"/api/v1/rag/ingestions/{reindexed.json()['job']['job_id']}", headers=auth_headers(token)).json()
    assert status_body["status"] == "succeeded"
    restored = client.get(f"/api/v1/rag/documents/{document['id']}/sync", headers=auth_headers(token)).json()
    assert restored["lexical_chunks"] > 0
    assert restored["in_sync"] is True


def test_rag_status_sources_and_config(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag-status"))
    token = _register(client, "ragst@example.com", "RagStatusOrg")
    document = _upload(client, token, "policy.txt", POLICY)

    status_body = client.get("/api/v1/rag/status", headers=auth_headers(token))
    assert status_body.status_code == 200, status_body.text
    status_json = status_body.json()
    assert status_json["documents"]["total"] >= 1
    assert status_json["documents"]["chunks"] > 0
    assert "vector" in status_json["index"]

    sources = client.get("/api/v1/rag/sources", headers=auth_headers(token))
    assert sources.status_code == 200
    assert any(item["id"] == document["id"] and item["chunk_count"] > 0 for item in sources.json()["documents"])

    config = client.get("/api/v1/rag/config", headers=auth_headers(token))
    assert config.status_code == 200, config.text
    assert config.json()["retrieval"]["fusion"] == "reciprocal_rank_fusion"
    serialized = json.dumps(config.json()).lower()
    assert "api_key" not in serialized
    assert "password" not in serialized

    health = client.get("/api/v1/rag/health", headers=auth_headers(token))
    assert health.status_code == 200
    assert health.json()["status"] in {"ok", "degraded"}


def test_rag_evaluation_uses_real_retrieval_metrics(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag-eval"))
    token = _register(client, "ragev@example.com", "RagEvalOrg")
    _upload(client, token, "policy.txt", POLICY)

    retrieval = client.post(
        "/api/v1/rag/retrieval/test",
        json={"query": "How many annual leave days?", "top_k": 5},
        headers=auth_headers(token),
    ).json()
    assert retrieval["evidence"]
    chunk_id = retrieval["evidence"][0]["chunk_id"]

    response = client.post(
        "/api/v1/rag/evaluation/run",
        json={
            "name": "policy-smoke",
            "items": [
                {
                    "query": "How many annual leave days?",
                    "relevant_chunk_ids": [chunk_id],
                }
            ],
            "k": 5,
            "generate": False,
            "persist": True,
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["item_count"] == 1
    assert report["metrics"]["recall@5"] == 1.0
    assert report["run_id"]

    runs = client.get("/api/v1/rag/evaluations", headers=auth_headers(token))
    assert runs.status_code == 200
    assert any(item["id"] == report["run_id"] for item in runs.json()["items"])


def test_rag_endpoints_require_authentication(client: TestClient):
    assert client.post("/api/v1/rag/query", json={"query": "hello"}).status_code == 401
    assert client.get("/api/v1/rag/status").status_code == 401
