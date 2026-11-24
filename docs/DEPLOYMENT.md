# Deployment — Supabase · Render · Vercel · Grafana Cloud · Upstash

This is the reference deployment for NEXUS AI. Each managed service owns one
concern, so the backend stays stateless apart from Qdrant.

```
Vercel (React/Vite UI)
        │  HTTPS  VITE_API_BASE_URL
        ▼
Render  (FastAPI API) ──► Supabase PostgreSQL   (relational data)
        │             └─► Supabase Storage      (documents, reports)
        │
        ├──► Upstash Redis     (Celery broker + result backend)
        ├──► Qdrant            (vector index)
        └──► LLM / embeddings provider (OpenAI-compatible)

Render  (Celery worker)  ── same env vars as the API

Grafana Cloud ── scrapes https://<api>.onrender.com/metrics
```

| Concern | Service | Notes |
|---|---|---|
| Relational database | Supabase PostgreSQL | Session pooler (port 5432), `sslmode=require` |
| Document storage | Supabase Storage | Private bucket, service-role key, backend-only |
| API + Celery worker | Render | Docker; migrations run at container start |
| Frontend | Vercel | Static Vite build; `VITE_API_BASE_URL` points at Render |
| Redis | Upstash | **RESP** endpoint (`rediss://`), not the REST API |
| Vector index | Qdrant | Qdrant Cloud free tier, or self-hosted |
| Monitoring | Grafana Cloud | Scrapes the public `/metrics` endpoint |

---

## 1. Supabase — PostgreSQL

1. Create a project at <https://supabase.com/dashboard>.
2. **Connect** → **Session pooler** → copy the URI.
3. Switch the driver to psycopg and keep `sslmode=require`:

```env
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

URL-encode special characters in the password (`@` → `%40`, `#` → `%23`).
Use the **session pooler (5432)**, not the transaction pooler (6543): Alembic
migrations and long-lived SQLAlchemy sessions behave predictably there.

`alembic upgrade head` runs automatically from `backend/Dockerfile`, so the
tables appear in the Supabase Table Editor on the first deploy.

## 2. Supabase — Storage

1. **Project Settings → API** → copy `Project URL` and the `service_role` key.
2. Create a **private** bucket (default name `nexus-documents`). The backend
   also creates it on first upload if it is missing.

```env
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
SUPABASE_STORAGE_BUCKET=nexus-documents
STORAGE_BACKEND=supabase
```

Keys stored in the bucket are organization-scoped:
`orgs/<org_id>/documents/<uuid>_<filename>` and `orgs/<org_id>/reports/<id>.md`.

⚠️ The service-role key bypasses row-level security. It belongs only in the
Render environment; never expose it to Vercel or the browser. Objects are
served to clients through the authenticated backend endpoints, never by
handing out storage keys.

### Object access model

`backend/app/services/storage.py` implements `StorageBackend` with four
backends: `supabase` (default), `minio` (self-hosted S3), `local` (ephemeral
disk) and the selection logic in `get_storage_backend()`. Documents persist the
backend that stored them, so a migration between backends keeps old files.

## 3. Upstash — Redis

Celery needs the Redis wire protocol, so copy the **Redis (RESP)** endpoint
(Upstash → database → Connect → *Redis (RESP)*), not the REST URL/token:

```env
REDIS_URL=rediss://default:<redis-password>@<db>.upstash.io:6379
```

TLS is enabled automatically for `rediss://` in
`backend/app/worker/celery_app.py`. Free-tier command/connection limits apply to
the worker's persistent connection and heartbeats.

## 4. Qdrant — vector index

The backend needs a vector store. The compose file runs one locally; in
production use Qdrant Cloud (free tier is enough to start):

```env
QDRANT_URL=https://<cluster-id>.<region>.cloud.qdrant.io:6333
QDRANT_API_KEY=<api-key>
QDRANT_COLLECTION=nexus_chunks
VECTOR_INDEX_BACKEND=qdrant
```

Keep the `:6333` REST port on the cluster URL. If a network blocks outbound
6333, Qdrant Cloud also answers REST on `:443` for the same cluster (verified),
so `https://<cluster-id>.<region>.cloud.qdrant.io:443` is a valid fallback.

Collection dimensions follow the configured embedding model; changing the
model requires re-indexing (`POST /api/v1/rag/documents/{id}/reindex`). The
collection is created on first ingestion; an existing collection with a
different vector size is rejected rather than silently mixed.

## 5. Render — API and worker

Commit `render.yaml` and create a **New → Blueprint** from the repository.
Every secret lives in the `nexus-shared` environment group with `sync: false`, so
you paste each value **once** and both services receive it. `SECRET_KEY` is
generated once for that group; the worker must use the same value because
connector credentials stored in PostgreSQL are encrypted with it.

