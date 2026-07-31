# Phase 6 Report — Pre-production Kernel Canonical

- **Gate:** `VP6_PREPRODUCTION_KERNEL_CANONICAL`
- **Status:** PASSED
- **Generated at:** 2026-07-31T23:33:20.914315+00:00

## Capability matrix

- Slices: 9; all present: True

## Golden comparison (equivalence_policy.md)

- Fixtures: 3
- All blocking fields passed: True

## Provider neutrality

- Kernel: `intelligence/windagent_intelligence/video/`
- Forbidden imports: 0
- Verdict: PASS

## Upstream retirement

- Scanned files: 22
- Upstream imports / sys.path mutations: 0
- Verdict: PASS

## Integration

- idea → package e2e: True
- Per-fixture runs: [{'fixture_id': 'fixture_short_cartoon', 'all_ok': True, 'steps': [{'step': 1, 'capability': 'CreativeBriefExpander', 'ok': True}, {'step': 2, 'capability': 'StoryOutliner', 'ok': True}, {'step': 3, 'capability': 'ScreenplayWriter', 'ok': True}, {'step': 4, 'capability': 'DialogueNarrator', 'ok': True}, {'step': 5, 'capability': 'EntityExtractor', 'ok': True}, {'step': 6, 'capability': 'StyleDesigner', 'ok': True}, {'step': 8, 'capability': 'AssetPromptSpecBuilder', 'ok': True}, {'step': 9, 'capability': 'PackageAssembler', 'ok': True}, {'step': 10, 'capability': 'Serialization+Validation', 'ok': True}, {'step': 11, 'capability': 'ContentHashDeterminism', 'ok': True}], 'content_hash': '507a09ca55d447d6fdc1b40f40abf1ce3c7e617e3432e16a8cc312538c40eb29', 'package_valid': True}, {'fixture_id': 'fixture_two_character_dialogue', 'all_ok': True, 'steps': [{'step': 1, 'capability': 'CreativeBriefExpander', 'ok': True}, {'step': 2, 'capability': 'StoryOutliner', 'ok': True}, {'step': 3, 'capability': 'ScreenplayWriter', 'ok': True}, {'step': 4, 'capability': 'DialogueNarrator', 'ok': True}, {'step': 5, 'capability': 'EntityExtractor', 'ok': True}, {'step': 6, 'capability': 'StyleDesigner', 'ok': True}, {'step': 8, 'capability': 'AssetPromptSpecBuilder', 'ok': True}, {'step': 9, 'capability': 'PackageAssembler', 'ok': True}, {'step': 10, 'capability': 'Serialization+Validation', 'ok': True}, {'step': 11, 'capability': 'ContentHashDeterminism', 'ok': True}], 'content_hash': '6518d341d68bfd521fb0c0be4fbfc9fe98f41741b3c7e09e7db11159fb3da890', 'package_valid': True}, {'fixture_id': 'fixture_multi_scene_drama', 'all_ok': True, 'steps': [{'step': 1, 'capability': 'CreativeBriefExpander', 'ok': True}, {'step': 2, 'capability': 'StoryOutliner', 'ok': True}, {'step': 3, 'capability': 'ScreenplayWriter', 'ok': True}, {'step': 4, 'capability': 'DialogueNarrator', 'ok': True}, {'step': 5, 'capability': 'EntityExtractor', 'ok': True}, {'step': 6, 'capability': 'StyleDesigner', 'ok': True}, {'step': 8, 'capability': 'AssetPromptSpecBuilder', 'ok': True}, {'step': 9, 'capability': 'PackageAssembler', 'ok': True}, {'step': 10, 'capability': 'Serialization+Validation', 'ok': True}, {'step': 11, 'capability': 'ContentHashDeterminism', 'ok': True}], 'content_hash': 'd6f09beb61f1528bb573c4055a37d750400ed17b3c140011fc2ba9aeddc4c84a', 'package_valid': True}]

## Evidence

- `capability_matrix.json`
- `golden_comparison.json`
- `provider_contract_receipt.json`
- `no_upstream_import_report.json`
- `integration_test_receipt.json`
- `phase_verdict.json`
