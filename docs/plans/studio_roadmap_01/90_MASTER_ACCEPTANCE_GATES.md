# Master Acceptance Gates

## Interpretation

This file separates two different outcomes:

- **Planning readiness:** whether Roadmap 1 has been audited and decomposed into exactly three independently executable, parallel-safe plans.
- **Implementation acceptance:** whether future Plan A/B/C branches have built and proven the product.

The planning package may be ready while every implementation gate is still pending. No gate below is claimed passed merely because its test/evidence requirement has been documented.

## Evidence standard for every implementation gate

Each gate result must identify:

```text
gate_id, result, integration_sha,
contract_version, artifact_schema_version, migration_head,
command_or_scenario, started_at, finished_at,
environment/tool versions, evidence URIs, checksums,
known warnings, owner, reviewer
```

Allowed results are `PASS`, `FAIL`, or `BLOCKED`. `BLOCKED` names the missing external prerequisite and cannot be converted to `PASS` with a fake. Raw logs belong in CI artifact storage; deterministic manifests/small reports may be committed. Evidence from another SHA or historic audit is invalid unless the gate explicitly tests an unchanged artifact and proves its checksum.

## Master gate matrix

| Order | Gate | Owner(s) | Entry | Pass criteria | Required evidence | Failure routes to |
|---:|---|---|---|---|---|---|
| 0 | `PARALLEL_BOOTSTRAP_GATE` | A+B+C+integration | Required baseline | v0.1 names/schemas/ownership/branches/baselines approved; no `NEEDS_DECISION` | Contract fixtures, owner acknowledgments, baseline manifest, clean doc/fixture checks | Bootstrap review |
| 1 | `STUDIO_ARCHITECTURE_GATE` | A | Gate 0 | Zero live architecture violations; no Story edge to legacy engines; V2/VP3D preserved | Graph/checker before/after, focused tests | A1 |
| 2 | `STUDIO_DOMAIN_INTEGRATION_GATE` | A; B/C consumers | Gate 1 | Aggregates/states/approvals/revisions/ports v0.1 compile and invariants pass | Domain/property/serialization tests, B/C consumer report | A2/contract review |
| 3 | `STORY_ARTIFACT_CONTRACT_GATE` | B; A/C consumers | Gates 0/2 fixtures | All artifact schemas/versions/validators/golden+invalid fixtures round-trip Python/TS | Schema checksums, fixture reports, duplicate-model check | B1/contract review |
| 4 | `STUDIO_PERSISTENCE_GATE` | A | Gate 2 | Clean+legacy migration, backfill, repository/UoW/outbox, rollback rehearsal pass | Migration checksums, row/hash reports, repository tests | A3 |
| 5 | `DURABLE_ORCHESTRATION_GATE` | A | Gates 2/4 | Orchestrator-created DAG durably submits/reconciles; restart/approval/retry/cancel deterministic | Run/node/task correlation, restart/failure tests | A4 |
| 6 | `STRUCTURED_MODEL_GATE` | B | Gate 3 | Every canonical model path has prompt/schema/version/hash, bounded repair, no tolerant free-text authority | Prompt manifest, invalid corpus, parser/checker tests | B2 |
| 7 | `IDEA_GATE` | B+A command | Gates 5/6 contract | 3–5 valid distinct candidates, scoring, selection/approval hash binding | Candidate/score fixtures, durable task/selection traces | B3/A approval |
| 8 | `STORY_BIBLE_GATE` | B | Gate 7 | Story/World/Character artifacts are mutually consistent and approved per policy | Cross-validation, approval wait/resume, provenance | B4 |
| 9 | `OUTLINE_GATE` | B | Gate 8 | Beats/outline trace canon and fit 180–300 seconds | Timing formula/report, causal/ref tests | B5 |
| 10 | `STORY_WORKER_GATE` | A+B | Gates 4/5/6 | Real SQL queue + independent worker executes a B contract handler with lease/fence/finalizer/reconcile/restart | Process/task/lease/artifact/outbox/event traces | A5/B handler |
| 11 | `REAL_MODEL_RUNTIME_GATE` | A+B | Gate 10 + real environment | Handler invokes configured real model through route lock/coordinator; provenance complete; fake/mock fails closed | Capability profile, redacted route receipt, real smoke | A6/environment |
| 12 | `SCREENPLAY_DRAFT_GATE` | B | Gates 9/11 | Structured screenplay validates, renders deterministically, fits duration, traces canon/beats | Draft/hash/schema/validation/duration reports | B6 |
| 13 | `STORY_REVIEW_GATE` | B | Gate 12 | Explainable review and immutable bounded revision converge or stop deterministically | Findings/rubric/diff/iteration traces | B7 |
| 14 | `SCREENPLAY_RUNTIME_GATE` | A+B | Gates 10–13 | Generation->review->revision handlers run durably with persisted immutable artifacts and recovery | Full run/node/task/artifact lineage | A5/A6/B6–B9 |
| 15 | `LOCKED_SCREENPLAY_GATE` | A+B | Gates 13/14 | Current approved hash locks atomically; receipt/package/lineage valid; edits derive new revision; ready event/state correct | Approval/lock receipt, concurrency/immutability tests | A2/A3/B8 |
| 16 | `STUDIO_API_GATE` | C+A | Gates 2/5 and applicable schemas | V3 resources/errors/idempotency/restart work through A services; V2 regression green | OpenAPI checksum, endpoint/error/idempotency/V2 tests | C1/A app service |
| 17 | `STUDIO_CLIENT_STATE_GATE` | C | Gates 3/16 | Generated contracts/client/state pass; no production fake/sample fallback | TS drift/client/state tests, bundle/fixed-ID scan | C0/C2 |
| 18 | `STUDIO_DESKTOP_SHELL_GATE` | C | Gate 17 | Tauri loads route-driven real Series/Episode state; accessible empty/error/recovery states | Tauri tests/build, route/accessibility/fake scan | C3 |
| 19 | `STORY_UI_GATE` | C+B | Gates 8/9/17/18 | UI observes real run and reaches approved outline with selection/approval/conflict/restart behavior | API/UI traces, interaction/accessibility tests | C4/B artifacts |
| 20 | `API_UI_INTEGRATION_GATE` | C+A+B | Gates 14–19 | Tauri drives real API through screenplay/review/revision/approval/lock; server receipt/state authoritative | Correlated UI/API/run/artifact evidence | C5 or first upstream boundary |
| 21 | `PLAN_A_HANDOFF_GATE` | A | Gates 1–5,10–11,15 | Full A regressions/contracts/migration/recovery/provider/V2/VP3D green | A manifest and fresh suite results | A phase owner |
| 22 | `PLAN_B_HANDOFF_GATE` | B | Gates 3,6–9,12–15 | Full B schemas/stages/handlers/contracts/quality green | B manifests and fresh suite results | B phase owner |
| 23 | `RELEASE_CANDIDATE_GATE` | C/integration | Gates 20–22 | Full API/frontend/Tauri/security/version/architecture/V2/VP3D matrix green; real-only composition | CI/build/checker/security/bundle manifest | C6 or introducing plan |
| 24 | `REAL_VERTICAL_SLICE_GATE` | C integration; A/B support | Gate 23 + real dependencies | Mandatory rabbit/kite happy path crosses every real hop and produces reviewed, revised, approved, locked package | Happy-path evidence bundle below | First broken hop owner |
| 25 | `RECOVERY_VERTICAL_SLICE_GATE` | C integration; A/B support | Gate 23 + injectable environment | Kill/restart, fence, duplicate/idempotency, reconnect/conflict, fail-closed provider behavior recover without manual DB repair | Recovery evidence bundle below | First broken hop owner |
| 26 | `FINAL_CERTIFICATION_GATE` | Integration owner | Gates 24/25 | All mandatory gates pass on compatible versions; evidence one-SHA/fresh/redacted; no unclassified regression | Master manifest and review sign-off | Earliest invalid/failed gate |

