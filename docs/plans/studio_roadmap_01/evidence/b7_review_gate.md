# B7 Evidence — STORY_REVIEW_GATE

Gate owner: Plan B. Baseline: B1 review/revision/diff models + validators, B2
prompt catalog + structured model boundary, B6 structured screenplay.
Fixtures: `fixtures/studio_contract_v0.1/story_review/` (corpora/golden) and
`.../story_prompts/` (prompt manifest).

## 1. Review/revise prompts (B7 canonical, non-legacy)

- Prompt: `story.review.assess` v1.2.0 — schema-first JSON,
  `legacy=False`. Hash: `bd3218df8cdf43de647caa5c10fd0cf5676ba7c8bff421f8bdc6be9afe9ef2b3`; output schema:
  `ReviewOutput.json` (narrative/age_fit/language scores + notes). The model
  is a SECONDARY signal: deterministic findings stay the gate authority.
- Prompt: `story.revise.rewrite` v1.1.0 — schema-first JSON,
  `legacy=False`. Hash: `cbbf06fb9e37ef397d244280da0f02d5094117d280e3150462c1666cd7652d6d`; output schema:
  `ScreenplayRevisionOutput.json` (NEW immutable draft; same scene shape as
  generation).
- Catalog invariants: **0 violation(s)**;
  registered prompt count: 11.

## 2. Deterministic review policy (versioned, provider-free)

- Policy `review_policy/v1`: deterministic findings map from the screenplay
  validation suite into stable codes/dimensions (format, duration,
  continuity, beat_coverage, structure); model dimension threshold 0.5;
  scores below threshold become `MODEL_DIMENSION_SCORE` WARNING findings.
- Verdict: any BLOCKING -> `REVIEW_REQUIRED`; warnings only ->
  `PASS_WITH_WARNINGS`; clean -> `PASS`. Dimension scores: 0.0 (blocking),
  0.8 (warnings), 1.0 (clean) for deterministic dims; model scores verbatim.
- Aggregation: `aggregate_findings` dedupes by (code, location), orders by
  severity; `validate_review_report` / `validate_revision_proposal` /
  `validate_story_diff` keep every artifact self-consistent.

## 3. Golden loop trace (Vietnamese rabbit/kite, 240s)

- Clean review `report_draft_rabbit_kite_1_pass`: verdict **PASS**,
  0 findings, hash `d8e50550164f97e2…`.
- Weak review `report_draft_rabbit_kite_1_pass_with_warnings`: verdict **PASS_WITH_WARNINGS**
  (age_fit 0.4 < 0.5 -> `MODEL_DIMENSION_SCORE` warning), hash
  `4b84e78eefb9359e…`.
- Revision proposal `proposal_draft_rabbit_kite_2`: iteration
  2/3, accepted
  codes `['MODEL_DIMENSION_SCORE']`, bound to report
  `report_draft_rabbit_kite_1_pass_with_warnings`.
- Revised draft `draft_rabbit_kite_r2` (NEW id, old draft
  untouched), hash `7e0f33992a53ca22…`; diff
  `{'ADDED': 0, 'DELETED': 0, 'MODIFIED': 2, 'REORDERED': 0}` (2 modified dialogue lines).
- Provenance: prompt id/version/hash, provider, finish reason, usage,
  repair_count — never raw content or reasoning.

## 4. Invalid-output corpora results (services + boundary)

Every case runs through `ReviewService` / `ReviseService` +
`StoryModelBoundary` + `FixtureModelPort`; results committed and re-verified
by `produce_b7_evidence.py --check` and
`tests/contracts/test_story_b7_review_gate.py`.

### 4a. Review corpus

| Case | Outcome | Code | Verdict | Finding codes |
|---|---|---|---|---|
| `valid_scores` | `ok` | `—` | PASS | — |
| `markdown_fenced_json` | `ok` | `—` | PASS | — |
| `empty_response` | `error` | `STORY_EMPTY_RESPONSE` | — | — |
| `not_json` | `error` | `STORY_SCHEMA_FAILURE` | — | — |
| `missing_notes` | `error` | `STORY_SCHEMA_FAILURE` | — | — |
| `score_out_of_range` | `error` | `STORY_SCHEMA_FAILURE` | — | — |
| `score_below_threshold` | `ok` | `—` | PASS_WITH_WARNINGS | MODEL_DIMENSION_SCORE |
| `unicode_vietnamese_notes` | `ok` | `—` | PASS | — |
| `prompt_injection_note` | `ok` | `—` | PASS | — |

### 4b. Revise corpus

| Case | Outcome | Code | Diff summary |
|---|---|---|---|
| `valid_revision` | `ok` | `—` | {"ADDED": 0, "DELETED": 0, "MODIFIED": 2, "REORDERED": 0} |
| `markdown_fenced_json` | `ok` | `—` | {"ADDED": 0, "DELETED": 0, "MODIFIED": 2, "REORDERED": 0} |
| `empty_response` | `error` | `STORY_EMPTY_RESPONSE` | — |
| `not_json` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `missing_scenes` | `error` | `STORY_SCHEMA_FAILURE` | — |
| `same_draft_id` | `error` | `REVISE_VALIDATION_FAILURE` | — |
| `no_structural_change` | `error` | `REVISE_VALIDATION_FAILURE` | — |
| `domain_invalid_new_draft` | `error` | `REVISE_VALIDATION_FAILURE` | — |
| `budget_exhausted` | `error` | `REVISE_VALIDATION_FAILURE` | — |
| `unicode_vietnamese` | `ok` | `—` | {"ADDED": 0, "DELETED": 0, "MODIFIED": 3, "REORDERED": 0} |
| `prompt_injection_in_field` | `ok` | `—` | {"ADDED": 0, "DELETED": 0, "MODIFIED": 3, "REORDERED": 0} |

- Schema failures come from the boundary BEFORE domain construction; the
  revision loop refuses (typed `ReviseValidationFailure`): same draft id,
  empty structural change, domain-invalid new draft, or an exhausted
  iteration budget. No hidden mutation, no infinite loop.

## 5. Handler surface

- Registered B7 handlers: `studio.story.review` (ScreenplayDraft ->
  ReviewReport), `studio.story.revise` (Draft + Report -> Proposal + new
  Draft) — matches `story_task_io.json`.
- No storage/queue/API imports in handlers; provider crossed only through
  `StoryModelBoundary`. Fixture provider rejected at certification
  (`assert_not_fixture`). Approval/lock of the draft are A checkpoint
  commands, not these handlers.

## 6. No tolerant free-text parsing on canonical paths

Tolerant-parser scan (reused from B2 over `core/.../domain/story/`,
`intelligence/.../story/`, incl. review + runtime_handlers):
**0 violation(s)**.

## 7. Gate verdict

**`STORY_REVIEW_GATE`: PASS (B-side evidence).**

- Golden loop: `review_loop_golden.json` (checksum
  `d6089dd933e2ebb2…`) — clean
  PASS, warning-level findings, bounded revision with immutable diff.
- Corpus results: `invalid_output_corpus_results.json`; checksums:
  `checksums.json`.
- Prompt manifest checksum: `ae3a52c10941ee7e…`
  (11 prompts incl. `story.review.assess` +
  `story.revise.rewrite`; B2 manifest refreshed).
- A-side (durable task execution + approval checkpoint) and C-side
  (review/finding display fields) halves are co-signed by their plan owners
  at contract review.
