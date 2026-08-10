# Cross-Plan Contracts

## Contract set

The normative cross-plan contract version is `studio.contract/v0.1`; Story artifacts use `studio.artifact/v1alpha1`. Detailed bilateral obligations are in:

- `PLAN_A_TO_PLAN_B_CONTRACT.md`
- `PLAN_A_TO_PLAN_C_CONTRACT.md`
- `PLAN_B_TO_PLAN_C_CONTRACT.md`

This file is the integration index. It defines authority, compatibility, evolution, and tests shared across all three plans.

## Authority map

| Concern | Source of truth | Producer | Consumers | Prohibited duplicate |
|---|---|---|---|---|
| Series/Episode/revision IDs and lifecycle | A core Studio domain | A | B, C | B artifact-local lifecycle; C client-local state enum authority |
| Approval policy and hash-bound decisions | A core/application | A | B, C | UI-only approval or B auto-approval outside policy |
| Artifact envelope/hash/lineage | A contract/domain | A wraps; B supplies content | A, B, C | Separate DB/API hash schemes |
| Story artifact content schemas | B Story domain | B | A persistence envelope, C schema client/UI | Handwritten API/TS copies |
| Task/event envelope and names | A contracts/catalog | A | B handlers, C run views | B/C private task/event taxonomy |
| Story prompts, scoring, validation, review | B intelligence | B | A runtime invokes, C displays result | Provider/API embedded prompt or scoring |
| Orchestration/DAG advancement | `OrchestratorService` through A service | A | C commands/read state; B tasks | API, worker handler, or legacy engine advancing Story independently |
| Durable execution/finalization | A queue/worker/UoW/outbox | A | B handler seam, C evidence | In-process API generation or fake completion |
| Provider/model route | A infrastructure adapter using canonical coordinator | A | B model port; C diagnostics/capability | B direct provider SDK; C provider call |
| HTTP contract | C V3 mapping over A/B schemas | C | Desktop/external client | Router-owned domain behavior |
| TypeScript/UI representation | C generated/mapped contracts | C | Desktop | Manual canonical domain redefinition |
| Final certification/evidence index | C, with A/B artifacts | C | Integration owner | Stale historic report as final truth |

## Canonical state and transition contract

The API, task results, events, persistence, and desktop all use the exact episode state values frozen in bootstrap. Normal progression:

```text
DRAFT
 -> IDEA_REVIEW
 -> STORY_BIBLE_REVIEW
 -> OUTLINE_REVIEW
 -> SCREENPLAY_REVIEW
 -> REVISING -> SCREENPLAY_REVIEW  (0..policy.max_revision_iterations)
 -> LOCKED
 -> READY_FOR_PRODUCTION
```

`FAILED` and `CANCELLED` are explicit terminal run/episode outcomes according to application rules; dependency unavailability and human approval waits are run statuses/wait reasons and must not be mislabeled success. State changes require expected version, valid input artifact hashes, and an allowed actor/policy decision.

## Hash, identity, and idempotency contract

- Canonical hash input is versioned canonical JSON of artifact content plus its schema discriminator; envelope timestamps, provider usage, and storage location do not change the content hash.
- Artifact identity is immutable. Equal validated content under equal schema may be deduplicated, but lineage references and task results remain explicit.
- A revision lock binds the revision ID, screenplay artifact ID/content hash, review artifact hash, approval decision, and package manifest hash.
- Idempotency scope includes actor/tenant as applicable, command type, aggregate ID, and key. Normalized request hash is stored. Same key/same hash returns the original result; same key/different hash is a 409 mismatch.
- Durable task idempotency additionally includes task type, DAG node, all input hashes, prompt version/hash, model-route lock, and attempt semantics.

## Task and event choreography

1. C submits a public command with idempotency and expected version/hash.
2. A persists the command outcome/run/DAG before exposing runnable work.
3. A submits a frozen `StudioTaskEnvelope` through the durable adapter.
4. Worker claims with lease/fencing and invokes exactly one B handler through A’s registry/context.
5. B validates inputs, uses A’s `PreproductionModelPort`, builds validated content, and requests artifact persistence through A’s UoW.
6. A finalizes task state/result/outbox atomically and rejects stale fencing.
7. A reconciles durable completion with run/node/version and enables only satisfied dependencies.
8. C observes durable run state/events and renders persisted artifacts.
9. Approval/selection/lock decisions return through public commands and repeat the choreography as applicable.

