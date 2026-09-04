# WindAgent V2 — migration status board

One row per capability group. A group is only marked done when every column
to its left is green (plan section 33). No "feels almost migrated".

| Group           | Design | Rewrite | Unit | Parity | Integration | Cutover |
| :-------------- | -----: | ------: | ---: | -----: | ----------: | ------: |
| Phase 0 freeze  |      ✅ |      n/a |   n/a |    n/a |         n/a |      ✅ |
| Foundation (P1) |      ✅ |      ✅ |    ✅ |    n/a |         n/a |      ✅ |
| Kernel (P2)     |      ✅ |      ✅ |    ✅ |    n/a |         n/a |      ✅ |
| Platform (P3)   |      ✅ |      ✅ |    ✅ |    n/a |         n/a |      ✅ |
| Module runtime (P4) |    ✅ |      ✅ |    ✅ |    n/a |         n/a |      ✅ |
| Persistence (P5)|      ✅ |      ✅ |    ✅ |    n/a |          ✅ |      ✅ |
| Events/Outbox   |      ✅ |      ✅ |    ✅ |    n/a |          ✅ |      ✅ |
| Job runtime (P7)|      ✅ |      ✅ |    ✅ |     ✅ |          ✅ |      ✅ |
| API (P8)        |      ✅ |      ✅ |    ✅ |    n/a |          ✅ |      ✅ |
| Security (P9)   |      ✅ |      ✅ |    ✅ |    n/a |          ✅ |      ✅ |
| Observability (P10) |   ✅ |      ✅ |   ✅ |    n/a |          ✅ |      ✅ |
| Model Gateway   |      ✅ |      ✅ |    ✅ |     ✅ |          ✅ |      ✅ |
| Automation (P12) |      ✅ |      ✅ |    ✅ |     ✅ |          ✅ |      ✅ |
| Agent Runtime (P13) |      ✅ |      ✅ |    ✅ |     ✅ |          ✅ |      ✅ |
| Context + Memory (P14) |  ✅ |      ✅ |    ✅ |     ✅ |          ✅ |      ✅ |
| Studio (P15)    |      ✅ |      ✅ |    ✅ |     ✅ |          ✅ |      ✅ |
| Production (P16) |      ✅ |      ✅ |    ✅ |     ✅ |          ✅ |      ✅ |
| Live Record (P17) |      ✅ |      ✅ |    ✅ |     ✅ |          ✅ |      ✅ |
| Workspace (M3)  |      ✅ |      ✅ |    ✅ |    n/a |          ✅ |      ✅ |
| Quality (P18)   |      ✅ |      ✅ |    ✅ |     ✅ |          ✅ |      ✅ |
| Frontend (M4)   |      ✅ |      ✅ |    ✅ |     ✅ |          ✅ |      ✅ |
| Desktop (M4)    |      ✅ |      ✅ |    ✅ |     ✅ |          ✅ |      ✅ |
| Migration & E2E (M4) |  ✅ |      ✅ |    ✅ |     ✅ |          ✅ |      ✅ |

---

## Milestone Milestones Summary

- **Milestone 1 (Foundation & Kernel)**: 100% COMPLETE (Phases 1–10).
- **Milestone 2 (Core Intelligence & Automation)**: 100% COMPLETE (Phases 11–14).
- **Milestone 3 (Product Capabilities & Production Engines)**: 100% COMPLETE (Phases 15–18, Workspace).
- **Milestone 4 (User Platform, Desktop, Migration & Production Cutover)**: 100% COMPLETE.

---

## Detailed Milestone Records

PostgreSQL 16 Docker certification passed locally on 2026-09-02: all integration tests are green. The full suite includes the complete HTTP → PostgreSQL → worker → outbox → WebSocket milestone, concurrent `SKIP LOCKED` claims, persistence helpers, migrations, and event/outbox recovery. Phases 5–8 are cut over.

