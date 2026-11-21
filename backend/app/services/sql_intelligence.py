"""Natural-language SQL helpers with provider and safety gates."""
from __future__ import annotations

import re
from typing import Any

from app.services.connectors import ConnectorContext, ConnectorError
from app.services.llm import ChatMessageData, LLMError, get_llm_provider, llm_available
from app.services.safe_sql import discover_schema, validate_read_only_sql


def schema_context(ctx: ConnectorContext) -> dict[str, Any]:
    return discover_schema(ctx)


def generate_sql(ctx: ConnectorContext, question: str) -> dict[str, Any]:
    if not question.strip():
        raise ConnectorError("Natural-language question must not be empty")
    schema = discover_schema(ctx)
    if not llm_available():
        raise LLMError("SQL generation requires a configured LLM provider")
    prompt = (
        "Generate one read-only SQL query for the user's request. Return only SQL, no markdown. "
        "Use only the tables and columns in this schema. Never mutate data or query secrets.\n"
        f"Schema: {schema}\nUser request: {question}"
    )
    generated = get_llm_provider().chat(
        [
            ChatMessageData(role="system", content="You are a SQL generation assistant. Output only one SELECT or WITH statement."),
            ChatMessageData(role="user", content=prompt),
        ],
        temperature=0,
        max_tokens=1200,
    ).text.strip()
    generated = re.sub(r"^```(?:sql)?\s*|\s*```$", "", generated, flags=re.IGNORECASE).strip()
    validated = validate_read_only_sql(generated)
    return {"sql": validated, "explanation": f"Generated from the permitted schema for: {question}", "schema": schema}
