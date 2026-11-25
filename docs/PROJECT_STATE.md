# Nexus AI – Project State

Last updated: 2026-11-21
Updated by: RAG implementation pass; Supabase Storage + Render/Vercel deployment pass

## Overall Status

The modular RAG subsystem is implemented and wired through the existing backend. Upload, connectors, chat, specialists, supervisor executions and the main chat API all use the same retrieval/generation path in `backend/app/rag`. No second agent framework, vector database, embedding provider, or retrieval implementation was added.

Validation in this environment (no live Docker/Postgres/Qdrant, no valid LLM/embedding API key):
- Backend suite: **148 passed** (SQLite, `VECTOR_INDEX_BACKEND=memory`, `EMBEDDING_PROVIDER=hashing`, Celery disabled; 16 of these cover the Supabase Storage backend with a mocked HTTP transport).
- Live checks against the owner's Supabase project and Qdrant Cloud: storage bucket auto-create, upload/download/delete and Qdrant collection create/upsert/search/delete all succeeded. PostgreSQL and Redis ports are blocked from this machine, so those were validated by URL parsing only.
- Frontend: `npm run type-check`, `npm run lint` and `npm run build` passed after the 3D dual-theme redesign.
- Alembic: single head `0014_rag_metadata`; migration **not applied to a live PostgreSQL instance** in this environment.
- Live Qdrant, live LLM generation, real semantic embeddings, Supabase Storage/MinIO, Redis/Celery, and external connectors were **not live-verified**.

## Deployment Topology

Production targets Supabase (PostgreSQL + document storage), Render (FastAPI + Celery worker), Vercel (frontend), Upstash (Redis) and Grafana Cloud (monitoring); Qdrant Cloud supplies the vector index. Full instructions and the environment-variable tables are in `docs/DEPLOYMENT.md`, and `render.yaml` is the blueprint. `backend/app/services/storage.py` gained a `supabase` backend (Storage REST API, service-role key, auto-created private bucket); `STORAGE_BACKEND=auto` prefers Supabase, then MinIO, then local disk, and each document records the backend that stored it.

## Implemented RAG Capabilities

### Ingestion
- Sources: uploads, inline RAG text/file API, connectors (website, GitHub, REST, Postgres/MySQL records, Google Drive, IMAP email) and database records through the existing connector framework.
- Formats: PDF, DOCX, TXT, MD, CSV, XLSX, PPTX, HTML, JSON, EML; OCR is explicitly unavailable rather than silently faked.
- Stages: load → validate (extension allow-list, size, magic bytes, archive bomb checks) → parse/layout/table extraction → normalize with span remapping → metadata extraction → duplicate detection/content hash → versioning → chunk → embed → vector upsert → chunk rows → version record.
- Chunking: recursive, token, sentence, semantic (documented lexical-cohesion heuristic), parent-child. Deterministic UUIDv5 chunk ids, provenance, content hashes and token counts.
- Embeddings: real provider adapters (OpenAI-compatible, local sentence-transformers if installed, deterministic hashing for tests/offline only) with zero/NaN/dimension validation. Hashing vectors are labelled as non-semantic.
- Versioning/dedupe: SHA-256 content hashes, `document_versions`, duplicate-of warnings, stale vector/row replacement on re-index.

### Retrieval
- Query understanding: intent, entities, date constraints, multi-part detection, specialist hints; deterministic fallback; optional validated LLM rewrite/decomposition.
- Dense + BM25 lexical retrieval, Reciprocal Rank Fusion, explicit degradation when a leg is unavailable.
- Filters: organization, document-level access scope, document IDs, source IDs/types, document version.
- Re-authorization of every fused candidate against live document/chunk rows before generation.
- Reranking: heuristic default, optional LLM and optional cross-encoder with explicit unavailability.
- Parent-child expansion and optional neighbouring context.
- Token-budgeted context builder with deduplication, verbatim extractive compression, prompt-injection neutralization, untrusted-evidence delimiters and citation indexing.

### Generation, Citations, Verification
- Grounded generation reusing the existing LLM abstraction; deterministic labelled extractive fallback; explicit `no_evidence` response when evidence is insufficient.
- Central citation resolver with organization/document validation and fabricated-index rejection.
- Claim-level verification with transparent statuses: `supported`, `partially_supported`, `unsupported`, `conflicting_evidence`, `insufficient_evidence`, plus numeric/polarity conflict signals and a non-certainty disclaimer.

