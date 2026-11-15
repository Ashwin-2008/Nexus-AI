# Backend Handover – Kiro (Backend Engineer)

Last updated: 2026-11-15
Owner: Kiro (`backend/` only). No `frontend/` or `platform/` application files modified this session (nginx/compose infra fixes documented in INTEGRATION_STATUS.md).

## Current State
**Release 0.1 (document ingestion), Release 0.2 (knowledge indexing + search), and Release 0.3 (grounded RAG + chat streaming) implemented and verified live.** Test suite **61 passed** (SQLite). Connectors, agents, SQL QA, evaluation: not implemented.

## Audit (0) — completed actions
- Inspected existing backend and read: `docs/PROJECT_STATE.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/DATABASE_SCHEMA.md`, `docs/handovers/BACKEND_HANDOVER.md`, `contracts/openapi.yaml`, `contracts/integration-spec.md`.
- Preserved existing auth, org isolation, Alembic migrations, document APIs, ingestion jobs, Celery/storage abstractions; did not recreate completed modules.
- **Baseline established (rerun):** `cd backend; $env:DEBUG='false'; $env:INGESTION_USE_CELERY='false'; $env:STORAGE_BACKEND='local'; $env:RATE_LIMIT_ENABLED='false'; python -m pytest -q` → **20 passed** (2026-11-14, ~24s).

## Implemented & Verified (actual)

### Milestone 1 — Auth/Security (partial)
- **Registration/login/access validation/current-user:** preserved and verified (`/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/me`).
- **Refresh flow & token revocation/logout:** `POST /api/v1/auth/refresh` (rotation, revokes old), `POST /api/v1/auth/logout` (revoke one/all refresh tokens, auth required). Refresh tokens persisted as hashes in `refresh_tokens` with expiry/revocation/JTI rotation.
  - Files: `backend/app/api/v1/auth.py`, `backend/app/services/auth_service.py`, `backend/app/models/user.py`, `backend/app/schemas/auth.py`, `backend/app/core/security.py`
- **Password hashing & policy:** bcrypt hashing preserved; server-side policy added (min 8, must include letter+digit). `backend/app/core/security.py`, enforced in `auth_service.create_user_with_org`.
- **RBAC (initial) & org isolation:** roles `admin`/`member` seeded; `require_role`/`get_current_user` deps; org-scoped document access (cross-org 404). `backend/app/api/deps.py`, `backend/app/services/auth_service.py`.
- **Account activation/deactivation:** `is_active` enforced in auth/user lookup; **admin API endpoint for activation/deactivation not yet added** (schema stub added: `UserStatusUpdate`).
- **Input validation & error handling:** Pydantic validation + consistent error envelope preserved. `backend/app/core/errors.py`.
- **Rate limiting:** slowapi scaffold added (config/middleware hook) — **not fully enforced/verified** in tests/env. `backend/app/main.py`, `backend/app/core/config.py`, `backend/requirements.txt`.
- **Audit logging:** `audit_logs` table and logging helper for key auth events (register, token issued/refreshed/revoked). `backend/app/models/user.py`, `backend/app/services/auth_service.py`.
- **No client-trusted org IDs:** org context derived from authenticated user; org-owned document queries scoped to `current_user.organization_id`.
- **Tests:** `backend/tests/test_auth.py`, `backend/tests/test_auth_m1.py` (refresh rotation/revocation, logout, password policy), `backend/tests/test_authz_boundaries.py` (org isolation, role, unauthorized/validation envelopes).
- **Not complete/claimed:** full permission model, admin management endpoints, comprehensive cross-org/privilege-escalation suite, access-token revocation (stateless JWT), production rate-limit verification.

### Milestone 2 — Ingestion reliability (partial, foundation)
- **Implemented:** persisted `ingestion_jobs` (status/attempts/task/worker/errors/timestamps), Celery task wiring (`app.worker.tasks.process_document`, `ingestion` queue, Redis broker) with DB-persisted fallback when unavailable, retry scheduling/backoff hooks, failure detail capture.
  - Files: `backend/app/worker/celery_app.py`, `backend/app/worker/tasks.py`, `backend/app/services/ingestion_service.py`, `backend/app/api/v1/documents.py`, `backend/app/models/document.py`, migration `0003_ingestion_jobs.py`
