# Nexus AI – Project State

Last updated: 2026-11-15
Updated by: Kiro (Backend)

## Overall Status
- Backend: Milestones 1–3 verified; **Release 0.2 (chunking + embeddings + Qdrant indexing + search) and Release 0.3 (grounded RAG + chat + streaming) implemented and verified live**. Connector APIs and a persisted, permission-scoped agent execution path are now implemented. The safe SQL tool is implemented but live external database execution remains credential-dependent.
- Frontend: official implementation is `frontend/` (Cline, in-repo). Builds/lints/type-checks clean. Chat workspace is wired to backend chat/SSE API. **Knowledge sources CRUD/test/sync UI and authenticated knowledge search UI were integrated by Copilot (2026-11-15).**
- Platform: compose stack runs end-to-end; nginx now re-resolves service IPs (502-on-recreate fix); MinIO images moved to bitnamilegacy (Docker Hub removal).

## Release 0.2 — VERIFIED (2026-11-15, live Docker)
- Real extraction: `app/services/processing.py` FileExtractor — PDF (pypdf, page spans), DOCX (paragraphs+tables), CSV (rows/header), XLSX (sheets/rows), TXT (encoding fallback). Malformed files raise ExtractionError → job failed (no silent completion).
- Chunking: configurable size/overlap, sentence/paragraph-aware breaks, per-chunk provenance (page/row/sheet), deterministic chunk IDs (uuid5 of document_id+index) → idempotent re-indexing (verified: re-index leaves exactly 5 points, no orphans).
- Embeddings: `app/services/embeddings.py` — providers: openai_compatible (HTTP, retries/backoff), local (sentence-transformers, requirements-embeddings.txt), hashing (deterministic, NON-SEMANTIC, dev/test only). Selection via EMBEDDING_PROVIDER. Dimension validation + provider/model tracking persisted per chunk.
- Qdrant: `app/services/vector_index.py` — collection lifecycle, upsert (wait=True), org+document filtered search, delete, count, health; payload indexes on organization_id/document_id. Client pinned to 1.9.x to match server v1.9.2.
- Search API: `GET /api/v1/search?q&mode&top_k&document_ids` — lexical (BM25 in-Python over org chunks), semantic (Qdrant), hybrid (RRF). Strictly org-scoped. Contract v0.5.0.
- Chunk persistence: migration 0005 `document_chunks` (applied to live Postgres), model `DocumentChunk`.

## Live verification evidence (Docker, 2026-11-15)
- 5-page PDF upload → doc completed; metadata page_count=5; 5 chunks persisted (char ranges overlap correctly); Qdrant points_count=5, status green, collection dim=256 cosine.
- Search live: lexical scores (BM25), semantic scores (Qdrant cosine), hybrid RRF scores; page provenance on hits.
- Org isolation live: second org's user gets total=0 on all modes, even with document_ids filter naming org A's document.
- Retry → re-queue → re-process verified live; deterministic chunk IDs prevent orphaned vectors.

## Release 0.3 — VERIFIED (2026-11-15, live Docker)
- LLM abstraction `app/services/llm.py`: OpenAI-compatible chat completions (streaming + non-streaming, retries, usage tracking); grounded **extractive fallback** (verbatim retrieved sentences, clearly labeled `answer_mode=extractive`) when no LLM configured or LLM fails — never fabricates.
- RAG pipeline `app/services/rag_service.py`: hybrid retrieval → context assembly (token budget, RAG_MAX_CONTEXT_CHUNKS) → generation (LLM w/ anti-prompt-injection system prompt) → **citation verification** (fabricated [n] references dropped; every citation maps to a retrieved chunk) → explicit insufficient-evidence handling.
- Chat API `app/api/v1/chat.py`: conversations CRUD (owner+org scoped, 404 not 403 to avoid existence leak), messages history, POST message with **SSE streaming** (message_start → context → token* → message_end) and non-streaming mode; both user and assistant messages persisted with citations/meta.
- Migration 0006: conversations, chat_messages (applied to live Postgres).
- Tests: 61 passed. Live E2E verified: grounded answer with page-provenance citations; streaming event sequence correct; assistant persistence after stream; cross-org questions return explicit no_evidence with zero leakage; LLM-failure degradation labeled (`degraded_from: llm`).

## Component Status

| Component | Engineer | Status | Notes |
|---|---|---|---|
| Platform | Amazon Q | existing | Not modified/re-verified end-to-end |
| Backend | Kiro | in progress (partial) | Auth+refresh/logout/policy/audit scaffold, RBAC/org isolation helpers, documents+ingestion jobs, storage abstraction, processing interfaces, health/metrics |
| Frontend | Cline (VS Code) | in-repo scaffold (partial) | API wiring mostly pending; contracts updated for backend reality |

