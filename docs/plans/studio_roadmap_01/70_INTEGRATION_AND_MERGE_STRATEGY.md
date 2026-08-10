# Integration and Merge Strategy

## Starting conditions

- Common implementation base: `9a09375700db02a64315068f008b15e43ba5f42d`.
- Current branch observed during planning: `chore/cleanup-stale-md-docs`.
- Existing user changes (`road_map.md` modified and `road_map_v2_implementation_plan.md` deleted) are not part of Roadmap 1 implementation commits unless the user separately decides so.
- This document proposes Git operations; the planning task does not create branches, worktrees, commits, pushes, or pull requests.

Before implementation, the integration owner should put the approved planning/contract documents in a dedicated coordination commit based on the required SHA or otherwise record their exact commit. Do not accidentally include the dirty roadmap files.

## Proposed branches/worktrees

| Role | Branch | Suggested worktree folder | Scope |
|---|---|---|---|
| Integration/merge train | `integration/studio-roadmap1` | sibling worktree chosen by owner | Contract commits, gate merges, certification only |
| Plan A | `refactor/studio-roadmap1-foundation` | `../WindAgent-studio-a` | S0–S3 kernel/runtime |
| Plan B | `feat/studio-roadmap1-story` | `../WindAgent-studio-b` | S4–S10 Story pipeline |
| Plan C | `feat/studio-roadmap1-product` | `../WindAgent-studio-c` | S11–S15 API/UI/certification |

All four start at the same approved bootstrap commit. Worktree paths must be resolved and checked before creation; the existing dirty worktree remains untouched. No agent uses reset/checkout to move the user’s changes.

## Commit discipline

Commits are small, single-purpose, and conventionally labeled (`refactor:`, `feat:`, `fix:`, `test:`, `docs:`, `chore:`). Each production commit includes or is immediately followed by its tests. Generated lock/schema changes are isolated so reviewers can distinguish tool output from semantic changes.

Suggested phase slices:

- A: boundary repair; domain contracts; migration; repositories; durable orchestration; worker/finalizer; provider/capability; regression manifest.
- B: artifact schemas; structured model boundary; each story stage; review/revision; lock package; runtime handlers.
- C: contract harness/test repair; V3 resources; client/state; shell; workflow screens; lock UI; release checks; certification harness/evidence.

Never combine a contract change, migration, provider behavior change, and UI adaptation into one commit. Never “resolve” conflicts by accepting all of one branch without reviewing semantics.

## Contract-first merge train

### Train 0 — Bootstrap

1. Merge one coordination commit containing frozen documents/fixtures and ownership.
2. Tag or record the commit as `CONTRACT_FREEZE_GATE` evidence.
3. Create A/B/C branches from that exact point.

### Train 1 — Definition slices

1. Integrate A’s architecture/boundary slice when live checks and regressions pass.
2. Integrate A’s v0.1 domain/port definitions at `STUDIO_DOMAIN_INTEGRATION_GATE`.
3. Rebase B/C onto the integration branch; update only consumer fixtures if the frozen shape is unchanged.
4. Integrate B’s artifact schema bundle at `STORY_ARTIFACT_CONTRACT_GATE`.
5. Rebase A/C and regenerate/check consumers in isolated commits.

This order makes A the aggregate/envelope authority and B the artifact-content authority before persistence/API/UI harden around them.

### Train 2 — Independent implementation slices

Merge reviewed commits when their local gates pass, without waiting for entire plans:

- A persistence/migration, then durable orchestration/worker/provider slices.
- B idea/bibles/outline/screenplay/review slices that consume already integrated contracts.
- C route/client/state/shell/read-only UI slices that still use clearly marked fixtures where real producers are not ready.

Integration branch does not enable the public Studio feature yet.

### Train 3 — Runtime integration

1. Merge A’s handler-registration seam and worker/recovery changes.
2. Rebase B, integrate B handlers one stage at a time with A contract/runtime tests.
3. Pass `SCREENPLAY_RUNTIME_GATE` and `LOCKED_SCREENPLAY_GATE` on the integration branch.
4. Merge A’s narrow API composition-provider handoff.
5. Rebase C, merge V3 real-service wiring and desktop production composition.
6. Pass `API_UI_INTEGRATION_GATE`.

### Train 4 — Certification

