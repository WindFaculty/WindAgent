# Continuity Override Policy (Phase 10)

- **Gate:** `VP10_CONTINUITY_LEDGER_VERIFIED`
- **Owner:** `HumanContinuityOverride` in
  `core/windagent_core/domain/video_production/continuity.py`
- **Ratified by:** [`03_phase_08_11_director_layer.md`](../plans/03_phase_08_11_director_layer.md) §19.3

## 1. Purpose

A continuity defect found by the deterministic rules is normally resolved by
a screenplay revision. When the screenplay is correct but the planned state is
wrong (or a creative deviation is intentionally approved), a **human override**
records the decision so the ledger stays auditable instead of being silently
rewritten.

## 2. Override record

Every override is appended as immutable evidence:

```text
override_id | actor | reason | target_revision | field
| before | after | applied_at_shot_id | timestamp
```

- `actor` — who approved the override (never blank);
- `reason` — why (never blank);
- `target_revision` — the revision the override is valid for;
- `field` — the canonical continuity field being overridden;
- `before` / `after` — the value change;
- `applied_at_shot_id` — the shot from which the override takes effect;
- `timestamp` — when it was recorded.

## 3. Application semantics

- An override with `applied_at_shot_id` takes effect from that shot onward
  (its planned change is sourced `HUMAN_OVERRIDE`).
- An override **without** a target shot applies from the **first shot** of the
  revision (deterministic policy).
- Overrides never mutate the recorded incoming/outgoing states of **earlier**
  shots — retroactive evidence is preserved (no retroactive edits, plan §19.3).
- The override change is exempt from `CHANGE_OUTSIDE_ALLOWED` and
  `PROP_UNEXPLAINED_CHANGE` (it is the escape hatch), but it does not bypass
  `IDENTITY_HASH_MISMATCH` for missing references.

## 4. Audit & traceability

The ledger's `overrides` list is the append-only audit trail. The ledger hash
covers overrides, so any change to an override (or the evidence around it)
produces a new hash and is detectable. Overrides feed the Phase 18-style
invalidation intent: an approved override makes the affected prompts/frames/
clips stale and records which shots depend on the overridden field.
