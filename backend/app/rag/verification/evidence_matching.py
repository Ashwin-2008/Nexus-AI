"""Evidence matching for claims.

This is a transparent lexical-support heuristic. It measures term coverage,
exact-phrase presence, numeric consistency and negation polarity. It is not a
trained NLI model and does not claim mathematical certainty.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.rag.query.expansion import query_terms, stem_variants
from app.rag.types import EvidenceChunk

_NUMBER_RE = re.compile(r"(?<!\w)(\d[\d,.]*)(?!\w)")
_NEGATION_RE = re.compile(r"\b(not|no|never|none|cannot|can't|doesn't|didn't|isn't|aren't|without|except)\b", re.IGNORECASE)


@dataclass
class EvidenceMatch:
    score: float
    chunk_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)
    negation_mismatch: bool = False
    contradictory: bool = False


def normalize_number(value: str) -> str:
    return value.replace(",", "").rstrip(".")


def match_claim(claim: str, evidence: list[EvidenceChunk]) -> EvidenceMatch:
    if not evidence:
        return EvidenceMatch(score=0.0, reasons=["no cited evidence"])
    wanted: set[str] = set()
    for term in query_terms(claim):
        wanted |= stem_variants(term)
    combined = "\n".join(item.text or "" for item in evidence)
    evidence_words: set[str] = set()
    for word in re.findall(r"[A-Za-zÀ-ÿ0-9']+", combined.lower()):
        if len(word) > 2:
            evidence_words.add(word)
    coverage = len(wanted & evidence_words) / len(wanted) if wanted else 0.0

    phrase = re.sub(r"\s+", " ", claim.strip().lower())
    phrase_bonus = 0.0
    for item in evidence:
        if len(phrase) >= 12 and phrase in re.sub(r"\s+", " ", (item.text or "").lower()):
            phrase_bonus = 1.0
            break

    claim_numbers = {normalize_number(value) for value in _NUMBER_RE.findall(claim)}
    evidence_numbers = {normalize_number(value) for value in _NUMBER_RE.findall(combined)}
    unsupported_numbers = sorted(claim_numbers - evidence_numbers)

    claim_negated = bool(_NEGATION_RE.search(claim))
    evidence_negated = bool(_NEGATION_RE.search(combined))
    negation_mismatch = bool(claim_negated != evidence_negated and (claim_numbers or wanted))

    # Conflicting polarity inside the retrieved evidence about the same terms.
    contradictory = _contradictory_polarity(claim, evidence)

    score = 0.75 * coverage + 0.15 * phrase_bonus + 0.10 * (
        0.0 if not claim_numbers else 1.0 - len(unsupported_numbers) / len(claim_numbers)
    )
    if negation_mismatch:
        score *= 0.65
    reasons: list[str] = []
    if coverage < 0.35:
        reasons.append("low term overlap with cited evidence")
    if unsupported_numbers:
        reasons.append(f"numbers not present in evidence: {unsupported_numbers}")
    if negation_mismatch:
        reasons.append("negation polarity differs between claim and evidence")
    if contradictory:
        reasons.append("cited evidence contains contradictory polarity")
    if phrase_bonus:
        reasons.append("exact claim phrase appears in evidence")
    return EvidenceMatch(
        score=round(max(0.0, min(1.0, score)), 4),
        chunk_ids=[item.chunk_id for item in evidence],
        reasons=reasons,
        unsupported_numbers=unsupported_numbers,
        negation_mismatch=negation_mismatch,
        contradictory=contradictory,
    )


def _contradictory_polarity(claim: str, evidence: list[EvidenceChunk]) -> bool:
    terms = set(query_terms(claim))
    if not terms:
        return False
    supportive = False
    negated = False
    for item in evidence:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", item.text or ""):
            words = set(re.findall(r"[A-Za-zÀ-ÿ0-9']+", sentence.lower()))
            if len(terms & words) / max(1, len(terms)) < 0.6:
                continue
            if _NEGATION_RE.search(sentence):
                negated = True
            else:
                supportive = True
    return supportive and negated