1. Freeze production code except fixes for failed gates.
2. C, as sole CI/lockfile/final-manifest owner, merges release-candidate jobs and runs the full deterministic matrix.
3. Run happy and recovery slices from a recorded integration SHA.
4. Gate fixes return to the owning plan branch as narrow commits, then re-enter the train; never patch only the evidence report.
5. After all reruns pass at a compatible SHA, publish `FINAL_CERTIFICATION_GATE` result. Promotion/PR merge remains an explicit maintainer action outside this planning task.

## Rebase and synchronization policy

- Each plan rebases on the integration branch immediately after any contract/gate merge it consumes, then runs its consumer contracts before resuming integration work.
- During a phase, plans may merge integration into their branch if project policy prefers; do not rewrite shared published history without team agreement.
- A plan does not routinely rebase merely because an unrelated plan merged internal code. Sync at named gates to limit churn.
- If a rebase touches a hotspot or generated schema/lockfile, the owning plan resolves it and obtains the affected contract owner’s review.
- Integration branch remains free of user roadmap changes and unrelated cleanup.

## High-conflict files and serialized resolution

| Hotspot | Required order | Required verification after resolution |
|---|---|---|
| `apps/api/windagent_api/composition.py` | A exposes application providers first; C consumes second | A application tests, C API dependency/route tests, no router-to-infra construction |
| `apps/api/windagent_api/main.py` | C only, one aggregator include | Full route/OpenAPI snapshot and V2 regression |
| `apps/worker/windagent_worker/composition.py` | A only; B registers through seam | Worker registry, capability, fake-guard, B handler contracts |
| `orchestrator_service.py` | A only; consumers adapt outside | Orchestrator/DAG/durable reconciliation tests |
| core package exports | A aggregate exports, then B separate Story exports | import compatibility and duplicate-model checks |
| existing screenplay module | A lock/hash authority freeze, then B content adapter | V2 screenplay plus A/B contract tests |
| event catalog | A only after B event proposal review | taxonomy and event fixture tests |
| migration head/registry | A only | clean/legacy upgrade, checksum, rollback rehearsal |
| frontend workspace manifests/lockfiles | C only, dependency batches | frozen install, package tests, Tauri build |
| `.github/workflows/ci.yaml` | C only in Train 4 | local command parity, YAML/check workflow validation, evidence upload test |

## Migration and data merge policy

- One Roadmap 1 migration chain; Plan A allocates the next actual revision after checking integration head at implementation time.
- No B/C migration file. Their schema needs enter A’s contract/migration review before A3 freezes.
- Expand/backfill/validate precedes canonical-write enablement; destructive cleanup is deferred beyond Roadmap 1.
- Migration commits include clean and representative-legacy upgrade tests, checksum/row validation, backup/restore or safe downgrade rehearsal, and exact minimum compatible application version.
- Never renumber or edit an integrated migration. Add a corrective migration if necessary.

## Evidence and generated artifacts

- Evidence is valid only when it records integration SHA, contract/schema versions, migration head, command, environment/tool versions, timestamp, result, and checksum.
- Raw logs, screenshots, videos, provider receipts, and large reports belong in CI artifact storage with retention. Git stores deterministic manifests, schemas, small reports, and fixture inputs.
- Historic reports under `artifacts/` are context, not final PASS evidence. C9 rejects mixed SHA/timestamps or reports that do not prove the named gate.
- Generated OpenAPI/TypeScript schema and lockfile changes are produced by pinned commands and reviewed as separate commits.
- Secrets, raw auth headers, private model reasoning, and sensitive provider payloads are redacted before persistence or upload.

## Regression and bisect policy

Every gate merge records the focused command set and last-green integration commit. On regression:

1. Reproduce on integration branch with the exact command/environment.
2. Find the first failing gate/commit, not merely the latest touched file.
3. Route the fix to the owning plan; use a minimal integration hotfix only when ownership and tests are explicit.
4. Rerun the failed gate and all downstream gates whose evidence depends on the changed code/schema.
5. Do not waive architecture, version, fake-path, V2, or VP3D regressions to keep schedule.

## Merge readiness checklist

A plan slice may enter integration only if:

- ownership is unambiguous and the branch contains no user-owned/unrelated changes;
- required upstream contract/gate commit is present;
- focused tests and relevant architecture/taxonomy/schema checks pass;
- migrations/generated files, if any, have their sole owner and deterministic command;
- compatibility and rollback are documented;
- consumer contract fixtures pass;
- evidence is fresh and tied to the commit;
- no hidden fake/mock/bypass or fixed sample identifier enters production composition.

The integration owner can defer a technically green commit when its contract or merge timing would destabilize another in-flight plan; this is sequencing, not a failure waiver.