No step may be collapsed into an API-local provider call or UI-local state mutation for certification.

## API representation and error mapping

| Domain/application outcome | HTTP behavior | Desktop behavior |
|---|---|---|
| Command accepted; work queued/running | `202` + durable run link/resource | Show pending/progress; poll/events; no synthetic artifact |
| Resource/command completed synchronously | `200`/`201` with server representation | Replace/invalidate from server result |
| Validation issue | `422 VALIDATION_ERROR` with stable field/issue codes | Focus affected input and show actionable issues |
| Stale revision/hash or invalid transition | `409` typed code | Refetch, compare server truth, require explicit retry decision |
| Idempotency mismatch | `409 IDEMPOTENCY_MISMATCH` | Never generate a new key automatically for the same ambiguous action |
| Waiting for required approval | Run resource `waiting_for_approval`; disallowed command is `409 APPROVAL_REQUIRED` | Render checkpoint and allowed actors/actions |
| Capability/provider unavailable | `503` typed, retry hint only when safe | Fail closed; show configuration/retry state; no fake fallback |
| Internal failure | `500 INTERNAL_ERROR`, correlation ID, redacted detail | Show recoverable diagnostic reference; never raw exception/secret |

## Schema evolution rules

1. Additive optional fields may remain within `v0.1`/`v1alpha1` only when old consumers safely ignore them and fixtures prove this.
2. Renames, type/meaning changes, discriminator/state/task/event changes, required-field additions, or hash-input changes are breaking and require a version bump.
3. Breaking proposal includes migration/compat adapter, regenerated fixtures/client, event/task replay impact, and rollback.
4. A approves envelope/task/event/aggregate changes; B approves Story content changes; C approves HTTP/client representation impact. All affected owners approve before merge.
5. Schema version and contract version appear in task/event/artifact/API evidence; mixed incompatible versions fail integration.

## Contract fixture set

At minimum, the bootstrap/implementation branches maintain:

- one valid Series/Episode/revision/approval lifecycle fixture;
- every Story artifact type, plus unknown-version and malformed fixtures;
- each task input/result and each event type;
- V3 request/response/error/idempotency fixtures;
- Vietnamese Unicode, long text, empty optional values, and maximum-size boundaries;
- stale revision/hash, duplicate delivery, retryable provider error, terminal schema error, locked revision, and capability-unavailable cases;
- rabbit/kite scenario input and expectation rules, but no canned generated final artifact used by production.

Fixtures validate in Python and TypeScript. Stored golden outputs used for unit/UI tests carry `fixture_only: true` metadata and are excluded from production composition and final real-slice artifact provenance.

## Cross-plan gate table

| Gate | Required producer | Required consumer proof | Blocks |
|---|---|---|---|
| `CONTRACT_FREEZE_GATE` | A/B/C | All fixtures/names/ownership agreed | All fan-out implementation |
| `STUDIO_DOMAIN_INTEGRATION_GATE` | A | B content envelope + C app fixture compile | B runtime handlers; C real routes |
| `STORY_ARTIFACT_CONTRACT_GATE` | B | A envelope round trip + C TS generation/render fixtures | C real artifact UI; persistence promotion |
| `DURABLE_ORCHESTRATION_GATE` | A | C start/status consumer; B task fixture | Real Story run |
| `SCREENPLAY_RUNTIME_GATE` | A+B | C sees persisted draft/review/revision/receipt through app fixture | API/UI real integration |
| `API_UI_INTEGRATION_GATE` | C with A/B | Public-path correlation across all layers | Certification |
| `REAL_VERTICAL_SLICE_GATE` | A+B+C | Real provider/durable evidence and UI receipt | Final acceptance |
| `FINAL_CERTIFICATION_GATE` | C integration owner | One-SHA evidence validation and regressions | Roadmap 1 promotion |

## Contract-change protocol

A plan discovering a bad assumption first records **OBSERVED** evidence, impact, and a migration-compatible proposal. It does not edit the shared shape. The integration owner calls a contract review, affected owners decide, fixtures/docs update in a dedicated contract commit, consumers update, and the earliest affected gate reruns. A workaround local to one plan that changes semantics is a contract violation, not a temporary implementation detail.
