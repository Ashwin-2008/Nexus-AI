# Backend Handover – Kiro (Backend Engineer)

Last updated: 2026-11-14
Owner: Kiro (`backend/` only). No `frontend/` or `platform/` files modified.

## Current State
Baseline re-established and verified (**20 passed**, SQLite). Milestone 1 security enhancements and Milestone 3 ingestion/storage foundations partially implemented and verified at unit/test and selected Docker levels. **RAG, chat/SSE, sources/connectors, agentic orchestration, SQL QA, and evaluation are not implemented/verified — not marked complete.**

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
1. **Complete M1 hardening:** add admin-gated activation/deactivation endpoint, expand RBAC permission matrix and tests (cross-org access, privilege escalation), and verify rate limiting behavior.
2. **Complete M2/M3 reliability:** add file checksum/duplicate detection, idempotent ingestion guards, and run live Docker integration (Postgres+Redis+MinIO+Qdrant+Celery worker) proving upload→queue→worker→final status, retries, and restart survival; record actual results.
3. **Begin M4–M6 only after M2/M3 verified:** chunk persistence/provenance, embedding abstraction/provider integration, Qdrant indexing with real ops — then retrieval/RAG per contract. Do not claim RAG/agents complete without end-to-end verification.
