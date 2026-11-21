"""Context construction.

Responsibilities: dedupe, optional compression, token budgeting, grouping by
source, prompt-safe delimiting, and stable citation indices. The builder never
adds evidence that did not pass retrieval authorization.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.rag.citations.resolver import resolve_citations
from app.rag.config import RagConfig
from app.rag.context.compression import compress_evidence
from app.rag.context.deduplication import dedupe_evidence
from app.rag.context.source_grouping import group_by_document
from app.rag.context.token_budget import TokenBudget, estimate_tokens
from app.rag.parsing.cleaning import neutralize_prompt_injection, wrap_untrusted_content
from app.rag.types import Citation, EvidenceChunk, QueryAnalysis, RagScope


@dataclass
class ContextPassage:
    index: int
    evidence: EvidenceChunk
    text: str
    header: str
    tokens: int
    compressed: bool = False


@dataclass
class ContextBundle:
    passages: list[ContextPassage] = field(default_factory=list)
    text: str = ""
    citations: list[Citation] = field(default_factory=list)
    tokens: int = 0
    token_limit: int = 0
    omitted: int = 0
    groups: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def evidence(self) -> list[EvidenceChunk]:
        return [passage.evidence for passage in self.passages]

    def index_for(self, chunk_id: str) -> int | None:
        for passage in self.passages:
            if passage.evidence.chunk_id == chunk_id:
                return passage.index
        return None


class ContextBuilder:
    def __init__(self, config: RagConfig | None = None) -> None:
        self.config = config or RagConfig.from_settings()

    def build(
        self,
        scope: RagScope,
        evidence: list[EvidenceChunk],
        *,
        query: str,
        analysis: QueryAnalysis | None = None,
        token_budget: int | None = None,
        max_chunks: int | None = None,
    ) -> ContextBundle:
        budget = TokenBudget(int(token_budget or self.config.context_token_budget))
        limit = int(max_chunks or self.config.max_context_chunks)
        warnings: list[str] = []
        candidates = dedupe_evidence(evidence)

        compressed_map: dict[str, str] = {}
        if self.config.context_compression:
            compressed_map, compression_warnings = compress_evidence(
                candidates,
                query,
                max_sentences=self.config.context_compression_max_sentences,
            )
            warnings.extend(compression_warnings)

        passages: list[ContextPassage] = []
        for item in candidates:
            if len(passages) >= limit:
                break
            text = compressed_map.get(item.chunk_id, item.text)
            header = _header(item)
            overhead = estimate_tokens(header) + 8  # wrapper markers
            # Trim an over-large passage rather than dropping it entirely.
            while text and not budget.fits(text, overhead=overhead):
                if len(text) <= 200:
                    break
                text = text[: max(200, len(text) - max(200, len(text) // 5))]
                warnings.append(f"truncated passage {item.chunk_id} to fit the context budget")
            if not budget.consume(text, overhead=overhead):
                break
            safe_text, injection = neutralize_prompt_injection(text)
            if injection:
                warnings.append(
                    f"removed {len(injection)} prompt-injection marker(s) from chunk {item.chunk_id}"
                )
            index = len(passages) + 1
            body = wrap_untrusted_content(safe_text, source=f"{item.document_filename}#{index}")
            passages.append(
                ContextPassage(
                    index=index,
                    evidence=item,
                    text=body,
                    header=f"[{index}] {header}",
                    tokens=estimate_tokens(text) + overhead,
                    compressed=item.chunk_id in compressed_map,
                )
            )

        block = "\n\n".join(f"{passage.header}\n{passage.text}" for passage in passages)
        selected_evidence = [passage.evidence for passage in passages]
        citations = resolve_citations(scope, selected_evidence) if passages else []
        return ContextBundle(
            passages=passages,
            text=block,
            citations=citations,
            tokens=budget.used,
            token_limit=budget.limit,
            omitted=max(0, len(candidates) - len(passages)),
            groups=group_by_document(selected_evidence),
            warnings=warnings,
        )

    @staticmethod
    def format_instruction(analysis: QueryAnalysis | None) -> str:
        if analysis is None:
            return "Answer concisely and cite every factual statement."
        answer_type = analysis.expected_answer_type
        if answer_type == "number":
            return "Answer with the exact number and its unit, then cite the source passage."
        if answer_type == "list":
            return "Answer as a bulleted list; cite each bullet."
        if answer_type == "comparison":
            return "Answer as a structured comparison; cite evidence for each side."
        if answer_type == "summary":
            return "Answer as a concise summary with citations for the key points."
        if answer_type == "procedure":
            return "Answer as ordered steps; cite the procedure source."
        if answer_type == "analysis":
            return "Separate measured facts from interpretation; cite all facts."
        return "Answer directly and concisely; cite every factual statement."


def _header(item: EvidenceChunk) -> str:
    title = (item.metadata or {}).get("document_title") or item.document_filename or "document"
    bits = [str(title)]
    if item.page_number:
        bits.append(f"page {item.page_number}")
    if item.section_heading:
        bits.append(f"section: {item.section_heading}")
    if item.source_type and item.source_type != "upload":
        bits.append(item.source_type)
    return " · ".join(bits)
