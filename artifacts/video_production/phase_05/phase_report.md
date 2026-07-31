# Phase 5 Report — VideoClaw Behavior Characterization

- **Gate:** `VP5_VIDEOCLAW_BEHAVIOR_CHARACTERIZED`
- **Status:** PASSED
- **Generated at:** 2026-07-31T22:41:43.260343+00:00

## Behavior matrix

- Cases: 27
- Capability coverage: {'CAP-001': {'happy': 5, 'failure': 5, 'covered': True}, 'CAP-002': {'happy': 4, 'failure': 1, 'covered': True}, 'CAP-003': {'happy': 2, 'failure': 1, 'covered': True}, 'CAP-004': {'happy': 1, 'failure': 2, 'covered': True}, 'CAP-005': {'happy': 4, 'failure': 2, 'covered': True}}
- Golden stability (3 reruns, post-canonicalization): STABLE

## Canonicalization

- Strip fields: created_at, updated_at, session_id, timestamp
- Never-strip: scene order, shot order / duration, dialogue attribution (speaker/tone/text), errors and warnings, artifact relationships (segment/unit ids, character ids)

## Defect inventory

- Defects: 5; all_decided: True

## Nondeterminism inventory

- Entries: 5; all_explained: True

## Harness isolation

- Runs upstream only via `scripts/verification/phase5_upstream_probe.py` (subprocess, temp CWD, network-blocked stubs).
- Architecture quarantine violations: 0

## Evidence

- `behavior_matrix.json`
- `golden_outputs/`
- `canonicalization_rules.json`
- `defect_inventory.json`
- `nondeterminism_inventory.json`
- `harness_test_receipt.json`
- `phase_verdict.json`
