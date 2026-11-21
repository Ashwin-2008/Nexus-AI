# NEXUS AI - System Architecture (Initial)

Status: living architecture (2026-11-15)

## Components
- **frontend/** (Lovable): UI, auth flows, chat, connectors, dashboards.
- **backend/** (Kiro): FastAPI API, auth/RBAC, connectors, ingestion pipeline, RAG, multi-agent orchestration, SQL intelligence, LLM abstraction, persistence.
- **platform/** (Amazon Q): infra, deployment, observability, data services provisioning (Postgres, Redis, Qdrant, Kafka/queue).

## Core data/services (planned)
- PostgreSQL: metadata, users/orgs/RBAC, documents, jobs, conversations, audit/usage.
- Qdrant: vector embeddings/chunk references.
- Redis: caching, rate limiting, session/ephemeral state.
- Kafka/queue: async ingestion and background jobs.
- Storage abstraction: local or MinIO objects under organization-scoped keys.
- Connected intelligence: IMAP email retrieval, approval-gated SMTP delivery, document extraction/comparison, safe SQL/analytics, cross-source workflow routing, and persisted report exports/metadata.

## Backend modules (planned, `backend/app/`)
- `core/`: config, security, logging
- `db/`: session, base, migrations support
- `models/`, `schemas/`: ORM and API schemas
- `api/v1/`: routers (auth, connectors, documents, chat, agents, analytics, admin)
- `services/`: ingestion, retrieval/RAG, agents, connectors, LLM providers, evaluation
- `services/intelligence.py`: organization-scoped email search, SMTP delivery, document extraction/comparison, and report export.
- `models/report.py`: organization-scoped report metadata linked to generated storage objects and optional executions.
- `services/specialists.py`: structured specialist handlers invoked by the durable execution service.

## Integration
- Contracts in `contracts/openapi.yaml` and `contracts/integration-spec.md` are authoritative for cross-team APIs.
- No frontend/platform code modified by backend; backend coordinates via contracts.

## Notes
- This is a living document; update only when architecture/structure materially changes.
