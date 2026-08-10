# B0 Evidence — Consumer Contract Test Report

Phase: Plan B B0 (consume freeze). Gate target: `B_CONTRACT_CONSUMER_GATE`.
Baseline: `9a09375700db02a64315068f008b15e43ba5f42d`. Date: 2026-08-09.

## 1. Verdict

`B_CONTRACT_CONSUMER_GATE` — **PASS (fresh)**.

- B fixtures validate against A `studio.contract/v0.1` (`tasks.json`, `artifact_envelope.json`).
- Every reuse decision in `b0_reuse_ledger.md` has an owner (ledger §8).
- Zero new production callers of soon-to-be-wrapped story services (boundary checker).
- Existing public imports and current story tests remain green (compatibility, no move).

## 2. New B0 artifacts (this phase)

| Artifact | Purpose |
|---|---|
| `docs/plans/studio_roadmap_01/evidence/b0_reuse_ledger.md` | Per-symbol reuse/wrap/migrate/deprecate/VP3D-only decision, code refs, owners, caller/zero-caller inventory. |
| `docs/plans/studio_roadmap_01/evidence/b0_registry_and_schema_freeze.md` | Frozen canonical package locations + artifact schema-version rules + prompt ID/version/hash rules. |
| `docs/plans/studio_roadmap_01/evidence/b0_quality_and_error_taxonomy.md` | Quality dimensions, severity model, finding shape, error/retry taxonomy, policy knobs. |
| `docs/plans/studio_roadmap_01/fixtures/studio_contract_v0.1/story_task_io.json` | B content proposal: 9 frozen task types → input/output artifact types. |
| `tests/contracts/test_story_b0_consumer_freeze.py` | Consumer freeze tests (fixture validation, import characterization, serialization snapshots, invalid/unknown fixtures, model-port contract). |
| `scripts/check_story_b0_legacy_boundary.py` | Guard: no new production caller of legacy story services. |
| `tests/architecture/test_story_b0_legacy_boundary.py` | Boundary checker tests. |

## 3. Test results (fresh run, repo `.venv` python)

| Suite | Result |
|---|---|
| `tests/contracts/test_story_b0_consumer_freeze.py` (16) + `tests/architecture/test_story_b0_legacy_boundary.py` (6) | 20 passed |
| `tests/contracts/test_studio_contract_fixtures_v0_1.py` (A0) + `tests/architecture/test_no_story_in_legacy_engines.py` (A0) + `tests/unit/api/test_studio_contract_fixtures.py` (C0) | 38 passed |
| `scripts/check_story_b0_legacy_boundary.py --root .` | PASS (zero violations) |
| Compatibility sanity: `test_phase06_kernel.py`, `test_phase10_continuity.py`, `test_screenplay_workspace.py` | 31 passed |
| Combined contract/fence run (B0 + A0 + C0) | **58 passed** |

No baseline suite was modified; no existing story service was deleted or moved.

## 4. What B0 pins (contract report)

1. **Task → IO map** (`story_task_io.json`) matches the 9 frozen task types exactly and references only frozen artifact types; **all 13** Story artifact types are reachable from tasks. Selection/approval remain commands, not hidden model tasks (frozen rule).
2. **Envelope separation**: current content models carry no envelope fields (`test_content_models_carry_no_envelope_fields`) — B1 wraps content behind the A envelope instead of inventing envelope substitutes.
3. **Model boundary**: `PreproductionModelPort` is runtime-checkable and remains the only provider crossing point; `capability` is a required parameter; deterministic fakes are unit-test-only.
4. **Serialization snapshots**: current content-model field inventories are pinned (`_PINNED_FIELDS`) so B1 canonical schemas preserve or explicitly migrate them; deterministic JSON + Vietnamese Unicode round-trips verified.
5. **Migration guard**: `check_story_b0_legacy_boundary.py` fails on any new production caller of `video.ideation|screenplay|entity_extraction|style_design|continuation|assembly|director|parsing|prompts` outside `video/**`, `story/**`, core compatibility re-exports, tests, and verification fixtures.

## 5. Open items for the gate owner

- `story_task_io.json` is marked `proposal-awaiting-a-approval` — Plan A must co-approve the task→IO mapping at the B1/A envelope integration.
- Zero-caller claims are fresh for the legacy story services; re-check at each phase gate (ledger §7).
- Prompt catalog and artifact registry are location-frozen but not yet implemented (B2/B1); only the rules are frozen now.
