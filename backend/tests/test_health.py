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
