"""Query expansion without external knowledge.

Expansion is limited to morphological variants of terms already present in the
query. This helps the heuristic reranker and verification matcher without
injecting synonyms or assumptions the user did not state.
"""
from __future__ import annotations

import re

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'-]{2,}")
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "what", "which", "when",
    "where", "who", "how", "are", "was", "were", "has", "have", "had", "does", "did",
    "not", "you", "your", "our", "their", "its", "about", "into", "than", "then",
}
_SUFFIXES = ("ations", "ation", "ments", "ment", "ings", "ing", "ies", "ed", "es", "s")


def query_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for match in _WORD_RE.finditer(query or ""):
        word = match.group(0).lower()
        if len(word) < 3 or word in _STOPWORDS or word in seen:
            continue
        seen.add(word)
        terms.append(word)
    return terms


def stem_variants(term: str) -> set[str]:
    variants = {term}
    for suffix in _SUFFIXES:
        if term.endswith(suffix) and len(term) - len(suffix) >= 3:
            variants.add(term[: -len(suffix)])
            break
    return variants


def expand_terms(query: str) -> list[str]:
    expanded: list[str] = []
    for term in query_terms(query):
        for variant in sorted(stem_variants(term)):
            if variant not in expanded:
                expanded.append(variant)
    return expanded[:40]
