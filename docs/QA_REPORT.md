# NEXUS AI QA Report

## Latest validation

- Backend: `DEBUG=false INGESTION_USE_CELERY=false STORAGE_BACKEND=local RATE_LIMIT_ENABLED=false python -m pytest -q` — **93 passed**, 1 existing Qdrant compatibility warning.
- Focused agent/intelligence tests: **7 passed** before the full-suite run.
- Frontend: `npm run type-check`, `npm run lint`, and `npm run build` — **passed**.
- OpenAPI YAML parse — **passed**.
- Alembic head — `0012_agent_approval_expiry`, singular.

## Connected intelligence coverage

- IMAP email validation/search uses real configured credentials; unavailable providers return explicit errors.
- Document extraction/comparison is organization-scoped and preserves extractor spans.
- PDF, DOCX, XLSX, and CSV report exports are generated and persisted through the storage abstraction.
- Report metadata is persisted through migration `0013_reports`, listed by organization, and shown with authenticated download controls in the agent workspace.
- Cross-source routing creates workflow plans and reports unavailable sources explicitly; no live external provider was used for this validation.

## Not live-verified in this increment

Redis/Celery duplicate delivery and worker recovery, external IMAP credentials, external database credentials, MinIO, Qdrant, SMTP delivery, and OAuth provider flows.
