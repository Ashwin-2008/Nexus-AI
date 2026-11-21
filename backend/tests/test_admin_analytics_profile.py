from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_password_hash
from app.models.rag import RagQueryLog
from app.models.user import Role, User

ADMIN = {
    "email": "admin@example.com",
    "password": "AdminPass123",
    "full_name": "Admin User",
    "organization_name": "Acme",
}


def _register_admin(client: TestClient) -> dict:
    response = client.post("/api/v1/auth/register", json=ADMIN)
    assert response.status_code == 201, response.text
    return response.json()


def _token(client: TestClient, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _member_token(db: Session, organization_id: str, email: str = "member@example.com") -> str:
    member_role = db.query(Role).filter(Role.name == "member").one()
    member = User(
        email=email,
        hashed_password=get_password_hash("MemberPass123"),
        full_name="Member User",
        organization_id=uuid.UUID(organization_id),
        role_id=member_role.id,
        is_active=True,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return create_access_token(subject=str(member.id), extra_claims={"org": str(member.organization_id)})


def test_profile_update_and_audit_log(client: TestClient) -> None:
    admin = _register_admin(client)
    token = _token(client, ADMIN["email"], ADMIN["password"])
    headers = {"Authorization": f"Bearer {token}"}

    response = client.patch(
        "/api/v1/auth/me",
        headers=headers,
        json={"full_name": "Renamed Admin", "email": "renamed@example.com"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["full_name"] == "Renamed Admin"
    assert body["email"] == "renamed@example.com"

    logs = client.get("/api/v1/admin/audit-logs", headers=headers)
    assert logs.status_code == 200, logs.text
    actions = {item["action"] for item in logs.json()["items"]}
    assert "auth.profile_updated" in actions

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "renamed@example.com"


def test_change_password_and_login_with_new_password(client: TestClient) -> None:
    _register_admin(client)
    token = _token(client, ADMIN["email"], ADMIN["password"])
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": ADMIN["password"], "new_password": "NewAdminPass123"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["message"] == "Password updated"

    old_login = client.post("/api/v1/auth/login", json={"email": ADMIN["email"], "password": ADMIN["password"]})
    assert old_login.status_code == 401
    _token(client, ADMIN["email"], "NewAdminPass123")


def test_change_password_rejects_wrong_current_password(client: TestClient) -> None:
    _register_admin(client)
    token = _token(client, ADMIN["email"], ADMIN["password"])
    response = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "not-the-password", "new_password": "AnotherPass123"},
    )
    assert response.status_code == 400
    body = response.json()
    detail = body.get("detail")
    message = detail.get("message") if isinstance(detail, dict) else body.get("error", {}).get("message")
    assert "incorrect" in (message or "").lower()


def test_admin_overview_and_member_forbidden(client: TestClient, db_session: Session) -> None:
    organization = _register_admin(client)
    token = _token(client, ADMIN["email"], ADMIN["password"])
    admin_headers = {"Authorization": f"Bearer {token}"}

    overview = client.get("/api/v1/admin/overview", headers=admin_headers)
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["organization"]["id"] == organization["organization_id"]
    assert body["counts"]["users"] == 1

    users = client.get("/api/v1/admin/users", headers=admin_headers)
    assert users.status_code == 200
    assert len(users.json()["items"]) == 1

    member_token = _member_token(db_session, organization["organization_id"])
    forbidden = client.get("/api/v1/admin/overview", headers={"Authorization": f"Bearer {member_token}"})
    assert forbidden.status_code == 403
    body = forbidden.json()
    detail = body.get("detail")
    message = detail.get("message") if isinstance(detail, dict) else body.get("error", {}).get("message")
    assert "administrator" in (message or "").lower()


def test_analytics_overview_shape(client: TestClient) -> None:
    _register_admin(client)
    token = _token(client, ADMIN["email"], ADMIN["password"])
    response = client.get("/api/v1/analytics/overview?days=14", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["window_days"] == 14
    assert len(body["series"]) == 14
    assert body["queries"]["total_all_time"] == 0
    assert body["knowledge"]["documents_total"] == 0
    assert body["agents"]["total"] == 0
    assert body["evaluation"]["run_id"] is None


def test_analytics_reads_persisted_query_telemetry(client: TestClient, db_session: Session) -> None:
    organization = _register_admin(client)
    token = _token(client, ADMIN["email"], ADMIN["password"])
    db_session.add(
        RagQueryLog(
            organization_id=uuid.UUID(organization["organization_id"]),
            user_id=uuid.UUID(organization["id"]),
            query="retention policy",
            mode="hybrid",
            retrieved_count=3,
            reranked_count=3,
            citation_count=2,
            answer_mode="extractive",
            verification_status="supported",
            retrieval_latency_ms=12,
            generation_latency_ms=3,
            total_latency_ms=15,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    db_session.commit()

    response = client.get("/api/v1/analytics/overview?days=14", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["queries"]["window"] == 1
    assert body["queries"]["successful"] == 1
    assert body["queries"]["success_rate"] == 100.0
    assert body["queries"]["avg_latency_ms"] == 15.0
    assert body["distribution"]["answer_modes"] == {"extractive": 1}
    assert body["distribution"]["verification"] == {"supported": 1}
