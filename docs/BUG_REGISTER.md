# NEXUS AI Bug Register

Last updated: 2026-11-21

| ID | Severity | Status | Description | Next action |
|---|---|---|---|---|
| BUG-001 | Medium | Open | Live Redis/Celery duplicate-delivery and worker-recovery behavior is not verified in this environment. | Run compose worker tests with Redis and inspect persisted transitions. |
| BUG-002 | Medium | Open | Approval-bound SMTP delivery and OAuth/IMAP paths depend on external credentials; not live-verified. | Configure real providers and execute delivery/retry tests. |
| BUG-003 | Low | Open | Document entity/date extraction uses deterministic heuristics; semantic clause comparison is limited. | Add evidence-grounded LLM extraction with citation validation. |
| BUG-004 | Low | Resolved | Report metadata migration, organization-scoped listing, and agent workspace download controls are implemented. | Richer report detail/failure history if required. |
| BUG-005 | High | Resolved | Memory vector backend created a new instance per `get_vector_index` call, so ingested points disappeared from later queries and sync appeared out of date. | Fixed with a process-wide dimension-keyed memory index. Tests added for sync/re-index. |
| BUG-006 | Medium | Resolved | Qdrant document deletion returned an operation id instead of the number of deleted points. | Count before delete and return the real count. |
| BUG-007 | High | Resolved | Semantic hit attachment bound string UUIDs to UUID SQL columns and could return 503 or stale evidence. | Parse UUIDs; drop hits without a live organization-owned document row. |
| BUG-008 | Medium | Resolved | Verification marked numeric contradictions as supported when terms overlapped. | Numeric conflict detection now yields `conflicting_evidence` with disclaimer. |
| BUG-009 | Medium | Resolved | Streaming `rag_end` citations omitted text, risking citation rendering failures. | Final SSE payload includes citation text. |
| BUG-010 | Medium | Resolved | Supervisor-reused evidence was not re-authorized before generation. | `answer_with_evidence` revalidates evidence against live rows. |
| BUG-011 | Medium | Open | Migration `0014_rag_metadata` is authored and head-checked but not applied to live PostgreSQL. | Apply in staging and verify upgrade/downgrade on PostgreSQL 15. |
| BUG-012 | Medium | Open | Live Qdrant, real embeddings and live LLM generation are not verified; tests use memory vectors and hashing embeddings/extractive fallback. | Configure providers/Qdrant and run a live smoke/evaluation. |
| BUG-013 | Low | Open | Postgres tsvector lexical backend not implemented; BM25 runs in Python over bounded chunk rows. | Add GIN/tsvector path for large corpora. |
| BUG-014 | Low | Open | OCR for scanned PDFs is unavailable by design; explicit error is raised. | Add optional OCR provider with provenance. |
| BUG-015 | Medium | Resolved | Conversation memory lookup passed a string conversation id into a UUID column and lacked ownership checks. | Parse UUIDs and verify conversation organization/user before reading prior citations. |
| BUG-016 | Medium | Resolved | Dashboard, analytics, administration and monitoring displayed hardcoded “Unavailable” placeholders despite persisted backend data. | Added organization admin/analytics read endpoints and wired every redesigned page to live API state with explicit empty/error fallbacks. |
| BUG-017 | Medium | Resolved | Report specialists wrote markdown artifacts to storage but the supervisor merge dropped `format`/`storage_key`, so no `Report` metadata existed and artifacts were not listable or downloadable. | Preserve artifact fields during merge, create/update organization-scoped `Report` rows, and add metadata-id download/delete routes. Covered by `tests/test_capabilities_reports.py`. |
| BUG-018 | Medium | Resolved | Connector creation templates used config keys the backend does not accept (e.g. website `url`, GitHub `owner/repo`, SQL host/table) and instructed users to put SQL passwords in plaintext config. | Templates now match connector validators; SQL passwords are injected from encrypted `credentials`. |
| BUG-019 | High | Resolved | Cancelling an execution left its pending approval actionable; a later approval could still dispatch an email or high-risk action. | Cancellation now marks linked pending approvals `cancelled`, and approval decisions reject already-final executions. |
