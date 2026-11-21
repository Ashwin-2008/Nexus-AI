"""High-level RAG service consumed by specialist agents.

Specialists call this façade instead of assembling retrieval/generation steps
themselves. Requests and responses are typed (``RagRequest``/``RagResponse``),
and every call is organization-scoped.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.rag.config import RagConfig
from app.rag.orchestration.rag_pipeline import RagOrchestrator
from app.rag.types import (
    EvidenceChunk,
    RagRequest,
    RagResponse,
    RagScope,
    RetrievalFilters,
    RetrievalResult,
    VerificationReport,
)
from app.rag.verification.groundedness import GroundednessVerifier


class RagService:
    def __init__(self, config: RagConfig | None = None, orchestrator: RagOrchestrator | None = None) -> None:
        self.config = config or RagConfig.from_settings()
        self.orchestrator = orchestrator or RagOrchestrator(self.config)

    def answer(
        self,
        db: Session,
        scope: RagScope,
        query: str,
        *,
        filters: RetrievalFilters | None = None,
        mode: str | None = None,
        top_k: int | None = None,
        rerank: bool | None = None,
        verify: bool | None = None,
        conversation_id: str | None = None,
        max_context_tokens: int | None = None,
    ) -> RagResponse:
        request = RagRequest(
            query=query,
            scope=scope,
            filters=filters or RetrievalFilters(),
            mode=mode,
            top_k=top_k,
            rerank=rerank,
            verify=verify,
            conversation_id=conversation_id,
            max_context_tokens=max_context_tokens,
        )
        return self.orchestrator.answer(db, scope, request)

    def retrieve(
        self,
        db: Session,
        scope: RagScope,
        query: str,
        *,
        filters: RetrievalFilters | None = None,
        mode: str | None = None,
        top_k: int | None = None,
        rerank: bool | None = None,
    ) -> RetrievalResult:
        request = RagRequest(
            query=query,
            scope=scope,
            filters=filters or RetrievalFilters(),
            mode=mode,
            top_k=top_k,
            rerank=rerank,
        )
        return self.orchestrator.retrieve(db, scope, query, request)

    def answer_with_evidence(
        self,
        db: Session,
        scope: RagScope,
        query: str,
        evidence: list[EvidenceChunk],
        *,
        top_k: int | None = None,
        conversation_id: str | None = None,
        conversation: list[str] | None = None,
    ) -> RagResponse:
        """Answer from already-retrieved, already-authorized evidence.

        Used by the supervisor to reuse retrieval performed by an earlier
        specialist step instead of querying the indexes twice.
        """
        from app.rag.citations.validation import validate_citations
        from app.rag.context.builder import ContextBuilder
        from app.rag.memory.session_context import SessionContext
        from app.rag.query.analyzer import QueryAnalyzer
        from app.rag.retrieval.filters import revalidate_evidence
        from app.rag.types import RagTimings

        session = SessionContext(
            conversation_id=conversation_id,
            organization_id=scope.organization_id,
            user_id=scope.user_id,
        )
        timings = RagTimings()
        analysis = QueryAnalyzer(self.config).analyze(query, conversation=conversation)
        evidence, _removed = revalidate_evidence(db, scope, RetrievalFilters(), evidence)
        bundle = ContextBuilder(self.config).build(
            scope, evidence[: top_k or self.config.final_top_k], query=query, analysis=analysis
        )
        if not bundle.passages:
            from app.rag.generation.prompts import INSUFFICIENT_EVIDENCE_MESSAGE

            return RagResponse(
                answer=INSUFFICIENT_EVIDENCE_MESSAGE,
                answer_mode="no_evidence",
                model="none",
                citations=[],
                evidence=[],
                verification=None,
                query_analysis=analysis,
                timings=timings,
                trace_id=session.trace_id,
                insufficient_evidence=True,
            )
        outcome = self.orchestrator.generator.generate(query, bundle, analysis)
        citations = []
        if outcome.answer_mode != "no_evidence":
            citations, _errors, _used = validate_citations(outcome.text, bundle.evidence, bundle.citations)
        verification = (
            self.orchestrator.verifier.verify(outcome.text, bundle.evidence, citations)
            if self.config.verification
            else None
        )
        timings.generation_ms = outcome.latency_ms
        timings.total_ms = outcome.latency_ms
        return RagResponse(
            answer=outcome.text,
            answer_mode=outcome.answer_mode,
            model=outcome.model,
            citations=citations,
            evidence=bundle.evidence,
            verification=verification,
            query_analysis=analysis,
            timings=timings,
            trace_id=session.trace_id,
            insufficient_evidence=outcome.insufficient_evidence,
            warnings=outcome.warnings,
            degraded_from=outcome.degraded_from,
            context_chunk_count=len(bundle.passages),
        )

    def verify(
        self,
        answer: str,
        evidence: list[EvidenceChunk],
        citations=None,
        *,
        scope: RagScope | None = None,
    ) -> VerificationReport:
        if scope is not None:
            for item in evidence:
                if item.organization_id and item.organization_id != scope.organization_id:
                    raise ValueError("evidence outside the caller's organization cannot be verified")
        return GroundednessVerifier(self.config).verify(answer, evidence, citations)

    @staticmethod
    def evidence_payload(result: RetrievalResult, include_text: bool = True) -> dict:
        return result.to_dict(include_text=include_text)

    @staticmethod
    def response_payload(response: RagResponse, include_evidence_text: bool = False) -> dict:
        return response.to_dict(include_evidence_text=include_evidence_text)


def get_rag_service(config: RagConfig | None = None) -> RagService:
    return RagService(config)


__all__ = ["RagService", "get_rag_service"]
