# Nexus AI – Project State

Last updated: 2026-11-14
Updated by: Kiro (Backend)

## Overall Status
- Backend: Milestones 1-3 **partially implemented with verified increments**. Full SQLite test suite baseline re-established (**20 passed**). Alembic migrations 0001–0004 verified on Docker PostgreSQL. Async ingestion/storage/processing foundations and auth security enhancements implemented; RAG, chat/SSE, sources/connectors, agents, SQL QA, and evaluation **not implemented/verified**.
- Frontend: **official implementation is `frontend/` (Cline, in-repo).** Lovable frontend abandoned. Frontend-owned gaps remain; backend must not modify it.
- Platform: existing infra present; not modified.

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
| Frontend ↔ Backend | ⏳ pending | Frontend wiring/chat/sources pending; contracts updated |

## Known Issues / Gaps
- `auth/register` returns `UserRead` (no token); login/refresh return token pair.
- Celery enqueue disabled in tests via `INGESTION_USE_CELERY=false` to ensure deterministic SQLite runs; production/compose behavior requires live verification.
- Chat/SSE, sources, chunk persistence, embeddings, vector indexing, retrieval, citations, RAG answers, agents absent.

## Next Actions (Backend)
1. Harden M1: add activation/deactivation endpoint, expand RBAC/permission checks and tests (cross-org/privilege escalation), verify rate limiting.
2. Harden M2/M3: checksums+duplicate detection, idempotent ingestion, MinIO live ops, Celery worker restart/retry integration tests.
3. Implement M4–M7 foundations (chunk persistence, embeddings, Qdrant indexing, hybrid retrieval) before any RAG claims.
4. Coordinate and implement chat/sources contracts with frontend once reconciled.
