"""Evaluation dataset loading (JSONL or inline)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.rag.exceptions import EvaluationError

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


@dataclass
class EvaluationItem:
    query: str
    relevant_chunk_ids: list[str] = field(default_factory=list)
    relevant_document_ids: list[str] = field(default_factory=list)
    reference_answer: str | None = None
    tags: list[str] = field(default_factory=list)


def parse_items(raw_items: list[dict]) -> list[EvaluationItem]:
    items: list[EvaluationItem] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise EvaluationError(f"dataset item {index} must be an object")
        query = str(raw.get("query") or "").strip()
        if not query:
            raise EvaluationError(f"dataset item {index} is missing a query")
        chunk_ids = [str(value) for value in raw.get("relevant_chunk_ids") or []]
        document_ids = [str(value) for value in raw.get("relevant_document_ids") or []]
        if not chunk_ids and not document_ids:
            raise EvaluationError(
                f"dataset item {index} needs relevant_chunk_ids or relevant_document_ids"
            )
        items.append(
            EvaluationItem(
                query=query,
                relevant_chunk_ids=chunk_ids,
                relevant_document_ids=document_ids,
                reference_answer=raw.get("reference_answer"),
                tags=[str(tag) for tag in raw.get("tags") or []],
            )
        )
    if not items:
        raise EvaluationError("dataset is empty")
    return items


def load_dataset(name: str) -> list[EvaluationItem]:
    """Load a bundled fixture by name (path traversal rejected)."""
    if "/" in name or "\\" in name or name.startswith("."):
        raise EvaluationError("dataset name must be a simple fixture name")
    path = FIXTURES_DIR / f"{name}.jsonl"
    if not path.is_file():
        raise EvaluationError(f"unknown evaluation fixture: {name}")
    items: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return parse_items(items)