### Shared Integration
- `app/services/rag_service.py` is now a compatibility façade over `app/rag`; chat and specialists use it.
- Chat (non-streaming and SSE) persists citations, verification, trace id, warnings, retrieval mode and timings.
- Specialist handlers (retrieval, document, research, database documentation lookup, verification, report, workflow, email where authorized) call the shared RAG service. Evidence from an earlier supervisor step is reused instead of retrieving twice.
- Supervisor merges/deduplicates citations and evidence and exposes verification status.
- New `/api/v1/rag/*` endpoints extend the API without replacing existing `/documents`, `/search` or `/chat` routes.
- Frontend RAG console (`/app/rag`) provides querying, filters, verification display, text ingestion, index re-index/deletion and status; admins also get evaluation runs, resolved configuration and index-health cards. Chat displays verification badges and the configured retrieval mode.

### Frontend Experience (3D redesign)
- Design system in `frontend/src/styles.css`: dark/light themes with persisted preference, animated aurora/grid atmosphere, glass cards, glow accents, 3D orbital visuals, responsive shell and reduced-motion support.
- Every page redesigned: landing/auth (login, register, recovery guidance), dashboard, chat, search, RAG console, sources, documents, agents, analytics, monitoring, administration, profile.
- Live wiring replaces prior “Unavailable” placeholders: dashboard/analytics use `/analytics/overview`, administration uses `/admin/overview|users|audit-logs` plus `/system/capabilities` and `/agents/catalog`, profile uses `PATCH /auth/me` and `POST /auth/change-password`, monitoring uses real health/index/connector/provider state.
- Added `/app/reports` (persisted artifacts, authenticated download, delete), `/app/email` (IMAP search, approval-gated SMTP drafts), `/app/database` (schema discovery, SQL generation/validation/execution, result tables/charts), document extraction preview/comparison, agent cancel/retry and chart-spec rendering.
- `frontend/src/theme.tsx` provides the theme provider; `frontend/components/nx.tsx` supplies shared badges, stats, modals, page headers and formatting helpers.
- Vite dev server proxies `/api` to `http://127.0.0.1:8000` so the default `/api/v1` base works without an environment variable; `VITE_API_BASE_URL` still overrides it.

### Observability and Evaluation
- Trace ids, structured RAG events, Prometheus counters/histograms, secret redaction, and bounded query telemetry (`rag_query_logs`).
- Evaluation framework: Recall@K, Precision@K, MRR, NDCG@K; optional generation metrics derived from real verification; persisted runs (`rag_evaluation_runs`) and lintable JSONL fixtures.

## Migrations
- `0014_rag_metadata` adds document hash/source/version/access scope, chunk headings/parent/hash/tokens/strategy/version/scope, and `document_versions`, `rag_query_logs`, `rag_evaluation_runs`.
- Historical migrations were not modified.

## Known Limitations / Honest Blockers
- No live PostgreSQL/Qdrant in this environment; vector behaviour was verified with the process-local cosine backend and real embedding-provider adapters were exercised only for the deterministic hashing provider.
- No valid live LLM/embedding key; generated answers in tests are extractive fallbacks, not live LLM output.
- OCR for scanned PDFs is not implemented; an explicit OCR-unavailable error is raised.
- Semantic chunking and verification are deterministic lexical heuristics, not trained models; verification is a review signal, not certainty.
- Celery/Redis worker paths, MinIO, live connector credentials, OAuth/SMTP, and large-corpus Postgres tsvector indexing remain environment-dependent follow-ups.
- Python is 3.14 in this environment; optional `sentence-transformers`/`pptx` libraries are not installed, so the corresponding paths report unavailability instead of pretending to work.

## Next Actions
1. Apply `0014_rag_metadata` to a live PostgreSQL and run ingestion/retrieval against live Qdrant.
2. Configure a real embedding provider and LLM key; run generation evaluation with `generate=true`.
3. Verify Celery worker recovery/duplicate delivery and connector credentials end-to-end.
4. Add a Postgres tsvector/GIN lexical backend for large organizations.
5. Expand evaluation datasets with organization-specific gold evidence.
