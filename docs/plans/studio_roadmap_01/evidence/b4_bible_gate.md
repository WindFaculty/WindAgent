# B4 Evidence — STORY_BIBLE_GATE

Gate owner: Plan B. Baseline: B1 canon models/validators, B2 prompt catalog +
structured model boundary, B3 ideation. Fixtures:
`fixtures/studio_contract_v0.1/story_bibles/` (corpus/golden/matrix) and
`.../story_prompts/` (prompt manifest).

## 1. Bible generation prompt (B4 canonical, non-legacy)

- Prompt: `story.bibles.generate` v1.1.0 — schema-first JSON,
  `legacy=False`.
- Hash: `8fbc297e38504e032f5db0ed2539c1e224711703b0577a63e7a6423eb7a4c234`; output schema: `BibleGenerationOutput.json`
  (story_bible + world_bible + character_canon required; nested rule/location/
  object/character/relationship shapes).
- Catalog invariants: **0 violation(s)**;
  registered prompt count: 11.

## 2. Golden bible set (Vietnamese rabbit/kite, ages 5-8, 240s)

- `bible_rabbit_kite` / `world_rabbit_kite` /
  `canon_rabbit_kite` — generated from selected idea
  `c_rabbit_kite`.
- Set content hash: `ba186c5334b51ee760fa344e837a56438806fc0369ffb82ee3ce0a98776cde1c` (deterministic; idempotent
  same inputs reproduce it). Per-artifact hashes:
  `be395a3c7205b71e…` / `8bc657275bbc75d4…` /
  `7142bc363c31ac74…`.
- Cross-validation: **True** (blocking 0,
  warnings 0, info 0; codes
  —).
- Generation provenance sample: prompt id/version/hash, provider, finish
  reason, usage, repair_count — never raw content or reasoning.

## 3. Invalid-output corpus results (service + boundary)

Every case runs through `BibleGenerationService` + `StoryModelBoundary` +
`FixtureModelPort`; results committed and re-verified by
`produce_b4_evidence.py --check` and `tests/contracts/test_story_b4_bible_gate.py`.

| Case | Outcome | Code | Issue codes |
|---|---|---|---|
| `valid_full_set` | `ok` | `—` | — |
| `markdown_fenced_json` | `ok` | `—` | — |
| `empty_response` | `error` | `STORY_EMPTY_RESPONSE` | — |
| `not_json` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `missing_world_bible` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `empty_character_name` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `duplicate_character_ids` | `error` | `BIBLE_VALIDATION_FAILURE` | ID_UNIQUE |
| `duplicate_character_names` | `error` | `BIBLE_VALIDATION_FAILURE` | DUPLICATE_NAME |
| `relationship_self_loop` | `error` | `BIBLE_VALIDATION_FAILURE` | RELATIONSHIP_CYCLE |
| `relationship_unknown_character` | `error` | `BIBLE_VALIDATION_FAILURE` | REF_MISSING |
| `age_band_outside_audience` | `error` | `BIBLE_VALIDATION_FAILURE` | SAFETY_AGE_UNSUITABLE |
| `duplicate_world_rule_id` | `error` | `BIBLE_VALIDATION_FAILURE` | ID_UNIQUE |
| `world_rule_conflict` | `error` | `BIBLE_VALIDATION_FAILURE` | WORLD_RULE_COMPLIANCE |
| `unicode_vietnamese` | `ok` | `—` | — |
| `prompt_injection_in_field` | `ok` | `—` | — |

- Schema failures (missing artifact/empty required field) come from the
  boundary BEFORE domain construction; canon violations (duplicate IDs/names,
  relationship cycles, missing refs, world-rule conflicts, age/safety) are
  typed `BibleValidationFailure` with stable issue codes. Canon is never
  auto-mutated.

## 4. Cross-validation matrix

| Dimension | Outcome | Issue codes |
|---|---|---|
| `empty_response` | `error` | STORY_EMPTY_RESPONSE |
| `not_json` | `error` | STORY_SCHEMA_FAILURE |
| `missing_world_bible` | `error` | STORY_SCHEMA_FAILURE |
| `empty_character_name` | `error` | STORY_SCHEMA_FAILURE |
| `duplicate_character_ids` | `error` | ID_UNIQUE |
| `duplicate_character_names` | `error` | DUPLICATE_NAME |
| `relationship_self_loop` | `error` | RELATIONSHIP_CYCLE |
| `relationship_unknown_character` | `error` | REF_MISSING |
| `age_band_outside_audience` | `error` | SAFETY_AGE_UNSUITABLE |
| `duplicate_world_rule_id` | `error` | ID_UNIQUE |
| `world_rule_conflict` | `error` | WORLD_RULE_COMPLIANCE |
| `valid_set` | `ok` | — |

## 5. Handler surface

- Registered B4 handler: `studio.story.bible.generate` (SelectedIdea ->
  StoryBible + WorldBible + CharacterCanon) — matches `story_task_io.json`.
- No storage/queue/API imports in handlers; provider crossed only through
  `StoryModelBoundary`. Fixture provider rejected at certification
  (`assert_not_fixture`). Approval of the generated set is an A checkpoint
  command, not a handler.

## 6. No tolerant free-text parsing on canonical paths

Tolerant-parser scan (reused from B2 over `core/.../domain/story/`,
`intelligence/.../story/`, incl. bibles + runtime_handlers):
**0 violation(s)**.

## 7. Gate verdict

**`STORY_BIBLE_GATE`: PASS (B-side evidence).**

- Golden: `bible_set_golden.json` (checksum
  `114072a2eb4ceb5a…`).
- Corpus results: `invalid_output_corpus_results.json`; matrix:
  `cross_validation_matrix.json`; checksums: `checksums.json`.
- Prompt manifest checksum: `363b3e5acadbc0ea…`
  (11 prompts incl. `story.bibles.generate`;
  B2 manifest refreshed).
- A-side (durable task execution + approval checkpoint) and C-side (bible
  display fields) halves are co-signed by their plan owners at contract
  review.
