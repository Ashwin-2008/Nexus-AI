# API Contract (living summary)

Source of truth for schemas: `contracts/openapi.yaml` (v0.10.0).
This document summarizes implemented behavior; OpenAPI wins for field-level details.

## Authentication and Platform
- `POST /api/v1/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`
- `GET /api/v1/auth/me`, `PATCH /api/v1/auth/me` (full name / email)
- `POST /api/v1/auth/change-password` (verifies current password, revokes all refresh tokens)
- `GET /api/v1/health`, `GET /metrics`
- `GET /api/v1/system/capabilities` — secret-free provider, retrieval, worker and connector inventory for authenticated members.
- `GET /api/v1/admin/overview|users|audit-logs` — organization-scoped, admin role enforced server-side.
- `GET /api/v1/analytics/overview?days=7..90` — persisted retrieval, agent, knowledge and evaluation analytics. Missing metrics are `null`, never fabricated.
- All protected routes require `Authorization: Bearer <JWT>` and are organization-scoped.

## Documents and Ingestion (existing, extended)
- `POST /api/v1/documents/upload` — upload and enqueue ingestion.
- `GET /api/v1/documents`, `GET /api/v1/documents/{id}`, `POST /api/v1/documents/{id}/retry`, `DELETE /api/v1/documents/{id}`.
- Ingestion validates extension allow-list, size, magic bytes and archives; errors are explicit and jobs persist failure details.

## RAG API (new)
All routes require authentication and return only the caller's organization data.

### Query and retrieval
- `POST /api/v1/rag/query` — runs the shared grounded pipeline.
  - Request: `query`; optional `filters` (`document_ids`, `source_ids`, `source_types`, `document_version`, `metadata`), `mode` (`hybrid|dense|sparse`), `top_k`, `rerank`, `verify`, `conversation_id`, `max_context_tokens`, `include_evidence`.
  - Response: `answer`, `answer_mode` (`llm|extractive|no_evidence`), `model`, `citations`, `evidence`, `verification`, `query_analysis`, `timings`, `trace_id`, `insufficient_evidence`, `warnings`, `retrieval_mode`, `reranker`, `degraded_from`, `context_chunk_count`.
- `POST /api/v1/rag/query/stream` — SSE events: `rag_start`, `query_analysis`, `context`, `token`, `verification`, `rag_end`, `error`. Final citations include text; full evidence text is not repeated in `rag_end`.
- `POST /api/v1/rag/retrieval/test` — diagnostics without generation; returns ranked evidence, queries used, reranker and timings.
- `GET /api/v1/rag/health` — index health (`ok` or `degraded`).

### Ingestion and index lifecycle
- `POST /api/v1/rag/ingest` — inline text/Markdown ingestion (`content`, optional filename/title/content type/source/access scope/metadata). Returns 202 with document + job.
- `POST /api/v1/rag/ingest/file` — multipart file ingestion (same pipeline); 413 for oversized files, 422 for unsupported content.
- `GET /api/v1/rag/ingestions/{job_id}` — job/document status, attempt, error, metadata.
- `POST /api/v1/rag/documents/{document_id}/reindex` — re-index with current configuration; uploader or admin only; 409/400 when already processing.
- `DELETE /api/v1/rag/documents/{document_id}/index` — remove lexical chunks and vector points, keep the file; returns counts and vector errors if any.
- `DELETE /api/v1/rag/documents/{document_id}` — remove index, chunks, vectors, stored file and document row.
- `GET /api/v1/rag/documents/{document_id}/sync` — lexical chunk vs vector point counts and `in_sync`.
- `GET /api/v1/rag/sources` — indexed documents with chunk counts and configured connectors (no secrets).
- `GET /api/v1/rag/status` — document/chunk counts, index health, sampled synchronization, capabilities.
- `GET /api/v1/rag/config` — admin-only, secret-free configuration description.

### Evaluation
- `POST /api/v1/rag/evaluation/run` — admin-only; accepts a fixture name or inline items, `mode`, `k`, `generate`, `persist`; returns retrieval metrics and item details.
- `GET /api/v1/rag/evaluations`, `GET /api/v1/rag/evaluations/{run_id}` — admin-only persisted runs.

## Search, Chat, Sources, Intelligence, Agents (existing)
- `GET /api/v1/search?q&mode&top_k&document_ids` — organization-scoped lexical/semantic/hybrid search.
- `/api/v1/chat/conversations` — history and POST SSE streaming; now persists verification, trace id, warnings and retrieval metadata.
- `/api/v1/sources` — connector create/list/get/update/delete/test/sync/history; connector items route through the same ingestion pipeline and carry `source_id`.
- `/api/v1/agents` — persisted supervisor executions, specialist catalog, durable steps/events, safe SQL, approvals, cancellation/retry. Specialists use the shared RAG service.
- `/api/v1/intelligence` — authorized email search, approval-gated email drafts, document extraction/comparison, report export/list/download/delete. Agent-generated markdown reports now create organization-scoped `Report` metadata and resolve downloads through `GET /intelligence/reports/{id}/download`.

## Error Contract
Errors use:
```json
{"error": {"code": "validation_error", "message": "...", "details": [...]}}
```
Notable RAG codes: `validation_error`, `configuration_error`, `rag_error`, `not_found`, `forbidden`, `internal_error`, `file_too_large`.

## Frontend Integration
- `frontend/src/api.ts`: typed RAG query/retrieval/status/ingest/reindex/delete-index/evaluation clients, admin/analytics clients, profile/password clients.
- Design system: `src/styles.css` (dark/light tokens, 3D glass/glow surfaces), `src/theme.tsx` (persisted theme provider), `components/nx.tsx` (shared primitives).
- `/app` dashboard, `/app/chat`, `/app/search`, `/app/rag`, `/app/knowledge-sources`, `/app/document-explorer`, `/app/email`, `/app/database`, `/app/reports`, `/app/agent-control-center`, `/app/analytics`, `/app/system-monitoring`, `/app/administration` and `/app/profile` are all live-wired.
- The former “Unavailable” placeholders were removed; pages render real persisted state, empty states, or explicit API errors.
- `/app/rag`: query console with filters, verification/claims, citations, evidence set, timings, trace, text ingestion, index lifecycle and status.
- `/app/chat`: streaming tokens, verification badge, citations, insufficient-evidence and warning display, plus the resolved retrieval mode from `/rag/status`.
- `/app/document-explorer`: preview extracted text/entities/obligations and compare up to 20 authorized documents.
- `/app/email`: live IMAP search and approval-gated outbound drafts (SMTP only after approval).
- `/app/database`: schema discovery, optional LLM SQL generation, read-only validation/execution, result tables and measured chart specs.
- `/app/reports`: persisted report library, authenticated artifact download and deletion.
- `/app/rag` (admin): evaluation runner, persisted run history, configuration and index-health cards.
- `/app/agents`: cancel/retry controls, step output summaries and measured chart-spec rendering.
- Vite proxies `/api` to `http://127.0.0.1:8000` by default; `VITE_API_BASE_URL` overrides it.
