from __future__ import annotations

import uuid

from app.services.safe_sql import validate_read_only_sql
from app.models.agent import AgentExecution
from app.models.user import User
from app.services.agent_service import run_execution
from app.services.specialists import analytics_agent, email_agent
from app.services.intelligence import export_report
from app.services.storage import get_storage_backend
from app.agents.registry import route_request
from tests.test_authz_boundaries import auth_headers, login_token, register_user


def test_safe_sql_rejects_mutations_and_comments():
    for query in ("DELETE FROM users", "SELECT 1; SELECT 2", "SELECT 1 -- comment", "WITH x AS (SELECT 1) UPDATE users SET x=1"):
        try:
            validate_read_only_sql(query)
        except Exception:
            continue
        raise AssertionError(f"unsafe query accepted: {query}")


def test_safe_sql_bounds_select():
    assert "LIMIT 25" in validate_read_only_sql("SELECT id FROM records", 25)
    assert validate_read_only_sql("SELECT id FROM records LIMIT 5", 25).endswith("LIMIT 5")


def test_analytics_returns_measured_metrics_and_chart_spec():
    result = analytics_agent(
        {
            "columns": ["month", "revenue"],
            "rows": [["2026-01", 100], ["2026-02", 125]],
            "source_id": "source-1",
            "sql": "SELECT month, revenue FROM revenue",
        }
    )
    assert result["metrics"]["revenue"]["sum"] == 225
    assert result["chart"]["type"] == "line"
    assert result["source_id"] == "source-1"


def test_email_agent_reports_unavailable_connector_without_fake_results():
    result = email_agent("Summarize Project Alpha emails")
    assert result["available"] is False
    assert result["status"] == "unavailable"


def test_report_exports_are_persisted_in_supported_formats():
    organization_id = uuid.uuid4()
    report = {"title": "Revenue", "rows": [{"month": "January", "value": 10}]}
    for file_format in ("csv", "xlsx", "docx", "pdf"):
        result = export_report(organization_id, f"test-{file_format}", report, file_format)
        assert result["size"] > 0
        assert get_storage_backend().get_bytes(result["storage_key"])


def test_cross_source_requests_create_workflow_steps():
    steps = route_request("Analyze Project Alpha using all available documents, emails and database records")
    assert steps[0]["agent_id"] == "workflow"
    assert any(step["agent_id"] == "retrieval" for step in steps)


def test_rag_execution_is_persisted_and_org_scoped(client):
    register_user(client, "agent@example.com", "Agent Org", name="Agent User")
    token = login_token(client, "agent@example.com")
    response = client.post(
        "/api/v1/agents/executions",
        headers=auth_headers(token),
        json={"request": "Summarize the connected knowledge"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["agent_type"] == "retrieval"
    steps = client.get(f"/api/v1/agents/executions/{body['id']}/steps", headers=auth_headers(token))
    assert steps.status_code == 200
    assert {step["status"] for step in steps.json()} >= {"completed"}
    events = client.get(f"/api/v1/agents/executions/{body['id']}/events", headers=auth_headers(token))
    assert events.status_code == 200
    assert any(event["event_type"] == "execution.completed" for event in events.json())
    catalog = client.get("/api/v1/agents/catalog", headers=auth_headers(token))
    assert catalog.status_code == 200
    assert any(agent["id"] == "database" for agent in catalog.json())
    listed = client.get("/api/v1/agents/executions", headers=auth_headers(token))
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == body["id"]


def test_background_fallback_does_not_create_duplicate_execution(client, db_session):
    register_user(client, "background@example.com", "Background Org", name="Background User")
    token = login_token(client, "background@example.com")
    response = client.post(
        "/api/v1/agents/executions",
        headers=auth_headers(token),
        json={"request": "Summarize the connected knowledge", "background": True},
    )
    assert response.status_code == 201
    execution = db_session.query(AgentExecution).one()
    user = db_session.query(User).filter(User.email == "background@example.com").one()
    result = run_execution(db_session, user, execution.request, execution=execution, task_id="duplicate-delivery")
    assert result.id == execution.id
    assert db_session.query(AgentExecution).count() == 1
