# NEXUS AI

NEXUS AI is a full-stack organizational knowledge platform:

- `backend/` — FastAPI, auth/RBAC, ingestion, shared RAG, specialists/supervisor, connectors, safe SQL, reports, evaluation.
- `frontend/` — React + Vite UI with a 3D dual-theme design system (dashboard, documents with preview/compare, sources, email, database, search, chat, agents, reports, analytics, monitoring, administration, profile, RAG console and evaluation).
- `platform/` — Docker Compose/nginx/monitoring assets.
- `contracts/` — OpenAPI and integration contracts.
- `docs/` — architecture, API, database, test strategy and QA documents.

## Quick start (local development, no Docker)

These commands run the backend on SQLite with local file storage, an in-process vector index and deterministic (non-semantic) embeddings. This is the fastest way to try the product without PostgreSQL, Redis, Qdrant, object storage or an LLM key.

### Prerequisites

- Python 3.11+ and the backend dependencies installed.
- Node.js 20+ and the frontend dependencies installed.

```bash
cd backend
python -m pip install -r requirements.txt

cd ../frontend
npm install
```

### 1. Create the local development database (first run only)

The backend defaults to PostgreSQL, so set `DATABASE_URL` for SQLite first. Run the database command from `backend/`:

**PowerShell**
```powershell
cd backend
$env:DATABASE_URL = "sqlite+pysqlite:///./nexus_dev_run.db"
python -c "from app.db.base import Base; import app.models; from app.db.session import engine; Base.metadata.create_all(bind=engine); print('Local database ready')"
```

**Git Bash**
```bash
cd backend
export DATABASE_URL="sqlite+pysqlite:///./nexus_dev_run.db"
python - <<'PY'
from app.db.base import Base
import app.models  # registers all ORM models
from app.db.session import engine
Base.metadata.create_all(bind=engine)
print("Local database ready")
PY
```

### 2. Start the backend

**PowerShell**
```powershell
cd backend
$env:DATABASE_URL = "sqlite+pysqlite:///./nexus_dev_run.db"
$env:SECRET_KEY = "local-dev-secret"
$env:STORAGE_BACKEND = "local"
$env:STORAGE_ROOT = "storage"
$env:VECTOR_INDEX_BACKEND = "memory"
$env:EMBEDDING_PROVIDER = "hashing"
$env:INGESTION_USE_CELERY = "false"
$env:RATE_LIMIT_ENABLED = "false"
$env:CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Git Bash**
```bash
cd backend
export DATABASE_URL="sqlite+pysqlite:///./nexus_dev_run.db"
export SECRET_KEY="local-dev-secret"
export STORAGE_BACKEND="local"
export STORAGE_ROOT="storage"
export VECTOR_INDEX_BACKEND="memory"
export EMBEDDING_PROVIDER="hashing"
export INGESTION_USE_CELERY="false"
export RATE_LIMIT_ENABLED="false"
export CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/v1/health`

The health response reports optional services (Redis, Qdrant, worker) as unhealthy in this mode; that is expected. Database and storage should be healthy.

### 3. Start the frontend

Open a second terminal:

**PowerShell**
```powershell
cd frontend
$env:VITE_API_BASE_URL = "http://localhost:8000/api/v1"
npm run dev -- --host 127.0.0.1 --port 5173
```

**Git Bash**
```bash
cd frontend
export VITE_API_BASE_URL="http://localhost:8000/api/v1"
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`.

`VITE_API_BASE_URL` is optional: Vite proxies `/api` to `http://127.0.0.1:8000` by default. Set `VITE_PROXY_TARGET` to proxy to a different backend port, or use `VITE_API_BASE_URL` when the backend is on another host. For example:

```bash
cd frontend
export VITE_PROXY_TARGET="http://127.0.0.1:8001"
npm run dev -- --host 127.0.0.1 --port 5174
```

Register the first user; the first registration also creates the organization and an administrator role. Then use **Dashboard**, **Chat**, **Search**, **RAG**, **Sources**, **Documents**, **Email**, **Database**, **Agents**, **Reports**, **Analytics**, **Monitoring**, **Administration** and **Profile** from the navigation.

