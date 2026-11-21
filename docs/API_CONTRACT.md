# API Contract (living summary)

Source of truth for schemas: `contracts/openapi.yaml`. Integration notes: `contracts/integration-spec.md`.

## Implemented (backend)
- `GET /` — root status (scaffold, not integration-verified)
- `GET /api/v1/health` — health check (scaffold, not integration-verified)
- `GET /api/v1/search?q&mode&top_k&document_ids` — organization-scoped lexical, semantic, or hybrid chunk search with provenance.
- `/api/v1/sources` — authenticated connector create/list/get/update/delete, connection test, sync trigger, and sync history.
- `/api/v1/chat/conversations` — persistent conversations, grounded citations, and POST-based SSE streaming.
- `/api/v1/agents` — persisted supervisor executions, durable steps/events, specialist catalog, retrieval/document/database/analytics/research/verification/report/email handlers, safe SQL schema/validation/generation, approval requests, cancellation, and eligible retry.
- `/api/v1/intelligence` — real email search, approval-gated email drafts, document extraction/comparison, report export, organization-scoped report metadata listing, and authenticated report download.

## Frontend integration status
- `frontend/src/api.ts` exposes typed source, sync, search, agent execution, step, approval, email search, document comparison, and report export clients.
- `frontend/pages/sources.tsx` calls real connector APIs and reports truthful loading/error/sync states.
- `frontend/pages/search.tsx` calls the real search endpoint and renders returned evidence and provenance.
- `frontend/pages/agents.tsx` submits real executions, displays durable step progress, and handles pending approvals.
- Frontend API base remains `VITE_API_BASE_URL` (default `/api/v1`); the agent workspace includes report metadata and download controls.

## Remaining
Live broker/worker validation, SMTP provider delivery/OAuth configuration, richer semantic document comparison, administration, and full source-level cross-source correlation remain follow-up work. Synchronous execution remains the backward-compatible default; background execution is available through the worker integration.
