# NEXUS AI QA Report

Last updated: 2026-11-21

## Latest validation

- Backend: `cd backend; python -m pytest -q` — **124 passed**, 1 existing qdrant-client compatibility warning.
  - Environment: SQLite in-memory, `INGESTION_USE_CELERY=false`, `STORAGE_BACKEND=local`, `VECTOR_INDEX_BACKEND=memory`, `EMBEDDING_PROVIDER=hashing`.
- RAG-specific suites: `tests/test_rag_units.py` (10), `tests/test_rag_pipeline.py` (10) and `tests/test_admin_analytics_profile.py` (6) and `tests/test_capabilities_reports.py` (3) passed.
- Frontend: `npm run type-check`, `npm run lint` and `npm run build` — **passed** after the full 3D dual-theme redesign.
- Alembic head: `0014_rag_metadata`, singular.
- OpenAPI YAML parse: **passed** (`contracts/openapi.yaml` v0.10.0, 66 paths).
- Local dev smoke: frontend `http://127.0.0.1:5174` returns 200, backend `http://127.0.0.1:8001/api/v1/health` returns 200 `degraded` (Redis/Qdrant/worker expected offline), and the Vite `/api` proxy forwards to the current backend. The pre-existing 8000 process was started before the new admin/analytics/profile routes and needs a restart to serve them.

## Coverage added in this increment

### Ingestion
- Real extraction for PDF/DOCX/TXT/MD/CSV/XLSX/HTML/JSON/EML; PPTX via stdlib ZIP/XML when available.
- Validators reject unsupported extensions, executables and malformed archives.
- Dedupe by SHA-256; version records; deterministic chunk ids; re-index replaces stale vectors/rows.
- Inline text and file RAG ingestion endpoints create pollable jobs; tested end-to-end on SQLite/local storage.

### Retrieval and generation
- Hybrid dense+BM25 with RRF; document/source/version/access filters; cross-org isolation tested.
- Query understanding deterministic fallback; optional rewrite/decomposition.
- Context injection neutralization and untrusted evidence wrappers tested.
- Grounded citations map to real chunks; fabricated indices are dropped.
- Verification statuses, numeric conflict detection and disclaimer tested; insufficient evidence returns `no_evidence` with no citations.

### Integration
- Chat non-streaming and SSE use the shared pipeline; citations/verification/trace warnings persisted.
- Specialists and supervisor use `RagService`; evidence is reused across steps and merged without duplicate citations.
- New `/api/v1/rag/*` endpoints for query, streaming, retrieval diagnostics, ingestion, re-index/delete, sync, sources, status, config, health and evaluation.
- Evaluation metrics are computed from real retrieval and persisted.
- New admin endpoints (`/admin/overview|users|audit-logs`), analytics endpoint (`/analytics/overview`) and profile/password endpoints are covered by `tests/test_admin_analytics_profile.py`, including server-enforced member 403 behavior.

### Intelligence, reports and configuration surface
- Agent-generated markdown reports now persist `Report` metadata tied to their execution; `GET /intelligence/reports/{id}/download` resolves the storage key server-side and `DELETE /intelligence/reports/{id}` removes metadata plus artifact.
- `GET /system/capabilities` exposes secret-free LLM/embedding/vector/storage/worker/connector configuration to authenticated members.
- Dashboard/analytics now include persisted conversations, reports, pending approvals and active ingestion counts.
- Connector templates match the backend contracts (website `base_url`, SQL `connection_url` + encrypted credentials, REST `item_path`, GitHub `repo`, Drive OAuth refresh token, IMAP/SMTP fields).

### Frontend
- Full redesign with dark/light themes, responsive 3D glass/glow surfaces, animated landing/auth experience and live data on every internal page.
- Dashboard, chat, search, RAG, sources, documents, agents, analytics, monitoring, administration and profile all compile, lint and build.
- Former “Unavailable” dashboard/analytics/admin/monitoring slots now render real API data or explicit empty/error states.
- Chat and RAG verification, citations, evidence, timings and trace IDs are rendered without fabricating missing values.
- New email, database and reports pages, document preview/comparison, agent cancel/retry, chart-spec rendering and provider capability cards are live-wired.

## Bugs found and fixed during this pass

1. **Memory vector backend was per-construction**, so ingestion points were invisible to later queries and synchronization tests. Fixed with a process-wide dimension-keyed memory index (still test/offline only).
2. **Qdrant `delete_document` returned an operation id, not a deletion count.** It now counts before deleting and returns the real number.
3. **Semantic hit attachment passed string UUIDs into a UUID-typed SQLAlchemy column**, causing 503s after stale points existed. IDs are now parsed as UUIDs and hits without a live organization-owned document row are dropped.
4. **Numeric contradictions were marked supported** when terms matched but numbers differed. Verification now flags disjoint numbers as `conflicting_evidence` with a review-signal disclaimer.
5. **Streaming final citations lacked text**, which could break citation rendering. The final SSE payload now includes citation text while omitting duplicate evidence text.
6. **`RagService.answer_with_evidence` did not re-authorize reused evidence.** It now revalidates against live document/chunk rows before generation.
7. **Conversation memory lookup used a string conversation id against a UUID column and did not check conversation ownership.** It now parses the UUID and verifies organization/user before reading prior citations.

## Not live-verified in this environment

- PostgreSQL migration execution (no live DB), Qdrant, Redis/Celery worker delivery/recovery, MinIO, live LLM/embedding providers, external IMAP/OAuth/SMTP/database connectors.
- OCR for scanned PDFs; optional `sentence-transformers` cross-encoder and PPTX library not installed.
- Frontend `npm run lint`, `npm run type-check` and `npm run build` all passed after the RAG UI changes.