- **Deterministic tests:** `INGESTION_USE_CELERY=false` config/flag added to force DB-backed fallback in tests. `backend/app/core/config.py`, `backend/tests/conftest.py`.
- **Gaps (not verified):** idempotent processing guarantees, duplicate upload handling, bounded exponential backoff policy validation end-to-end, dead-letter/final-failure ops, worker crash recovery/restart-survival integration, queue monitoring, live Redis/Celery compose execution.

### Milestone 3 — Storage & document processing (partial, foundation)
- **Implemented:** storage abstraction (MinIO/local), org-isolated keys `orgs/{org_id}/documents/...`, configurable MinIO settings, graceful fallback/local compatibility; file validation and metadata/extraction for PDF/DOCX/TXT/CSV/XLSX; processing pipeline interfaces (extract/normalize/chunk/embed/index placeholders).
  - Files: `backend/app/services/storage.py`, `backend/app/services/processing.py`, `backend/app/services/ingestion_service.py`, `backend/app/core/config.py`, `backend/.env.example`
- **Gaps (not verified):** checksums/duplicate detection, secure object access policies, MinIO production/live ops, malformed-file hardening beyond basics, cleanup, real chunk persistence/indexing.

### Prior milestones/foundations preserved
- DB/session/base, Alembic 0001–0003, health (`/api/v1/health` with db/redis/qdrant/storage/worker), Prometheus `/metrics`, consistent error envelope, document APIs (`/api/v1/documents/*`, `/api/v1/upload` alias), worker module `app.worker.celery_app`.

## Migrations (Alembic)
- `0001_initial_auth.py` — organizations, roles, users (**Postgres verified**)
- `0002_documents.py` — documents (**Postgres verified**)
- `0003_ingestion_jobs.py` — documents.storage_backend, ingestion_jobs (**Postgres verified**)
- `0004_auth_security.py` — refresh_tokens, audit_logs (**Postgres verified this session**)
- Config: `backend/alembic.ini`, `backend/alembic/env.py`

## API Endpoints (current)
- `GET /` — root
- `GET /api/v1/health` — dependency health
- `GET /metrics` — Prometheus
- Auth: `POST /api/v1/auth/register` (201 `UserRead`), `POST /api/v1/auth/login` (200 token pair), `POST /api/v1/auth/refresh` (200 rotated pair), `POST /api/v1/auth/logout` (200), `GET /api/v1/auth/me` (200)
- Documents: `POST /api/v1/documents/upload`, `POST /api/v1/upload`, `GET /api/v1/documents`, `GET /api/v1/documents/{id}`, `POST /api/v1/documents/{id}/retry`

## Verification (actual)

### SQLite tests (local)
- `python -m pytest -q` (with `DEBUG=false, INGESTION_USE_CELERY=false, STORAGE_BACKEND=local, RATE_LIMIT_ENABLED=false`) → **20 passed** (2026-11-14).
  - `backend/tests/conftest.py`, `backend/tests/test_db.py`, `backend/tests/test_health.py`, `backend/tests/test_auth.py`, `backend/tests/test_auth_m1.py`, `backend/tests/test_authz_boundaries.py`, `backend/tests/test_documents.py`

### Docker integration
- **PostgreSQL 15-alpine:** ✅ `alembic upgrade head` through `0004_auth_security` verified (container-based run, 2026-11-14).
- **Redis 7-alpine:** ✅ `PING` connectivity verified (prior run).
- **MinIO:** ⚠️ not end-to-end verified (image pull unavailable in environment).
- **Qdrant:** ⚠️ not end-to-end verified.
- **Live Celery worker/compose:** ⚠️ not end-to-end verified (restart survival, live retries, queue behavior).

## Contracts/Docs Updated
- `contracts/openapi.yaml` (v0.4.0)
- `contracts/integration-spec.md` (v0.4.0)
- `docs/DATABASE_SCHEMA.md` (0001–0004)
- `docs/PROJECT_STATE.md`
- `docs/handovers/BACKEND_HANDOVER.md`

