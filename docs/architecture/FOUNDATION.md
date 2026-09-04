# WindAgent V2 foundation layout (Phase 1)

Dependency direction is one-way and CI-enforced
(`tests/architecture/test_import_boundaries.py`):

```text
apps/*  (api, worker, scheduler, cli)
   │
   ▼
modules/*  ── may import ──►  platform/*  ── may import ──►  kernel/*
   │
   └── modules NEVER import other modules;
       nothing in V2 imports the frozen old WindAgent repository.
```

## Boundaries enforced today

| Rule (plan §35)                                   | Enforcement |
| ------------------------------------------------- | ----------- |
| V2 files must not import legacy packages          | architecture test + CI |
| `kernel` imports no FastAPI/SQLAlchemy/httpx/pydantic, no platform/modules | architecture test |
| `platform` imports no feature modules or app packages | architecture test |
| `modules/x` imports no `modules/y`                | architecture test |
| SQLite is not a default anywhere in backend source | architecture test + Settings startup error |
| persistence adapters import only the DB toolchain | architecture test (ADR-0002) |
| Alembic refuses `sqlite://` outside tests         | contract test |
| API ships health/readiness only until Phase 8     | app factory scope |

## Where each later phase plugs in

- Phase 2 Kernel: fills `kernel/{ids,errors,events,result,time,types}`.
- Phase 3 Platform contracts: fills `platform/{commands,queries,modules,jobs,
  events,artifacts,security,observability}`.
- Phase 4 Module runtime: `ModuleManifest`, package/static discovery, full-set
  validation, and ordered loader registration in `platform/modules`.
- Phase 5 Persistence (done): `platform/persistence` owns the engine, the
  SQL unit of work, transaction scopes, health probes and the shared
  SQLAlchemy metadata; Alembic autogenerate is live via
  `metadata.target_metadata`, anchored at the clean `0001_v2_foundation`.
- Phase 6 Events/Outbox (done): `platform/events` owns the event registry,
  in-process dispatch, the transactional outbox
  (`platform_events` + `platform_outbox`, migration `0002`) and the
  claim→deliver→finalize publisher loop.
- Phase 7 Jobs, worker: `platform/jobs` runtime, `apps/worker` engine on
  top of the outbox publisher loop.
- Phase 8 API: routers in `apps/api` calling Command/Query buses only.

PostgreSQL is canonical everywhere (`compose.yaml` provides a local
PostgreSQL 16 on port 55433 to avoid the old repo's 55432 dev cluster).
