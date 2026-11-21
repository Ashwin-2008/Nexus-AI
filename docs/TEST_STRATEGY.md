# NEXUS AI – Test Strategy (RAG)

Last updated: 2026-11-21

## Objectives

Verify that the shared RAG subsystem:
1. ingests supported sources without silent failure or fabricated content;
2. retrieves only organization-authorized evidence;
3. produces grounded answers with real citation mappings;
4. reports verification limitations transparently;
5. integrates with every caller (chat, specialists, supervisor, API, frontend);
6. remains backward compatible with pre-RAG behavior.

## Test Layers

### Unit tests (`backend/tests/test_rag_units.py`)
- Chunking strategies, deterministic ids, parent-child links, content hashes and token counts.
- RRF fusion ordering and hybrid mode marking.
- Scope permission intersection.
- Upload validation: extension allow-list, executable magic-byte rejection.
- Embedding validation: empty, zero, non-finite and dimension drift rejection.
- Context builder: token budget, prompt-injection neutralization, untrusted wrappers, citation indexing.
- Citation validation: fabricated indices removed, duplicate chunk collapse.
- Verification: supported, numeric-conflict and missing-citation statuses, disclaimer.
- Query analyzer deterministic fallback.
- Retrieval metrics computed from definitions (Recall, Precision, MRR, NDCG).

### Integration tests (`backend/tests/test_rag_pipeline.py`, SQLite + memory vector + hashing embeddings)
- Grounded query returns citations mapped to real chunks with verification.
- SSE stream emits context/tokens/verification/final payload.
- Insufficient evidence returns explicit `no_evidence`, zero citations, no invented answer.
- Document filters restrict evidence; cross-organization queries return no citations.
- Inline text ingestion returns a pollable job, completes, and is searchable.
- Unsupported file upload rejected with the documented error envelope.
- Re-index/delete-index keeps lexical and vector counts synchronized.
- Status/sources/config/health endpoints; config contains no secrets.
- Evaluation run returns real retrieval metrics, persists and lists the run.
- Unauthenticated access returns 401.

### Admin, analytics and profile tests (`backend/tests/test_admin_analytics_profile.py`)
- Profile name/email update persists and writes an audit entry.
- Password change rejects an incorrect current password, accepts a valid rotation, invalidates the old password and revokes refresh tokens.
- Admin overview returns organization counts; member tokens receive 403 from admin routes.
- Analytics overview returns a 14-day series and honest empty/`None` values when no telemetry exists.

### Capabilities, reports and activity tests (`backend/tests/test_capabilities_reports.py`)
- `/system/capabilities` exposes provider/connector inventory without secrets.
- Report-oriented supervisor runs persist markdown report metadata tied to the execution; the artifact lists and downloads through the organization-scoped metadata route.
- Analytics activity counters (conversations, reports, pending approvals, active ingestions) are present and start at zero.
- Cancelling an execution revokes its pending approval; a late approve request returns 409.

### Regression tests (existing suite)
- Auth/RBAC, organization isolation, documents/ingestion jobs, processing/extraction, embeddings, search modes, chat/SSE and citations, connectors, agents/supervisor, safe SQL, intelligence/reports.
- The compatibility facade `app/services/rag_service.py` keeps old public names (`RagPipeline`, `RagResult`, `verify_citations`) working.

### Frontend checks
- `npm run type-check`, `npm run lint` and `npm run build` pass for the redesigned UI and typed API clients.
- Manual/browser checks (when backend is running): landing/auth theme switch, dashboard telemetry, `/app/rag` query/ingest/index/evaluation, `/app/chat` streaming citations + verification, `/app/search` modes, `/app/documents` preview/compare, `/app/email`, `/app/database`, `/app/reports`, agents cancel/retry, admin/analytics/monitoring live data and mobile navigation.
- Theme persistence is verified through `localStorage` (`nexus_theme`) and `data-theme` on the document root.

### Evaluation framework
- Retrieval metrics: Recall@K, Precision@K, MRR, NDCG@K.
- Optional generation: answer relevance, faithfulness, citation correctness, evidence coverage, unsupported claim rate, verification status.
- Datasets: JSONL with query + relevant chunk/document ids; fixture at `backend/app/rag/tests/fixtures/sample_eval_dataset.jsonl`.
- Persisted runs in `rag_evaluation_runs`; admin-only API.
- Gold evidence must come from real indexed chunks; no synthetic citations.

## Environment Matrix

| Variable | CI/local value | Production expectation |
|---|---|---|
| `DATABASE_URL` | SQLite in-memory | PostgreSQL + Redis/Celery |
| `VECTOR_INDEX_BACKEND` | `memory` | `qdrant` |
| `EMBEDDING_PROVIDER` | `hashing` (non-semantic, test only) | `local` or `openai_compatible` |
| `INGESTION_USE_CELERY` | `false` | `true` with worker |
| `STORAGE_BACKEND` | `local` | MinIO/S3 |
| LLM key | absent → extractive fallback | valid provider key |

## Gates for “Done”

- Full backend suite green (currently 124 passed).
- Frontend type-check green; lint/build green in CI.
- Migration head singular and applied to a staging PostgreSQL.
- Live Qdrant/embedding/LLM smoke test with a real corpus.
- No fabricated citations in evaluation runs; insufficient evidence is explicit.
- Cross-organization retrieval returns zero evidence on every mode.
- Connector sync populates `source_id` and feeds the same ingestion pipeline.

## Non-Goals / Known Limits

- Tests using hashing embeddings validate machinery, not semantic quality.
- Memory vector backend is ephemeral and unsuitable for production.
- Verification is lexical grounding; it is not an NLI model and does not guarantee truth.
- OCR, live external systems and large-corpus performance require separate validation.
