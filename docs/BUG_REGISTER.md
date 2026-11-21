# NEXUS AI Bug Register

| ID | Severity | Status | Description | Next action |
|---|---|---|---|---|
| BUG-001 | Medium | Open | Live Redis/Celery duplicate-delivery and worker-recovery behavior is not verified in this environment. | Run compose worker tests with Redis and inspect persisted transitions. |
| BUG-002 | Medium | Partial | Approval-bound SMTP delivery path is implemented, but provider credentials and OAuth flows are not live-verified. | Configure a real provider and execute delivery/retry tests. |
| BUG-003 | Low | Open | Document entity/date extraction uses deterministic heuristics and does not yet provide full semantic clause comparison. | Add evidence-grounded LLM extraction with citation validation. |
| BUG-004 | Low | Resolved | Report metadata migration, organization-scoped listing, and agent workspace download controls are implemented. | Add richer report details and failure-state history if required. |