## Mandatory happy-path scenario

The real vertical slice is not optional and may not be replaced by service-level tests.

### Input

- Language: Vietnamese.
- Audience: children ages 5–8.
- Target duration: 3–5 minutes (180–300 seconds).
- Creative premise: a rabbit and a kite.
- Approval policy: chosen at preflight but must exercise all configured checkpoints; at least one checkpoint requires an explicit public decision.
- Review policy: configured so that at least one genuine finding leads to one immutable screenplay revision. The finding/revision content is produced by actual validators/model output, not injected as a completed artifact.

### Required observed chain

```text
Tauri or public API request
 -> /api/v3/studio
 -> Plan A application service
 -> OrchestratorService creates/persists Studio run and DAG
 -> durable Studio task submission + outbox
 -> independent worker claim + lease/fencing
 -> Plan B handler
 -> Plan A real provider adapter
 -> route lock + endpoint coordinator + real provider/model
 -> validated Plan B artifact content
 -> Plan A UoW persistence
 -> atomic task finalization + outbox
 -> orchestrator completion reconciliation
 -> public run/event/artifact read model
 -> selection/approval commands
 -> screenplay review and at least one new immutable revision
 -> hash-bound approval and lock
 -> LockedScreenplayReceipt/package
 -> READY_FOR_PRODUCTION state and studio.episode.ready_for_production event
 -> Tauri displays server-issued result
```

