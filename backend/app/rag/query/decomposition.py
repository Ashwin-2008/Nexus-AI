"""Question decomposition for multi-part/comparison questions."""
from __future__ import annotations

import json
import re

from app.rag.config import RagConfig

_COMPARE = re.compile(r"\bcompare\s+(.{3,120}?)\s+(?:and|with|versus|vs\.?)\s+(.{3,120})", re.IGNORECASE)
_SPLIT = re.compile(r"\s*(?:;|\bas well as\b|\band also\b)\s*", re.IGNORECASE)


def deterministic_decomposition(query: str, max_subqueries: int = 3) -> list[str]:
    text = (query or "").strip()
    if not text:
        return []
    compare = _COMPARE.search(text)
    if compare:
        left = compare.group(1).strip(" ,.")
        right = compare.group(2).strip(" ,.")
        parts = [f"{left} details", f"{right} details"]
        return [part for part in parts if len(part) > 4][:max_subqueries]
    parts = [part.strip(" ,.") for part in _SPLIT.split(text) if part.strip()]
    if len(parts) > 1 and all(len(part) >= 8 for part in parts):
        return parts[:max_subqueries]
    return []


def _parse_json_array(raw: str) -> list[str] | None:
    value = (raw or "").strip()
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.IGNORECASE).strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    items = [str(item).strip() for item in parsed if isinstance(item, str) and item.strip()]
    return items or None


def decompose_query(
    query: str,
    *,
    config: RagConfig | None = None,
    use_llm: bool = False,
) -> tuple[list[str], str]:
    config = config or RagConfig.from_settings()
    deterministic = deterministic_decomposition(query, config.max_subqueries)
    if not config.multi_query:
        return deterministic, "deterministic"
    if not use_llm:
        return deterministic, "deterministic"
    try:
        from app.prompts import load_prompt
        from app.services.llm import ChatMessageData, LLMError, get_llm_provider, llm_available

        if not llm_available():
            return deterministic, "deterministic"
        prompt = load_prompt(
            "rag/query_decomposition.md",
            max_subqueries=config.max_subqueries,
            question=query,
        )
        result = get_llm_provider().chat(
            [
                ChatMessageData(role="system", content="Return only a JSON array of retrieval queries."),
                ChatMessageData(role="user", content=prompt),
            ],
            temperature=0,
            max_tokens=200,
        )
        parsed = _parse_json_array(result.text)
        if not parsed or len(parsed) > config.max_subqueries:
            return deterministic, "deterministic"
        # Reject subqueries that drop numbers from the original question.
        original_digits = set(re.findall(r"\d+", query))
        if any(original_digits - set(re.findall(r"\d+", item)) for item in parsed):
            return deterministic, "deterministic"
        return parsed, "llm"
    except LLMError:
        return deterministic, "deterministic"
    except Exception:  # noqa: BLE001
        return deterministic, "deterministic"
