"""Answer groundedness verification.

Produces a transparent per-claim status plus an aggregate status. The method is
deterministic lexical grounding; callers must not present the result as a
guarantee of factuality.
"""
from __future__ import annotations

from app.rag.citations.validation import cited_indices, validate_citations
from app.rag.config import RagConfig
from app.rag.constants import (
    VERIFICATION_CONFLICTING,
    VERIFICATION_INSUFFICIENT,
    VERIFICATION_PARTIALLY_SUPPORTED,
    VERIFICATION_SUPPORTED,
    VERIFICATION_UNSUPPORTED,
)
from app.rag.types import Citation, ClaimVerification, EvidenceChunk, VerificationReport
from app.rag.verification.claim_extraction import extract_claims
from app.rag.verification.evidence_matching import match_claim
from app.rag.verification.hallucination_checks import fabricated_citations
from app.rag.verification.llm_verifier import verify_claims_with_llm


class GroundednessVerifier:
    def __init__(self, config: RagConfig | None = None) -> None:
        self.config = config or RagConfig.from_settings()

    def verify(
        self,
        answer: str,
        evidence: list[EvidenceChunk],
        citations: list[Citation] | None = None,
    ) -> VerificationReport:
        claims = extract_claims(answer)
        by_index = {index: item for index, item in enumerate(evidence, start=1)}
        used = cited_indices(answer)
        citation_errors: list[str] = []
        fabricated = fabricated_citations(used, len(evidence))
        if fabricated:
            citation_errors.append(f"answer cited non-existent passages: {fabricated}")
        if citations is not None:
            _, errors, _ = validate_citations(answer, evidence, citations)
            citation_errors.extend(errors)

        verified_claims: list[ClaimVerification] = []
        ambiguous: list[tuple[int, str, list[EvidenceChunk]]] = []
        for claim in claims:
            cited = [by_index[index] for index in claim.citation_indices if index in by_index]
            if not claim.citation_indices:
                verified_claims.append(
                    ClaimVerification(
                        claim=claim.text,
                        status=VERIFICATION_UNSUPPORTED,
                        reasons=["claim has no citation"],
                        support_score=0.0,
                    )
                )
                continue
            if not cited:
                verified_claims.append(
                    ClaimVerification(
                        claim=claim.text,
                        status=VERIFICATION_INSUFFICIENT,
                        citation_indices=list(claim.citation_indices),
                        reasons=["cited passages do not exist in the retrieved evidence"],
                        support_score=0.0,
                    )
                )
                continue
            match = match_claim(claim.text, cited)
            status = self._status(match.score, match.contradictory, match.negation_mismatch)
            verified_claims.append(
                ClaimVerification(
                    claim=claim.text,
                    status=status,
                    citation_indices=list(claim.citation_indices),
                    evidence_chunk_ids=match.chunk_ids,
                    support_score=match.score,
                    reasons=match.reasons,
                    unsupported_numbers=match.unsupported_numbers,
                )
            )
            # The lexical matcher is intentionally conservative. Paraphrases,
            # numeric re-statements and sentence-level negation are exactly the
            # cases it flags without being sure. Ask the configured LLM to audit
            # only those claims, with their cited passages, and keep the
            # deterministic result when no model is available.
            if self.config.llm_verification and (
                match.score < self.config.support_threshold
                or match.contradictory
                or match.negation_mismatch
            ):
                ambiguous.append((len(verified_claims) - 1, claim.text, cited))

        refined = 0
        if ambiguous:
            verdicts = verify_claims_with_llm([(text, cited) for _, text, cited in ambiguous])
            for local_index, verdict in verdicts.items():
                if local_index >= len(ambiguous):
                    continue
                claim_index, _, _ = ambiguous[local_index]
                target = verified_claims[claim_index]
                mapped = {
                    "supported": VERIFICATION_SUPPORTED,
                    "partial": VERIFICATION_PARTIALLY_SUPPORTED,
                    "unsupported": VERIFICATION_UNSUPPORTED,
                    "conflicting": VERIFICATION_CONFLICTING,
                }.get(verdict["verdict"])
                if not mapped:
                    continue
                # Never let the LLM override a missing number in the cited
                # passage. That is the one deterministic signal strong enough
                # to keep a claim out of the fully-supported bucket.
                if (
                    mapped == VERIFICATION_SUPPORTED
                    and target.unsupported_numbers
                    and verdict["score"] < 0.8
                ):
                    mapped = VERIFICATION_PARTIALLY_SUPPORTED
                target.status = mapped
                target.support_score = round(max(target.support_score, verdict["score"]), 4)
                reason = verdict.get("reason") or ""
                if reason:
                    target.reasons = [f"LLM entailment: {reason}"]
                refined += 1

        unsupported = [claim.claim for claim in verified_claims if claim.status == VERIFICATION_UNSUPPORTED]
        conflicting = [claim.claim for claim in verified_claims if claim.status == VERIFICATION_CONFLICTING]
        insufficient = [claim.claim for claim in verified_claims if claim.status == VERIFICATION_INSUFFICIENT]
        supported_count = sum(
            1 for claim in verified_claims if claim.status in {VERIFICATION_SUPPORTED, VERIFICATION_PARTIALLY_SUPPORTED}
        )
        coverage = supported_count / len(verified_claims) if verified_claims else 0.0
        return VerificationReport(
            status=self._aggregate(verified_claims),
            claims=verified_claims,
            unsupported_claims=unsupported,
            conflicting_claims=conflicting,
            insufficient_claims=insufficient,
            citation_errors=citation_errors,
            evidence_coverage=round(coverage, 4),
            method=(
                "deterministic_lexical_grounding+llm_entailment"
                if refined
                else "deterministic_lexical_grounding"
            ),
            disclaimer=(
                "Verification combines lexical support with an optional meaning-based LLM audit. "
                "It is a review signal, not a guarantee against hallucination."
            ),
            notes=[
                f"{len(verified_claims)} claim(s) extracted",
                f"{refined} claim(s) re-checked by LLM entailment",
                f"{len(citation_errors)} citation error(s)",
            ],
        )

    def _status(self, score: float, contradictory: bool, negation_mismatch: bool) -> str:
        if contradictory:
            return VERIFICATION_CONFLICTING
        if negation_mismatch:
            return VERIFICATION_PARTIALLY_SUPPORTED if score >= self.config.partial_threshold else VERIFICATION_UNSUPPORTED
        if score >= self.config.support_threshold:
            return VERIFICATION_SUPPORTED
        if score >= self.config.partial_threshold:
            return VERIFICATION_PARTIALLY_SUPPORTED
        return VERIFICATION_UNSUPPORTED

    @staticmethod
    def _aggregate(claims: list[ClaimVerification]) -> str:
        if not claims:
            return VERIFICATION_INSUFFICIENT
        statuses = [claim.status for claim in claims]
        if VERIFICATION_CONFLICTING in statuses:
            return VERIFICATION_CONFLICTING
        if all(status == VERIFICATION_SUPPORTED for status in statuses):
            return VERIFICATION_SUPPORTED
        if any(status in {VERIFICATION_SUPPORTED, VERIFICATION_PARTIALLY_SUPPORTED} for status in statuses):
            return VERIFICATION_PARTIALLY_SUPPORTED
        if all(status == VERIFICATION_INSUFFICIENT for status in statuses):
            return VERIFICATION_INSUFFICIENT
        return VERIFICATION_UNSUPPORTED


def verify_groundedness(
    answer: str,
    evidence: list[EvidenceChunk],
    citations: list[Citation] | None = None,
    config: RagConfig | None = None,
) -> VerificationReport:
    return GroundednessVerifier(config).verify(answer, evidence, citations)