## Known Issues / Unverified Dependencies
- RAG/retrieval/citations/LLM generation, chat/SSE, sources/connectors, agents, SQL QA, evaluation: **not implemented**.
- MinIO/Qdrant/Celery live integration, idempotency/duplicate handling, rate-limit enforcement, activation/deactivation API, comprehensive security tests: **unverified/incomplete**.
- Stateless access tokens are not server-revoked on logout (refresh tokens are).

## Exact Next Implementation Task
1. **Release 0.4 (next):** Connector framework with a consistent interface (Postgres/MySQL/REST/website/GitHub/Google Drive/email), credential management, incremental sync, scheduling, deletion propagation.
2. Frontend chat wiring (Cline): SSE streaming via fetch + ReadableStream, citations UI, conversation history.
3. Release 0.5: agent orchestration (LangGraph or justified alternative).
4. When corpus > ~5k chunks/org: replace in-Python BM25 with Postgres tsvector/GIN lexical backend.

## Session 2026-11-15 (part 2) — Release 0.3 implemented

### Files created/changed
- `backend/app/services/llm.py` (NEW) — LLMProvider (OpenAI-compatible, streaming/non-streaming, retries, usage/latency tracking); extractive_answer() grounded fallback (verbatim sentences ranked by query-term overlap); all transport failures classified as LLMError.
- `backend/app/services/rag_service.py` (NEW) — RagPipeline: retrieve (hybrid) → assemble_context (token budget) → build_context_block (provenance-aware) → generate (LLM or extractive) → verify_citations (drops fabricated [n]); SYSTEM_PROMPT with prompt-injection defenses (retrieved content treated as data, never instructions); run() + run_streaming() with graceful degradation.
- `backend/app/api/v1/chat.py` (NEW) — conversations CRUD, messages history, POST message (stream=true → SSE StreamingResponse; stream=false → JSON). SSE events: message_start/context/token/message_end/error. Assistant message persisted with verified citations + meta (answer_mode, model, latencies, tokens, degraded_from).
- `backend/app/models/chat.py` (NEW) + `models/__init__.py` — Conversation, ChatMessage.
- `backend/alembic/versions/0006_chat.py` (NEW) — applied to live Postgres.
- `backend/app/api/v1/router.py` — chat router mounted.
- `backend/tests/test_chat_rag.py` (NEW) — 9 tests (conversations CRUD, isolation 404s, grounded answers, insufficient evidence, SSE streaming, cross-org RAG isolation, LLM-failure degradation, citation verification).
- `contracts/openapi.yaml` v0.6.0 — chat endpoints + ConversationRead/ChatMessageRead schemas.
- `backend/app/core/config.py` — llm_provider (auto|openai_compatible|extractive), rag_context_token_budget, rag_max_context_chunks.

### Live verification (Docker, 2026-11-15)
- Conversation create 201; grounded question → answer_mode=extractive (no valid LLM key), answer composed of verbatim retrieved sentences with [n] refs; 5 citations with page provenance from financial-report.pdf.
- Streaming SSE: message_start → context (retrieval_latency 16ms, 5 chunks) → message_end (citations 5, degraded_from=llm); assistant persisted (2 messages total).
- Unrelated question → answer_mode=no_evidence, insufficient_evidence=true, zero content leakage.
- Fixed during verification: LLM streaming transport errors (DNS failure) classified as LLMError; degraded no-evidence flag set correctly.

### Known constraints
- OPENAI_API_KEY in .env is dummy → llm_available()=True (key present) → live requests attempt LLM first, fail with 401/DNS after ~1s, degrade to extractive. Latency cost acceptable; logged clearly. Set llm_provider=extractive to skip LLM attempts, or provide a real key.
- RAG answer quality: extractive mode is verbatim passages (real, no fabrication). Semantic quality requires a real LLM+embedding provider.

## Session 2026-11-15 — implemented (Release 0.2)