## Backend – Verified increments (actual)

### Baseline tests (SQLite, local)
- Command: `cd backend; $env:DEBUG='false'; $env:INGESTION_USE_CELERY='false'; $env:STORAGE_BACKEND='local'; $env:RATE_LIMIT_ENABLED='false'; python -m pytest -q`
- Result: **20 passed** (2026-11-14). Includes DB/health, auth register/login/me/JWT/unauthorized/duplicate, org isolation, validation/error envelopes, document upload/validation/metadata/retry/jobs, refresh/rotation/logout, password policy.

### Docker integration (actual)
- **PostgreSQL (postgres:15-alpine):** ✅ `alembic upgrade head` applied `0001_initial_auth`–`0004_auth_security` (tables include users/orgs/roles/documents/ingestion_jobs/refresh_tokens/audit_logs).
- **Redis (redis:7-alpine):** ✅ connectivity `PONG` verified previously.
- **MinIO:** ⚠️ not end-to-end verified (image unavailable in env); MinIO backend/config/fallback implemented.
- **Qdrant:** ⚠️ not end-to-end verified.
- **Celery worker (live/compose):** ⚠️ task registration importable; live worker/restart-survival/retry execution not fully integration-tested.

## Milestone status (high level)
- **M1 Auth & security:** partial. Implemented: register/login/me, access+refresh tokens with rotation/revocation, logout, password policy, hashed refresh storage, audit log scaffolding, org isolation on resources, RBAC deps/roles seeded. Gaps: account activation/deactivation API, full permission model/admin endpoints, enforced rate limiting verification, comprehensive cross-org/privilege-escalation test coverage beyond current suite, logout invalidation semantics for access tokens (stateless JWT).
- **M2 Ingestion reliability:** partial. Persisted jobs/attempts/failure details, Celery+Redis path with DB fallback, backoff retries. Gaps: idempotency guarantees, duplicate upload handling/checksum, dead-letter handling, queue monitoring, restart/recovery integration proof.
- **M3 Storage & document processing:** partial. Storage abstraction (local/MinIO), org-isolated keys, extractors/metadata for PDF/DOCX/TXT/CSV/XLSX, limits/basic validation. Gaps: checksums/duplicate detection, secure access controls, MinIO production verification, malformed-file hardening, cleanup.
- **M4–M15 (chunking, embeddings, Qdrant indexing, retrieval, RAG, chat/SSE, connectors, agents, SQL QA, eval, hardening, full verification):** **not implemented/verified** (interfaces/placeholders only where noted). **Do not mark RAG or agentic functionality complete.**

## Integration Status
| Integration | Status | Notes |
|---|---|---|
| Backend ↔ Postgres (migrations 0001-0004) | ✅ verified (Docker) | Alembic upgrade succeeded |
| Backend ↔ Redis (connectivity) | ✅ verified (Docker) | Live Celery execution not fully verified |
| Backend ↔ MinIO | ⚠️ partial | Code/config ready; live ops not verified |
| Backend ↔ Qdrant | ⚠️ partial | Interfaces/health present; runtime not verified |
| Frontend ↔ Backend | ✅ integrated | Chat, sources, search, agent executions, durable steps, and approvals use typed authenticated APIs |

## Known Issues / Gaps
- `auth/register` returns `UserRead` (no token); login/refresh return token pairs.
- Live SMTP/OAuth provider verification, richer semantic document comparison, and live approval/Celery validation remain incomplete. Approval-gated SMTP delivery code, report metadata persistence/UI, and workflow routing are implemented.
- Default EMBEDDING_PROVIDER=hashing produces NON-semantic vectors — retrieval machinery verified, but real answer quality requires EMBEDDING_PROVIDER=local (install requirements-embeddings.txt) or openai_compatible with a valid key (current .env key is a dummy `sk-...`).
- Lexical BM25 computed in Python over org chunks (bounded 5000); Postgres tsvector/GIN migration path for large corpora.
- PDF page-level metadata extraction: page_count verified; page-level text char offsets via spans.
- OCR for scanned PDFs not implemented (clear ExtractionError raised instead).

## Next Actions (Backend)
1. Release 0.4 backend connector framework and frontend management/search wiring are implemented; live provider verification remains credential-dependent.
2. Agent execution foundation is implemented: persisted executions, retrieval supervisor path, bounded read-only SQL tool, audit records, API routes, and frontend execution history.
3. Add source-level edit/reconnect configuration forms and scheduled sync controls.
4. Configure and live-verify SMTP/OAuth delivery, deepen semantic cross-source correlation, and validate Celery against a live broker/worker.
5. Consider Postgres tsvector lexical backend when corpus > 5k chunks/org.