### Happy-path assertions

- Series, Episode, ProductionRevision, Studio run, DAG node, durable task, artifact, approval, receipt, event, and correlation IDs are real and traceable.
- Candidate set contains 3–5 distinct validated ideas; selected candidate matches exact set hash.
- Bibles/canon, beats, outline, screenplay, review, revision proposal/new draft, and lock artifacts are persisted with schema/prompt/model provenance.
- Outline and final locked screenplay estimates fall within 180–300 seconds or a documented policy tolerance that was frozen before the run.
- Content is Vietnamese, uses rabbit/kite premise, and passes age/safety/continuity/format/feasibility checks.
- Revision count increases and old screenplay artifact/hash remains unchanged.
- Approval and lock bind current revision/artifact/review hashes; replay is idempotent and a different request with the same key conflicts.
- Locked content rejects mutation; a corrective edit requires a derived revision.
- The worker is an independent process and a real provider/model route receipt is present.
- `WINDAGENT_FAKE_RUNTIME`, mock/emergency fallback, fake client, canned response, sample ID, direct service/repository setup, and manual database state edits are absent.

### Required happy-path evidence bundle

- Redacted input and API/Tauri command transcript with idempotency/version headers.
- Capability preflight and process topology.
- Run/DAG/node/task/lease timeline and queue/finalizer/reconcile states.
- Provider/model route, prompt/schema versions/hashes, usage and retry count, safely redacted.
- Artifact lineage manifest with IDs/hashes/revisions and validation/quality/duration results.
- Candidate evaluation and selected hash.
- Approval records, review findings, revision diff, final receipt/package checksum.
- Ordered Studio event/outbox references and final aggregate/read model.
- Tauri build checksum and UI capture showing server-issued locked/ready state.

## Mandatory failure/recovery scenario

At minimum the certification harness executes and records:

| Failure | Injection point | Required recovery assertion |
|---|---|---|
| Worker death | After claim/provider or artifact stage, before terminal finalizer commit (choose a deterministic supported hook) | Lease expires/takes over; stale fence rejected; at most one canonical artifact/result; DAG advances once |
| API response loss/restart | After mutating command is durably committed but before client receives response | Same idempotency key returns original resource/result; no duplicate run/decision |
| Desktop/network restart | While run is queued/running/waiting | Route/server hydration and event cursor restore state; no local completion claim |
| Stale approval/lock | Competing revision/hash becomes current | Typed 409; UI refetches/displays server truth; no approval/lock on stale content |
| Provider/capability unavailable | Real route disabled/unavailable in controlled environment | Typed retryable/blocked state and explicit capability status; no mock/fake success; safe resume when restored if supported |
| Duplicate/out-of-order event delivery | Read-model/event consumer test path | Idempotent by event ID/sequence; no state regression or duplicate action |

