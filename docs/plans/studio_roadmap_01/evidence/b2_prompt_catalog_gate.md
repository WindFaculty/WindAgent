# B2 Evidence — STRUCTURED_MODEL_GATE

Gate owner: Plan B. Baseline: B0 registry/schema freeze (§3 prompt rules) and
quality/error taxonomy (§3 error codes). Fixtures: `fixtures/studio_contract_v0.1/story_prompts/`.

## 1. Prompt catalog manifest

- Prompt schema version: `studio.prompt/v1alpha1`.
- Registered prompts: **11** — all declare output
  schemas and safety constraints (`validate_registry_invariants()` empty).
- Catalog invariants: **clean** (0 violations).

| Prompt ID | Version | Hash | Kind | Output format | Max tokens | Schema |
|---|---|---|---|---|---|---|
| `story.beats.generate` | `1.1.0` | `4f4290e5a133…` | canonical | json | 8000 | `BeatGenerationOutput.json` |
| `story.bibles.generate` | `1.8.0` | `f7afff48a1d1…` | canonical | json | 8000 | `BibleGenerationOutput.json` |
| `story.brief_expansion.expand` | `1.0.0` | `2a882ce066c5…` | legacy | json | 1200 | `BriefExpansionOutput.json` |
| `story.continuation.continue` | `1.0.0` | `f233d9b02c5c…` | legacy | text | 3000 | `canonical_screenplay_text_v1.json` |
| `story.ideation.generate` | `1.1.0` | `84e5cf22fdde…` | canonical | json | 6000 | `IdeaGenerationOutput.json` |
| `story.outline.generate` | `1.0.0` | `34b418e63b04…` | legacy | json | 1500 | `OutlineOutput.json` |
| `story.outline.structured` | `1.1.0` | `56870479040e…` | canonical | json | 8000 | `OutlineGenerationOutput.json` |
| `story.review.assess` | `1.2.0` | `bd3218df8cdf…` | canonical | json | 3000 | `ReviewOutput.json` |
| `story.revise.rewrite` | `1.1.0` | `cbbf06fb9e37…` | canonical | json | 8000 | `ScreenplayRevisionOutput.json` |
| `story.screenplay.structured` | `1.0.3` | `a3f71de56fbf…` | canonical | json | 8000 | `ScreenplayGenerationOutput.json` |
| `story.screenplay.write` | `1.0.0` | `d546496f9718…` | legacy | text | 4000 | `canonical_screenplay_text_v1.json` |

Extracted legacy prompts keep template/hash equality with their live
`PromptSpec` constants (equivalence test in `tests/unit/intelligence/story/test_prompt_registry.py`).

## 2. Schema bundle

- **10** schema files under `story_prompts/schemas/`,
  checksummed in `story_prompts/checksums.json`.
- JSON prompts validate via `jsonschema` Draft 2020-12; text-format legacy
  prompts declare a format spec (size/safety enforced at the boundary).

## 3. Invalid-output corpus results (bounded repair)

Every case runs through `StoryModelBoundary` + `FixtureModelPort`; results are
committed and re-verified by `produce_b2_evidence.py --check` and
`tests/contracts/test_story_b2_prompt_catalog.py`.

| Case | Outcome | Code | Repairs |
|---|---|---|---|
| `valid_brief_json` | `ok` | `—` | 0 |
| `markdown_fenced_json` | `ok` | `—` | 1 |
| `broken_json_trailing_comma` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `schema_missing_required` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `non_object_json` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `empty_response` | `error` | `STORY_EMPTY_RESPONSE` | — |
| `blank_response` | `error` | `STORY_EMPTY_RESPONSE` | — |
| `oversized_text_output` | `error` | `STORY_SAFETY_FAILURE` | — |
| `valid_screenplay_text` | `ok` | `—` | 0 |
| `prompt_injection_in_field` | `ok` | `—` | 0 |
| `unicode_vietnamese` | `ok` | `—` | 0 |
| `prohibited_pattern` | `error` | `STORY_SAFETY_FAILURE` | — |

- At most ONE format-repair attempt per call (fenced-block extraction);
  a second failure is terminal `STORY_SCHEMA_FAILURE`.
- `STORY_PARSE_TRANSIENT` is raised only when repair is explicitly bypassed
  (caller retries the provider instead).

## 4. Error taxonomy mapping

`story_error_code()` maps every Story boundary failure to the frozen B0 codes:
`STORY_PROVIDER_TRANSIENT`, `STORY_EMPTY_RESPONSE`, `STORY_PARSE_TRANSIENT`,
`STORY_SCHEMA_FAILURE`, `STORY_SAFETY_FAILURE`; unknown -> `STORY_UNKNOWN_ERROR`.

## 5. Redaction review

- Provenance (`StoryModelProvenance`) carries only: prompt id/version/hash,
  capability, provider, finish_reason, usage, repair_count, route_lock_id.
- Never recorded: raw model output, rendered prompts, system text, private
  reasoning, or secrets. Catalog entries contain no secrets.
- Prompt-injection text in model output is parsed as DATA only (never
  executed); corpus case `prompt_injection_in_field` proves it.

## 6. Fixture fake rejection contract

- `FixtureModelPort` is unit-test-only; `is_fixture_provider()` + 
  `assert_not_fixture()` fail closed when a fixture provider or
  `provider == "fixture"` provenance reaches certification.
- A refusing fixture (`reject=True`) surfaces as a failure, never as silent
  canned output.

## 7. No tolerant free-text parsing on canonical paths

Tolerant-parser scan over `core/.../domain/story/` + `intelligence/.../story/`
(`parse_json_contract`, `split_episodes`, `video.parsing`,
`parse_screenplay_text`): **0 violation(s)**.
None.

## 8. Gate verdict

**`STRUCTURED_MODEL_GATE`: PASS (B-side evidence).**

- Manifest: `story_prompts/prompt_manifest.json` (checksum `ae3a52c10941ee7e…`).
- Schema checksums: `story_prompts/checksums.json`.
- Corpus results: `story_prompts/invalid_output_corpus_results.json`.
- C/A halves (runtime model-route lock, TypeScript schema consumption) are
  co-signed by their plan owners at contract review.
