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
| `nexus-worker` | Worker | `backend/Dockerfile.worker` | Celery queues `ingestion,agents,default` |

Background workers are a **paid** Render plan feature; the free plan only runs
web services. The API probes the Celery control channel before enqueueing: when
no worker answers, connector syncs and document ingestion run in the API process
instead of sitting at `queued`/`0 ingested` forever. You can also set
`INGESTION_USE_CELERY=false` to force the in-process path.

Add a **Pre-Deploy Command** of `alembic upgrade head` if you deploy more than
one API instance, so migrations run once instead of per instance.

If you deploy with Render's **Python** runtime instead of the blueprint's
Dockerfile, Render's default start command skips migrations, so a fresh database
stays empty and every write fails with `relation "users" does not exist`. Use:

| Setting | Value |
|---|---|
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

The same env group applies; only the container command differs.

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
LLM_MODEL=openai/gpt-oss-120b
EMBEDDING_PROVIDER=hashing   # or a real embeddings provider
```

`EMBEDDING_PROVIDER=hashing` is deterministic but **not semantic**: retrieval is
keyword-only and paraphrased questions can return no evidence. The API reports
this in `/api/v1/rag/status` and in query warnings. Configure a real embeddings
provider with matching `EMBEDDING_DIMENSIONS`, then reindex the documents.

Groq serves chat but **not** embeddings, so a separate embedding endpoint is
supported (it defaults to `OPENAI_BASE_URL` only when left empty):

```env
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=<embeddings-provider-key>
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

Changing dimensions changes the vector size: use a new `QDRANT_COLLECTION`
name (or recreate the collection), then reindex. Existing 256-dimension hashing
vectors cannot be mixed with 1536-dimension embeddings.

`LLM_MODEL` is validated against the provider's `/models` endpoint on the first
404: a retired model is replaced automatically, with a warning in the API log.

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

4. Add the Vercel production and preview origins to `CORS_ORIGINS` on Render as
   exact `scheme://host` entries, comma separated, no trailing slash and no
   wildcards. A miss shows up in the browser as `Disallowed CORS origin` (HTTP
   400 on the preflight, no `Access-Control-Allow-Origin`). Vercel preview URLs
   change per deployment (`<project>-<hash>-<team>.vercel.app`), so whitelist the
   stable production domain and only the preview hosts you actually test from.

`frontend/src/api.ts` reads `VITE_API_BASE_URL` at build time; without it the
client falls back to `/api/v1`, which only works behind the compose nginx. The
value must end with `/api/v1` and without a trailing slash — Vite env changes
only take effect after a new deployment. `frontend/src/api.ts` now normalises the
value: trailing slashes are stripped and a bare origin
(`https://<api>.onrender.com`) gets `/api/v1` appended, so a half-configured
variable degrades to the correct URL instead of `//auth/login`.

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
