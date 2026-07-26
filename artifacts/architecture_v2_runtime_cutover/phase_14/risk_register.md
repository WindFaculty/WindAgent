# Phase 14 Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Worker reads a different DB than API (env mismatch) | Was REAL, now fixed | Total breakdown of durable runtime | WorkerContainer.bootstrap honors WINDAGENT_DATABASE_URL |
| API submits task but Worker never claims | Was REAL, now fixed | Task stuck pending forever | API create_task now enqueues via SqlWorkSubmissionAdapter |
| Terminal state never persisted by Worker | Was REAL, now fixed | API cannot read result after worker exit | poll_and_execute_tick commits completed via SqlUnitOfWork |
| Health readiness broken by wrong registry/outbox/queue checks | Was REAL, now fixed | /health/ready DOWN blocks deploy gate | Fixed registry introspection, queue table, migration_history marker |
| SQLite concurrent DDL race between processes | Low | Table creation flakiness | E2E pre-creates full schema before spawning processes |
| Outbox publisher errors (aggregate_id) | Observed as noise | Outbox events not emitted in E2E | Non-fatal (outbox NOT_REQUIRED in dev); tracked separately from durable runtime |
