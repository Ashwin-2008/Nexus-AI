# NEXUS AI

NEXUS AI is a multi-tenant organizational knowledge platform. It ingests an
organization's documents and connected sources, indexes them for retrieval, and
answers questions with citations, claim-level verification and traceable evidence -
through a chat UI, a shared RAG API, and specialist agents coordinated by a supervisor.

| Path | Contents |
|---|---|
| `backend/` | FastAPI service, RAG engine, agents, workers, migrations, tests |
| `frontend/` | React + Vite single page application |
| `platform/` | Docker Compose assets, nginx, Prometheus and Grafana provisioning, scripts |
| `contracts/` | OpenAPI contract and integration contracts |
| `docs/` | Architecture, API, database schema, test strategy, QA and deployment docs |

## Contents

- [What the product does](#what-the-product-does)
- [Tech stack](#tech-stack)
- [Architecture](#architecture)
- [Workflows](#workflows)
- [Repository layout](#repository-layout)
- [Run locally](#run-locally)
- [Configuration](#configuration)
- [Testing](#testing)
- [Deployment](#deployment)
- [API surface](#api-surface)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)

## What the product does

- **Organizations and access control** - every user belongs to one organization;
  roles (member, admin) decide which documents, sources and admin screens
  they can reach. The organization id always comes from the token, never from a request filter.
- **Ingestion** - upload PDF, DOCX, XLSX, CSV, TXT, Markdown, HTML or JSON; add a web
  page; or sync a database connector. Everything is parsed, deduplicated, versioned,
  chunked, embedded and indexed by the same pipeline.
- **Retrieval-augmented answers** - hybrid dense + lexical retrieval, reciprocal rank
  fusion, re-authorization of every candidate, reranking, parent-chunk expansion, a
  token-budgeted context, grounded generation, resolved citations and claim verification.
- **Chat, search and a RAG console** - conversational answers, document/filtered search,
  and an operator view of retrieval, citations, verification, timings and evaluation runs.
- **Specialist agents and a supervisor** - scoped specialists (retrieval, documents, SQL,
  reports) that always call the shared `RagService`; the supervisor plans, executes steps,
  passes evidence forward and merges citations.
- **Safe SQL intelligence, connectors, reports and analytics** - read-only allowlisted SQL
  over permitted tables, connector sync, generated reports, org analytics, audit logs.
- **Operations** - health endpoint, Prometheus metrics, Grafana dashboards, structured logs,
  per-request trace ids and an evaluation harness.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript 5.6, Vite 6, Tailwind CSS 4, react-router 7, axios, lucide-react |
| Design system | CSS custom properties in `frontend/src/styles.css`, persisted theme in `src/theme.tsx` |
| Backend | Python 3.11+, FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2, Alembic, psycopg 3 |
| Auth | JWT access tokens (python-jose), passlib + bcrypt, organization-scoped RBAC |
| RAG engine | `backend/app/rag/` (owned pipeline), qdrant-client, BM25 lexical index over PostgreSQL |
| Embeddings | `openai_compatible`, `local`, or deterministic `hashing` (tests and offline dev) |
| Generation | Any OpenAI-compatible endpoint - OpenAI, Groq, Ollama - with a labelled extractive fallback |
| Database | PostgreSQL (Supabase in production), SQLite for the zero-setup local path |
| Vector store | Qdrant (Cloud in production, container or in-process memory locally) |
| Object storage | Supabase Storage, MinIO (S3 API), or local disk |
| Async jobs | Celery 5 worker with a Redis broker; FastAPI background tasks as the fallback |
| Parsing | pypdf, python-docx, openpyxl |
| Reporting | reportlab, openpyxl, python-docx |
| Observability | prometheus-client, `/metrics`, Grafana Cloud or the bundled Prometheus + Grafana |
| Delivery | Docker Compose + nginx, Render blueprint (`render.yaml`), Vercel |

## Architecture

```
Browser - React 18 SPA (Vercel or nginx)
  chat | documents | sources | agents | reports | analytics | admin | RAG console
        |
        |  HTTPS + JSON, JWT bearer token, CORS allow-list
        v
FastAPI  app/main.py
  /api/v1/*  routers: auth, documents, sources, chat, search, rag,
             agents, analytics, admin, intelligence, health  (+ /metrics)
        |
  api/  ->  services/  ->  rag/ orchestrator  ->  providers
        |
        +--> db/ (SQLAlchemy 2)      --> PostgreSQL: users, orgs, documents,
        |                                chunks, versions, telemetry, evals
        +--> storage backend         --> Supabase Storage | MinIO | local disk
        +--> vector index            --> Qdrant collection nexus_chunks
        +--> worker/celery_app       --> Redis broker (Upstash)
        |
        +--> LLM provider            --> OpenAI-compatible endpoint

Celery worker (Dockerfile.worker): queues ingestion, agents, default
```

**Backend layering.** `app/api/v1/*` contains thin routers (validation, auth, HTTP
status). They call `app/services/*`, which owns domain rules and transactions. The RAG
engine lives in `app/rag/` and is reached through `RagService` / `RagOrchestrator` -
no router, specialist or chat handler talks to a retriever, embedder or vector store
directly. `app/models/` and `app/db/` hold SQLAlchemy models and sessions;
`app/core/` holds settings, security, logging and middleware; `app/worker/` holds the
Celery app and tasks; `app/prompts/` holds versioned Markdown prompt templates.

**What is stored where.**

| Store | Contents |
|---|---|
| PostgreSQL | organizations, users, documents (hash, source, version, scope), chunks (heading, parent, tokens, strategy), document versions, ingestion jobs, connectors, conversations, query telemetry, agent executions, reports, audit logs, evaluation runs |
| Qdrant | chunk vectors and payloads (organization, document, chunk, source, version, access scope), collection `nexus_chunks`, cosine distance |
| Object storage | original uploads under organization-scoped keys |
| Redis | Celery broker/result backend (no application state) |

**Security invariants.** The organization id comes from the authenticated user. Requested
filters are intersected with the allowed scopes, so a denied filter narrows to nothing
rather than widening the search. Every fused candidate is re-checked against live rows
before it reaches the prompt. Retrieved text is untrusted: injection markers are
neutralized, evidence is wrapped in `<untrusted_evidence>`, and the system prompt forbids
following instructions found inside documents. Admin-only: RAG config inspection,
evaluation runs, and non-organization ingestion scopes.

## Workflows

### 1. Registration and requests

1. `POST /api/v1/auth/register` creates the organization and its first admin, then returns
   a JWT. `POST /api/v1/auth/login` issues tokens for existing users.
2. The SPA stores the token and sends `Authorization: Bearer <token>` on every call.
3. `app/main.py` applies CORS (exact origins only), request id and timing middleware, and
   rate limiting; the router resolves the current user and organization before the handler runs.

### 2. Ingestion (upload, connector, or inline)

1. `POST /api/v1/documents/upload` validates type and size and writes the bytes to the
   configured storage backend under an organization-scoped key.
2. A `documents` row (content hash, version, scope) and an ingestion job are created.
3. Dispatch: Celery task `process_document` on the `ingestion` queue when async is enabled;
   otherwise a FastAPI background task runs after the response returns.
4. Pipeline: loader -> parser (text, layout, tables) -> normalizer (span remapping) ->
   metadata extraction + content hash -> dedupe and version detection -> chunker
   (recursive, token, sentence, semantic or parent-child) -> batched, validated embeddings
   -> Qdrant upsert + `document_chunks` rows + `document_versions` entry.
5. Status is pollable; failures are recorded with a reason instead of silently disappearing.

Connectors (`/api/v1/sources`) reuse the same pipeline: a sync pulls records, normalizes
them into documents, and indexes them.

### 3. Asking a question

```
POST /api/v1/rag/query  (or /chat, or a specialist agent)
  -> query analysis: intent, entities, dates, multi-part questions
     (deterministic fallback when no LLM is available)
  -> optional rewrite / decomposition / multi-query expansion
  -> scope = authorization scopes INTERSECT requested filters
  -> dense retrieval (Qdrant) + lexical BM25 (PostgreSQL chunk rows)
  -> reciprocal rank fusion
  -> live re-authorization of every candidate
  -> reranking (heuristic, LLM, or cross-encoder)
  -> parent / neighbour context expansion
  -> dedupe, compression, token budget, injection neutralization
  -> grounded generation (LLM, or labelled extractive fallback)
  -> citation resolution and validation (fabricated ids dropped)
  -> claim-level verification against the evidence
  -> { answer, citations, evidence, verification, timings, warnings, trace_id }
```

`POST /api/v1/rag/query/stream` streams the same pipeline over server-sent events.

### 4. Agents and the supervisor

1. `POST /api/v1/agents/executions` records an execution and dispatches it.
2. Specialists are scoped to a role and a tool set; they query knowledge only through
   `RagService`, so retrieval, citations and verification stay identical everywhere.
3. The supervisor plans steps, runs them in order, carries evidence forward to avoid
   duplicate retrieval, and merges/deduplicates final citations.
4. The execution, its steps and its citations are persisted for the UI and for audit.

### 5. Safe SQL and reports

Questions that map to structured data run through an allowlisted, read-only SQL path with
statement, row and time limits. Reports render from query results into PDF, XLSX or DOCX
and are stored as documents so they can be retrieved and cited like any other source.

### 6. Background execution

| `INGESTION_USE_CELERY` | Uploads | Connector sync | Agent runs |
|---|---|---|---|
| `true` (with a reachable Redis) | `ingestion` queue | `ingestion` queue | `agents` queue |
| `false` or no Redis | background task after the response | synchronous, inside the request | synchronous, inside the request |

The synchronous fallback keeps the product working with no extra infrastructure, but it
shares the web process: long jobs can hit the platform request timeout and are lost if the
instance restarts. Use the worker for anything beyond a demo.

## Repository layout

```
NEXUS AI/
  backend/
    app/
      api/v1/        routers: auth, documents, sources, chat, search, rag, agents,
                     analytics, admin, intelligence, health; metrics at /metrics
      agents/        specialists, supervisor, tools, execution runtime
      core/          settings, security, logging, middleware, rate limiting
      db/            session, engine, declarative base
      models/        SQLAlchemy models
      schemas/       Pydantic request/response models
      rag/           loaders, parsing, ingestion, chunking, embeddings, vectorstores,
                     indexes, retrieval, query, reranking, context, citations,
                     verification, generation, memory, observability, evaluation,
                     orchestration
      prompts/       versioned Markdown prompt templates
      services/      domain services (documents, storage, vector index, connectors,
                     agents, reports, analytics, auth)
      worker/        celery_app and tasks
    migrations/      Alembic revisions
    tests/           pytest suite
    Dockerfile       API image (runs alembic upgrade head, then uvicorn)
    Dockerfile.worker  Celery image
  frontend/
    src/             App.tsx (screens), api.ts (typed client), auth.tsx, theme.tsx,
                     styles.css (design tokens), ErrorBoundary.tsx, main.tsx
    Dockerfile       builds the SPA and serves it through nginx
  platform/
    nginx/           reverse proxy configuration
    monitoring/      Prometheus scrape config, Grafana provisioning and dashboards
    scripts/         dev-setup.sh, health-check.sh
  contracts/         openapi.yaml and integration contracts
  docs/              architecture, API, database, tests, QA, deployment
  docker-compose.yml           base stack (production shape)
  docker-compose.override.yml  development overrides (local postgres, exposed ports)
  render.yaml                  Render blueprint (API + worker)
```

## Run locally

### Prerequisites

- Python **3.11+** and pip.
- Node.js **20+** and npm.
- Docker Desktop only if you choose the Compose path.

Install dependencies once:

```bash
cd backend
python -m pip install -r requirements.txt

cd ../frontend
npm install
```

### Option A - no Docker, no external services (fastest)

Runs on SQLite with local file storage, an in-process vector index and deterministic
hashing embeddings. No PostgreSQL, Redis, Qdrant, object storage or LLM key required.
Answers are extractive rather than generated, which is enough to exercise the whole product.

**1. Create the local database (first run only).** Run from `backend/`.

PowerShell:

```powershell
cd backend
$env:DATABASE_URL = 'sqlite+pysqlite:///./nexus_dev_run.db'
python -c "from app.db.base import Base; import app.models; from app.db.session import engine; Base.metadata.create_all(bind=engine); print('Local database ready')"
```

Git Bash / macOS / Linux:

```bash
cd backend
export DATABASE_URL='sqlite+pysqlite:///./nexus_dev_run.db'
python - <<'PY'
from app.db.base import Base
import app.models  # registers all ORM models
from app.db.session import engine
Base.metadata.create_all(bind=engine)
print('Local database ready')
PY
```

**2. Start the backend.**

PowerShell:

```powershell
cd backend
$env:DATABASE_URL = 'sqlite+pysqlite:///./nexus_dev_run.db'
$env:SECRET_KEY = 'local-dev-secret'
$env:STORAGE_BACKEND = 'local'
$env:STORAGE_ROOT = 'storage'
$env:VECTOR_INDEX_BACKEND = 'memory'
$env:EMBEDDING_PROVIDER = 'hashing'
$env:INGESTION_USE_CELERY = 'false'
$env:RATE_LIMIT_ENABLED = 'false'
$env:CORS_ORIGINS = 'http://localhost:5173,http://127.0.0.1:5173'
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Git Bash / macOS / Linux:

```bash
cd backend
export DATABASE_URL='sqlite+pysqlite:///./nexus_dev_run.db'
export SECRET_KEY='local-dev-secret'
export STORAGE_BACKEND='local'
export STORAGE_ROOT='storage'
export VECTOR_INDEX_BACKEND='memory'
export EMBEDDING_PROVIDER='hashing'
export INGESTION_USE_CELERY='false'
export RATE_LIMIT_ENABLED='false'
export CORS_ORIGINS='http://localhost:5173,http://127.0.0.1:5173'
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/v1/health`
- Metrics: `http://127.0.0.1:8000/metrics`

In this mode `redis`, `qdrant` and `worker` report unhealthy in `/health`; that is
expected. `database` and `storage` must be healthy.

**3. Start the frontend** in a second terminal.

```powershell
cd frontend
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000/api/v1'
npm run dev -- --host 127.0.0.1 --port 5173
```

```bash
cd frontend
export VITE_API_BASE_URL='http://127.0.0.1:8000/api/v1'
npm run dev -- --host 127.0.0.1 --port 5173
```

`VITE_API_BASE_URL` is optional: the Vite dev server proxies `/api` to
`http://127.0.0.1:8000` (override with `VITE_PROXY_TARGET`), so plain `npm run dev` works
too. Set it explicitly when you want the browser to call the API directly.

Open `http://127.0.0.1:5173`.

**4. First run.** Register with an email, password, full name and organization name -
the first user of a new organization becomes its admin. Then upload a file under
**Documents**, wait for the ingestion job to finish, and ask a question in **Chat** or the
**RAG console**.

### Option B - full stack with Docker Compose

Brings up PostgreSQL, Qdrant, the API, the Celery worker, the SPA behind nginx, and
Prometheus + Grafana.

**1. Create the environment file.**

```bash
cp .env.example .env
```

Then set at least:

```ini
JWT_SECRET=<paste output of: openssl rand -hex 32>
POSTGRES_PASSWORD=<any strong local password>
```

Leave `DATABASE_URL` empty to use the bundled PostgreSQL, and set
`INGESTION_USE_CELERY=false` if you have no Redis at all. Cloud values (`SUPABASE_*`,
`QDRANT_URL`, `REDIS_URL`) override the local containers service by service; see
[Configuration](#configuration).

**2. Start the stack.**

```bash
docker compose up -d --build
```

`docker-compose.override.yml` is picked up automatically, adding the local PostgreSQL
service and publishing the ports in the table below. The API container runs
`alembic upgrade head` before uvicorn, so the schema is created on start.

**3. Inspect.**

```bash
docker compose ps
docker compose logs -f backend
curl -s http://localhost:8000/api/v1/health
```

**4. Stop.** `docker compose down` (add `-v` to drop the local database volume).

For a production-shaped run without the dev overrides, use
`docker compose -f docker-compose.yml up -d --build`.

### Option C - real embeddings and generated answers

Point the backend at a real embedding provider and an LLM (see
[Configuration](#configuration)). Groq, OpenAI and local Ollama all work because the
client speaks the OpenAI API:

```ini
OPENAI_API_KEY=<key>
OPENAI_BASE_URL=https://api.groq.com/openai/v1   # or your own endpoint
LLM_MODEL=llama-3.3-70b-versatile
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_MODEL=<embedding model id>
EMBEDDING_DIMENSIONS=1536
VECTOR_INDEX_BACKEND=qdrant
QDRANT_URL=https://<cluster>.cloud.qdrant.io:6333
QDRANT_API_KEY=<key>
```

Re-index existing documents after changing the embedding model or its dimensions;
vectors from different models are not comparable.

### Ports and URLs

| Service | Local URL | Notes |
|---|---|---|
| Frontend (Vite dev) | `http://127.0.0.1:5173` | `npm run dev` |
| Frontend (container) | `http://localhost:3000` | nginx serving the built SPA |
| API | `http://127.0.0.1:8000` | `/docs`, `/api/v1/health`, `/metrics` |
| nginx (compose) | `http://localhost` | `HTTP_PORT`, proxies to API and SPA |
| PostgreSQL | `localhost:5432` | compose override only |
| Qdrant | `http://localhost:6333` | REST, dashboard at `/dashboard` |
| Prometheus | `http://localhost:9090` | compose only |
| Grafana | `http://localhost:3001` | compose only |

### Verify a local setup

```bash
curl -s http://127.0.0.1:8000/api/v1/health      # database and storage healthy
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/docs   # 200
```

Then register in the UI and confirm the browser network tab shows requests to
`http://127.0.0.1:8000/api/v1/...` - not to the Vite origin.

## Configuration

`backend/app/core/config.py` reads environment variables (and `backend/.env`). The root
`.env` feeds Docker Compose; on Render the same names are set in the service environment.
`.env.example` lists the variables you normally set; every setting and its default is in
that config module.

| Group | Variables | Notes |
|---|---|---|
| Core | `ENVIRONMENT`, `DEBUG`, `LOG_LEVEL`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES` | `SECRET_KEY` is required; changing it invalidates existing tokens |
| Database | `DATABASE_URL` | `postgresql+psycopg://user:pass@host:5432/db?sslmode=require`; use the session pooler on port 5432 for Supabase |
| Storage | `STORAGE_BACKEND`, `STORAGE_ROOT`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET`, `MINIO_*` | `auto` picks Supabase when configured, then MinIO, then local disk |
| Vector | `VECTOR_INDEX_BACKEND`, `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` | `memory` is for tests only |
| Embeddings | `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `EMBEDDING_BATCH_SIZE` | `hashing` is deterministic and non-semantic |
| Generation | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`, `LLM_PROVIDER` | any OpenAI-compatible endpoint |
| Chunking | `CHUNK_SIZE`, `CHUNK_OVERLAP`, `RAG_CHUNK_STRATEGY`, `RAG_PARENT_CHUNK_SIZE`, `RAG_CHILD_CHUNK_SIZE` | `recursive`, `token`, `sentence`, `semantic`, `parent_child` |
| Retrieval | `RAG_RETRIEVAL_MODE`, `RAG_FINAL_TOP_K`, `RAG_RERANKER`, `RAG_QUERY_REWRITE`, `RAG_MULTI_QUERY`, `RAG_VERIFICATION` | defaults: hybrid, 8, heuristic |
| Async | `REDIS_URL`, `INGESTION_USE_CELERY` | `rediss://` for Upstash; set `INGESTION_USE_CELERY=false` to run without a worker |
| Security | `CORS_ORIGINS`, `RATE_LIMIT_ENABLED`, `AUTH_RATE_LIMIT`, `RAG_RATE_LIMIT_PER_MINUTE` | CORS entries are exact origins, comma separated, no trailing slash |
| Monitoring | `LOG_LEVEL` | `/metrics` is always exposed as a plain Prometheus endpoint |

Two configuration mistakes account for most deployment issues, so they are called out:

- **CORS origins are compared byte for byte.** `https://app.vercel.app/` with a trailing
  slash never matches the `Origin` header a browser sends (`https://app.vercel.app`).
  The parser now normalizes trailing slashes, quotes and a pasted `CORS_ORIGINS=` prefix,
  but the value should still be written correctly.
- **`VITE_API_BASE_URL` is compiled into the bundle.** Changing it in Vercel does nothing
  until a new build runs. The value must end with `/api/v1`.

## Testing

```bash
cd backend
python -m pytest -q          # 148 passed

cd ../frontend
npm run type-check
npm run lint
npm run build
```

The backend suite forces SQLite, local storage, an in-memory vector index, hashing
embeddings and Celery disabled, so it never touches a real database, Redis or Qdrant.
Integration tests live in `tests/` at the repository root.

## Deployment

| Component | Host | Notes |
|---|---|---|
| API + Celery worker | Render (`render.yaml` blueprint, Docker) | start command runs `alembic upgrade head` |
| Frontend | Vercel | `VITE_API_BASE_URL=https://<api>.onrender.com/api/v1` |
| Database + storage | Supabase | PostgreSQL on port 5432 (session pooler), bucket `nexus-documents` |
| Redis | Upstash | `rediss://default:<password>@<host>:6379` |
| Vector index | Qdrant Cloud | `QDRANT_URL=https://<cluster>:6333` plus `QDRANT_API_KEY` |
| Monitoring | Grafana Cloud | agentless scrape of `https://<api>.onrender.com/metrics` |

Step-by-step instructions, including the exact Render and Vercel settings, are in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). After deploying, check:

```bash
curl -s https://<api>.onrender.com/api/v1/health
# database, storage, qdrant healthy; worker healthy only when the Celery service runs
```

## API surface

Routers are mounted under `/api/v1`. The shared RAG API lives at `/api/v1/rag`:

- `POST /rag/query`, `POST /rag/query/stream`
- `POST /rag/retrieval/test`
- `POST /rag/ingest`, `POST /rag/ingest/file`, `GET /rag/ingestions/{job_id}`
- `POST /rag/documents/{id}/reindex`, `DELETE /rag/documents/{id}/index`, `DELETE /rag/documents/{id}`
- `GET /rag/documents/{id}/sync`, `GET /rag/sources`, `GET /rag/status`, `GET /rag/config`, `GET /rag/health`
- `POST /rag/evaluation/run`, `GET /rag/evaluations`

Product endpoints used by the UI:

- `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `PATCH /auth/me`, `POST /auth/change-password`
- `GET/POST /documents`, `POST /documents/upload`, `GET /documents/{id}`
- `GET/POST /sources`, `POST /sources/{id}/sync`
- `POST /chat/conversations`, `GET /chat/conversations`, `POST /chat/conversations/{id}/messages`
- `GET /search`
- `GET /agents/catalog`, `POST /agents/executions`, `GET /agents/executions/{id}`, `/agents/executions/{id}/steps`, `/agents/approvals`
- `POST /agents/sql/generate`, `/agents/sql/validate`, `/agents/sql/schema`
- `GET /intelligence/reports`, `POST /intelligence/reports/export`, `POST /intelligence/documents/compare`, `POST /intelligence/email/search`
- `GET /admin/overview`, `/admin/users`, `/admin/audit-logs` (admin only)
- `GET /analytics/overview?days=14`
- `GET /health`, `/metrics`

`contracts/openapi.yaml` is the canonical contract.

## Troubleshooting

- **`no such table`** - create the local SQLite database as shown above, or run
  `alembic upgrade head` against the configured PostgreSQL instance.
- **`/health` shows `database: unhealthy`** - the DSN is wrong or the host is unreachable;
  the payload includes the exception class in `detail.database`. Supabase users: use the
  session pooler on port 5432 and do not add `?pgbouncer=true`.
- **Frontend gets `404` on `/auth/register`** - the API base URL is wrong. It must be an
  absolute URL ending in `/api/v1`; a missing prefix or a doubled slash (`//auth/...`)
  means the built bundle carries a stale value. Rebuild after changing `VITE_API_BASE_URL`.
- **`400 Disallowed CORS origin`** - the browser origin is not in `CORS_ORIGINS`. Copy the
  exact value of `location.origin` (scheme, host, port, no trailing slash) from the browser
  console, and restart the API after changing the variable.
- **Uploads stay `pending`** - no worker is consuming the queue. Set
  `INGESTION_USE_CELERY=false` for the in-process fallback, or start the worker with
  `-Q ingestion,agents,default`.
- **Port already in use** - change `--port 8000` / `--port 5173` and update
  `VITE_API_BASE_URL` and `VITE_PROXY_TARGET`.
- **Answers are extractive, not generated** - no LLM key is configured, or the provider
  call failed; the RAG console shows `answer_mode` and warnings for the run.
- **Semantic search returns nothing useful** - `EMBEDDING_PROVIDER=hashing` produces
  non-semantic vectors. Configure a real provider and re-index.

## Documentation

| Document | Purpose |
|---|---|
| [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) | Components, RAG pipeline, security model, persistence |
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | Endpoint contracts and error shapes |
| [`docs/DATABASE_SCHEMA.md`](docs/DATABASE_SCHEMA.md) | Tables, relationships, indexes |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Render, Vercel, Supabase, Upstash, Qdrant, Grafana |
| [`docs/TEST_STRATEGY.md`](docs/TEST_STRATEGY.md) | Test layers and what each covers |
| [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) | Implemented scope and known limitations |
| [`docs/INTEGRATION_STATUS.md`](docs/INTEGRATION_STATUS.md) | Verified integrations and their status |
| [`docs/QA_REPORT.md`](docs/QA_REPORT.md) | QA findings and resolutions |
| [`docs/BUG_REGISTER.md`](docs/BUG_REGISTER.md) | Open and closed defects |

## License

Proprietary - internal project. All rights reserved.
