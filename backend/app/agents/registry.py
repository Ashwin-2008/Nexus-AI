"""Capability-based specialist agent registry.

Routing is intentionally deterministic and conservative. The LLM may enrich
plans later, but it never decides permissions or directly invokes tools.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    name: str
    description: str
    capabilities: frozenset[str]
    required_permissions: frozenset[str]
    tools: tuple[str, ...]


AGENTS = (
    AgentDefinition("retrieval", "Knowledge Retrieval Agent", "Finds grounded organizational evidence.", frozenset({"retrieve", "cite"}), frozenset({"knowledge.read"}), ("knowledge.search",)),
    AgentDefinition("document", "Document Intelligence Agent", "Summarizes and compares permitted documents.", frozenset({"summarize_documents", "compare_documents"}), frozenset({"knowledge.read"}), ("knowledge.search", "document.read")),
    AgentDefinition("database", "Database Intelligence Agent", "Discovers schemas and executes bounded read-only SQL.", frozenset({"schema_discovery", "safe_sql"}), frozenset({"database.read"}), ("database.schema", "database.query")),
    AgentDefinition("analytics", "Analytics Agent", "Analyzes structured result sets without inventing metrics.", frozenset({"aggregate", "compare", "trend"}), frozenset({"analytics.read"}), ("analytics.calculate",)),
    AgentDefinition("verification", "Verification Agent", "Checks evidence and citation support.", frozenset({"verify_evidence", "detect_conflicts"}), frozenset({"knowledge.read"}), ("knowledge.verify",)),
    AgentDefinition("report", "Report Generation Agent", "Produces structured evidence-backed reports.", frozenset({"report"}), frozenset({"report.create"}), ("report.generate",)),
    AgentDefinition("research", "Research Agent", "Combines evidence across permitted organizational sources.", frozenset({"research", "cross_source"}), frozenset({"knowledge.read"}), ("knowledge.search", "source.compare")),
    AgentDefinition("email", "Email Intelligence Agent", "Searches connected mail without inventing unavailable results.", frozenset({"email.search", "email.summarize"}), frozenset({"connector.email.read"}), ("email.search",)),
    AgentDefinition("workflow", "Workflow Agent", "Coordinates permitted specialist tools and dependencies.", frozenset({"orchestrate"}), frozenset({"workflow.execute"}), ("workflow.dispatch",)),
)


def list_agents() -> list[AgentDefinition]:
    return list(AGENTS)


def get_agent(agent_id: str) -> AgentDefinition:
    for agent in AGENTS:
        if agent.agent_id == agent_id:
            return agent
    raise KeyError(f"Unknown agent: {agent_id}")


def route_request(request: str, has_sql: bool = False, has_source: bool = False) -> list[dict[str, Any]]:
    text = request.lower()
    steps: list[dict[str, Any]] = []
    if any(word in text for word in ("analyze project", "project intelligence", "contract intelligence", "organization intelligence", "organizational performance", "cross-source")):
        steps.append({"key": "workflow", "agent_id": "workflow", "description": "Coordinate authorized cross-source intelligence"})
    if has_sql or any(word in text for word in ("database", "sql", "table", "revenue", "sales", "customers")):
        steps.append({"key": "database", "agent_id": "database", "description": "Inspect and query the permitted database"})
    if has_source or not steps or steps or any(word in text for word in ("document", "policy", "report", "knowledge", "summarize", "compare")):
        steps.append({"key": "retrieval", "agent_id": "retrieval", "description": "Retrieve supporting organizational evidence"})
    if any(word in text for word in ("research", "across sources", "cross-source")):
        steps.append({"key": "research", "agent_id": "research", "description": "Combine evidence across permitted sources", "dependencies": [step["key"] for step in steps]})
    if any(word in text for word in ("email", "mailbox", "inbox")):
        steps.append({"key": "email", "agent_id": "email", "description": "Search the configured email connector", "dependencies": [step["key"] for step in steps]})
    if any(word in text for word in ("management report", "generate a report", "report")):
        steps.append({"key": "report", "agent_id": "report", "description": "Generate an evidence-backed report", "dependencies": [step["key"] for step in steps]})
    if len(steps) > 1 or any(word in text for word in ("analyze", "compare", "trend", "status")):
        steps.append({"key": "analytics", "agent_id": "analytics", "description": "Analyze returned structured evidence", "dependencies": [step["key"] for step in steps]})
    steps.append({"key": "verification", "agent_id": "verification", "description": "Verify evidence and provenance", "dependencies": [step["key"] for step in steps]})
    return steps
