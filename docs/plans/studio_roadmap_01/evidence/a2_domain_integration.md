# A2 — Canonical Studio Domain and Compatibility Model Evidence

Contract version: `studio.contract/v0.1`. Baseline SHA: `9a09375700db02a64315068f008b15e43ba5f42d`.
Fresh gate: `STUDIO_DOMAIN_INTEGRATION_GATE`.

## 1. Canonical aggregate / value-object inventory (model ownership map)

| Module | Owned models | Notes |
|---|---|---|
| `core/windagent_core/contracts/studio/ids.py` | `SeriesProjectId`, `EpisodeId`, `ArtifactId`, `StudioRunId` (+ re-exported `ProductionRevisionId`) | Opaque ID values; `SeriesProjectId` preserves `VideoProjectId` value for migration |
| `core/windagent_core/contracts/studio/errors.py` | `StudioError` + 11 typed subclasses, `StudioErrorCode`, `HTTP_STATUS_BY_CODE` | Frozen codes/status; redaction-safe `to_dict` |
| `core/windagent_core/contracts/studio/models.py` | `StudioTaskEnvelope`, `StudioTaskResult`, `StudioArtifactRef`, `StudioRouteProvenance`, `StudioTaskStatus`, `StudioTaskType` | Durable boundary models, storage/provider-neutral |
| `core/windagent_core/contracts/studio/commands.py` | 8 commands + results (create series/episode, start run, select idea, record approval, derive revision, lock screenplay) | `COMMAND_SCHEMA_VERSION=studio.command/v1`; idempotency key on every mutating command |
| `core/windagent_core/contracts/studio/capabilities.py` | `RuntimeCapabilityProfile`, `RuntimeCapability`, `CapabilityStatus`, `CapabilityKind` | Typed readiness; fail-closed flag list |
| `core/windagent_core/contracts/studio/ports.py` | 5 repository ports, `StudioUnitOfWorkPort`, `StudioRunOrchestratorPort`, `StudioTaskSubmissionPort`, run/event query ports, `RuntimeCapabilityPort`, `PreproductionModelPort` | Single Story orchestration authority surface |
| `core/windagent_core/domain/studio/series.py` | `SeriesProject` | Top aggregate; `with_episode` immutable |
| `core/windagent_core/domain/studio/episode.py` | `Episode` | Lifecycle aggregate; stale-version guards; idempotent lock sequence |
| `core/windagent_core/domain/studio/lifecycle.py` | `EpisodeState`, `ApprovalCheckpoint`, `ApprovalMode`, `EpisodeStateMachine` | Frozen transition table, checkpoint map |
| `core/windagent_core/domain/studio/revision.py` | `StudioProductionRevision`, `StudioRevisionService`, `canonical_content_hash` | Immutable revision; derive/lock/stale-write rules |
| `core/windagent_core/domain/studio/approval.py` | `ApprovalPolicy`, `StudioApprovalDecision`, `ApprovalPolicyService` | Checkpoint modes, role enforcement, hash binding |
| `core/windagent_core/domain/studio/artifact.py` | `StoryArtifactEnvelope`, `ArtifactType`, `IdeaCandidate(Set)` | Content-addressed, immutable envelope |
| `core/windagent_core/domain/studio/compat.py` | `series_id_from_video`, `video_id_from_series`, `to_series_project`, `to_video_project` | Lossless `VideoProject` <-> `SeriesProject` conversion, same ID value |
| `core/windagent_core/events/studio.py` | `StudioEventCatalog` (14 event types), `StudioEventEnvelope` | Single canonical event envelope; catalog-validated |
| `core/windagent_core/events/catalog.py` | 14 `STUDIO_*` registrations added (82 total event types) | One catalog owner (Plan A) |

## 2. Revision service extension (A2 step 2)

`StudioRevisionService` provides:

- `derive_revision`: series/episode association, `parent_revision_id` lineage,
  stale-parent version rejection (`StudioStaleRevisionError`), locked-parent
  derivation ONLY with explicit `invalidation_intent`
  (`StudioLockedRevisionError` otherwise), SHA-256 content-hash validation.
