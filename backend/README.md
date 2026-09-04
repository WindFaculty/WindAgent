# WindAgent V2 backend package

Holds the three V2 layers as one installable distribution (`windagent`):

```text
src/windagent/
├── kernel/     # Phase 2 — IDs, errors/results, events, time, money, versions
├── platform/   # Phase 3+ — domain-agnostic contracts and implementations
└── modules/    # Phase 11+ — bounded contexts (studio, production, ...)
```

Rules (enforced by `tests/architecture/`):

- `kernel` may not import FastAPI, SQLAlchemy, Alembic, httpx, `platform`,
  `modules` or any `windagent_*` application package.
- `platform` is domain-agnostic: no feature vocabulary.
- `platform.observability` stays vendor-neutral: W3C context, telemetry
  contracts, structured logging, and bounded metrics have no SDK dependency.
- Only PostgreSQL is canonical for anything that persists; SQLite is allowed
  in isolated unit tests only.
