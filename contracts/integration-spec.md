# NEXUS AI - Integration Specification

Version: 0.4.0 (draft)
Status: backend Milestone 1 auth security increments added (refresh/logout/password policy/audit scaffolding) on top of Milestone 3 foundations — 2026-11-14
Frontend ownership: **official frontend is `frontend/` in this repo (implemented by Cline in VS Code).** Lovable frontend abandoned. Coordinate backend compatibility against actual `frontend/` calls and update this spec/contracts on changes.

## Purpose
Shared contract between Frontend (Cline, `frontend/`), Backend (Kiro), and Platform (Amazon Q) for NEXUS AI.

## Conventions
- Base URL (dev): `http://localhost:8000`
- API prefix: `/api/v1`
- Frontend base: `VITE_API_BASE_URL=/api/v1` (relative; nginx routes `/api/*` to backend)
- Auth: JWT Bearer `Authorization: Bearer <token>` (access tokens)
- Content-Type: `application/json` unless noted (uploads: `multipart/form-data`)
- Errors (current backend): `{"error":{"code":"...","message":"...","details"? : ...}}`
- Streaming chat: SSE — **planned** (backend chat not implemented)

## Implemented & verified endpoints (backend, 2026-11-14)
- `GET /` — root status
- `GET /api/v1/health` — health + dependency checks (`status`, `services{api,database,redis,qdrant,storage,worker}`)
- `GET /metrics` — Prometheus text format
- `POST /api/v1/auth/register` — body `{email,password,full_name?,organization_name}` → **201** `UserRead` (password policy enforced; no auto-login token)
- `POST /api/v1/auth/login` — body `{email,password}` → **200** `{access_token, token_type:"bearer", refresh_token}`
- `POST /api/v1/auth/refresh` — body `{refresh_token}` → **200** rotated `{access_token, token_type, refresh_token}` (401 on invalid/revoked/expired)
- `POST /api/v1/auth/logout` — bearer auth, body `{refresh_token?, all_sessions?}` → **200** `{message}`
- `GET /api/v1/auth/me` — bearer auth → **200** `UserRead`
- `POST /api/v1/documents/upload` — bearer auth, multipart `file` (PDF/DOCX/TXT/CSV/XLSX) → **201** `DocumentRead` (queued async ingestion)
- `POST /api/v1/upload` — compatibility alias for document upload
- `GET /api/v1/documents` — bearer auth → `{items:[DocumentRead]}`
- `GET /api/v1/documents/{document_id}` — bearer auth, org-isolated → `DocumentRead`
- `POST /api/v1/documents/{document_id}/retry` — bearer auth → `DocumentRead`

### Auth notes (current)
- Access tokens are JWT with `sub`, `type=access`, `org` claim; `/auth/me` and protected routes require valid, non-revoked-by-inactivity user (active account).
- Refresh tokens are persisted (hashed), rotated on refresh, revocable on logout; revoked/expired tokens rejected.
- Password policy (server-side): min 8 chars, must include at least one letter and one digit (schema also enforces length bounds).
- Roles seeded: `admin` (org creator), `member`. RBAC dependency helpers exist (`require_role`); no admin management endpoints exposed yet.
- Rate limiting scaffolded (slowapi) but not fully enforced/verified in all environments.

### Document / ingestion contract notes (current)
- `DocumentRead`: `storage_backend`, `status` (`pending|processing|completed|failed`), `error_message`, `retry_count`, `metadata`, `latest_job`.
- `latest_job` (`IngestionJobRead`): `id,status(queued|running|succeeded|failed|retrying),attempt,max_attempts,task_id,worker,error_message,started_at,finished_at,created_at,updated_at`.
- Jobs/status persisted in DB; Celery/Redis preferred when available, fallback to in-process background execution (DB-persisted). Worker/storage reported in health.

## Frontend (`frontend/`) compatibility notes (observed 2026-11-14)
- `VITE_API_BASE_URL=/api/v1`. Auth UI stubbed (no API/token storage). Chat expects `EventSource ${base}/chat?stream=true` and `POST ${base}/chat` `{message,stream:true}` — **not implemented**. Documents/Sources static. Frontend-owned build issues remain.

## Contract coordination (open items)
- **Auth responses:** register returns `UserRead` (not token); login/refresh return token pair — frontend must adapt when wiring.
- **Chat POST/SSE and sources APIs:** not implemented; reconcile frontend expectations before implementation.
- **Account activation/deactivation/admin RBAC endpoints:** not yet exposed as API (internal model supports `is_active`).

## SSE Streaming Contract (target, unimplemented)
- Endpoint: `POST /api/v1/chat` with `"stream": true` (streaming via fetch/readable stream or SSE as agreed; native EventSource cannot POST).
- Event format/types TBD (`token`, `citations`, `done`, `error`).

## Storage & processing (current)
- Storage abstraction: MinIO/local, org-isolated keys, configurable; graceful fallback. Live MinIO ops not fully verified in all environments.
- Processing foundation interfaces only (no RAG retrieval/citations/answers).

## Change Log
| Date       | Change                                                        | Author        |
|------------|---------------------------------------------------------------|---------------|
| 2025-01-01 | Platform service map, env vars, IC log added                  | Amazon Q      |
| 2026-11-14 | Frontend ownership clarified; observed frontend API usage     | Kiro (Backend)|
| 2026-11-14 | Milestone 3: async ingestion jobs, storage abstraction, health/contract | Kiro (Backend) |
| 2026-11-14 | Milestone 1 (partial): refresh/logout, password policy, token pair, audit scaffolding, 0004 migration | Kiro (Backend) |