### Frontend experience

- **Dark/light themes** — persisted per browser and switchable from the top bar or auth screen.
- **3D glass surfaces** — animated aurora/grid background, glow cards, orbital landing visual and responsive mobile navigation.
- **Live data everywhere** — dashboard/analytics use persisted telemetry, administration uses admin-only organization endpoints, monitoring probes `/health` and index state, and profile updates are written to the backend.
- **Grounded answers** — chat and RAG render citations, evidence, verification status, warnings and trace IDs; missing evidence is shown explicitly instead of fabricated.
- **Reduced motion** — animations collapse automatically when the OS requests reduced motion.

### Local mode limitations

- `VECTOR_INDEX_BACKEND=memory` keeps vectors in process memory only; restarting the backend loses them.
- `EMBEDDING_PROVIDER=hashing` produces deterministic, **non-semantic** vectors for machinery verification only.
- Without an LLM key, chat/RAG answers use the labelled extractive fallback, never fabricated text.
- Redis/Celery, Qdrant, Supabase Storage and external connectors require their own services/credentials.
- Delete `backend/nexus_dev_run.db` and repeat the database step to reset local data.

## Optional: run the complete stack with Docker Compose

Requires Docker Desktop to be running and a root `.env` (copy `.env.example` and fill it in). Start from the repository root:

```bash
docker compose -f docker-compose.yml up -d --build
docker compose ps        # wait for the backend healthcheck to pass
```

(Docker Compose auto-loads `docker-compose.override.yml`; pass `-f docker-compose.yml` in production to skip those debug-port overrides.)

### Redis: Upstash (managed)

Redis runs as Celery broker + result backend and feeds the health check. The local `redis` container is **disabled**; point the stack at Upstash with one variable in `.env`:

```env
# Upstash console → your database → Connect → "Redis (RESP)":
REDIS_URL=rediss://default:<redis-password>@<your-db>.upstash.io:6379
```

- Use the **Redis (RESP)** endpoint — **not** the REST URL/token. This backend speaks the Redis wire protocol (redis-py, Celery); Upstash's REST API is a different protocol and will not work here.
- The `rediss://` scheme (TLS) is required; the Celery app enables TLS automatically for it (`backend/app/worker/celery_app.py`).
- On the Upstash free tier, watch the connection and command limits — the Celery worker keeps a persistent broker connection and periodic heartbeats.
- `REDIS_PASSWORD` is only needed if you run a local redis container yourself.

### Database: Supabase PostgreSQL (recommended) or local container

The local `postgres` container is **disabled in production compose**. Point the stack at a managed database by setting one variable in `.env`:

```env
# Supabase → Connect → "Session pooler" string, driver switched to psycopg:
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

- URL-encode special characters in the database password (`@` → `%40`, `#` → `%23`, …).
- Use the **session pooler (port 5432)** string, not the transaction pooler (6543), so Alembic migrations and long-lived sessions behave predictably.
- On first start the backend runs `alembic upgrade head` and creates every table in Supabase — verify in the Supabase Table Editor.
- Qdrant still runs as a container locally; PostgreSQL and document storage move to Supabase.

For quick local dev without Supabase, the override file starts a containerized postgres on port 5432 (set `POSTGRES_PASSWORD` in `.env`).

Migrations run automatically in the backend container. Register the first user through the UI — the first registration creates the organization and the admin role.

### Document storage: Supabase Storage (default)

Uploaded documents, connector snapshots and generated reports live in a private Supabase Storage bucket; PostgreSQL keeps only metadata plus a `storage_path` key of the form `orgs/<org_id>/documents/<uuid>_<filename>`. In `.env`:

```env
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>   # backend only — never ship to the browser
SUPABASE_STORAGE_BUCKET=nexus-documents
STORAGE_BACKEND=supabase
```

- Copy both values from Supabase → Project Settings → API. The service-role key bypasses row-level security, so it stays on the backend; clients always download through the authenticated API.
- The bucket is created on first upload if it does not exist (keep it private).
- `STORAGE_BACKEND=auto` (default) prefers Supabase, then MinIO, then local disk. Documents record the backend that stored them, so switching backends does not break existing files.
- Self-hosted MinIO is still supported (`STORAGE_BACKEND=minio` + `MINIO_*`); the compose file no longer ships a MinIO container.