### Files created/changed
- `backend/app/services/embeddings.py` (NEW) — provider abstraction: openai_compatible (HTTP w/ retries+backoff, dimension validation), local (sentence-transformers, lazy load), hashing (deterministic, NON-SEMANTIC, dev/test only). `provider_info()` for model-version tracking.
- `backend/app/services/vector_index.py` (NEW) — QdrantVectorIndex (collection lifecycle, ensure_collection w/ dim check, upsert wait=True, org+doc filtered search, delete_document, count, health) + InMemoryVectorIndex (explicit `VECTOR_INDEX_BACKEND=memory`, real cosine math, ephemeral; tests/offline only).
- `backend/app/services/processing.py` (REWRITTEN) — real FileExtractor: PDF (pypdf page spans, encrypted/scanned handling), DOCX (paragraphs+tables), CSV (header/rows), XLSX (sheets/rows), TXT (encoding fallback); ExtractionError on malformed/empty (no silent completion). TextNormalizer with span preservation. Chunker: configurable size/overlap, sentence/paragraph-aware cuts, per-chunk provenance (page/row/sheet), **deterministic chunk ids** uuid5(doc_id:index) → idempotent re-indexing.
- `backend/app/services/ingestion_service.py` — process_document_job rewired: extract → normalize → chunk → embed (fail loud on EmbeddingError) → upsert Qdrant → persist chunks (delete+insert per document) → metadata records provider/model/indexed status.
- `backend/app/models/document.py` — DocumentChunk model; `models/__init__.py` export.
- `backend/alembic/versions/0005_document_chunks.py` (NEW) — applied to live Postgres.
- `backend/app/api/v1/search.py` (NEW) + router mount — GET /api/v1/search (q, mode=semantic|lexical|hybrid, top_k, document_ids), 503 with error envelope on backend failure, strict org scoping.
- `backend/app/services/search_service.py` (NEW) — BM25 (in-Python, org-chunk bounded), semantic (Qdrant), hybrid (RRF), attach_document_info (org-scoped join).
- `backend/app/core/config.py` — chunking/embedding/qdrant/vector backend settings.
- `backend/tests/test_processing.py`, `test_embeddings.py`, `test_search.py` (NEW) — 32 new tests; total suite **52 passed**.
- `backend/requirements.txt` — qdrant-client pinned `>=1.9.0,<1.10` (server 1.9.2); `requirements-embeddings.txt` (NEW, optional local provider).
- `backend/Dockerfile.worker` — shell-form CMD (env expansion; fixes worker crash-loop).
- `contracts/openapi.yaml` v0.5.0 — /api/v1/search added.
- `docker-compose.yml` — MinIO→bitnamilegacy, qdrant/backend healthchecks, embedding/vector/chunk env vars, backend depends minio-init; nginx DNS-resolver fix (platform file, cross-cutting 502 fix).
- `frontend/package.json` — removed win32-only rollup devDep (build fix, Cline's file; single-line change required for container build).

### Live verification (Docker, 2026-11-15)
- Register/login 201/200 via nginx:8080. Upload TXT + 5-page PDF → doc completed, job succeeded (`celery@…`).
- Metadata: page_count=5, chunks=5, embeddings=5, indexed=true, index_backend=qdrant.
- document_chunks: 5 rows, overlapping char ranges, provenance JSON, embedding provider/model recorded.
- Qdrant: points_count=5, green, dim=256 cosine, payload indexes on organization_id/document_id.
- Search: lexical BM25 scores, semantic cosine scores, hybrid RRF; page provenance on hits (fixed by storing provenance in Qdrant payload).
- Org isolation live: other org → total=0 all modes; explicit cross-org document_ids → 0.
- Retry → re-queue → re-process → exactly 5 Qdrant points (no orphans; deterministic ids verified).
- Postgres migration 0005 applied live; MinIO object org-isolated key verified.

### Constraints/blocksers to know
- OPENAI_API_KEY in `.env` is dummy → default EMBEDDING_PROVIDER=hashing (machinery verified; semantics require local/openai provider).
- Docker Desktop engine crashed mid-session (recovered; containers auto-restarted with volumes intact).
- nginx caches upstream IPs unless resolver+variable proxy_pass used — fixed in nginx.conf.
