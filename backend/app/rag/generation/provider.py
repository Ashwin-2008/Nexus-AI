"""LLM provider access for generation (reuses app.services.llm)."""
from __future__ import annotations

from typing import Any, Iterator

from app.rag.exceptions import GenerationError


def llm_configured() -> bool:
    try:
        from app.services.llm import llm_available

        return llm_available()
    except Exception:  # noqa: BLE001
        return False


def chat(messages: list[dict[str, str]], *, temperature: float = 0.2, max_tokens: int = 1200):
    from app.services.llm import ChatMessageData, LLMError, get_llm_provider

    try:
        provider = get_llm_provider()
        return provider.chat(
            [ChatMessageData(role=item["role"], content=item["content"]) for item in messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except LLMError as exc:
        raise GenerationError(str(exc)) from exc


def stream(messages: list[dict[str, str]], *, temperature: float = 0.2, max_tokens: int = 1200) -> Iterator[dict[str, Any]]:
    from app.services.llm import ChatMessageData, LLMError, get_llm_provider

    try:
        provider = get_llm_provider()
        yield from provider.stream_chat(
            [ChatMessageData(role=item["role"], content=item["content"]) for item in messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except LLMError as exc:
        raise GenerationError(str(exc)) from exc
