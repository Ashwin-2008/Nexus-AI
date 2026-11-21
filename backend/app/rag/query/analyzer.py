"""Query classification: intent, expected answer type, constraints."""
from __future__ import annotations

import re

from app.rag.types import QueryAnalysis

_COMPARE = re.compile(r"\b(compare|comparison|versus|vs\.?|difference between|differ)\b", re.IGNORECASE)
_SUMMARIZE = re.compile(r"\b(summarize|summary|overview|tl;?dr|key points)\b", re.IGNORECASE)
_ANALYTICAL = re.compile(r"\b(analy[sz]e|trend|calculate|aggregate|metric|kpi|forecast|correlat)\b", re.IGNORECASE)
_REPORT = re.compile(r"\b(report|briefing|memo|executive summary)\b", re.IGNORECASE)
_LIST = re.compile(r"\b(list|top \d+|enumerate|which ones)\b", re.IGNORECASE)
_NUMBER = re.compile(r"\b(how many|how much|total|number of|percentage|rate|average)\b", re.IGNORECASE)
_PROCEDURE = re.compile(r"\b(how (do|does|can|should)|steps?|process for|procedure)\b", re.IGNORECASE)
_GREETING = re.compile(r"^\s*(hi|hello|hey|good (morning|afternoon|evening)|thanks|thank you)\b", re.IGNORECASE)
_DATE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}|"
    r"q[1-4]\s*\d{4}|fy\s*\d{2,4}|last (week|month|quarter|year)|this (week|month|quarter|year))\b",
    re.IGNORECASE,
)
_ENTITY = re.compile(r"\b(?:[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,3}|[A-Z]{2,}(?:-\d+)?)\b")
_PRONOUN = re.compile(r"\b(it|they|them|this|that|those|these|he|she|its|their)\b", re.IGNORECASE)
_QUESTION_WORD = re.compile(r"^\s*(who|what|when|where|why|how|which|whose|is|are|was|were|do|does|did|can|could|should|would)\b", re.IGNORECASE)


def classify_intent(query: str) -> str:
    text = query or ""
    if _GREETING.match(text):
        return "conversational"
    if _COMPARE.search(text):
        return "compare"
    if _REPORT.search(text) and _SUMMARIZE.search(text):
        return "report"
    if _SUMMARIZE.search(text):
        return "summarize"
    if _ANALYTICAL.search(text):
        return "analytical"
    if _LIST.search(text):
        return "list"
    if _QUESTION_WORD.match(text) or text.strip().endswith("?"):
        return "question"
    return "lookup"


def expected_answer_type(query: str, intent: str) -> str:
    if _NUMBER.search(query):
        return "number"
    if _COMPARE.search(query) or intent == "compare":
        return "comparison"
    if intent == "summarize":
        return "summary"
    if intent == "list" or _LIST.search(query):
        return "list"
    if _PROCEDURE.search(query):
        return "procedure"
    if intent == "analytical":
        return "analysis"
    if intent == "report":
        return "report"
    return "fact"


def analyze_deterministic(query: str, conversation: list[str] | None = None) -> QueryAnalysis:
    original = (query or "").strip()
    normalized = re.sub(r"\s+", " ", original)
    intent = classify_intent(original)
    answer_type = expected_answer_type(original, intent)
    entities = _dedupe(match.group(0) for match in _ENTITY.finditer(original) if len(match.group(0)) > 2)
    dates = _dedupe(match.group(0) for match in _DATE.finditer(original))
    needs_retrieval = intent != "conversational" and bool(normalized)
    multiple = bool(
        _COMPARE.search(original)
        or ";" in original
        or len(re.findall(r"\?", original)) > 1
        or re.search(r"\b(and also|as well as|both|respectively)\b", original, re.IGNORECASE)
        or len(original) > 220
    )
    needs_specialists = bool(
        _ANALYTICAL.search(original)
        or _REPORT.search(original)
        or re.search(r"\b(database|sql|email|inbox|across sources|cross-source)\b", original, re.IGNORECASE)
    )
    notes: list[str] = []
    if conversation:
        notes.append("conversation context supplied")
    if _PRONOUN.search(original):
        notes.append("query contains pronoun references")
    return QueryAnalysis(
        original=original,
        normalized=normalized,
        intent=intent,
        expected_answer_type=answer_type,
        entities=entities[:20],
        time_constraints=dates[:10],
        needs_retrieval=needs_retrieval,
        needs_multiple_retrieval=multiple,
        needs_specialists=needs_specialists,
        method="deterministic",
        notes=notes,
    )


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value.strip())
    return result


class QueryAnalyzer:
    """Single entry point for query understanding.

    Deterministic analysis always runs. Rewriting/decomposition may call the
    configured LLM only for genuinely complex queries and always validate the
    result; on failure the deterministic path is used.
    """

    def __init__(self, config=None) -> None:
        from app.rag.config import RagConfig

        self.config = config or RagConfig.from_settings()

    def analyze(
        self,
        query: str,
        *,
        conversation: list[str] | None = None,
        has_database_source: bool = False,
    ) -> QueryAnalysis:
        from app.rag.query.decomposition import decompose_query
        from app.rag.query.expansion import expand_terms
        from app.rag.query.rewriter import rewrite_query
        from app.rag.query.routing import suggested_agents

        analysis = analyze_deterministic(query, conversation)
        rewritten, rewrite_method, rewrite_notes = rewrite_query(
            analysis.normalized, conversation=conversation, config=self.config
        )
        analysis.rewritten = rewritten if rewritten != analysis.normalized else None
        analysis.notes.extend(rewrite_notes)
        if rewrite_method == "llm":
            analysis.method = "llm_assisted"
            analysis.notes.append("query rewritten by configured LLM")

        use_llm_decomposition = bool(
            self.config.multi_query
            and analysis.needs_multiple_retrieval
            and (len(query) > 200 or len(re.findall(r"\?", query)) > 1)
        )
        subqueries, decomposition_method = decompose_query(
            analysis.original, config=self.config, use_llm=use_llm_decomposition
        )
        analysis.subqueries = subqueries
        if decomposition_method == "llm":
            analysis.method = "llm_assisted"
            analysis.notes.append("question decomposed by configured LLM")

        analysis.expansion_terms = expand_terms(analysis.original)
        analysis.suggested_agents = suggested_agents(
            analysis, has_database_source=has_database_source
        )
        return analysis
