# Phase 0 — WindAgent behavioural baseline

Phase 0 freezes the old WindAgent as a behavioural reference before any V2
implementation is started.  It does **not** copy source files, schemas, or
routers into V2.

## Frozen source

- Repository: `../WindAgent`
- Git revision: `01695ca48dddb7220efd60c212e52dac1d6a5f2d`
- Captured: 2026-09-01
- Working-tree changes: excluded.  They must be committed to the old project
  and the baseline revision deliberately advanced before they can affect V2.

The old repository is read-only for migration work.  Its tests and observable
behaviour remain the parity oracle until each V2 capability has cut over.

## Manifest contract

The six files under `migration/manifests/` are the source of truth for the
migration.  Each capability has the following required fields:

`id`, `capability`, `source`, `target`, `owner`, `action`, `dependencies`,
`test_oracle`, and `status`.

`migration_matrix.yaml` is the canonical cross-inventory index.  A capability
must occur once in its specialist inventory and once in that matrix.  The
validator enforces this relationship and the required fields.

Actions are intentionally limited to `REWRITE`, `EXTRACT_LOGIC`, `KEEP_ASSET`,
`ADAPT`, and `DELETE`.

## Statuses

- `FROZEN`: captured as a source baseline; no V2 implementation has begun.
- `NOT_STARTED`: reserved for later planning updates after the freeze gate.
- `IN_PROGRESS`, `PARITY_READY`, `CUT_OVER`, and `RETIRED`: later migration
  states; none is allowed in this phase.

## Phase 0 gate

Run from the V2 root:

```powershell
python scripts/validate_phase0_manifests.py
```

The gate passes only when all six manifests exist, all capability rows contain
the required migration decision, every matrix ID is represented by exactly one
specialist inventory, and all rows remain in the `FROZEN` state.

