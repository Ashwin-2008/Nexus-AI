"""Answer verification."""
from app.rag.verification.claim_extraction import Claim, extract_claims
from app.rag.verification.evidence_matching import EvidenceMatch, match_claim
from app.rag.verification.groundedness import GroundednessVerifier, verify_groundedness
from app.rag.verification.hallucination_checks import (
    contradictory_pairs,
    fabricated_citations,
    uncited_claims,
    unsupported_numbers,
)

__all__ = [
    "Claim",
    "EvidenceMatch",
    "GroundednessVerifier",
    "contradictory_pairs",
    "extract_claims",
    "fabricated_citations",
    "match_claim",
    "uncited_claims",
    "unsupported_numbers",
    "verify_groundedness",
]
