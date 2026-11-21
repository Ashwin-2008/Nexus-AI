"""Request routing helpers shared with the supervisor.

Routing decisions come from the existing agent registry so there is exactly one
plan definition. RAG only adds retrieval-specific decisions (whether retrieval
is needed at all).
"""
from __future__ import annotations

from typing import Any

from app.agents.registry import list_agents, route_request
from app.rag.config import RagConfig
from app.rag.query.analyzer import QueryAnalyzer
from app.rag.types import QueryAnalysis


def plan_request(query: str, *, has_database_source: bool = False) -> list[dict[str, Any]]:
    return route_request(query, has_sql=has_database_source, has_source=False)


def plan_for_analysis(analysis: QueryAnalysis, *, has_database_source: bool = False) -> list[dict[str, Any]]:
    return plan_request(analysis.original, has_database_source=has_database_source)


def specialist_ids(query: str, *, has_database_source: bool = False) -> list[str]:
    return [step["agent_id"] for step in plan_request(query, has_database_source=has_database_source)]


def requires_retrieval(query: str, config: RagConfig | None = None) -> bool:
    analysis = QueryAnalyzer(config or RagConfig.from_settings()).analyze(query)
    return analysis.needs_retrieval


def capability_catalog() -> list[dict[str, Any]]:
    return [
        {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "capabilities": sorted(agent.capabilities),
            "tools": list(agent.tools),
        }
        for agent in list_agents()
    ]


__all__ = ["capability_catalog", "plan_for_analysis", "plan_request", "requires_retrieval", "specialist_ids"]
