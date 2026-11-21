# NEXUS AI – System Architecture

Status: living architecture, RAG subsystem integrated (2026-11-21)

## Components

- **frontend/** — React/Vite UI with a 3D dual-theme design system: landing/auth, dashboard, chat, search, RAG console, sources, documents, agents, analytics, monitoring, administration and profile. All pages call the live API; Vite proxies `/api` to the backend in development.
- **backend/** — FastAPI application: auth/RBAC, organization isolation, document/connector ingestion, shared RAG, LLM abstraction, specialist supervisor, safe SQL, reports, evaluation, observability.
- **platform/** — Docker Compose, PostgreSQL, Redis/Celery, Qdrant, MinIO, nginx, Prometheus/Grafana.
- **contracts/** — OpenAPI and integration specifications; API behavior source of truth.

## Shared RAG Architecture

There is exactly one RAG implementation. All callers use:

```
app/rag/orchestration/RagOrchestrator + RagService
```

Callers: `services/rag_service.py` compatibility facade, chat API, specialist handlers, supervisor executions, RAG API. No specialist owns a separate retriever, embedding provider, vector store or generation path.

### Pipeline

```
Source (upload / connector / inline text / DB record)
  → loader + validation
  → parser (text, layout, tables, OCR-unavailable signal)
  → normalizer (span remapping)
  → metadata extraction + content hash
  → dedupe + version detection
  → chunker (recursive | token | sentence | semantic | parent-child)
  → embedder (validated real vectors)
  → Qdrant upsert + PostgreSQL chunk rows + document version

Question
  → query analysis (intent/entities/dates/multi-part; deterministic fallback)
  → optional rewrite/decomposition/expansion
  → permission-intersected filters
  → dense + BM25 lexical retrieval
  → Reciprocal Rank Fusion
  → live re-authorization of candidates
  → reranking (heuristic | LLM | cross-encoder)
  → parent/neighbour context expansion
  → token-budgeted context + injection neutralization + untrusted wrappers
  → grounded generation (LLM or labelled extractive fallback)
  → citation resolution/validation
  → claim-level verification
  → response with answer, citations, evidence, verification, timings, warnings, trace id
```

### Module Map (`backend/app/rag/`)

| Package | Responsibility |
|---|---|
| `loaders/` | Per-format, web (SSRF-protected) and database loaders |
| `parsing/` | Layout/table extraction, cleaning, injection neutralization, OCR status |
| `ingestion/` | Validators, metadata, dedupe, versioning, pipeline, orchestrator |
| `chunking/` | Recursive, token, sentence, semantic, parent-child, deterministic ids |
| `embeddings/` | Provider adapter, cache, batcher, vector validation |
| `vectorstores/` | Qdrant adapter over the existing vector index, filters, health |
| `indexes/` | Lexical/vector/hybrid facades, synchronization, index manager |
| `retrieval/` | Dense, sparse, hybrid, RRF, filters/revalidation, rerank, parent/context expansion |
| `query/` | Deterministic analyzer, optional rewrite/decomposition, routing |
| `reranking/` | Heuristic, LLM, optional cross-encoder, provider selection |
| `context/` | Token budget, dedupe, compression, grouping, builder |
| `citations/` | Span resolution, validation, formatting |
| `verification/` | Claim extraction, evidence matching, hallucination checks, statuses |
| `generation/` | Prompt construction, structured output, generator, streaming |
| `memory/` | Conversation context (ownership-enforced) and session trace/timings |
| `observability/` | Tracing, logging, Prometheus metrics, performance |
| `evaluation/` | Datasets, retrieval metrics, faithfulness, evaluator, reports |
| `orchestration/` | Pipeline steps, `RagOrchestrator`, `RagService`, router helpers |

Prompts are Markdown templates in `backend/app/prompts/` (`rag/`, `system/`, `agents/`, `workflows/`) loaded through a validated loader with hashing.

## Security Model

- Organization id is derived from the authenticated user, never from request filters.
- `RagScope` contains allowed document scopes (`organization`, `member`, `admin`) by role.
- Requested document/source filters are intersected with authorization; denied filters produce an empty result, not a broader search.
- Every fused candidate is revalidated against live document/chunk rows before context building/generation.
- Retrieved text is treated as untrusted: prompt-injection markers are neutralized, evidence is wrapped in `<untrusted_evidence>` and the system prompt forbids following document instructions.
- Citation IDs are validated and fabricated indices are dropped.
- Admin-only operations: RAG config inspection, evaluation runs/history and non-organization access scopes for ingestion.
- Secrets are never returned by config inspection; RAG logs avoid document content and redact secret-like values.

## Persistence

- PostgreSQL: documents (hash/source/version/scope), chunks (heading/parent/hash/tokens/strategy/version/scope), document versions, query telemetry, evaluation runs, conversations/messages, connectors, agent executions, reports.
- Qdrant: chunk vectors and payloads including organization/document/chunk ids, source id, version and access scope. Collection `nexus_chunks`, cosine distance.
- Lexical: BM25 over organization chunk rows in PostgreSQL/SQLite.
- Object storage: local or MinIO under organization-scoped keys.

## Integration Boundaries

- Specialists call `RagService`, not lower-level retrieval modules.
- Chat uses the compatibility facade over the same pipeline.
- Supervisor passes execution-scoped evidence to later steps to avoid duplicate retrieval and merges/deduplicates final citations.
- RAG APIs extend existing routes; upload remains `/documents/upload`, search remains `/search`, chat remains `/chat`.
- Frontend uses typed clients in `frontend/src/api.ts` and renders verification/citation/trace information.
- The UI design system lives in `src/styles.css` (dark/light tokens, glass/glow cards, 3D orbital visuals, responsive shell) with `src/theme.tsx` for persisted theme state and `components/nx.tsx` for shared primitives.
- Organization administration reads `/api/v1/admin/*`; analytics reads `/api/v1/analytics/overview`; profile/password changes use `PATCH /auth/me` and `POST /auth/change-password`. No page uses hardcoded “Unavailable” values.

## Observability and Evaluation

- Trace id per request/session; stage timings and warnings.
- Prometheus counters/histograms for queries, retrieval modes, answer modes and citations.
- Query telemetry persisted with organization/user/conversation scope.
- Evaluation: retrieval metrics, optional generation metrics from real verification, persisted reports; fixtures in `app/rag/tests/fixtures/`.

## Deliberate Non-Goals / Limitations

- No second vector database or embedding implementation.
- No fake embeddings, citations or evidence; unavailable OCR/providers/LLM raise or fall back explicitly.
- Verification is deterministic lexical grounding, not a factual guarantee.
- Live provider/Qdrant/Celery verification depends on external infrastructure and credentials.
