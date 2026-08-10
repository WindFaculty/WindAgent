# Plan C C0 — Contract Generation Path Selection and Drift Report

Contract version: `studio.contract/v0.1` · Artifact schema version: `studio.artifact/v1alpha1`

## Generation path selection

Plan A/B publish the frozen vocabulary as JSON Schema documents
(`studio.contract/v0.1`, `studio.artifact/v1alpha1`). The selected mapping path from
JSON Schema to TypeScript is:

| Concern | Selection | Rationale |
|---|---|---|
| JSON Schema -> TypeScript | `json-schema-to-typescript@15` (checked-in generated output under `src/generated/`) | Mature, dependency-light, deterministic given the schema set; no runtime codec required for type parity |
| Cross-file `$ref` resolution | Relative file refs (`studio.episode-state.schema.json#/$defs/state`) canonicalized to `https://windagent.io/schemas/<file>` at validation time | Single mechanism that works for both `json-schema-to-typescript` (cwd-based file resolution) and Python `referencing.Registry` |
| TypeScript runtime validation | `ajv` (draft 2020-12) + `ajv-formats` in the round-trip test only | Proves the fixtures validate under the same schemas in both languages |
| Python validation | `jsonschema` + `referencing.Registry` (draft 2020-12) | Root workspace already depends on `jsonschema>=4.26` |
| Single source of truth | `frontend/packages/studio-contracts/schemas/*.schema.json` (C-owned); bootstrap freeze fixtures in `docs/plans/studio_roadmap_01/fixtures/studio_contract_v0.1/` are enforced equal by dedicated drift tests | Prevents hand-written TS/Python duplicate definitions |

Generated TypeScript is committed. A schema edit without regenerating fails
`npm run check:drift` (and the CI-local command set in C6).

## Fixture set

- 10 JSON Schema documents under `frontend/packages/studio-contracts/schemas/`.
- 17 fixture instances under `frontend/packages/studio-contracts/fixtures/` (kinds:
  `valid`, `vocabulary`, `negative-malformed`, `negative-unsupported-version`), all
  marked `fixture_only` via the manifest.
- Includes the mandatory rabbit/kite scenario input (Vietnamese, ages 5-8,
  180-300 s) with expectation rules but no canned generated artifact.

## Drift checks (CI-local commands)

| Command | Behavior |
|---|---|
| `npm run generate:contracts` (in `@windagent/studio-contracts`) | Regenerates `src/generated/` from schemas |
| `npm run check:drift` (in `@windagent/studio-contracts`) | Regenerates to a temp dir and fails if committed output differs |
| `uv run python scripts/check_openapi_snapshot.py` | Dumps the FastAPI OpenAPI doc and compares to the committed snapshot; `--update` refreshes after a reviewed contract change |
| `uv run pytest tests/unit/api/test_studio_contract_fixtures.py tests/unit/api/test_openapi_snapshot.py` | Python-side round trip + snapshot boundary + bootstrap-freeze alignment |
| `vitest run` (in `@windagent/studio-contracts`) | TS-side round trip + bootstrap-freeze alignment |

## Report (generated 2026-08-09)

- Generator: `json-schema-to-typescript@15.0.4` (installed), checksum of generated
  `src/generated/index.ts` recorded in `artifacts/studio_roadmap_01/c0/`.
- Schema checksums: `artifacts/studio_roadmap_01/c0/contract_schema_checksums.json`.
- OpenAPI snapshot SHA256: `7b377a8aaaf1423c69760cf2b2d6e956aba18c5a1c1228e1b22166c2aa7cfe0e`
  (V2 baseline; grows with V3 in C1).
- Python round trip: 10 passed. TS round trip: 9 passed.
- Drift: no drift at generation time; snapshot is deterministic across processes.

## Gate

`C_CONTRACT_CONSUMER_GATE` evidence: this report plus
`artifacts/studio_roadmap_01/c0/test_baseline_before_after.json` and
`artifacts/studio_roadmap_01/c0/fake_sample_inventory.json`.
