"""Prompt construction for grounded generation."""
from __future__ import annotations

from typing import Any

from app.prompts import load_prompt, prompt_version
from app.rag.context.builder import ContextBundle
from app.rag.types import QueryAnalysis

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "I could not find enough relevant information in the connected knowledge sources to answer "
    "this question with confidence. You may want to upload or connect sources that cover this topic, "
    "or try rephrasing the question."
)


def build_messages(
    query: str,
    bundle: ContextBundle,
    analysis: QueryAnalysis | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    system = load_prompt("system/grounded_assistant.md")
    format_instruction = _format_instruction(analysis)
    user = load_prompt(
        "rag/answer_generation.md",
        question=query,
        context=bundle.text,
        format_instruction=format_instruction,
    )
    metadata = {
        "prompt_versions": {
            "system": prompt_version("system/grounded_assistant.md"),
            "answer_generation": prompt_version("rag/answer_generation.md"),
        },
        "format_instruction": format_instruction,
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], metadata


def _format_instruction(analysis: QueryAnalysis | None) -> str:
    if analysis is None:
        return "Answer concisely and cite every factual statement."
    mapping = {
        "number": "Answer with the exact number and its unit, then cite the source passage.",
        "list": "Answer as a bulleted list; cite each bullet.",
        "comparison": "Answer as a structured comparison; cite evidence for each side.",
        "summary": "Answer as a concise summary with citations for the key points.",
        "procedure": "Answer as ordered steps; cite the procedure source.",
        "analysis": "Separate measured facts from interpretation; cite all facts.",
        "report": "Answer as a structured briefing with citations for every finding.",
    }
    return mapping.get(analysis.expected_answer_type, "Answer directly and concisely; cite every factual statement.")
