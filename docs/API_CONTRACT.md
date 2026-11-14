# API Contract (living summary)

Source of truth for schemas: `contracts/openapi.yaml`. Integration notes: `contracts/integration-spec.md`.

## Implemented (backend)
- `GET /` — root status (scaffold, not integration-verified)
- `GET /api/v1/health` — health check (scaffold, not integration-verified)

## Planned
Auth, dashboard, connectors, documents, chat (SSE), conversations, agents, analytics, monitoring, administration. Endpoints and schemas TBD and must be added to OpenAPI before frontend integration.
