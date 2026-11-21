"""Grounded answer generation with an explicit extractive fallback.

The LLM is used only when configured. If it is unavailable or fails, answers
are composed from verbatim retrieved sentences (``answer_mode=extractive``),
never fabricated. Evidence-free questions return an explicit
``answer_mode=no_evidence`` response.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

from app.rag.config import RagConfig
from app.rag.context.builder import ContextBundle
from app.rag.exceptions import GenerationError
from app.rag.generation.prompts import INSUFFICIENT_EVIDENCE_MESSAGE, build_messages
from app.rag.generation.provider import chat, llm_configured
from app.rag.generation.structured_output import parse_answer
from app.rag.query.expansion import query_terms, stem_variants
from app.rag.types import QueryAnalysis

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass
class GenerationOutcome:
    text: str
    answer_mode: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int = 0
    prompt_versions: dict[str, str] = field(default_factory=dict)
    degraded_from: str | None = None
    insufficient_evidence: bool = False
    structured: bool = False
    warnings: list[str] = field(default_factory=list)


class Generator:
    def __init__(self, config: RagConfig | None = None) -> None:
        self.config = config or RagConfig.from_settings()

    def generate(
        self,
        query: str,
        bundle: ContextBundle,
        analysis: QueryAnalysis | None = None,
    ) -> GenerationOutcome:
        started = time.monotonic()
        if not bundle.passages:
            return GenerationOutcome(
                text=INSUFFICIENT_EVIDENCE_MESSAGE,
                answer_mode="no_evidence",
                model="none",
                latency_ms=_ms(started),
                insufficient_evidence=True,
            )
        if not llm_configured():
            return self._extractive(query, bundle, started, degraded_from=None)

        messages, prompt_metadata = build_messages(query, bundle, analysis)
        try:
            result = chat(messages)
        except GenerationError as exc:
            outcome = self._extractive(query, bundle, started, degraded_from="llm")
            outcome.warnings.append(f"LLM generation failed: {str(exc)[:250]}")
            outcome.prompt_versions = prompt_metadata.get("prompt_versions", {})
            return outcome
        parsed = parse_answer(result.text)
        if not parsed.answer:
            outcome = self._extractive(query, bundle, started, degraded_from="llm")
            outcome.warnings.extend(parsed.warnings or ["LLM returned no usable answer"])
            return outcome
        return GenerationOutcome(
            text=parsed.answer,
            answer_mode="llm",
            model=result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            latency_ms=result.latency_ms or _ms(started),
            prompt_versions=prompt_metadata.get("prompt_versions", {}),
            structured=parsed.structured,
            warnings=parsed.warnings,
        )

    def stream(
        self,
        query: str,
        bundle: ContextBundle,
        analysis: QueryAnalysis | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield ``{'type': 'token'|'done'|'error', ...}`` events."""
        started = time.monotonic()
        if not bundle.passages:
            yield {
                "type": "done",
                "outcome": GenerationOutcome(
                    text=INSUFFICIENT_EVIDENCE_MESSAGE,
                    answer_mode="no_evidence",
                    model="none",
                    latency_ms=_ms(started),
                    insufficient_evidence=True,
                ),
            }
            return
        if not llm_configured():
            outcome = self._extractive(query, bundle, started, degraded_from=None)
            yield {"type": "token", "text": outcome.text}
            yield {"type": "done", "outcome": outcome}
            return

        messages, prompt_metadata = build_messages(query, bundle, analysis)
        chunks: list[str] = []
        usage: dict[str, Any] = {}
        try:
            from app.rag.generation.provider import stream

            for event in stream(messages):
                if event["type"] == "token":
                    chunks.append(event["text"])
                    yield {"type": "token", "text": event["text"]}
                elif event["type"] == "done":
                    usage = event
            text = "".join(chunks)
            if not text.strip():
                raise GenerationError("LLM streamed no content")
            parsed = parse_answer(text)
            yield {
                "type": "done",
                "outcome": GenerationOutcome(
                    text=parsed.answer,
                    answer_mode="llm",
                    model=str(usage.get("model") or ""),
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    latency_ms=int(usage.get("latency_ms") or _ms(started)),
                    prompt_versions=prompt_metadata.get("prompt_versions", {}),
                    structured=parsed.structured,
                    warnings=parsed.warnings,
                ),
            }
        except Exception as exc:  # noqa: BLE001 — degrade, never fabricate
            outcome = self._extractive(query, bundle, started, degraded_from="llm")
            outcome.warnings.append(f"LLM streaming failed: {str(exc)[:250]}")
            outcome.prompt_versions = prompt_metadata.get("prompt_versions", {})
            yield {"type": "token", "text": outcome.text}
            yield {"type": "done", "outcome": outcome}

    # -- fallback ------------------------------------------------------------

    def _extractive(
        self,
        query: str,
        bundle: ContextBundle,
        started: float,
        *,
        degraded_from: str | None,
    ) -> GenerationOutcome:
        wanted: set[str] = set()
        for term in query_terms(query):
            wanted |= stem_variants(term)
        candidates: list[tuple[float, int, str]] = []
        for passage in bundle.passages:
            for sentence in _SENTENCE_RE.split(passage.evidence.text or ""):
                sentence = sentence.strip()
                if len(sentence) < 12:
                    continue
                words = {word.lower() for word in re.findall(r"[A-Za-zÀ-ÿ0-9]+", sentence)}
                overlap = len(wanted & words)
                if overlap:
                    candidates.append((overlap / max(1, len(wanted)), passage.index, sentence))
        if not candidates:
            return GenerationOutcome(
                text=INSUFFICIENT_EVIDENCE_MESSAGE,
                answer_mode="no_evidence",
                model="none",
                latency_ms=_ms(started),
                degraded_from=degraded_from,
                insufficient_evidence=True,
            )
        candidates.sort(key=lambda item: (-item[0], item[1]))
        seen: set[str] = set()
        selected: list[tuple[float, int, str]] = []
        for candidate in candidates:
            key = candidate[2].lower()[:120]
            if key in seen:
                continue
            seen.add(key)
            selected.append(candidate)
            if len(selected) >= 6:
                break
        selected.sort(key=lambda item: item[1])
        lines = [f"[{index}] {sentence}" for _score, index, sentence in selected]
        return GenerationOutcome(
            text="Here is what the retrieved sources say:\n" + "\n".join(lines),
            answer_mode="extractive",
            model="none",
            latency_ms=_ms(started),
            degraded_from=degraded_from,
            warnings=["extractive answer: verbatim sentences, no LLM synthesis"],
        )


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
