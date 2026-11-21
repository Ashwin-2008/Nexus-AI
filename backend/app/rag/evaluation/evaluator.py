"""Evaluation runner.

Retrieval metrics use relevance labels supplied by the dataset. Generation
metrics are computed from the actual verification report of the generated
answer. No score is reported without running the pipeline.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.rag.config import RagConfig
from app.rag.context.builder import ContextBuilder
from app.rag.evaluation.datasets import EvaluationItem
from app.rag.evaluation.faithfulness import (
    citation_correctness,
    evidence_coverage,
    faithfulness,
    unsupported_claim_rate,
)
from app.rag.evaluation.relevance import answer_relevance
from app.rag.evaluation.retrieval_metrics import mean, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank
from app.rag.generation.generator import Generator
from app.rag.retrieval.retriever import Retriever
from app.rag.types import RagScope
from app.rag.verification.groundedness import GroundednessVerifier


@dataclass
class EvaluationReport:
    name: str
    item_count: int
    metrics: dict[str, float]
    items: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "hybrid"
    generated: bool = False
    duration_ms: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "item_count": self.item_count,
            "mode": self.mode,
            "generated": self.generated,
            "metrics": self.metrics,
            "items": self.items,
            "duration_ms": self.duration_ms,
            "errors": self.errors,
        }


class Evaluator:
    def __init__(
        self,
        config: RagConfig | None = None,
        *,
        retriever: Retriever | None = None,
        generator: Generator | None = None,
    ) -> None:
        self.config = config or RagConfig.from_settings()
        self.retriever = retriever or Retriever(self.config)
        self.generator = generator or Generator(self.config)
        self.context_builder = ContextBuilder(self.config)
        self.verifier = GroundednessVerifier(self.config)

    def run(
        self,
        db: Session,
        scope: RagScope,
        items: list[EvaluationItem],
        *,
        name: str = "evaluation",
        mode: str | None = None,
        k: int = 5,
        generate: bool = False,
    ) -> EvaluationReport:
        started = time.monotonic()
        retrieval_metrics: dict[str, list[float]] = {}
        generation_metrics: dict[str, list[float]] = {}
        item_reports: list[dict[str, Any]] = []
        errors: list[str] = []
        for item in items:
            result = self.retriever.retrieve(db, scope, item.query, mode=mode, top_k=k)
            ranks = [evidence.chunk_id for evidence in result.evidence]
            document_ranks = [evidence.document_id for evidence in result.evidence]
            if item.relevant_chunk_ids:
                relevant = item.relevant_chunk_ids
                ranked = ranks
            else:
                relevant = item.relevant_document_ids
                ranked = document_ranks
            item_metrics = {
                f"recall@{k}": recall_at_k(ranked, relevant, k),
                f"precision@{k}": precision_at_k(ranked, relevant, k),
                "mrr": reciprocal_rank(ranked, relevant, k),
                f"ndcg@{k}": ndcg_at_k(ranked, relevant, k),
            }
            for key, value in item_metrics.items():
                retrieval_metrics.setdefault(key, []).append(value)
            detail: dict[str, Any] = {
                "query": item.query,
                "retrieved_chunk_ids": ranks,
                "retrieval_metrics": item_metrics,
            }
            if generate:
                try:
                    bundle = self.context_builder.build(scope, result.evidence, query=item.query)
                    outcome = self.generator.generate(item.query, bundle)
                    report = self.verifier.verify(outcome.text, bundle.evidence, bundle.citations)
                    generation = {
                        "answer_mode": outcome.answer_mode,
                        "insufficient_evidence": outcome.insufficient_evidence,
                        "answer_relevance": answer_relevance(item.query, outcome.text),
                        "faithfulness": faithfulness(report),
                        "citation_correctness": citation_correctness(report),
                        "evidence_coverage": evidence_coverage(report),
                        "unsupported_claim_rate": unsupported_claim_rate(report),
                        "verification_status": report.status,
                    }
                    for key, value in generation.items():
                        if isinstance(value, (int, float)):
                            generation_metrics.setdefault(key, []).append(float(value))
                    detail["generation"] = generation
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{item.query[:60]}: {exc}"[:300])
            item_reports.append(detail)
        metrics = {key: round(mean(values), 4) for key, values in retrieval_metrics.items()}
        if generation_metrics:
            metrics.update({key: round(mean(values), 4) for key, values in generation_metrics.items()})
        return EvaluationReport(
            name=name,
            item_count=len(items),
            metrics=metrics,
            items=item_reports,
            mode=mode or self.config.retrieval_mode,
            generated=generate,
            duration_ms=int((time.monotonic() - started) * 1000),
            errors=errors,
        )
