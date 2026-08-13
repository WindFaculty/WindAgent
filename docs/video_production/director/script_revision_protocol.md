# Script Revision Protocol (Phase 8)

- **Gate:** `VP8_DIRECTOR_FOUNDATION_VERIFIED`
- **Owner:** `intelligence/windagent_intelligence/video/director/revision.py`
- **Ratified by:** `../../intelligence/windagent_intelligence/video/director/` (plan 03 đã retired) §9.3

## 1. Invariant

The Director **never mutates a screenplay**. When it discovers a problem it
emits a `DirectorialIssue`; blocking issues are converted into
`ScriptRevisionProposal`s. The proposal does NOT change the package — it is a
record of what a new screenplay revision would need to change.

## 2. Flow

```text
DirectorialIssue
    → ScriptRevisionProposal
    → human/workflow approval (APPROVED | REJECTED)
    → new screenplay revision (derived via RevisionService, with an explicit
      downstream invalidation intent)
    → regenerate the cinematic plan
```

- A **rejected** proposal leaves the package untouched.
- An **approved** proposal is a prerequisite for deriving a new revision; the
  plan that produced the proposal is invalidated (Phase 18).

## 3. Proposal fields (plan §9.3)

| Field | Meaning |
|---|---|
| `proposal_id` | Stable proposal ID. |
| `source_issue_id` | The `DirectorialIssue` that produced this proposal. |
| `target_scene_id` | Scene that needs the change. |
| `target_line` | Optional specific dialogue/beat line. |
| `reason` | The issue message (why the change is needed). |
| `suggested_change` | Deterministic suggested change (per issue category). |
| `impact` | What downstream artifacts are affected. |
| `source_plan_hash` | The plan hash this proposal was derived from. |
| `status` | `PENDING` → `APPROVED` | `REJECTED` |

## 4. Category → suggestion mapping

| Category | Suggested change |
|---|---|
| `DURATION_OVERFLOW` | Trim or reallocate shot durations within the constraint tolerance. |
| `DIALOGUE_DURATION_MISMATCH` | Extend the shot or shorten/merge the line — never silently cut. |
| `UNKNOWN_REFERENCE` | Fix the entity/reference ID so it exists in the package. |
| `MISSING_COVERAGE` | Add a shot or bind every dialogue line to a shot. |
| `CONSTRAINT_VIOLATION` | Adjust the plan to respect production constraints. |

## 5. Audit

Human overrides are out of scope for Phase 8 (they land with the continuity
ledger in Phase 10). For Phase 8 the proposal record itself is the audit
trail: every blocking issue has a proposal, and the source plan hash ties the
proposal to the exact plan that found the problem.
