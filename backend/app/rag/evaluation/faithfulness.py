"""Faithfulness/citation metrics derived from the verification report."""
from __future__ import annotations

from app.rag.constants import (
    VERIFICATION_PARTIALLY_SUPPORTED,
    VERIFICATION_SUPPORTED,
)
from app.rag.types import VerificationReport


def faithfulness(report: VerificationReport | None) -> float:
    if report is None or not report.claims:
        return 0.0
    score = 0.0
    for claim in report.claims:
        if claim.status == VERIFICATION_SUPPORTED:
            score += 1.0
        elif claim.status == VERIFICATION_PARTIALLY_SUPPORTED:
            score += 0.5
    return round(score / len(report.claims), 4)


def unsupported_claim_rate(report: VerificationReport | None) -> float:
    if report is None or not report.claims:
        return 0.0
    unsupported = sum(1 for claim in report.claims if claim.status == "unsupported")
    return round(unsupported / len(report.claims), 4)


def citation_correctness(report: VerificationReport | None) -> float:
    if report is None or not report.claims:
        return 0.0
    cited = sum(1 for claim in report.claims if claim.citation_indices)
    errors = len(report.citation_errors)
    if cited == 0:
        return 0.0
    return round(max(0.0, (cited - errors)) / cited, 4)


def evidence_coverage(report: VerificationReport | None) -> float:
    return float(report.evidence_coverage) if report else 0.0