Recovery uses normal public/worker mechanisms. Manual row edits, deleting leases/events, injecting successful task results, or reusing a happy-path artifact make the gate invalid.

## Regression matrix required at final SHA

| Surface | Minimum final proof |
|---|---|
| Architecture | import/dependency/cycle checker green; no Story legacy-engine edge |
| Contracts/taxonomy | duplicate canonical models, event taxonomy, task/artifact/OpenAPI/TS drift green |
| Persistence | migration clean+legacy upgrade, repository/UoW/outbox/order/concurrency/rehearsal green |
| Orchestration/worker | DAG, durable queue, lease/fence/heartbeat/finalizer/reconcile/restart/cancel/retry green |
| Provider | route lock/coordinator error/provenance/capability tests plus real tagged smoke |
| Story | all artifact/stage/structured/review/revision/lock tests and Vietnamese invariants green |
| API | V3 endpoints/errors/auth/idempotency/restart and V2 regressions green |
| Frontend | schema/client/state/UI/desktop tests, production bundle fake/fixed-ID scan green |
| Tauri | production build and runtime smoke against real API; checksum recorded |
| Existing production | video workspace, VP3D/director/Blender port/adaptor regression suites green |
| Version/evidence/security | version checker, evidence manifest validator, secret/redaction scan green |

The targeted 40 Python tests and 106 desktop tests observed during planning are baseline evidence only. The existing 13 architecture violations, version failure/warning, and UI runner failure must not remain as unclassified final failures.

## Plan acceptance and rollback decisions

- If an A gate fails, keep Studio writes/runs disabled and route the defect to A; B/C may continue fixture-only work.
- If a B gate fails, preserve valid upstream artifacts and stop at the failed stage; do not synthesize the missing artifact or lower quality thresholds after the fact.
- If a C gate fails, keep V3/Studio navigation disabled or read-only; V2 remains operational.
- If a real environment prerequisite is absent, report `BLOCKED` with capability evidence. A fake does not unblock it.
- A contract/migration/hash change after certification starts invalidates all downstream evidence and requires rerun from the earliest affected gate.
- A locked artifact is never rolled back by mutation. Corrections derive a new revision.

## Planning package acceptance checklist

- [x] Exact baseline and dirty worktree were audited and preserved.
- [x] Full current Roadmap 1 was treated as the scope source.
- [x] Current assumptions were classified only with the required status vocabulary and supported by current evidence.
- [x] Work is decomposed into exactly three detailed plans: A S0–S3, B S4–S10, C S11–S15.
- [x] A short, non-implementation bootstrap gate precedes fan-out.
- [x] Domain/artifact/task/event/port/orchestrator/API contracts are frozen at planning v0.1.
- [x] Hard, contract, integration, test, and optional dependencies are explicit.
- [x] File ownership, hotspots, Git branches/merge train, conflict protocol, risks, rollbacks, and cross-plan gates are explicit.
- [x] Each plan contains purpose, scope, non-goals, evidence, target architecture, owned/forbidden files, dependencies, detailed phases with objective/inspection/steps/migration/compatibility/tests/evidence/gate/rollback, parallel lanes, risks, conflicts, acceptance, and verdict rules.
- [x] Mandatory real happy and recovery slices cover public API, canonical orchestrator, durable worker, real provider/model, persistence, review, revision, approval, immutable lock, and Tauri display with no fake/bypass/hardcode.
- [x] Existing V2 and VP3D foundations are protected by mandatory regression gates.

## Planning verdict

Implementation gates remain pending by design. The requested planning/audit/decomposition package is complete and independently executable:

`WIND_STUDIO_ROADMAP_1_PARALLEL_PLANS_READY`
