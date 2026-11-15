# Nexus AI – Integration Status

Last updated: 2026-11-15
Updated by: Kiro (Backend) — full stack re-verification with live Docker E2E

## Ownership
- Frontend: **Cline (VS Code)** — `frontend/` (Lovable abandoned)
- Backend: **Kiro** — `backend/`
- Platform: **Amazon Q** — `platform/`, compose, nginx, monitoring
- QA: **Copilot** — `tests/`, independent verification

## Verification Key
- ✅ Verified — confirmed by direct execution this session
- ⏳ Not yet attempted
- ⚠️ Exists but incomplete/non-conformant

## Live Stack Status (Docker Compose, 2026-11-15)

| Check | Result | Evidence |
|---|---|---|
| Full compose stack starts | ✅ | 11 services up (postgres/qdrant/redis/minio/backend/worker/frontend/nginx/prometheus/grafana + minio-init) |
| Alembic migrations 0001–0005 | ✅ | `alembic upgrade head` against live Postgres; all tables present incl. document_chunks |
| Backend health via Nginx (8080) | ✅ | GET /api/v1/health → all services healthy |
| Register/Login/Me/Refresh/Logout | ✅ | Live HTTP 201/200 verified; token rotation + logout verified in tests |
| Upload → MinIO → Redis → Celery → completed | ✅ | TXT + 5-page PDF: doc completed, job succeeded by `celery@…`, MinIO object at org-isolated key |
| Extraction (real) | ✅ | PDF page_count=5; TXT/CSV/XLSX/DOCX extractors unit-tested |
| Chunk persistence | ✅ | document_chunks rows with char ranges + provenance + embedding info |
| Qdrant indexing | ✅ | points_count=5, collection dim=256 cosine, org/document payload indexes |
| Semantic / lexical / hybrid search | ✅ | GET /api/v1/search all modes return real scores + provenance |
| Org isolation on search | ✅ | Other org user: total=0 on all modes, incl. explicit document_ids filter |
| Retry → re-index idempotency | ✅ | Deterministic chunk ids; re-index leaves exactly 5 points, no orphans |
| Cross-org document access | ✅ | 404 (not leaked), list empty, retry denied |
| Frontend build (type-check/lint/build) | ✅ | Clean (2026-11-15) |
| Frontend chat wiring (F6) | ✅ | chat.tsx consumes conversations CRUD + POST SSE streaming (fetch ReadableStream) via src/api.ts; served bundle verified live |
| Frontend ↔ Backend /search wiring | ⏳ | Search API not yet consumed by frontend |
| Chat/RAG streaming | ✅ backend verified live | SSE streaming + grounded citations; frontend chat page wired (2026-11-15) |
| Connectors / agents / SQL QA | ⏳ | Release 0.4/0.5 — not implemented |

## Infrastructure Fixes Applied (2026-11-15)
| Issue | Fix | File |
|---|---|---|
| minio/minio + minio/mc removed from Docker Hub (pull denied) | Switched to `bitnamilegacy/minio:2024` + `bitnamilegacy/minio-client:2024` (mc bundled); credentials via MC_HOST env, not argv | docker-compose.yml |
| Qdrant healthcheck used wget (absent in image) | bash /dev/tcp port probe | docker-compose.yml |
| Backend healthcheck used wget (absent) | curl (installed in image) | docker-compose.yml |
| Worker crash-loop: exec-form CMD doesn't expand env | Shell-form CMD in Dockerfile.worker | backend/Dockerfile.worker |
| Frontend image build failed: win32-only rollup dep in lockfile | Removed `@rollup/rollup-win32-x64-msvc` from devDependencies | frontend/package.json |
| Nginx 502 after backend container recreation (cached IP) | Docker DNS resolver + variable proxy_pass (re-resolve every 10s) | platform/nginx/nginx.conf |
| qdrant-client 1.20 vs server 1.9.2 mismatch | Pinned `qdrant-client>=1.9.0,<1.10` | backend/requirements.txt |
| Port 80 reserved on Windows host | HTTP_PORT=8080 in .env | .env |

## Environment Notes
- `.env` is populated with real values (not committed). OPENAI_API_KEY is a **dummy** (`sk-...`) — embedding provider defaults to `hashing` (non-semantic, machinery only). For real semantics set `EMBEDDING_PROVIDER=local` (install backend/requirements-embeddings.txt) or `openai_compatible` with a valid key.

## API Contract
- `contracts/openapi.yaml` v0.5.0 — auth, documents, **/api/v1/search (new)**, health, metrics.
- Endpoint implementations match contract; frontend /search consumption pending.

## Test Baseline
- Backend: **52 passed** (SQLite; vector backend=memory, embedding=hashing, celery off). Command: `cd backend; DEBUG=false INGESTION_USE_CELERY=false STORAGE_BACKEND=local RATE_LIMIT_ENABLED=false; python -m pytest -q`.
- New suites: test_processing.py (extraction/chunking/provenance), test_embeddings.py (providers), test_search.py (3 modes + org isolation).

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-01-01..03 | Initial reconciliation, IC-001..024 | Amazon Q |
| 2026-11-14 | IC-005..024 resolved by Cline/Kiro (frontend builds clean, backend suite 20 passed) | Cline/Kiro |
| 2026-11-15 | Release 0.2 implemented + live-verified (extraction/chunking/embeddings/Qdrant/search); infra fixes above; contract v0.5.0; suite 52 passed | Kiro |
| 2026-11-15 | Release 0.3 implemented + live-verified (RAG/chat/SSE); contract v0.6.0; suite 61 passed | Kiro |
| 2026-11-15 | Frontend chat wiring (F6): pages/chat.tsx rewritten against chat API (conversations, streaming, citations, answer_mode, insufficient-evidence, errors); api.ts SSE client; type-check/lint/build clean; live-served bundle + full UI request cycle verified through nginx:8080 | Kiro (frontend fill-in; Cline owns `frontend/`) |
