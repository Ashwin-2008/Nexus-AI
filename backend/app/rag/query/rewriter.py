"""Conservative query rewriting.

Simple queries are not rewritten (cost control). LLM rewriting is attempted
only when the query is long, conversational, or contains pronoun references —
and the candidate is validated before use. Any failure falls back to the
deterministic normalization.
"""
from __future__ import annotations

import re

from app.rag.config import RagConfig

_POLITE_PREFIX = re.compile(
    r"^\s*(please|kindly|could you|can you|would you|i want to know|i'd like to know|tell me)\b[ ,]*",
    re.IGNORECASE,
)
_PRONOUN = re.compile(r"\b(it|they|them|this|that|those|these|its|their)\b", re.IGNORECASE)
_DIGITS = re.compile(r"\d+")


def normalize_query(query: str) -> str:
    text = re.sub(r"\s+", " ", (query or "").strip())
    text = _POLITE_PREFIX.sub("", text)
    return text.strip()


def needs_llm_rewrite(query: str, conversation: list[str] | None = None, config: RagConfig | None = None) -> bool:
    config = config or RagConfig.from_settings()
    if not config.query_rewrite:
        return False
    if len(query or "") > 180:
        return True
    if conversation and _PRONOUN.search(query or ""):
        return True
    return False


def _validate_candidate(candidate: str, original: str) -> str | None:
    value = (candidate or "").strip().strip('"').strip("'")
    if not value or "\n" in value:
        return None
    if len(value) > 400 or len(value) > max(80, len(original) * 3):
        return None
    # Numbers and quoted entities must survive rewriting unchanged.
    if set(_DIGITS.findall(original)) - set(_DIGITS.findall(value)):
        return None
    for quoted in re.findall(r"[\"']([^\"']{2,})[\"']", original):
        if quoted.lower() not in value.lower():
            return None
    return value


def rewrite_query(
    query: str,
    *,
    conversation: list[str] | None = None,
    config: RagConfig | None = None,
) -> tuple[str, str, list[str]]:
    """Return ``(rewritten, method, notes)``."""
    config = config or RagConfig.from_settings()
    normalized = normalize_query(query)
    notes: list[str] = []
    if not needs_llm_rewrite(query, conversation, config):
        return normalized, "deterministic", notes
    try:
        from app.prompts import load_prompt
        from app.services.llm import ChatMessageData, LLMError, get_llm_provider, llm_available

        if not llm_available():
            return normalized, "deterministic", ["llm unavailable; deterministic rewrite"]
        excerpt = "\n".join((conversation or [])[-4:])[:1200]
        prompt = load_prompt(
            "rag/query_rewrite.md",
            conversation=excerpt or "(no prior conversation)",
            question=normalized,
        )
        result = get_llm_provider().chat(
            [
                ChatMessageData(
                    role="system",
                    content="Rewrite the question into one retrieval query. Never add facts or answer it.",
                ),
                ChatMessageData(role="user", content=prompt),
            ],
            temperature=0,
            max_tokens=120,
        )
        candidate = _validate_candidate(result.text, normalized)
        if candidate is None:
            note = "llm rewrite rejected by validation"
            return normalized, "deterministic", [note]
        return candidate, "llm", notes
    except LLMError as exc:
        return normalized, "deterministic", [f"llm rewrite failed: {str(exc)[:200]}"]
    except Exception as exc:  # noqa: BLE001
        return normalized, "deterministic", [f"rewrite fallback: {str(exc)[:200]}"]