Phase 8 (2026-09-02): API foundation cut over — `/api/v4` canonical prefix, Command/QueryBus dispatch discipline, canonical error envelope, request identity middleware, DB-backed readiness.

Phase 9 (2026-09-02): Security foundation cut over — HMAC bearer authentication middleware, fail-closed policy engine with durable outbox audit, secret stores, sliding-window rate limiting (ADR-0005).

Phase 10 (2026-09-02): Observability foundation cut over — W3C trace propagation, task-local causal context, structured JSON logs with redaction, bounded process metrics and `/metrics`, HTTP/command/query/worker spans, contextual audit, and durable job trace/actor fields (`0004`).

Phase 11 (2026-09-02): Model Gateway cut over — single routing authority, provider registry/credential write-only store, endpoint & binding catalog, 10 routing-rule families, 8 provider adapters (openai-compatible primary), route-lock CAS with fallback, circuit breaker & quota state.

Phase 12 (2026-09-02): Automation / Tool Runtime cut over — canonical Tool Runtime, 7 runtime adapters (in_process, subprocess, browser, mcp, desktop, container, remote), path-sandbox + destructive-guard policy semantics, and atomic outbox + CAS.

Phase 13 (2026-09-02): Agent Runtime cut over — DAG validation, stale-write CAS, budget inheritance, checkpoint hash, retry classifier/backoff, and delegation parent-child hierarchy.

Phase 14 (2026-09-02): Context Assembly Engine & Memory cut over — 14 source types, SensitivityLevel, 9-stage ContextPipeline, token budgeting, prompt-injection defense, 8 extended memory scopes, secret scanning, provenance verification, and TTL auto-eviction.

Phase Workspace (2026-09-02): Workspace Management & Sandboxing cut over — multi-tenant isolation, member RBAC, resource quota limits, distributed resource locking with monotonic fencing tokens and TTL, immutable state snapshots, and strict WorkspaceSandbox containment.

Phase 15 (2026-09-02): Studio cut over — projects/series/episodes/story/characters/world/storyboard with frozen lifecycle + stale-write + lock semantics.

Phase 16 (2026-09-02): Production cut over — video/assets/audio/code_video/rendering/postproduction with frozen asset lifecycle + revision lock/invalidation + ACEScg colorspace + multi-track EDL assembly.

Phase 17 (2026-09-02): Live Record cut over — plans/sessions/takes/cues/director/preparation with frozen plan lifecycle + payload-bundles artifact isolation + hash-gated playback + privacy-scan.

Phase 18 (2026-09-02): Quality, Evaluations, Verification & Regression cut over — 11 canonical evaluation dimensions, strict fail-closed evidence invariant, 9 automated rubric evaluators, 7 verification gates with ExecutionEvidence, and regression detection.

Phase Milestone 4 (2026-09-02): User Platform, Desktop, Migration & Production Cutover —
1. Modern Frontend monorepo (`@windagent/api-sdk`, `@windagent/ui`, `@windagent/realtime`, `@windagent/app`) providing end-to-end views for Workspace, Studio, Agent System (with DAG inspector), Model Gateway, Automation, Production, Live Record, Quality, and Operations.
2. Desktop platform (`apps/desktop`) with `DesktopSupervisor` daemon and `NativeRecordingAdapter` (`recorder_*` IPC, tokenized paths, fail-closed WGC/NVENC probe).
3. Migration & Importers (`migration/`) with full data transformers and parity test suites.
4. E2E integration test suites (`tests/e2e/`) validating all 9 bounded contexts and the unified cross-module journey.
5. Production deployment setup (`deploy/docker/`, `compose.prod.yaml`, `configs/production.yaml`, `scripts/healthcheck.py`, `scripts/backup_db.py`).
6. Old-system retirement & cutover certification completed (ADR-0014, `OLD_SYSTEM_RETIREMENT.md`, `PHASE_MILESTONE_4.md`).

**WindAgent V2 Clean-Room Reimplementation is 100% COMPLETE.**
