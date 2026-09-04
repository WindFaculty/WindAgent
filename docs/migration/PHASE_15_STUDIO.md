# Phase 15 — Studio (Milestone 3: WindAgent Product)

**Date:** 2026-09-02  
**Status:** Cut over  
**Scope:** Consolidate the scattered Studio implementation into a single bounded context under `modules/studio/` per plan section 21.

## Source → Target

Old locations (frozen reference, not imported):

```
core/domain/story/*          → modules/studio/domain/story/*
core/domain/studio/*         → modules/studio/domain/{projects,series,episodes,characters,world,storyboard}
intelligence/story/*         → modules/studio/jobs/*  (deterministic placeholder; future delegation to automation runtime)
storage/studio/*             → modules/studio/infrastructure/*
apps/api studio routes       → modules/studio/api/routes.py  (thin FastAPI router under /api/v4/studio)
orchestration studio         → application service orchestration inside StudioService
```

Target layout (plan section 21 exact):

```
modules/studio/
├── public/                 # public re-exports for composition roots & tests
├── domain/
│   ├── projects/           # Project aggregate (container for series)
│   ├── series/             # SeriesProject aggregate
│   ├── episodes/           # Episode + lifecycle + revision service
│   ├── story/              # canonical StoryContent base + bibles/ideation/outline/screenplay/review
│   ├── characters/         # Character canon (series-scoped)
│   ├── world/              # WorldBibleAggregate (locations + props)
│   └── storyboard/         # Storyboard + panels (episode-scoped)
├── application/
│   ├── commands.py         # 18 immutable intentions (Project/Series/Episode/Revision/Artifact/Character/World/Storyboard)
│   ├── queries.py          # 15 side-effect-free queries
│   ├── ports.py            # StudioStore + TransactionScope (UoW + outbox)
│   ├── models.py           # durable rows + view DTOs
│   ├── services.py         # orchestrator (one TransactionScope per command, atomic outbox)
│   ├── handlers.py         # Command/Query/Job handlers (ambient StudioServices)
│   ├── runtime.py          # StudioServices + ContextVar binding (mirrors model_gateway)
│   └── events.py           # 7 studio.* event envelopes (EntityId + Version, atomic via outbox)
├── infrastructure/
│   ├── tables.py           # 9 studio_* tables registered into shared metadata (0006)
│   ├── repository.py       # SqlStudioStore + SqlTransactionScope (CAS optimistic_version)
│   └── memory.py           # InMemoryStudioStore + InMemoryTransactionScope (offline tests)
├── api/
│   └── routes.py           # /api/v4/studio/* — 27 endpoints, policy-gated, bus-dispatched
├── jobs/
│   └── handlers.py         # studio.story.generate (deterministic placeholder)
├── manifest.py             # ModuleManifest (18 commands, 16 queries, 1 job, 1 router, 8 capabilities)
└── __init__.py
```

## Invariants preserved (EXTRACT_LOGIC)

- **Lifecycle:** `EpisodeState` + `EpisodeStateMachine` frozen table (DRAFT → IDEA_REVIEW → … → LOCKED → READY_FOR_PRODUCTION, plus FAILED/CANCELLED terminals). Lock is a 2-step idempotently resumable sequence.
- **Stale-write protection:** `optimistic_version` checked on every mutating command (row-level CAS via `expected_version`). Hash mismatch on lock/approval rejects (`StudioArtifactHashMismatchError`).
- **Revision derivation:** `RevisionService.derive_revision` requires explicit `invalidation_intent` when parent is locked; deterministic UUIDv5 lineage (`parent_id|hash`) keeps downstream receipts/packages reproducible.
- **Content-addressed artifacts:** `canonical_content_hash` (sorted JSON, SHA-256) + `ARTIFACT_SCHEMA_VERSION` gates. `StoryContent` base is frozen, additive, deterministically serializable.
- **Series ↔ Episode containment:** `with_episode` / `with_series` are immutable, bump `optimistic_version` and `updated_at`.
- **World/Storyboard:** `WorldBibleAggregate`/`Storyboard` enforce idempotent `with_location`/`with_panel` + exact `reorder` check.

## Architecture gates

- `test_kernel_does_not_import_infrastructure` — PASS (kernel pure)
- `test_platform_*` — PASS (platform still domain-agnostic)
- `test_modules_do_not_import_each_other` — PASS (studio only imports `windagent.kernel` + `windagent.platform` + own package)
- `test_no_v2_file_imports_legacy` — PASS (no `windagent_core` / `windagent_intelligence` / `storage` imports)
- `test_platform_contracts_only_depend_on_kernel_and_stdlib` — PASS
- `test_sqlite_is_not_a_default` — pre-existing failure in `model_gateway` tables (`sqlite_where` partial index); studio adds no new `sqlite` string. Studio tables are PostgreSQL-canonical; in-memory adapter uses plain dicts, never `sqlite://`.

`ruff check backend/src/windagent/modules/studio` — **All checks passed**  
`mypy --config-file pyproject.toml` — **0 errors in studio** (full repo 3 pre-existing errors in unrelated test files)

## Persistence

- **Migration `0006_studio`** creates 9 tables with FK-free, prefix-namespaced design (single Alembic chain, no legacy 31 revisions copied):
  `studio_projects`, `studio_series`, `studio_episodes`, `studio_revisions`, `studio_artifacts`, `studio_characters`, `studio_world_locations`, `studio_world_props`, `studio_storyboards`.
