"""RAG evaluation framework."""
from app.rag.evaluation.datasets import EvaluationItem, load_dataset, parse_items
from app.rag.evaluation.evaluator import EvaluationReport, Evaluator
from app.rag.evaluation.faithfulness import (
    citation_correctness,
    evidence_coverage,
    faithfulness,
    unsupported_claim_rate,
)
from app.rag.evaluation.relevance import answer_relevance, evidence_relevance
from app.rag.evaluation.reports import list_reports, persist_report, read_report
from app.rag.evaluation.retrieval_metrics import (
    mean,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

__all__ = [
    "EvaluationItem",
    "EvaluationReport",
    "Evaluator",
    "answer_relevance",
    "citation_correctness",
    "evidence_coverage",
    "evidence_relevance",
    "faithfulness",
    "list_reports",
    "load_dataset",
    "mean",
    "ndcg_at_k",
    "parse_items",
    "persist_report",
    "precision_at_k",
    "read_report",
    "recall_at_k",
    "reciprocal_rank",
    "unsupported_claim_rate",
]
