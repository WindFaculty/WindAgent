# Phase 17 — Durable Production Workflow: Workflow Definition Contract

- **Gate:** `VP17_DURABLE_WORKFLOW_VERIFIED`
- **Plan:** `docs/video_production/plans/05_phase_17_20_orchestration_cost_review.md` §6–§7
- **Module:** `orchestration/windagent_orchestration/production/engine.py`,
  `workflows/windagent_workflows/video_production/definition.py`

## 1. Workflow definition

The durable production workflow is a linear 16-step DAG (plan 05 §7):

```text
CREATE_PROJECT
→ GENERATE_CONCEPTS
→ SELECT_CONCEPT
→ GENERATE_SCREENPLAY
→ LOCK_SCREENPLAY
→ BUILD_CHARACTER_AND_LOCATION_BIBLES
→ APPROVE_REFERENCES
→ CREATE_CINEMATIC_PLAN
→ LOCK_SHOT_PLAN
→ ESTIMATE_COST
→ RENDER_ASSETS
→ RENDER_SHOTS
→ REVIEW_CANDIDATES
→ POST_PRODUCTION
→ FINAL_VERIFICATION
→ PUBLISH
```

The step list, per-step metadata and the scheduler-ready node graph live in
`definition.py`. The immutable pack definition is built by
`VideoProductionWorkflowPack.build_workflow_definition()`.

## 2. Step contract

Each step (plan 05 §7) is described by `step_contract(step_id)`:

```text
step_id                  unique step id
version                  step contract version (bump = new definition)
input_revision_hash      input revision/content hash of the run
preconditions            all dependency steps completed; approval gate satisfied if any
operation                step_executor.execute (injected StepExecutorPort)
expected_events          canonical events emitted for this step
checkpoint               current_step + attempt + input/output hashes + lease + pending external op
retry_class / budget     fast | llm | provider | review | render; bounded max attempts
compensation_or_recovery inspect durable state + provider before retry; never blind resubmit
approval_requirement     none | one of the 7 approval gates
output_artifact_types    artifact families produced by the step
```

Example (`RENDER_SHOTS`):

```json
{
  "step_id": "RENDER_SHOTS",
  "version": 1,
  "approval_requirement": "none",
  "retry_class": "provider",
  "retry_budget": 3,
  "external_cost": true,
  "expected_events": [
    "video_production.generation_submitted",
    "video_production.generation_completed"
  ],
  "output_artifact_types": ["shot_clips", "candidate_set"]
}
```

## 3. Approval gates bound to steps

Per plan 05 §8.2, seven gates gate specific steps:

| Gate                  | Step(s) it gates                          |
|-----------------------|-------------------------------------------|
| CONCEPT_APPROVAL      | SELECT_CONCEPT                            |
| SCREENPLAY_APPROVAL   | LOCK_SCREENPLAY                           |
| CHARACTER_APPROVAL    | BUILD_CHARACTER_AND_LOCATION_BIBLES       |
| LOCATION_APPROVAL     | APPROVE_REFERENCES                        |
| SHOT_PLAN_APPROVAL    | LOCK_SHOT_PLAN                            |
| COST_APPROVAL         | ESTIMATE_COST                             |
| FINAL_CUT_APPROVAL    | PUBLISH                                   |

A step behind an unapproved gate is never scheduled
(`ProductionScheduler.ready_steps` skips it; the engine moves the run to
`WAITING_APPROVAL`).

## 4. Determinism

- The step graph has a stable topological order (dependency count, then
  step_id).
- Identical inputs produce identical schedule decisions
  (`scheduler_signature`).
- The whole gate runs offline with a fake `StepExecutorPort`; no provider,
  browser, or network is required.

## 5. Evidence

- `artifacts/video_production/phase_17/workflow_definition_receipt.json`
- `artifacts/video_production/phase_17/state_machine_receipt.json`
