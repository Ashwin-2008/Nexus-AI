"""Answer relevance heuristics."""
from __future__ import annotations

from app.rag.query.expansion import query_terms, stem_variants


def answer_relevance(query: str, answer: str) -> float:
    """Fraction of query content terms present in the answer."""
    wanted: set[str] = set()
    for term in query_terms(query):
        wanted |= stem_variants(term)
    if not wanted:
        return 0.0
    answer_words = {word.lower() for word in answer.lower().split()}
    stripped = {word.strip(".,;:!?()[]{}") for word in answer_words}
    return round(len(wanted & stripped) / len(wanted), 4)


def evidence_relevance(query: str, texts: list[str]) -> float:
    wanted = set(query_terms(query))
    if not wanted:
        return 0.0
    hits = 0
    for text in texts:
        words = {word.lower() for word in text.lower().split()}
        if wanted & words:
            hits += 1
    return round(hits / len(texts), 4) if texts else 0.0
