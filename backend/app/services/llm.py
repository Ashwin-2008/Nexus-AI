"""LLM provider abstraction (OpenAI-compatible) + grounded extractive fallback.

- openai_compatible: chat completions over any OpenAI-compatible endpoint
  (OpenAI, Azure, vLLM, Ollama `v1`, LM Studio, ...), streaming and
  non-streaming.
- extractive: grounded, deterministic answerer that composes answers strictly
  from retrieved chunks (verbatim passages). Used when no LLM is configured.
  Clearly labeled `answer_mode: extractive` — it never invents content.

Selection: LLM_PROVIDER = openai_compatible | extractive (default: auto —
openai_compatible when an API key/base is configured, else extractive).
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


@dataclass
class ChatMessageData:
    role: str  # system | user | assistant
    content: str


@dataclass
class GenerationResult:
    text: str
    answer_mode: str  # "llm" | "extractive"
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int | None = None


class LLMProvider:
    """OpenAI-compatible chat completions provider."""

    name = "openai_compatible"

    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or settings.openai_api_key or ""
        self.model = model or settings.llm_model or "gpt-4o-mini"
        self.timeout = 60.0
        self.max_retries = 2
        if not self.api_key:
            raise LLMError(
                "LLM provider openai_compatible selected but no API key configured "
                "(set OPENAI_API_KEY and optionally OPENAI_BASE_URL)."
            )

    def stream_chat(self, messages: list[ChatMessageData], temperature: float = 0.2, max_tokens: int = 1024) -> Iterator[dict[str, Any]]:
        """Yield events: {'type':'token','text':...} and {'type':'usage',...}."""
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        started = time.monotonic()
        try:
            with httpx.stream("POST", url, headers=headers, json=payload, timeout=self.timeout) as resp:
                if resp.status_code != 200:
                    body = resp.read().decode("utf-8", errors="ignore")
                    raise LLMError(f"LLM API HTTP {resp.status_code}: {body[:300]}")
                usage: dict[str, Any] | None = None
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        text = delta.get("content")
                        if text:
                            yield {"type": "token", "text": text}
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                yield {
                    "type": "done",
                    "model": self.model,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                    "prompt_tokens": usage.get("prompt_tokens") if usage else None,
                    "completion_tokens": usage.get("completion_tokens") if usage else None,
                }
        except LLMError:
            raise
        except Exception as e:  # noqa: BLE001 — transport/protocol failures classified as LLMError
            raise LLMError(f"LLM streaming request failed: {e}") from e

    def chat(self, messages: list[ChatMessageData], temperature: float = 0.2, max_tokens: int = 1024) -> GenerationResult:
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        started = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise LLMError(f"LLM API transient HTTP {resp.status_code}")
                resp.raise_for_status()
                body = resp.json()
                text = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
                usage = body.get("usage") or {}
                return GenerationResult(
                    text=text,
                    answer_mode="llm",
                    model=self.model,
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
            except LLMError as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(0.5 * attempt)
            except Exception as e:  # noqa: BLE001
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(0.5 * attempt)
        raise LLMError(f"LLM chat failed after {self.max_retries} attempts: {last_error}")


# ---------------------------------------------------------------------------
# Extractive fallback (no LLM configured)
# ---------------------------------------------------------------------------

_SENT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_RE.split(text or "") if p.strip()]
    return parts


@dataclass
class ExtractiveGeneration:
    text: str
    answer_mode: str = "extractive"
    model: str = "none"
    latency_ms: int | None = None
    citations: list[int] = field(default_factory=list)


def extractive_answer(query: str, contexts: list[dict[str, Any]], max_sentences: int = 6) -> ExtractiveGeneration:
    """Compose a grounded answer strictly from retrieved chunks.

    Sentences are selected verbatim from retrieved passages ranked by overlap
    with the query terms. No content is invented. If retrieval is too weak,
    returns the standard insufficient-evidence message.
    """
    started = time.monotonic()
    query_terms = {t.lower() for t in re.findall(r"[\w']+", query) if len(t) > 2}
    candidates: list[tuple[float, str, int]] = []
    for ctx in contexts:
        chunk_index = int(ctx.get("index", 0))
        for sent in split_sentences(ctx.get("text", "")):
            sent_terms = {t.lower() for t in re.findall(r"[\w']+", sent)}
            overlap = len(query_terms & sent_terms)
            if overlap:
                candidates.append((float(overlap), sent, chunk_index))
    if not candidates:
        return ExtractiveGeneration(
            text=(
                "I could not find enough relevant information in the connected knowledge sources "
                "to answer this question. Try rephrasing, or upload documents that cover this topic."
            ),
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    candidates.sort(key=lambda c: -c[0])
    # Deduplicate near-identical sentences, keep best first.
    seen: set[str] = set()
    chosen: list[tuple[float, str, int]] = []
    for cand in candidates:
        key = cand[1].lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        chosen.append(cand)
        if len(chosen) >= max_sentences:
            break
    chosen.sort(key=lambda c: c[2])  # keep original document order
    lines = [f"[{chunk_index + 1}] {sent}" for _score, sent, chunk_index in chosen]
    text = "Here is what the retrieved sources say:\n" + "\n".join(lines)
    citation_ids = sorted({c[2] for c in chosen})
    return ExtractiveGeneration(
        text=text,
        latency_ms=int((time.monotonic() - started) * 1000),
        citations=citation_ids,
    )


def get_llm_provider() -> LLMProvider:
    provider = (settings.llm_provider or "auto").strip().lower()
    if provider == "extractive":
        raise LLMError("extractive selected: use extractive_answer() directly")
    if provider == "openai_compatible" or provider == "auto":
        return LLMProvider()
    raise LLMError(f"Unknown LLM provider '{provider}' (valid: openai_compatible, extractive)")


def llm_available() -> bool:
    try:
        get_llm_provider()
        return True
    except LLMError:
        return False
