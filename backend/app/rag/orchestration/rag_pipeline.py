"""Full RAG orchestration: query understanding → retrieval → context →
generation → citations → verification → telemetry.

This is the single canonical pipeline used by the chat API, the RAG API and
specialist agents. Legacy ``app.services.rag_service`` delegates here.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.models.rag import RagQueryLog
from app.rag.citations.validation import validate_citations
from app.rag.config import RagConfig
from app.rag.constants import ANSWER_MODE_NO_EVIDENCE
from app.rag.context.builder import ContextBuilder
from app.rag.context.deduplication import dedupe_evidence
from app.rag.generation.generator import GenerationOutcome, Generator
from app.rag.generation.prompts import INSUFFICIENT_EVIDENCE_MESSAGE
from app.rag.memory.conversation import load_conversation_context
from app.rag.memory.memory_retrieval import prior_evidence
from app.rag.memory.session_context import SessionContext
from app.rag.observability import (
    log_event,
    record_citations,
    record_generation,
    record_query,
    record_retrieval,
    record_verification,
)
from app.rag.query.analyzer import QueryAnalyzer
from app.rag.retrieval.retriever import Retriever
from app.rag.types import (
    Citation,
    EvidenceChunk,
    QueryAnalysis,
    RagRequest,
    RagResponse,
    RagScope,
    RagTimings,
    RetrievalResult,
    VerificationReport,
)
from app.rag.verification.groundedness import GroundednessVerifier


class RagOrchestrator:
    def __init__(
        self,
        config: RagConfig | None = None,
        *,
        retriever: Retriever | None = None,
        analyzer: QueryAnalyzer | None = None,
        context_builder: ContextBuilder | None = None,
        generator: Generator | None = None,
        verifier: GroundednessVerifier | None = None,
    ) -> None:
        self.config = config or RagConfig.from_settings()
        self.retriever = retriever or Retriever(self.config)
        self.analyzer = analyzer or QueryAnalyzer(self.config)
        self.context_builder = context_builder or ContextBuilder(self.config)
        self.generator = generator or Generator(self.config)
        self.verifier = verifier or GroundednessVerifier(self.config)

    # -- public API ----------------------------------------------------------

    def retrieve(
        self,
        db: Session,
        scope: RagScope,
        query: str,
        request: RagRequest | None = None,
        *,
        analysis: QueryAnalysis | None = None,
    ) -> RetrievalResult:
        request = request or RagRequest(query=query, scope=scope)
        conversation = (
            load_conversation_context(
                db, request.conversation_id, scope.organization_id, scope.user_id, max_turns=self.config.memory_max_turns
            )
            if request.conversation_id
            else []
        )
        analysis = analysis or self.analyzer.analyze(query, conversation=conversation or None)
        return self.retriever.retrieve(
            db,
            scope,
            query,
            filters=request.filters,
            mode=request.mode,
            top_k=request.top_k,
            rerank=request.rerank,
            analysis=analysis,
        )

    def answer(self, db: Session, scope: RagScope, request: RagRequest) -> RagResponse:
        session = SessionContext(
            conversation_id=request.conversation_id,
            organization_id=scope.organization_id,
            user_id=scope.user_id,
        )
        timings = RagTimings()
        started = time.monotonic()

        analysis_started = time.monotonic()
        conversation = (
            load_conversation_context(
                db,
                request.conversation_id,
                scope.organization_id,
                scope.user_id,
                max_turns=self.config.memory_max_turns,
            )
            if request.conversation_id
            else []
        )
        analysis = self.analyzer.analyze(request.query, conversation=conversation or None)
        timings.analysis_ms = _ms(analysis_started)

        retrieval_started = time.monotonic()
        result = self.retriever.retrieve(
            db,
            scope,
            request.query,
            filters=request.filters,
            mode=request.mode,
            top_k=request.top_k,
            rerank=request.rerank,
            analysis=analysis,
        )
        timings.retrieval_ms = _ms(retrieval_started)
        timings.rerank_ms = int(result.timings.get("rerank_ms", 0))
        record_retrieval(result.mode, timings.retrieval_ms / 1000.0)

        evidence = list(result.evidence)
        if request.conversation_id and len(evidence) < 3:
            memory = prior_evidence(
                db, scope, request.conversation_id, limit=max(1, self.config.final_top_k - len(evidence))
            )
            if memory:
                evidence = dedupe_evidence(evidence + memory)
                result.warnings.append("included previously cited evidence for a follow-up question")

        if not evidence:
            response = self._no_evidence_response(analysis, result, request, timings, session, db)
            return response

        context_started = time.monotonic()
        bundle = self.context_builder.build(
            scope,
            evidence,
            query=request.query,
            analysis=analysis,
            token_budget=request.max_context_tokens,
        )
        timings.context_ms = _ms(context_started)
        session.warnings.extend(bundle.warnings)

        if not bundle.passages:
            return self._no_evidence_response(analysis, result, request, timings, session, db)

        generation_started = time.monotonic()
        outcome = self.generator.generate(request.query, bundle, analysis)
        timings.generation_ms = int(outcome.latency_ms or _ms(generation_started))
        record_generation(outcome.answer_mode, timings.generation_ms / 1000.0)

        citations: list[Citation] = []
        citation_errors: list[str] = []
        if outcome.answer_mode != ANSWER_MODE_NO_EVIDENCE:
            citations, citation_errors, _used = validate_citations(
                outcome.text, bundle.evidence, bundle.citations
            )

        verification: VerificationReport | None = None
        if self.config.verification and outcome.answer_mode != ANSWER_MODE_NO_EVIDENCE:
            verification_started = time.monotonic()
            verification = self.verifier.verify(outcome.text, bundle.evidence, citations)
            if citation_errors:
                verification.citation_errors.extend(citation_errors)
            timings.verification_ms = _ms(verification_started)
            record_verification(verification.status)

        timings.total_ms = _ms(started)
        session.warnings.extend(outcome.warnings)
        response = RagResponse(
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
            warnings=_dedupe(session.warnings),
            prompt_tokens=outcome.prompt_tokens,
            completion_tokens=outcome.completion_tokens,
            retrieval_mode=result.mode,
            reranker=result.reranker,
            degraded_from=outcome.degraded_from,
            context_chunk_count=len(bundle.passages),
        )
        self._persist_query_log(db, scope, request, response, analysis)
        record_query(result.mode, outcome.answer_mode)
        record_citations(len(citations))
        log_event(
            "rag_answer",
            trace_id=session.trace_id,
            mode=result.mode,
            answer_mode=outcome.answer_mode,
            evidence=len(bundle.passages),
            citations=len(citations),
            total_ms=timings.total_ms,
            verification=verification.status if verification else None,
        )
        return response

    def stream(self, db: Session, scope: RagScope, request: RagRequest) -> Iterator[dict[str, Any]]:
        """Yield SSE-ready event dictionaries."""
        session = SessionContext(
            conversation_id=request.conversation_id,
            organization_id=scope.organization_id,
            user_id=scope.user_id,
        )
        timings = RagTimings()
        yield {"event": "rag_start", "data": {"trace_id": session.trace_id}}
        try:
            analysis_started = time.monotonic()
            conversation = (
                load_conversation_context(
                    db,
                    request.conversation_id,
                    scope.organization_id,
                    scope.user_id,
                    max_turns=self.config.memory_max_turns,
                )
                if request.conversation_id
                else []
            )
            analysis = self.analyzer.analyze(request.query, conversation=conversation or None)
            timings.analysis_ms = _ms(analysis_started)
            yield {"event": "query_analysis", "data": _analysis_payload(analysis)}

            retrieval_started = time.monotonic()
            result = self.retriever.retrieve(
                db,
                scope,
                request.query,
                filters=request.filters,
                mode=request.mode,
                top_k=request.top_k,
                rerank=request.rerank,
                analysis=analysis,
            )
            timings.retrieval_ms = _ms(retrieval_started)
            if not result.evidence:
                response = self._no_evidence_response(analysis, result, request, timings, session, db)
                yield {"event": "rag_end", "data": self._stream_payload(response)}
                return
            bundle = self.context_builder.build(
                scope,
                result.evidence,
                query=request.query,
                analysis=analysis,
                token_budget=request.max_context_tokens,
            )
            if not bundle.passages:
                response = self._no_evidence_response(analysis, result, request, timings, session, db)
                yield {"event": "rag_end", "data": self._stream_payload(response)}
                return
            yield {
                "event": "context",
                "data": {
                    "retrieval_latency_ms": timings.retrieval_ms,
                    "tokens": bundle.tokens,
                    "token_limit": bundle.token_limit,
                    "context_chunks": [citation.to_dict() for citation in bundle.citations],
                },
            }

            generation_started = time.monotonic()
            outcome: GenerationOutcome | None = None
            for event in self.generator.stream(request.query, bundle, analysis):
                if event["type"] == "token":
                    yield {"event": "token", "data": {"text": event["text"]}}
                elif event["type"] == "done":
                    outcome = event["outcome"]
            if outcome is None:
                raise RuntimeError("generation stream ended without an outcome")
            timings.generation_ms = int(outcome.latency_ms or _ms(generation_started))

            citations: list[Citation] = []
            citation_errors: list[str] = []
            if outcome.answer_mode != ANSWER_MODE_NO_EVIDENCE:
                citations, citation_errors, _used = validate_citations(
                    outcome.text, bundle.evidence, bundle.citations
                )
            verification: VerificationReport | None = None
            if self.config.verification and outcome.answer_mode != ANSWER_MODE_NO_EVIDENCE:
                verification = self.verifier.verify(outcome.text, bundle.evidence, citations)
                if citation_errors:
                    verification.citation_errors.extend(citation_errors)
                yield {"event": "verification", "data": verification.to_dict()}
            timings.total_ms = _ms(session.started_at)
            response = RagResponse(
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
                warnings=_dedupe(session.warnings + outcome.warnings),
                prompt_tokens=outcome.prompt_tokens,
                completion_tokens=outcome.completion_tokens,
                retrieval_mode=result.mode,
                reranker=result.reranker,
                degraded_from=outcome.degraded_from,
                context_chunk_count=len(bundle.passages),
            )
            self._persist_query_log(db, scope, request, response, analysis)
            record_query(result.mode, outcome.answer_mode)
            record_citations(len(citations))
            yield {"event": "rag_end", "data": self._stream_payload(response)}
        except Exception as exc:  # noqa: BLE001 — stream must terminate with an event
            log_event("rag_stream_error", trace_id=session.trace_id, error=str(exc)[:300])
            yield {
                "event": "error",
                "data": {
                    "code": "rag_stream_failed",
                    "message": str(exc)[:300],
                    "trace_id": session.trace_id,
                },
            }

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _stream_payload(response: RagResponse) -> dict[str, Any]:
        """Final SSE payload: citation text is needed by clients, evidence is not."""
        payload = response.to_dict(include_evidence_text=False)
        payload["citations"] = [citation.to_dict(include_text=True) for citation in response.citations]
        return payload

    def _no_evidence_response(
        self,
        analysis: QueryAnalysis,
        result: RetrievalResult,
        request: RagRequest,
        timings: RagTimings,
        session: SessionContext,
        db: Session,
    ) -> RagResponse:
        timings.total_ms = _ms(session.started_at)
        verification = (
            VerificationReport(
                status="insufficient_evidence",
                method="deterministic_lexical_grounding",
                notes=["no authorized evidence was retrieved"],
            )
            if self.config.verification
            else None
        )
        response = RagResponse(
            answer=INSUFFICIENT_EVIDENCE_MESSAGE,
            answer_mode=ANSWER_MODE_NO_EVIDENCE,
            model="none",
            citations=[],
            evidence=[],
            verification=verification,
            query_analysis=analysis,
            timings=timings,
            trace_id=session.trace_id,
            insufficient_evidence=True,
            warnings=_dedupe(session.warnings + result.warnings),
            retrieval_mode=result.mode,
            reranker=result.reranker,
            context_chunk_count=0,
        )
        self._persist_query_log(db, request.scope, request, response, analysis)
        record_query(result.mode, ANSWER_MODE_NO_EVIDENCE)
        return response

    def _persist_query_log(
        self,
        db: Session,
        scope: RagScope,
        request: RagRequest,
        response: RagResponse,
        analysis: QueryAnalysis,
    ) -> None:
        if not self.config.query_log_enabled:
            return
        try:
            row = RagQueryLog(
                organization_id=uuid.UUID(scope.organization_id),
                user_id=uuid.UUID(scope.user_id) if scope.user_id else None,
                conversation_id=uuid.UUID(request.conversation_id) if request.conversation_id else None,
                trace_id=response.trace_id,
                query=request.query[:8000],
                mode=response.retrieval_mode,
                filters=json.dumps(request.filters.describe(), ensure_ascii=False),
                retrieved_count=len(response.evidence),
                reranked_count=len(response.evidence),
                citation_count=len(response.citations),
                answer_mode=response.answer_mode,
                verification_status=response.verification.status if response.verification else None,
                retrieval_latency_ms=response.timings.retrieval_ms,
                generation_latency_ms=response.timings.generation_ms,
                total_latency_ms=response.timings.total_ms,
                detail=json.dumps(
                    {
                        "analysis": {
                            "intent": analysis.intent,
                            "expected_answer_type": analysis.expected_answer_type,
                            "needs_multiple_retrieval": analysis.needs_multiple_retrieval,
                            "suggested_agents": analysis.suggested_agents,
                            "method": analysis.method,
                        },
                        "reranker": response.reranker,
                        "evidence_chunk_ids": [item.chunk_id for item in response.evidence],
                        "warnings": response.warnings,
                    },
                    ensure_ascii=False,
                ),
            )
            db.add(row)
            db.commit()
        except Exception as exc:  # noqa: BLE001 — telemetry must not break answers
            db.rollback()
            log_event("rag_query_log_failed", error=str(exc)[:200])


def _analysis_payload(analysis: QueryAnalysis) -> dict[str, Any]:
    return {
        "intent": analysis.intent,
        "expected_answer_type": analysis.expected_answer_type,
        "needs_retrieval": analysis.needs_retrieval,
        "needs_multiple_retrieval": analysis.needs_multiple_retrieval,
        "entities": analysis.entities,
        "time_constraints": analysis.time_constraints,
        "subqueries": analysis.subqueries,
        "suggested_agents": analysis.suggested_agents,
        "method": analysis.method,
    }


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
