# B0 Evidence — Registry & Schema-Version Freeze

Freezes the registry locations and schema-version rules that B1 (artifact schemas) and B2 (prompt catalog) build on. No production code is moved in B0; this document fixes the targets.

Contract context: `studio.contract/v0.1`, artifact schema version `studio.artifact/v1alpha1`.

## 1. Canonical Story package locations (frozen)

| Concern | Location | Owner | Notes |
|---|---|---|---|
| Story artifact content models, validators, findings/diffs | `core/windagent_core/domain/story/**` | B | Subpackages: `ideation`, `bibles`, `outline`, `screenplay`, `review` (content side). |
| Story pipeline services, prompts, parsers, validators, handlers | `intelligence/windagent_intelligence/story/**` | B | Subpackages: `ideation`, `bibles`, `outline`, `screenplay`, `review`, `prompts`, `runtime_handlers`. |
| Prompt catalog (registry) | `intelligence/windagent_intelligence/story/prompts/` | B | Registry module is the ONLY source of prompt definitions for canonical stages. |
| Artifact type registry | `core/windagent_core/domain/story/registry.py` | B | Maps frozen `artifact_type` → content schema + validation-code catalog. |
| Narrow compatibility adapters / re-exports | `core/.../video_production/screenplay.py`, `intelligence/.../video/**` | B (narrow scope) | No bulk moves; old modules stay public (B0 rule). |
| Envelope / identity / hash / lock / repository | A-owned (`core/.../domain/studio/**`, `core/.../contracts/studio/**`, `storage/.../studio/**`) | A | B never owns envelope construction. |

## 2. Artifact schema-version rules (frozen for B1)

1. Every content artifact declares `schema_version` = `studio.artifact/v1alpha1` content-form family (e.g. `v1alpha1`) and a stable content discriminator (`artifact_type`).
2. Unknown MAJOR/alpha versions fail closed at parse time (reuse `UnsupportedMajorVersionError` semantics) — never silently interpreted.
3. Canonical serialization is deterministic: sorted keys, `ensure_ascii=False`, UTC ISO timestamps, no operational state in the content hash (reuse `VideoProductionPackage.to_content_dict` semantics).
4. Content models carry NO envelope fields (verified by `test_content_models_carry_no_envelope_fields`); the immutable A envelope owns `artifact_id`, `schema_version (envelope)`, `content_hash`, `input_artifact_refs`, prompt/route provenance.
5. Additive compatible fields are allowed within the same version; a semantic change to an existing field requires a new version and a documented mapping.
6. `LockedScreenplayPackage` references immutable approved artifacts by `(artifact_id, content_hash, revision_id)`; it never embeds a mutable in-memory draft as authority (rule 7).

## 3. Prompt identity / version / hash (frozen for B2)

- Every canonical generation stage declares a `PromptSpec` with a stable prompt ID `story.<capability>.<name>`, a semantic version, an input schema, an output schema, and safety constraints.
- `content_hash` = SHA-256 over `capability + version + template` (existing `PromptSpec.content_hash` semantics, `prompts.py:28`).
- Prompts are immutable once versioned; a content change with the same ID/version is a registry violation (prompt snapshot test).
- Prompt/route/model/usage provenance is recorded on artifacts; private reasoning and secrets never are.
- Model output is untrusted input: schema parse, length limits, Unicode handling, instruction-injection isolation, and redaction happen before domain construction (rule 2).
- Repair is bounded and observable: at most one format-repair attempt per generation call, counted in usage/evidence; semantic revision is a separate orchestrated task (rule 4).

## 4. Registry manifests

- `registry.py`: `{artifact_type -> (content_model, validation_codes, presentation_summary)}`.
- Prompt manifest: `story/prompts/manifest.json`-style snapshot, one entry per prompt (id, version, content_hash, schema refs).
- Schema bundle: one JSON Schema + TypeScript source of truth for C (`frontend/packages/studio-contracts/**` is C-owned; B publishes the Python schema bundle that generates it).
- Golden/invalid fixtures and a checksum bundle ship with each artifact family (B1).

## 5. Gate

`B_CONTRACT_CONSUMER_GATE` (B0) evidence: reuse ledger (this doc set), consumer freeze tests green, boundary checker green, A v0.1 fixtures consumed, all reuse decisions owned (see `b0_reuse_ledger.md §8`).

`STORY_ARTIFACT_CONTRACT_GATE` (B1) uses these frozen rules to accept canonical schemas + A envelope wrapping + C fixture generation.