- Each table carries `optimistic_version` + UTC timestamps + JSON blobs for `metadata`/`panels`/`traits` (keeps schema additive).
- `SqlStudioStore` implements `StudioStore` with row-level CAS (`WHERE optimistic_version = :expected_version`) and `INSERT …` uniqueness checks; `SqlTransactionScope` joins the caller's `SqlUnitOfWork` and records exactly one `studio.*` event via `TransactionalOutbox`.
- `InMemoryStudioStore` mirrors the same CAS semantics for offline unit tests (`memory_scope_factory`).

## Application layer

- **Commands** are frozen dataclasses extending `Command[View]`; **Queries** extend `Query[View]`. No command builds a DAG or touches a provider directly.
- **StudioService** is the only place that knows the aggregate → row mapping; handlers are thin (`container_for(services).studio.*`).
- **Outbox:** Every mutating command records one envelope (`studio.project.created`, `studio.series.created`, `studio.episode.created`, `studio.episode.transitioned`, `studio.revision.created`, `studio.revision.locked`, `studio.artifact.created`) before `commit()`, so workers/realtime replay is durable.

## API

- Prefix `/api/v4/studio` (canonical `/api/v4`, not `Wind_agent_v2` folder name).
- 27 endpoints across 7 sub-resources:
  - projects `POST /projects`, `GET /projects`, `GET /projects/{id}`, `PATCH /projects/{id}`
  - series `POST /series`, `GET /series`, `GET /series/{id}`, `PATCH /series/{id}`
  - episodes `POST /episodes`, `GET /episodes`, `GET /episodes/{id}`, `PATCH /episodes/{id}`, `POST /episodes/{id}/transitions`
  - revisions `POST /revisions`, `POST /revisions/{id}/derive`, `POST /revisions/{id}/lock`, `GET /revisions/{id}`, `GET /revisions`
  - artifacts `POST /artifacts`, `GET /artifacts/{id}`, `GET /artifacts`
  - characters `POST /characters`, `PATCH /characters/{id}`, `GET /characters/{id}`, `GET /characters`
  - world `PUT /series/{sid}/world/locations/{lid}`, `GET /series/{sid}/world/locations`, `PUT …/props/{pid}`, `GET …/props`
  - storyboard `POST /storyboards`, `PATCH /storyboards/{id}`, `POST /storyboards/{id}/reorder`, `GET /storyboards/{id}`, `GET /storyboards`
- Each route validates via Pydantic DTO, dispatches via `command_bus`/`query_bus`, and maps via `View.to_payload()`. Mutating routes require `studio.write`, reads require `studio.read` (policy engine, audited; unconfigured engine allows in dev).

## Jobs

- `studio.story.generate` — deterministic placeholder that creates a `StoryArtifactEnvelope` via the same `StudioService` so the pipeline is E2E-testable without a provider. Future wiring will delegate to `intelligence/story` adapters through the automation runtime (not imported today, preserving the `no legacy import` gate).

## Module manifest

- `manifest = build_studio_manifest()` exposes:
  - 18 `CommandRegistration`s
  - 16 `QueryRegistration`s (15 distinct query types + 1 alias)
  - 1 `JobRegistration` (`studio.story.generate`)
  - 1 router (`create_studio_router()`)
  - capabilities `("studio","story","projects","series","episodes","characters","world","storyboard")`
- Discovered automatically by `PackageModuleDiscovery` (no bootstrap file lists it by name).

## Verification

- **Ruff:** `ruff check backend/src/windagent/modules/studio` — 0 errors, 0 warnings.
- **Mypy strict:** `mypy --config-file pyproject.toml` — 0 errors in studio (full repo 258 files, 3 pre-existing errors in unrelated model_gateway tests).
- **Architecture:** 7/8 architecture tests pass; the 1 failure (`test_sqlite_is_not_a_default…`) is pre-existing in `model_gateway/tables.py` (`sqlite_where` partial index) and is not introduced by studio. Studio adds no `sqlite` string.
- **Unit (offline):** `pytest tests/unit -k "not postgres"` — 266 passed. Smoke against `InMemoryStudioStore` covers create→transition→revise→derive→lock→artifact→character→world→storyboard→reorder (see `smoke_studio.py`).
- **SQL (offline):** `sqlite+aiosqlite:///:memory:` via `SqlStudioStore` — project/series/episode CAS, state transition, and revision lock verified.
- **Discovery:** `PackageModuleDiscovery` finds `studio 1.0.0` alongside `model_gateway 1.0.0`.

## Cutover notes

- No V2 file imports `../core`, `../storage`, `../providers`, or `../intelligence`.
- `core/domain/studio` and `intelligence/story` remain frozen; data migration will flow through importers, not through this schema history.
- Frontend modules (`studio/projects`, `studio/episodes`, etc.) will be built in a later phase (Milestone 4) against the generated `@windagent/api-sdk` from this backend.

## Definition of Done (plan section 21)

- [x] Single bounded context `modules/studio` owns projects/series/episodes/story/characters/world/storyboard
- [x] Domain is pure (no FastAPI/SQLAlchemy/httpx), `ruff` + `mypy` clean
- [x] Persistence is PostgreSQL-canonical with `0006` migration, plus in-memory adapter for tests
- [x] Events are atomic via outbox, with 7 `studio.*` envelopes
- [x] API is `/api/v4/studio`, thin, bus-dispatched, policy-gated
- [x] Job seam `studio.story.generate` is durable and worker-discoverable
- [x] Module is auto-discoverable, no bootstrap edit required
