"""Agent routing derived from the authoritative agent registry.

RAG does not define a second agent framework: it asks the existing registry for
a deterministic plan and maps the resulting agent ids into suggestions.
"""
from __future__ import annotations

from app.agents.registry import route_request
from app.rag.types import QueryAnalysis


def suggested_agents(analysis: QueryAnalysis, *, has_database_source: bool = False) -> list[str]:
    steps = route_request(
        analysis.original,
        has_sql=has_database_source,
        has_source=bool(analysis.suggested_agents),
    )
    agents = [step["agent_id"] for step in steps]
    if "retrieval" not in agents:
        agents.insert(0, "retrieval")
    return _dedupe(agents)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
