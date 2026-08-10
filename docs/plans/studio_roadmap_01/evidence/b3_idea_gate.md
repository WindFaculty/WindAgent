# B3 Evidence — IDEA_GATE

Gate owner: Plan B. Baseline: B1 ideation models/scoring/validators, B2 prompt
catalog + structured model boundary. Fixtures:
`fixtures/studio_contract_v0.1/story_ideation/` (corpus) and
`.../story_prompts/` (prompt manifest).

## 1. Idea generation prompt (B3 canonical, non-legacy)

- Prompt: `story.ideation.generate` v1.0.0 — schema-first JSON,
  `legacy=False`.
- Hash: `e5c9c9799df19dd1e9ee990ce8e43ff3c0e5ebe8a58cfc39ac2b52790a059b08`; output schema: `IdeaGenerationOutput.json`
  (3-5 candidates, required fields, age_fit/counts bounds, safety flag).
- Catalog invariants: **0 violation(s)**;
  registered prompt count: 9.

## 2. Golden candidate set (Vietnamese rabbit/kite, ages 5-8, 240s)

- Evaluated set: 4 candidates, rubric
  `score_rubric/v1`, recommendation
  `c_rabbit_kite`.
- Set content hash: `5ca950192beed9903862425998f47c925d7816343f5d641165bad08e50555e6f` (deterministic; idempotent
  same inputs reproduce it).
- Generation provenance sample: prompt id/version/hash, provider, finish
  reason, usage, repair_count — never raw content or reasoning.

## 3. Invalid-output corpus results (service + boundary)

Every case runs through `IdeaGenerationService` + `StoryModelBoundary` +
`FixtureModelPort`; results committed and re-verified by
`produce_b3_evidence.py --check` and `tests/contracts/test_story_b3_idea_gate.py`.

| Case | Outcome | Code | Issue codes | Repairs |
|---|---|---|---|---|
| `valid_4_candidates` | `ok` | `—` | — | 0 |
| `markdown_fenced_json` | `ok` | `—` | — | 1 |
| `too_few_candidates` | `error` | `STORY_SCHEMA_FAILURE` | — | 0 |
| `too_many_candidates` | `error` | `STORY_SCHEMA_FAILURE` | — | 0 |
| `missing_required_field` | `error` | `STORY_SCHEMA_FAILURE` | — | 0 |
| `duplicate_candidate_ids` | `error` | `IDEA_VALIDATION_FAILURE` | IDEA_DUPLICATE | 0 |
| `unsafe_candidate` | `error` | `IDEA_VALIDATION_FAILURE` | SAFETY_PROHIBITED | 0 |
| `age_fit_too_low` | `error` | `IDEA_VALIDATION_FAILURE` | SAFETY_AGE_UNSUITABLE | 0 |
| `prohibited_term_in_candidate` | `error` | `IDEA_VALIDATION_FAILURE` | SAFETY_PROHIBITED | 0 |
| `empty_response` | `error` | `STORY_EMPTY_RESPONSE` | — | 0 |
| `not_json` | `error` | `STORY_SCHEMA_FAILURE` | — | 0 |
| `unicode_vietnamese` | `ok` | `—` | — | 0 |
| `prompt_injection_in_field` | `ok` | `—` | — | 0 |

- Schema failures (count/required) come from the boundary BEFORE domain
  construction; domain failures (duplicates, safety, age fit, prohibited
  terms) are typed `IdeaValidationFailure` with stable issue codes.

## 4. Selection policy matrix (deterministic; selection is an A command)

| Policy | Evaluated | Auto-selection allowed |
|---|---|---|
| `AUTO_WHEN_POLICY_ALLOWS` | `True` | `True` |
| `HUMAN_REQUIRED` | `True` | `False` |
| `UNKNOWN_POLICY` | `True` | `False` |
| `AUTO_WHEN_POLICY_ALLOWS` | `False` | `False` |

- Unknown policy and unevaluated sets fail closed (never auto-select).
- `HUMAN_REQUIRED` always waits for the human; the A-side `SelectIdeaCommand`
  binds candidate_id + expected_content_hash (stale data is rejected there).

## 5. Handler surface

- Registered B3 handlers: `studio.story.idea.generate` (CreativeBrief ->
  IdeaCandidateSet), `studio.story.idea.evaluate` (IdeaCandidateSet -> scored
  IdeaCandidateSet) — matches `story_task_io.json`.
- No storage/queue/API imports in handlers; provider crossed only through
  `StoryModelBoundary`. Fixture provider rejected at certification
  (`assert_not_fixture`).

## 6. No tolerant free-text parsing on canonical paths

Tolerant-parser scan (reused from B2 over `core/.../domain/story/`,
`intelligence/.../story/`, incl. ideation + runtime_handlers):
**0 violation(s)**.

## 7. Gate verdict

**`IDEA_GATE`: PASS (B-side evidence).**

- Golden: `idea_candidates_golden.json` (checksum
  `d749525a0f4fe793…`).
- Corpus results: `invalid_output_corpus_results.json`; policy matrix:
  `selection_policy_matrix.json`; checksums: `checksums.json`.
- Prompt manifest checksum: `196e5d91841aeaad…` (5 prompts incl.
  `story.ideation.generate`; B2 manifest refreshed).
- A-side (durable task execution + approval command) and C-side (UI
  comparison fields) halves are co-signed by their plan owners at contract
  review.