### Using Groq as the LLM provider

Groq serves an OpenAI-compatible chat API, so no backend code changes are needed. In `.env`:

```env
OPENAI_API_KEY=gsk_your_groq_key_here
OPENAI_BASE_URL=https://api.groq.com/openai/v1
LLM_PROVIDER=openai_compatible
LLM_MODEL=llama-3.3-70b-versatile
```

`docker-compose.yml` passes these to both `backend` and `worker`. Groq does **not** expose an embeddings endpoint, so keep `EMBEDDING_PROVIDER=hashing` (non-semantic) or run a dedicated embeddings provider separately — do not set it to `openai_compatible` while `OPENAI_BASE_URL` points at Groq.

## Production deployment (Supabase · Render · Vercel · Grafana Cloud)

This is the supported production topology; the full walkthrough is in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

| Layer | Service | Backend variables |
|---|---|---|
| Database | Supabase PostgreSQL | `DATABASE_URL` |
| Document storage | Supabase Storage (private bucket) | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET`, `STORAGE_BACKEND=supabase` |
| API + Celery worker | Render (Docker) | `render.yaml` blueprint; secrets entered in the dashboard |
| Frontend | Vercel | `VITE_API_BASE_URL=https://<api>.onrender.com/api/v1` |
| Redis | Upstash | `REDIS_URL=rediss://…` |
| Vector index | Qdrant Cloud | `QDRANT_URL`, `QDRANT_API_KEY` |
| Monitoring | Grafana Cloud | Agentless scrape of `https://<api>.onrender.com/metrics` |

```bash
# one-time: create the Render services from the blueprint
# (Dashboard → New → Blueprint → select this repository)

# after deploy
curl -s https://<api>.onrender.com/api/v1/health
```

Health reports `storage: healthy` only when the Supabase bucket is reachable;
`/api/v1/system/capabilities` shows the resolved storage backend
(`storage.backend`) rather than just the configured mode.

`.env` at the repository root is the single source of truth for compose; on
Render the same variables are set in the service environment instead.

```bash
cd backend
python -m pytest -q

cd ../frontend
npm run type-check
npm run lint
npm run build
```

## RAG endpoints

The shared RAG API is available at `/api/v1/rag`:

- `POST /rag/query`, `POST /rag/query/stream`
- `POST /rag/retrieval/test`
- `POST /rag/ingest`, `POST /rag/ingest/file`
- `GET /rag/ingestions/{job_id}`
- `POST /rag/documents/{id}/reindex`, `DELETE /rag/documents/{id}/index`, `DELETE /rag/documents/{id}`
- `GET /rag/documents/{id}/sync`, `GET /rag/sources`, `GET /rag/status`, `GET /rag/config`, `GET /rag/health`
- `POST /rag/evaluation/run`, `GET /rag/evaluations`

Organization and account endpoints used by the redesigned UI:

- `GET /api/v1/admin/overview`, `/admin/users`, `/admin/audit-logs` (admin only)
- `GET /api/v1/analytics/overview?days=14`
- `PATCH /api/v1/auth/me`, `POST /api/v1/auth/change-password`

See `contracts/openapi.yaml` (v0.10.0) and `docs/` for details.

## Troubleshooting

- **Port already in use**: change `--port 8000` / `--port 5173` and update `VITE_API_BASE_URL`.
- **`no such table` errors**: create the local database as shown above, or point `DATABASE_URL` at a migrated database.
- **Frontend requests fail**: confirm the backend is listening on port 8000 (Vite proxies `/api` there), or set `VITE_PROXY_TARGET`/`VITE_API_BASE_URL`. The backend CORS origins should include the frontend URL for direct API calls.
- **New admin/analytics routes return 404**: restart the backend so it reloads the current router (the documented command uses `--reload`; a manually started server without it must be restarted).
- **Semantic/LLM answers unavailable**: configure a real embedding provider and `OPENAI_API_KEY` (or an OpenAI-compatible endpoint); see `docs/PROJECT_STATE.md`.