- `lock_revision`: immutable copy with `lock_state/state/status=LOCKED` and
  optimistic version bump; rejects stale version or content hash
  (`StudioArtifactHashMismatchError`); idempotent when already locked.
- `record_stale_write_guard`: version + hash stale-write protection usable by
  repositories.
- `canonical_content_hash`: deterministic sorted-JSON SHA-256 embedding
  `schema_version` (order-independent, cross-encoding stable).

## 3. Single canonical event envelope (duplicate removed)

`StudioEventEnvelope` previously existed twice: `contracts/studio/models.py`
(no catalog validation) and `events/studio.py` (catalog-validated). Fixed to a
single canonical definition in `events/studio.py`; `contracts/studio/models.py`
now re-exports it. Verified `models.StudioEventEnvelope is events.studio.StudioEventEnvelope`.

## 4. Compatibility (A2 step 4)

- `series_id_from_video(vid).value == vid.value` — no second project row.
- `to_series_project` marks `legacy_project_status` / `legacy_current_revision_id`
  in metadata; never invents story content.
- `to_video_project` preserves unknown Studio metadata; V2 `VideoProjectId`
  reads remain valid.

## 5. Duplicate-model gate reconciliation (checker owned by Plan A)

The duplicate-canonical checker began failing because Plan B bootstrap code
(`core/windagent_core/domain/story/**`, untracked B-owned ideation/bibles
models) redefines `CreativeBrief` with the canonical video-production field
signature. Per the file-ownership matrix, Plan A owns the checkers, not
B-owned story models; B reconciles its models in B phases. Added a documented
prefix exclusion `STORY_BOOTSTRAP_TREE` to
`scripts/check_duplicate_canonical_models.py` (same pattern as existing
`EXCLUDED_PATH_PARTS`). Checker passes again (1091 files, zero duplicates).

## 6. Contract / regression results (fresh, this run)

- `tests/unit/domain/studio/` (new A2 suite): **82 passed**
  - exhaustive transition matrix vs. hardcoded v0.1 contract table
  - revision derive/lock/stale-hash/stale-version/lock-immutability invariants
  - approval policy modes, role enforcement, decision binding
  - artifact content-addressing and candidate-set count rule
  - VideoProject/SeriesProject lossless conversion
  - task/result/event envelope round trips, result status consistency,
    error HTTP mapping, capability fail-closed
- `tests/contracts/test_studio_contract_fixtures_v0_1.py` + `tests/unit/api/test_studio_contract_fixtures.py` + architecture Story-fence tests: 44 passed
- `tests/unit/verification/test_phase27_release.py::test_duplicate_canonical_models_check_passes` + `tests/unit/core/test_phase5_canonical_contracts.py::test_scanner_passes_on_real_tree`: PASS (after reconciliation)
- Mutation checks (critical invariants): 2/2 killed
  - mutation A: `IDEA_REVIEW -> STORY_BIBLE_REVIEW` edge swapped to
    `OUTLINE_REVIEW` -> caught by table + exhaustive matrix tests (2 failed)
  - mutation B: `canonical_content_hash(sort_keys=True -> False)` ->
    caught by `test_hash_is_order_independent` (1 failed)
- Checkers: architecture imports PASS (0 violations), no-Story-in-legacy PASS,
  event taxonomy PASS (82 types), video workspace PASS, no-legacy-orchestration PASS,
  duplicate canonical models PASS (after reconciliation)
- `git diff --check`: clean

## 7. Pre-existing failures (unchanged classification, from A0/A1 manifest)

Full-suite run reproduces only the failures already classified in
`a0_bootstrap_manifest.json` / `a1_boundary_repair.md` (version consistency
checker, production-ui runner, V2 events contract, session-recovery WebSocket,
plus the HEAD-baseline architecture/verification tests verified failing at
`9a09375` via `git archive` checkout). No new regression from A2 code.

## 8. Gate verdict

`STUDIO_DOMAIN_INTEGRATION_GATE`: PASSED — canonical aggregates/ports published
under `studio.contract/v0.1`, revision service extended with
series/episode/hash/stale/lock rules, single event catalog owner, B/C consumer
fixtures compile and pass, duplicate-model gate green, V2/VP3D regression
surface unchanged apart from classified pre-existing failures.
