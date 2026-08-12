# B5 Evidence — OUTLINE_GATE

Gate owner: Plan B. Baseline: B1 outline models/validators/duration, B2 prompt
catalog + structured model boundary, B4 canon. Fixtures:
`fixtures/studio_contract_v0.1/story_outline/` (corpora/golden) and
`.../story_prompts/` (prompt manifest).

## 1. Outline generation prompts (B5 canonical, non-legacy)

- Prompt: `story.beats.generate` v1.0.1 — schema-first JSON,
  `legacy=False`. Hash: `61cec0219c03c012f8097ef51ea2ef1dc8e4b86a68379b4064f7fb976d5d549e`; output schema:
  `BeatGenerationOutput.json` (4-12 beats, order, roles, canon refs, budget).
- Prompt: `story.outline.structured` v1.0.2 — schema-first
  JSON, `legacy=False` (canonical successor of the legacy
  `story.outline.generate` prompt, which stays for the old pipeline).
  Hash: `3e468ffabec6c098ac7b55946e883fee4a5473db9d6a0af3ca6d1c5e9efe5816`; output schema:
  `OutlineGenerationOutput.json` (3-12 scenes, intent, canon refs, beat
  coverage, duration budget).
- Catalog invariants: **0 violation(s)**;
  registered prompt count: 11.

## 2. Golden outline set (Vietnamese rabbit/kite, ages 5-8, 240s)

- BeatSheet `bs_rabbit_kite`: 4 beats,
  allocated 240s / target
  240s — validation:
  **True** (blocking 0, warnings 0).
- EpisodeOutline `ol_rabbit_kite`:
  4 scenes, total
  240s — validation:
  **True** (blocking 0, warnings 0).
- Hashes: beat sheet `f64db297f2ba7acb…`, outline
  `6e6653b711b72a05…` (deterministic; idempotent same
  inputs reproduce them).
- Provenance: prompt id/version/hash, provider, finish reason, usage,
  repair_count — never raw content or reasoning.

## 3. Invalid-output corpora results (services + boundary)

Every case runs through `BeatGenerationService` / `OutlineGenerationService`
+ `StoryModelBoundary` + `FixtureModelPort`; results committed and re-verified
by `produce_b5_evidence.py --check` and
`tests/contracts/test_story_b5_outline_gate.py`.

### 3a. Beats corpus

| Case | Outcome | Code | Issue codes |
|---|---|---|---|
| `valid_beat_sheet` | `ok` | `—` | — |
| `markdown_fenced_json` | `ok` | `—` | — |
| `empty_response` | `error` | `STORY_EMPTY_RESPONSE` | — |
| `not_json` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `missing_beats` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `beat_missing_description` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `beat_order_not_starting_at_1` | `error` | `OUTLINE_VALIDATION_FAILURE` | ORDER_SEQUENCE |
| `duplicate_beat_ids` | `error` | `OUTLINE_VALIDATION_FAILURE` | ID_UNIQUE |
| `unknown_character_ref` | `error` | `OUTLINE_VALIDATION_FAILURE` | REF_MISSING |
| `unknown_beat_role` | `error` | `OUTLINE_VALIDATION_FAILURE` | UNKNOWN_REF_KIND |
| `duration_sum_outside_tolerance` | `error` | `OUTLINE_VALIDATION_FAILURE` | DURATION_SUM |
| `unicode_vietnamese` | `ok` | `—` | — |
| `prompt_injection_in_field` | `ok` | `—` | — |

### 3b. Outline corpus

| Case | Outcome | Code | Issue codes |
|---|---|---|---|
| `valid_outline` | `ok` | `—` | — |
| `markdown_fenced_json` | `ok` | `—` | — |
| `empty_response` | `error` | `STORY_EMPTY_RESPONSE` | — |
| `not_json` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `missing_scenes` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `scene_missing_intent` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `duplicate_scene_ids` | `error` | `OUTLINE_VALIDATION_FAILURE` | ID_UNIQUE |
| `scene_order_not_starting_at_1` | `error` | `OUTLINE_VALIDATION_FAILURE` | ID_STABILITY,ORDER_SEQUENCE |
| `unknown_location_ref` | `error` | `OUTLINE_VALIDATION_FAILURE` | ID_STABILITY,REF_MISSING |
| `unknown_beat_ref` | `error` | `OUTLINE_VALIDATION_FAILURE` | BEAT_ORPHAN,ID_STABILITY,SCENE_ORPHAN |
| `orphan_beat` | `error` | `OUTLINE_VALIDATION_FAILURE` | BEAT_ORPHAN,ID_STABILITY |
| `causal_order_violation` | `error` | `OUTLINE_VALIDATION_FAILURE` | BEAT_ORPHAN,CAUSAL_ORDER,DURATION_SUM,ID_STABILITY |
| `duration_outside_180_300` | `error` | `OUTLINE_VALIDATION_FAILURE` | DURATION_BOUND,DURATION_SUM |
| `too_few_scenes` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `unicode_vietnamese` | `ok` | `—` | — |
| `prompt_injection_in_field` | `ok` | `—` | — |

- Schema failures (missing array/required field) come from the boundary
  BEFORE domain construction; structure violations (order, duplicates,
  canon refs, roles, beat coverage, causality, duration) are typed
  `OutlineValidationFailure` with stable issue codes. Structure is never
  auto-fixed.

## 4. Duration planning (deterministic, versioned)

- Formula `duration_formula/v1`: per-scene estimate = action + dialogue +
  narration (chars/sec 3.5 for Vietnamese) + 2.0s
  transition; bounds 180-300 s, default tolerance 15 s.
- Boundaries exercised in tests: 180/240/300 s targets, tolerance edges,
  DURATION_SUM vs DURATION_BOUND separation.

## 5. Handler surface

- Registered B5 handlers: `studio.story.beats.generate` (canon set ->
  BeatSheet), `studio.story.outline.generate` (BeatSheet -> EpisodeOutline)
  — matches `story_task_io.json`.
- No storage/queue/API imports in handlers; provider crossed only through
  `StoryModelBoundary`. Fixture provider rejected at certification
  (`assert_not_fixture`). Approval of the outline is an A checkpoint command,
  not a handler.

## 6. No tolerant free-text parsing on canonical paths

Tolerant-parser scan (reused from B2 over `core/.../domain/story/`,
`intelligence/.../story/`, incl. outline + runtime_handlers):
**0 violation(s)**.

## 7. Gate verdict

**`OUTLINE_GATE`: PASS (B-side evidence).**

- Golden: `outline_set_golden.json` (checksum
  `49c600d60f54cfee…`).
- Corpus results: `invalid_output_corpus_results.json` (beats + outline);
  checksums: `checksums.json`.
- Prompt manifest checksum: `02e0f550a7d76c64…`
  (11 prompts incl. `story.beats.generate` +
  `story.outline.structured`; B2 manifest refreshed).
- A-side (durable task execution + approval checkpoint) and C-side (beat/
  scene display fields) halves are co-signed by their plan owners at contract
  review.
