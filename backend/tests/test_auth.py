from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.security import create_access_token, decode_access_token


REGISTER_PAYLOAD = {
    "email": "alice@example.com",
    "password": "strongpass123",
    "full_name": "Alice Example",
    "organization_name": "Acme Corp",
}


def _register(client: TestClient, payload: dict | None = None) -> dict:
    resp = client.post("/api/v1/auth/register", json=payload or REGISTER_PAYLOAD)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_user_registration(client: TestClient) -> None:
    data = _register(client)
    assert data["email"] == REGISTER_PAYLOAD["email"]
    assert data["full_name"] == REGISTER_PAYLOAD["full_name"]
    assert data["is_active"] is True
    assert data["role"] == "admin"
    assert "id" in data and "organization_id" in data
    assert "hashed_password" not in data
    assert "password" not in data


def test_duplicate_registration_rejected(client: TestClient) -> None:
    _register(client)
    resp = client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert resp.status_code == 409
    body = resp.json()
    msg = body.get("detail") or body.get("error", {}).get("message", "")
    assert "already" in str(msg).lower()


def test_login_success(client: TestClient) -> None:
    _register(client)
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER_PAYLOAD["email"], "password": REGISTER_PAYLOAD["password"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert decode_access_token(data["access_token"]) is not None


def test_login_invalid_credentials(client: TestClient) -> None:
    _register(client)
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER_PAYLOAD["email"], "password": "wrongpassword"},
    )
    assert resp.status_code == 401
    # unknown user
    resp2 = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "whatever123"},
    )
    assert resp2.status_code == 401


def test_jwt_validation(client: TestClient) -> None:
    token = create_access_token(subject="11111111-1111-1111-1111-111111111111")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload.get("sub") == "11111111-1111-1111-1111-111111111111"
    assert decode_access_token("not-a-valid-token") is None
    assert decode_access_token("") is None


def test_current_user_retrieval(client: TestClient) -> None:
    _register(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER_PAYLOAD["email"], "password": REGISTER_PAYLOAD["password"]},
    ).json()
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == REGISTER_PAYLOAD["email"]
    assert data["role"] == "admin"


def test_unauthorized_requests(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)
    resp2 = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalidtoken"})
    assert resp2.status_code == 401
