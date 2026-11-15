"""Tests for chat API, RAG grounding, citation verification, org isolation."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.test_authz_boundaries import auth_headers, login_token, register_user


def _upload_and_complete(client: TestClient, token: str, name: str, content: bytes, ctype: str = "text/plain") -> dict:
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": (name, content, ctype)},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    final = client.get(f"/api/v1/documents/{doc['id']}", headers=auth_headers(token)).json()
    assert final["status"] == "completed", f"got {final['status']}: {final.get('error_message')}"
    return final


def _parse_sse(raw: str) -> dict[str, list[dict]]:
    events: dict[str, list[dict]] = {}
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event_name = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_name = line[7:].strip()
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event_name:
            events.setdefault(event_name, []).append(data or {})
    return events


class TestConversations:
    def test_create_list_get_delete(self, client: TestClient):
        register_user(client, "chat1@example.com", "ChatOrg1")
        token = login_token(client, "chat1@example.com")
        r = client.post("/api/v1/chat/conversations", json={"title": "Test chat"}, headers=auth_headers(token))
        assert r.status_code == 201, r.text
        conv = r.json()
        assert conv["title"] == "Test chat"

        r2 = client.get("/api/v1/chat/conversations", headers=auth_headers(token))
        assert r2.status_code == 200
        assert len(r2.json()) == 1

        r3 = client.get(f"/api/v1/chat/conversations/{conv['id']}", headers=auth_headers(token))
        assert r3.status_code == 200

        r4 = client.delete(f"/api/v1/chat/conversations/{conv['id']}", headers=auth_headers(token))
        assert r4.status_code == 204
        r5 = client.get(f"/api/v1/chat/conversations/{conv['id']}", headers=auth_headers(token))
        assert r5.status_code == 404

    def test_conversation_isolation_between_users_and_orgs(self, client: TestClient):
        register_user(client, "chat-a@example.com", "ChatOrgA")
        token_a = login_token(client, "chat-a@example.com")
        conv = client.post("/api/v1/chat/conversations", json=None, headers=auth_headers(token_a)).json()

        register_user(client, "chat-b@example.com", "ChatOrgB")
        token_b = login_token(client, "chat-b@example.com")
        # Same org, different user: denied (owner-scoped)
        register_user(client, "chat-a2@example.com", "ChatOrgA")
        token_a2 = login_token(client, "chat-a2@example.com")
        r = client.get(f"/api/v1/chat/conversations/{conv['id']}", headers=auth_headers(token_a2))
        assert r.status_code == 404
        # Different org: denied
        r2 = client.get(f"/api/v1/chat/conversations/{conv['id']}", headers=auth_headers(token_b))
        assert r2.status_code == 404

    def test_requires_auth(self, client: TestClient):
        assert client.get("/api/v1/chat/conversations").status_code == 401


class TestGroundedRag:
    def test_grounded_answer_with_citations(self, client: TestClient, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag1"))
        register_user(client, "rag1@example.com", "RagOrg1")
        token = login_token(client, "rag1@example.com")
        _upload_and_complete(client, token, "policy.txt",
                             b"Employee leave policy: annual leave is 25 days per year. "
                             b"Sick leave is 10 days. Parental leave is 90 days.")
        conv = client.post("/api/v1/chat/conversations", json=None, headers=auth_headers(token)).json()
        r = client.post(
            f"/api/v1/chat/conversations/{conv['id']}/messages",
            json={"content": "How many annual leave days do employees get?", "stream": False},
            headers=auth_headers(token),
        )
        assert r.status_code == 200, r.text
        msg = r.json()
        assert msg["role"] == "assistant"
        assert msg["meta"]["answer_mode"] == "extractive"  # no LLM configured
        assert "25 days" in msg["content"]
        assert len(msg["citations"]) >= 1
        # every citation maps to a real retrieved chunk with document info
        for c in msg["citations"]:
            assert c["document_filename"] == "policy.txt"
            assert c["chunk_id"]
            assert "text" in c
        # user message persisted too
        msgs = client.get(f"/api/v1/chat/conversations/{conv['id']}/messages", headers=auth_headers(token)).json()
        assert [m["role"] for m in msgs] == ["user", "assistant"]

    def test_insufficient_evidence_explicit(self, client: TestClient, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag2"))
        register_user(client, "rag2@example.com", "RagOrg2")
        token = login_token(client, "rag2@example.com")
        _upload_and_complete(client, token, "cooking.txt", b"Chocolate cake requires flour, sugar, cocoa and butter.")
        conv = client.post("/api/v1/chat/conversations", json=None, headers=auth_headers(token)).json()
        r = client.post(
            f"/api/v1/chat/conversations/{conv['id']}/messages",
            json={"content": "What are the quantum mechanics implications of superconductivity?", "stream": False},
            headers=auth_headers(token),
        )
        assert r.status_code == 200
        msg = r.json()
        assert msg["meta"]["answer_mode"] == "no_evidence"
        assert msg["meta"]["insufficient_evidence"] is True
        assert "could not find enough" in msg["content"]
        assert msg["citations"] == []

    def test_streaming_sse(self, client: TestClient, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag3"))
        register_user(client, "rag3@example.com", "RagOrg3")
        token = login_token(client, "rag3@example.com")
        _upload_and_complete(client, token, "revenue.txt", b"Q1 revenue was 1,200,000 USD. Q2 revenue was 1,450,000 USD.")
        conv = client.post("/api/v1/chat/conversations", json=None, headers=auth_headers(token)).json()
        r = client.post(
            f"/api/v1/chat/conversations/{conv['id']}/messages",
            json={"content": "What was the Q1 revenue?", "stream": True},
            headers=auth_headers(token),
        )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
        events = _parse_sse(r.text)
        assert "message_start" in events
        assert "context" in events
        assert "message_end" in events
        end = events["message_end"][-1]
        assert end["answer_mode"] == "extractive"
        assert "1,200,000" in end["answer"]
        assert len(end["citations"]) >= 1
        # assistant message persisted after stream
        msgs = client.get(f"/api/v1/chat/conversations/{conv['id']}/messages", headers=auth_headers(token)).json()
        assert len(msgs) == 2

    def test_rag_org_isolation(self, client: TestClient, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag4"))
        register_user(client, "rag-a@example.com", "RagIsolationA")
        token_a = login_token(client, "rag-a@example.com")
        _upload_and_complete(client, token_a, "secret.txt", b"Project Phoenix classified budget is 9,000,000 USD.")

        register_user(client, "rag-b@example.com", "RagIsolationB")
        token_b = login_token(client, "rag-b@example.com")
        conv_b = client.post("/api/v1/chat/conversations", json=None, headers=auth_headers(token_b)).json()
        r = client.post(
            f"/api/v1/chat/conversations/{conv_b['id']}/messages",
            json={"content": "What is the Project Phoenix budget?", "stream": False},
            headers=auth_headers(token_b),
        )
        assert r.status_code == 200
        msg = r.json()
        # Org B has no knowledge indexed -> must be explicit insufficient evidence, no leakage
        assert msg["meta"]["insufficient_evidence"] is True
        assert "Phoenix" not in msg["content"].lower() or "could not find" in msg["content"]
        assert msg["citations"] == []
        assert "9,000,000" not in msg["content"]


    def test_llm_failure_degrades_to_extractive_with_insufficient_flag(self, client: TestClient, tmp_path, monkeypatch):
        """LLM configured but failing -> degrade to extractive / explicit no-evidence."""
        monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "rag5"))
        from app.services import rag_service as rag_mod

        register_user(client, "rag-lf@example.com", "RagLLMFail")
        token = login_token(client, "rag-lf@example.com")
        _upload_and_complete(client, token, "biz.txt", b"The quarterly target for sales is 2,000 units per region.")

        def failing_provider():
            raise rag_mod.LLMError("LLM unreachable (simulated)")

        monkeypatch.setattr(rag_mod, "llm_available", lambda: True)
        monkeypatch.setattr(rag_mod, "get_llm_provider", failing_provider)
        p = rag_mod.RagPipeline()
        p.use_llm = True

        conv = client.post("/api/v1/chat/conversations", json=None, headers=auth_headers(token)).json()
        # question with real overlap -> extractive degradation, citations kept
        r = client.post(
            f"/api/v1/chat/conversations/{conv['id']}/messages",
            json={"content": "quarterly sales target units", "stream": False},
            headers=auth_headers(token),
        )
        assert r.status_code == 200
        msg = r.json()
        assert msg["meta"]["answer_mode"] in ("extractive", "no_evidence")
        if msg["meta"]["answer_mode"] == "no_evidence":
            assert msg["meta"]["insufficient_evidence"] is True
        else:
            assert len(msg["citations"]) >= 1
            assert "2,000 units" in msg["content"]


class TestCitationVerification:
    def test_verify_citations_drops_fabricated(self):
        from app.services.rag_service import RetrievedChunk, verify_citations

        chunks = [
            RetrievedChunk(index=1, chunk_id="c1", document_id="d1", document_filename="a.txt",
                           text="alpha", score=1.0, provenance=[]),
            RetrievedChunk(index=2, chunk_id="c2", document_id="d1", document_filename="a.txt",
                           text="beta", score=0.9, provenance=[]),
        ]
        # Answer references [1] (valid) and [7] (fabricated)
        verified = verify_citations("Alpha says [1]. Something about [7].", chunks)
        assert [c["index"] for c in verified] == [1]