| Service | Type | Dockerfile | Notes |
|---|---|---|---|
| `nexus-api` | Web | `backend/Dockerfile` | Health check `/api/v1/health`, listens on `$PORT` |
| `nexus-worker` | Worker | `backend/Dockerfile.worker` | Celery queue `ingestion,default` |

Background workers are a **paid** Render plan feature; the free plan only runs
web services. If the worker cannot run, set `INGESTION_USE_CELERY=false` so
ingestion executes in the API process (documented, synchronous fallback).

Add a **Pre-Deploy Command** of `alembic upgrade head` if you deploy more than
one API instance, so migrations run once instead of per instance.

Required API environment:

```env
SECRET_KEY=<generated>
DATABASE_URL=postgresql+psycopg://...
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
SUPABASE_STORAGE_BUCKET=nexus-documents
STORAGE_BACKEND=supabase
REDIS_URL=rediss://...
QDRANT_URL=https://...
QDRANT_API_KEY=<key>
CORS_ORIGINS=https://<your-app>.vercel.app
OPENAI_API_KEY=<key>
OPENAI_BASE_URL=https://api.groq.com/openai/v1
LLM_PROVIDER=openai_compatible
LLM_MODEL=llama-3.3-70b-versatile
EMBEDDING_PROVIDER=hashing   # or a real embeddings provider
```

The worker receives the same database, storage, Redis, Qdrant, LLM and embedding
variables through `fromGroup: nexus-shared`, plus `WORKER_CONCURRENCY=2`.
`CORS_ORIGINS` belongs to the same group but only the API reads it.

## 6. Vercel — frontend

1. Import the repository, set **Root Directory** to `frontend`.
2. Framework preset: **Vite**. Build: `npm run build`. Output: `dist`.
3. Environment variable:

```env
VITE_API_BASE_URL=https://<your-api>.onrender.com/api/v1
```

4. Add the Vercel production (and preview) origins to `CORS_ORIGINS` on Render.
   Preview URLs change per deployment; either add wildcard patterns you
   actually use or send preview traffic through the production API explicitly.

`frontend/src/api.ts` reads `VITE_API_BASE_URL` at build time; without it the
client falls back to `/api/v1`, which only works behind the compose nginx.

## 7. Grafana Cloud — monitoring

Two supported paths:

**A. Agentless scraping (recommended on Render).** The API exposes
`/metrics` publicly. In Grafana Cloud → **Connections → Agentless scraping**,
add a scrape job:

```yaml
scrape_configs:
  - job_name: nexus-api
    scheme: https
    metrics_path: /metrics
    static_configs:
      - targets: [<your-api>.onrender.com]
```

**B. Prometheus `remote_write`.** For a self-hosted Prometheus (compose),
uncomment the `remote_write` block at the bottom of
`platform/monitoring/prometheus/prometheus.yml` and paste the URL, user id and
API token from Grafana Cloud → Stack → Prometheus.

Import `platform/monitoring/grafana/dashboards/nexus-overview.json` as a
dashboard. Alert on `up{job="nexus-api"} == 0`, ingestion failures
(`nexus_ingestion_*`) and RAG latency histograms.

⚠️ `/metrics` is unauthenticated. Do not put tenant names or document content
in metric labels, and consider restricting the endpoint at the edge if your
plan supports it.

## 8. Verification checklist

```bash
# API is up and dependencies resolve
curl -s https://<your-api>.onrender.com/api/v1/health
# → storage: healthy (supabase), database: healthy, redis: healthy (or degraded)

# Runtime capabilities report the resolved backends
curl -s -H "Authorization: Bearer <jwt>" \
  https://<your-api>.onrender.com/api/v1/system/capabilities
```

1. Upload a document in the UI; `GET /api/v1/rag/documents/{id}/sync` shows
   `storage_backend: supabase`.
2. The object appears in Supabase → Storage → `nexus-documents` under
   `orgs/<org_id>/documents/…`.
3. Ingestion completes (`/api/v1/rag/ingestions/{job_id}` → `succeeded`).
4. A RAG query returns chunks and citations, and a second organization cannot
   retrieve them (organization isolation).

## 9. Known limitations

- Supabase Storage is accessed with the service-role key; per-user object
  authorization is enforced by the backend, not by Supabase RLS.
- Local disk storage (`STORAGE_BACKEND=local`, the automatic fallback) is
  ephemeral on Render: restarting the service loses those objects.
- The Celery worker needs a paid Render plan; otherwise ingestion runs
  in-process.
- `hashing` embeddings are deterministic but **not semantic**; configure a real
  embedding provider before judging retrieval quality.
- `alembic upgrade head` on container start is safe for a single API instance;
  use Render's pre-deploy command when scaling out.
