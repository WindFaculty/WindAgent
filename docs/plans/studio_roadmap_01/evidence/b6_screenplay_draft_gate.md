# B6 Evidence — SCREENPLAY_DRAFT_GATE

Gate owner: Plan B. Baseline: B1 screenplay models/validators/adapters, B2
prompt catalog + structured model boundary, B4 canon, B5 outline. Fixtures:
`fixtures/studio_contract_v0.1/story_screenplay/` (corpus/golden/rendered
sample) and `.../story_prompts/` (prompt manifest).

## 1. Structured screenplay prompt (B6 canonical, non-legacy)

- Prompt: `story.screenplay.structured` v1.0.3 — schema-first JSON,
  `legacy=False` (canonical successor of the legacy `story.screenplay.write`
  TEXT prompt, which stays for the old pipeline). Hash: `a3f71de56fbf88dff090925ab2bf2129ede2ef955bf948efc288d0a49f5b2420`;
  output schema: `ScreenplayGenerationOutput.json` (3-12 scenes, action,
  dialogue with attribution, optional narration, transitions, per-scene
  timing, outline/beat/canon source refs).
- Structured JSON is the AUTHORITY; canonical screenplay text is a derived
  view rendered deterministically by `render_screenplay_text` (same draft ->
  same bytes; dialogue ordered by `order`; display names from canon).
- Catalog invariants: **0 violation(s)**;
  registered prompt count: 11.

## 2. Golden draft (Vietnamese rabbit/kite, ages 5-8, 240s)

- ScreenplayDraft `draft_rabbit_kite`: 4
  scenes, 7 dialogue lines, total
  240s / target
  240s — validation:
  **True** (blocking 0, warnings 0).
- Every draft scene traces to an outline scene (`s1`..`s4`), beat
  (`b1`..`b4`, full coverage), and canon IDs (characters/locations); dialogue
  attribution matches scene casts.
- Draft hash `dde24760a1963eec…`; rendered sample checksum
  `29b0d3e2046b6f2b…` (committed as `rendered_sample.txt`,
  SHA-256 `29b0d3e2046b6f2b…`).
- Provenance: prompt id/version/hash, provider, finish reason, usage,
  repair_count — never raw content or reasoning.

## 3. Invalid-output corpus results (service + boundary)

Every case runs through `ScreenplayGenerationService` +
`StoryModelBoundary` + `FixtureModelPort`; results committed and re-verified
by `produce_b6_evidence.py --check` and
`tests/contracts/test_story_b6_screenplay_gate.py`.

| Case | Outcome | Code | Issue codes |
|---|---|---|---|
| `valid_draft` | `ok` | `—` | — |
| `markdown_fenced_json` | `ok` | `—` | — |
| `empty_response` | `error` | `STORY_EMPTY_RESPONSE` | — |
| `not_json` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `missing_scenes` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `too_few_scenes` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `scene_without_content` | `error` | `SCREENPLAY_VALIDATION_FAILURE` | FIELD_EMPTY |
| `duplicate_scene_ids` | `error` | `SCREENPLAY_VALIDATION_FAILURE` | ID_STABILITY,ID_UNIQUE |
| `scene_order_not_starting_at_1` | `error` | `SCREENPLAY_VALIDATION_FAILURE` | ID_STABILITY,ORDER_SEQUENCE |
| `unknown_location_ref` | `error` | `SCREENPLAY_VALIDATION_FAILURE` | ID_STABILITY,REF_MISSING |
| `unknown_outline_scene_ref` | `error` | `SCREENPLAY_VALIDATION_FAILURE` | ID_STABILITY,REF_MISSING |
| `unknown_character_ref` | `error` | `SCREENPLAY_VALIDATION_FAILURE` | DIALOGUE_ATTRIBUTION,ID_STABILITY,REF_MISSING |
| `dialogue_attribution_mismatch` | `error` | `SCREENPLAY_VALIDATION_FAILURE` | DIALOGUE_ATTRIBUTION |
| `dialogue_scene_id_mismatch` | `error` | `SCREENPLAY_VALIDATION_FAILURE` | ID_STABILITY |
| `dialogue_empty_text` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `unknown_transition` | `error` | `SCREENPLAY_VALIDATION_FAILURE` | FORMAT_VALIDITY |
| `orphan_beat` | `error` | `SCREENPLAY_VALIDATION_FAILURE` | BEAT_COVERAGE,ID_STABILITY |
| `unknown_beat_ref` | `error` | `SCREENPLAY_VALIDATION_FAILURE` | BEAT_COVERAGE,ID_STABILITY |
| `duration_outside_180_300` | `error` | `SCREENPLAY_VALIDATION_FAILURE` | DURATION_BOUND,DURATION_SUM,ID_STABILITY |
| `unicode_vietnamese` | `ok` | `—` | — |
| `prompt_injection_in_field` | `ok` | `—` | — |

- Schema failures (missing array/required field, empty dialogue text, <3
  scenes) come from the boundary BEFORE domain construction; structure
  violations (order, duplicates, canon/outline refs, dialogue attribution,
  ID stability, transition format, beat coverage, duration) are typed
  `ScreenplayValidationFailure` with stable issue codes. Structure is never
  auto-fixed; warnings fail the gate too.

## 4. Formatting / duration / coverage (deterministic, versioned)

- Format: scene/order/ID stability (`ID_UNIQUE`, `ORDER_SEQUENCE`,
  `ID_STABILITY`), dialogue attribution (`DIALOGUE_ATTRIBUTION`), transition
  vocabulary (`FORMAT_VALIDITY`), empty-scene check (`FIELD_EMPTY`).
- Duration: formula `duration_formula/v1` (action + dialogue + narration +
  2.0s transition); bounds 180-300 s, default
  tolerance 15 s (`DURATION_BOUND` vs `DURATION_SUM` separated).
- Coverage: every beat referenced by >=1 scene and no unknown beat refs
  (`BEAT_COVERAGE`); outline scene and canon refs (`REF_MISSING`).
- Boundaries exercised in tests: 180/240/300 s targets, tolerance edges,
  rendered-text determinism, V2 conversion loss report (B1 adapters).

## 5. Handler surface

- Registered B6 handler: `studio.story.screenplay.generate` (EpisodeOutline
  -> ScreenplayDraft) — matches `story_task_io.json`. Canonical text is a
  derived view of the draft, never a model output.
- No storage/queue/API imports in handlers; provider crossed only through
  `StoryModelBoundary`. Fixture provider rejected at certification
  (`assert_not_fixture`). Approval/lock of the draft are A checkpoint
  commands, not this handler.

## 6. No tolerant free-text parsing on canonical paths

Tolerant-parser scan (reused from B2 over `core/.../domain/story/`,
`intelligence/.../story/`, incl. screenplay + runtime_handlers):
**0 violation(s)**.

## 7. Gate verdict

**`SCREENPLAY_DRAFT_GATE`: PASS (B-side evidence).**

- Golden: `screenplay_set_golden.json` (checksum
  `297ef40c5736d6fe…`).
- Rendered sample: `rendered_sample.txt` (deterministic derived text view).
- Corpus results: `invalid_output_corpus_results.json`; checksums:
  `checksums.json`.
- Prompt manifest checksum: `da41b029a78ecb4d…`
  (11 prompts incl. `story.screenplay.structured`;
  B2 manifest refreshed).
- A-side (durable task execution + approval checkpoint) and C-side (draft/
  text display fields) halves are co-signed by their plan owners at contract
  review.
