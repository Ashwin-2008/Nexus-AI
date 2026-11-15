# Database Schema

Last updated: 2026-11-15 (Kiro, Backend)

## Implemented (Alembic migrations)

### 0001_initial_auth (verified on PostgreSQL 15-alpine)
- **organizations**: `id` UUID PK, `name` VARCHAR(255) NOT NULL, `created_at` TIMESTAMPTZ NOT NULL DEFAULT now()
- **roles**: `id` UUID PK, `name` VARCHAR(64) NOT NULL UNIQUE (indexed), `description` VARCHAR(255)
- **users**: `id` UUID PK, `email` VARCHAR(320) NOT NULL UNIQUE (indexed), `hashed_password` VARCHAR(255) NOT NULL, `full_name` VARCHAR(255), `is_active` BOOLEAN NOT NULL DEFAULT true, `organization_id` UUID NOT NULL FK organizations(id) CASCADE (indexed), `role_id` UUID NOT NULL FK roles(id) RESTRICT (indexed), `created_at` TIMESTAMPTZ NOT NULL DEFAULT now()

### 0002_documents (verified on PostgreSQL 15-alpine)
- **documents**: `id` UUID PK, `organization_id` UUID NOT NULL FK organizations(id) CASCADE (indexed), `uploaded_by` UUID NULL FK users(id) SET NULL (indexed), `filename` VARCHAR(512) NOT NULL, `content_type` VARCHAR(128) NOT NULL, `file_size` INTEGER NOT NULL, `storage_path` VARCHAR(1024) NOT NULL, `status` VARCHAR(32) NOT NULL DEFAULT 'pending' (pending|processing|completed|failed), `error_message` TEXT, `retry_count` INTEGER NOT NULL DEFAULT 0, `doc_metadata` TEXT (JSON), `created_at` TIMESTAMPTZ NOT NULL DEFAULT now(), `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now()

### 0003_ingestion_jobs (verified on PostgreSQL 15-alpine)
- **documents (alter)**: added `storage_backend` VARCHAR(32) NOT NULL DEFAULT 'local'
- **ingestion_jobs**: `id` UUID PK, `document_id` UUID NOT NULL FK documents(id) CASCADE (indexed), `organization_id` UUID NOT NULL FK organizations(id) CASCADE (indexed), `status` VARCHAR(32) NOT NULL DEFAULT 'queued' (queued|running|succeeded|failed|retrying), `attempt` INTEGER NOT NULL DEFAULT 1, `max_attempts` INTEGER NOT NULL DEFAULT 3, `task_id` VARCHAR(255) NULL (indexed), `worker` VARCHAR(255) NULL, `error_message` TEXT NULL, `error_details` TEXT NULL (JSON), `started_at` TIMESTAMPTZ NULL, `finished_at` TIMESTAMPTZ NULL, `created_at` TIMESTAMPTZ NOT NULL DEFAULT now(), `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now()

### 0004_auth_security (verified on PostgreSQL 15-alpine)
- **refresh_tokens**: `id` UUID PK, `user_id` UUID NOT NULL FK users(id) CASCADE (indexed), `token_hash` VARCHAR(128) NOT NULL UNIQUE (indexed), `jti` VARCHAR(64) NOT NULL UNIQUE (indexed), `expires_at` TIMESTAMPTZ NOT NULL, `revoked_at` TIMESTAMPTZ NULL, `created_at` TIMESTAMPTZ NOT NULL DEFAULT now(), `replaced_by_jti` VARCHAR(64) NULL
- **audit_logs**: `id` UUID PK, `organization_id` UUID NULL FK organizations(id) SET NULL (indexed), `user_id` UUID NULL FK users(id) SET NULL (indexed), `action` VARCHAR(128) NOT NULL (indexed), `resource_type` VARCHAR(64) NULL, `resource_id` VARCHAR(128) NULL, `details` TEXT NULL (JSON), `ip_address` VARCHAR(64) NULL, `created_at` TIMESTAMPTZ NOT NULL DEFAULT now()

### 0005_document_chunks (verified on PostgreSQL 15-alpine, 2026-11-15)
- **document_chunks**: `id` UUID PK, `document_id` UUID NOT NULL FK documents(id) CASCADE (indexed), `organization_id` UUID NOT NULL FK organizations(id) CASCADE (indexed), `chunk_index` INTEGER NOT NULL, `text` TEXT NOT NULL, `char_start` INTEGER NOT NULL DEFAULT 0, `char_end` INTEGER NOT NULL DEFAULT 0, `provenance` TEXT NULL (JSON: pages/rows/sheets spans), `embedding_model` VARCHAR(255) NULL, `embedding_provider` VARCHAR(64) NULL, `indexed_at` TIMESTAMPTZ NULL, `created_at` TIMESTAMPTZ NOT NULL DEFAULT now()
- Chunk IDs are deterministic (uuid5 of document_id + index) → re-indexing replaces the same rows/points.

## Vector store (Qdrant)
- Collection `nexus_chunks` (config `QDRANT_COLLECTION`), vectors dim per provider (hashing default 256, all-MiniLM-L6-v2 = 384, text-embedding-3-small = 1536), distance COSINE.
- Point payload: organization_id, document_id, chunk_id, chunk_index, text, metadata{provenance, ...}; keyword payload indexes on organization_id and document_id. All retrieval filtered by organization_id — cross-org leakage structurally prevented.

## Notes
- Passwords stored only as bcrypt hashes (`hashed_password`). No plaintext secrets in DB.
- Refresh tokens stored as SHA-256 hashes (`token_hash`); rotation and revocation supported.
- Organization isolation enforced at query/service layer (`organization_id` scoping) for documents and ingestion jobs.
- Alembic: `backend/alembic.ini`, `backend/alembic/env.py`, versions `0001_initial_auth.py`–`0005_document_chunks.py`.

## Planned (not yet implemented)
Data sources/connectors, document versions, conversations, messages, citations, agent executions, extended audit coverage, usage records, permissions tables/policies, Postgres tsvector lexical index.
