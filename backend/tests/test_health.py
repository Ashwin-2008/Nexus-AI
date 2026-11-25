from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in {"healthy", "degraded", "unhealthy"}
    assert isinstance(data.get("services"), dict)
    assert data["services"].get("api") == "healthy"
    assert "database" in data["services"]
    assert "redis" in data["services"]
    assert "qdrant" in data["services"]
    assert "storage" in data["services"]
    assert "worker" in data["services"]

def test_health_reports_database_error_class(client: TestClient, monkeypatch) -> None:
    from app.api.v1 import health as health_module

    class BrokenConn:
        def __enter__(self):
            raise RuntimeError("boom")

        def __exit__(self, *exc):
            return False

    class BrokenEngine:
        def connect(self):
            raise RuntimeError("postgresql://user:secret@host/db is down")

    monkeypatch.setattr(health_module, "engine", BrokenEngine())
    data = client.get("/api/v1/health").json()
    assert data["services"]["database"] == "unhealthy"
    assert data["detail"]["database"] == "RuntimeError"
    assert "secret" not in str(data)