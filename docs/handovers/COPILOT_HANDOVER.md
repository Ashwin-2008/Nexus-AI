# Copilot Integration Handover

Last updated: 2026-11-21

## Current State

The modular RAG subsystem is implemented in `backend/app/rag` and is the single retrieval/generation path for chat, specialists, supervisor executions and the RAG API. Existing upload/search/chat/connectors remain the canonical surfaces and were not replaced.

### Backend
- New RAG packages: loaders, parsing, ingestion, chunking, embeddings, vectorstores, indexes, retrieval, query, reranking, context, citations, verification, generation, memory, observability, evaluation, orchestration.
- `app/services/rag_service.py` is now a compatibility façade; old names (`RagPipeline`, `RagResult`, `verify_citations`) still work.
- Specialists and supervisor use `RagService`; evidence is reused across steps and citations/evidence are merged and deduplicated.
- Chat persists verification, trace id, warnings, retrieval mode/reranker and context chunk count.
- New endpoints under `/api/v1/rag`: query, stream, retrieval test, text/file ingestion, job status, re-index, index delete, document delete, sync, sources, status, config, health, evaluation run/list/detail.
- Connector ingestion now sets `source_id`, content hash and content type; HTML/Markdown/JSON/CSV extensions are preserved where the connector provides a MIME type.
- Migration `0014_rag_metadata` adds document/chunk RAG metadata and document versions, query logs and evaluation runs.

### Frontend
- `frontend/src/api.ts`: typed RAG query/retrieval/status/ingest/reindex/delete-index/evaluation clients; admin/analytics clients; profile/password clients; chat meta includes verification/trace/warnings.
- Full 3D redesign with dark/light themes in `src/styles.css`, `src/theme.tsx` and `components/nx.tsx`; every page was rebuilt.
- `frontend/pages/rag.tsx`: query console with filters, verification/claims, citations, evidence, timings/trace, text ingestion, index re-index/delete and source status.
- `frontend/pages/chat.tsx`: streaming tokens, verification badge, citations, warnings, stop control.
- Dashboard/analytics/admin/monitoring now render real API data; `/app/profile` supports profile and password updates.
- Route `/app/rag` and navigation links added; `/app/profile` is now inside the main shell.

## Validation

- Backend: `python -m pytest -q` — **124 passed** (SQLite, memory vectors, hashing embeddings, Celery off).
- Frontend: `npm run type-check`, `npm run lint` and `npm run build` — all passed.
- Alembic: `python -m alembic heads` — `0014_rag_metadata` (single head).
- OpenAPI YAML parse — passed, version 0.10.0, 66 paths.

## Known Limitations

- No live PostgreSQL/Qdrant/LLM/embedding provider verification in this environment; migration 0014 is not applied to a live DB.
- Tests use `VECTOR_INDEX_BACKEND=memory` (real cosine math, ephemeral) and `EMBEDDING_PROVIDER=hashing` (non-semantic).
- OCR not implemented; optional sentence-transformers/pptx not installed.
- Celery/Redis/MinIO/external connector credentials remain environment-dependent.
- Verification is deterministic lexical grounding, not a truth guarantee.
- Frontend `npm run lint`, `npm run type-check` and `npm run build` all passed.
- Running local dev processes may need a backend restart to pick up new admin/analytics/profile routes (`uvicorn` without `--reload` in this environment).

## Next Implementation Step

1. Apply `0014_rag_metadata` to staging PostgreSQL and run test suite.
2. Start Qdrant and configure a real embedding provider; run ingestion/retrieval/evaluation smoke tests.
3. Configure a real LLM key and run generation evaluation (`generate=true`) to measure faithfulness and citation correctness.
4. Verify Celery worker recovery and connector credentials end-to-end.
5. Add Postgres tsvector lexical backend and, if required, an OCR provider.
