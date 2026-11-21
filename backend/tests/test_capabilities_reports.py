from __future__ import annotations

from fastapi.testclient import TestClient

from tests.test_authz_boundaries import auth_headers, login_token, register_user


def test_system_capabilities_exposes_secret_free_provider_inventory(client: TestClient) -> None:
    register_user(client, "capabilities@example.com", "Capabilities Org", name="Capabilities User")
    token = login_token(client, "capabilities@example.com")

    response = client.get("/api/v1/system/capabilities", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["providers"]["embeddings"]["provider"]
    assert isinstance(body["providers"]["embeddings"]["semantic"], bool)
    assert body["providers"]["vector"]["backend"]
    assert "email" in body["connectors"]
    assert "retrieval" in body
    assert "worker" in body
    assert "secret" not in response.text.lower()


def test_report_agent_artifact_is_listed_and_downloadable(client: TestClient) -> None:
    register_user(client, "reporter@example.com", "Reporter Org", name="Reporter")
    token = login_token(client, "reporter@example.com")
    headers = auth_headers(token)

    execution = client.post(
        "/api/v1/agents/executions",
        headers=headers,
        json={"request": "Generate a report on the connected knowledge"},
    )
    assert execution.status_code == 201, execution.text
    assert execution.json()["status"] == "succeeded", execution.text
    assert execution.json()["result"]["format"] == "markdown"

    listed = client.get("/api/v1/intelligence/reports", headers=headers)
    assert listed.status_code == 200, listed.text
    reports = listed.json()
    assert len(reports) == 1
    report = reports[0]
    assert report["file_format"] == "md"
    assert report["execution_id"] == execution.json()["id"]
    assert report["status"] == "completed"

    download = client.get(f"/api/v1/intelligence/reports/{report['id']}/download", headers=headers)
    assert download.status_code == 200, download.text
    assert download.headers["content-type"].startswith("text/markdown")
    assert b"# NEXUS AI Report" in download.content


def test_analytics_activity_counts_are_present(client: TestClient) -> None:
    register_user(client, "activity@example.com", "Activity Org", name="Activity User")
    token = login_token(client, "activity@example.com")

    response = client.get("/api/v1/analytics/overview?days=14", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    activity = response.json()["activity"]
    assert activity == {
        "conversations": 0,
        "reports": 0,
        "pending_approvals": 0,
        "active_ingestions": 0,
    }


def test_cancelling_execution_revokes_pending_approval(client: TestClient) -> None:
    register_user(client, "cancel@example.com", "Cancel Org", name="Cancel User")
    token = login_token(client, "cancel@example.com")
    headers = auth_headers(token)

    source = client.post(
        "/api/v1/sources",
        headers=headers,
        json={
            "name": "Support mailbox",
            "type": "email",
            "config": {
                "host": "imap.example.com",
                "folder": "INBOX",
                "smtp_host": "smtp.example.com",
                "from_address": "support@example.com",
            },
            "credentials": {"username": "support@example.com", "password": "placeholder"},
        },
    )
    assert source.status_code == 201, source.text

    draft = client.post(
        "/api/v1/intelligence/email/draft",
        headers=headers,
        json={
            "source_id": source.json()["id"],
            "recipients": ["customer@example.com"],
            "subject": "Status update",
            "body": "Your request is being reviewed.",
        },
    )
    assert draft.status_code == 201, draft.text
    execution_id = draft.json()["execution_id"]
    approval_id = draft.json()["approval_id"]

    cancelled = client.post(f"/api/v1/agents/executions/{execution_id}/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    pending = client.get("/api/v1/agents/approvals?pending_only=true", headers=headers)
    assert pending.status_code == 200
    assert all(item["id"] != approval_id for item in pending.json())

    late_approval = client.post(f"/api/v1/agents/approvals/{approval_id}/approve", headers=headers)
    assert late_approval.status_code == 409, late_approval.text
