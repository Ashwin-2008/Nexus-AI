from __future__ import annotations

from fastapi.testclient import TestClient

from tests.test_authz_boundaries import login_token, register_user


REGISTER = {
    "email": "refresh@example.com",
    "password": "Strongpass1",
    "full_name": "Refresh User",
    "organization_name": "RefreshOrg",
}


def test_login_returns_refresh_and_refresh_rotates(client: TestClient) -> None:
    register_user(client, "refresh@example.com", "RefreshOrg", password="Strongpass1")
    login = client.post("/api/v1/auth/login", json={"email": "refresh@example.com", "password": "Strongpass1"})
    assert login.status_code == 200
    data = login.json()
    assert data.get("access_token")
    assert data.get("refresh_token")
    old_refresh = data["refresh_token"]

    ref = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert ref.status_code == 200, ref.text
    rdata = ref.json()
    assert rdata.get("access_token")
    assert rdata.get("refresh_token")
    assert rdata["refresh_token"] != old_refresh

    # old refresh should be revoked after rotation
    ref2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert ref2.status_code == 401


def test_logout_revokes_refresh(client: TestClient) -> None:
    register_user(client, "logout@example.com", "LogoutOrg", password="Strongpass1")
    login = client.post("/api/v1/auth/login", json={"email": "logout@example.com", "password": "Strongpass1"}).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    out = client.post("/api/v1/auth/logout", json={"refresh_token": login["refresh_token"]}, headers=headers)
    assert out.status_code == 200
    ref = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert ref.status_code == 401


def test_password_policy_rejects_weak_password(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "weakpass", "full_name": "W", "organization_name": "OrgW"},
    )
    # min_length 8 passes schema but policy requires letter+digit mix -> 400
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("error", {}).get("code") == "validation_error"
