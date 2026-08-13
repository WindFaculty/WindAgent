# S2 Verification — Final Report

## 1. Executive Summary

```text
S2_SHA:             16602f3b777e103f7565dcfb44abf0682b0cb550
S2_FULL_SUITE:      PASS (no regression vs baseline: 3590 passed / 15 pre-existing failed / 36 skipped)
C7:                 FAIL (quality gate: language 0.80 < 0.85, PROVIDER_MODEL_QUALITY)
C8:                 NOT_RUN_BY_STOP_CONDITION
C9:                 NOT_RUN_BY_STOP_CONDITION
FINAL_VERDICT:      BLOCKED (case C: C7_PROVIDER_MODEL_QUALITY_BLOCKED)
```

## 2. S2 Full Regression (Phase B)

Command: `.venv/Scripts/python.exe -m pytest tests/ -p no:cacheprovider -q`

```text
passed:    3590   (S1 was 3588; +2 from new revise regression test)
failed:    15     (identical pre-existing baseline set, reproduced at a25f34d / S1 / S2)
skipped:   36
xfailed:   0
xpassed:   0
duration:  543.64s
exit code: 1 (15 pre-existing failures)
```

Failure classification: 15/15 = B (pre-existing baseline). Zero A (S1→S2 regression), zero C/D/E/F/G.
Full list: `artifacts/studio_roadmap_01/c7/s2_verification/s2_full_suite.json`.
Log: `.tmp/fullsuite-s2-16602f3.log`.

**The 16-failed S1 run belongs to S1 (37c6c64f); S2 full suite is 15 failed / 3590 passed — not copied from S1.**

## 3. S1 → S2 Diff Audit (Phase C)

`git log 37c6c64f..16602f3` = 1 commit: `fix(story): bounded revision sees full draft, not truncated digest`.

| File | Change | Why | Coverage | Risk |
|---|---|---|---|---|
| `intelligence/.../prompts/registry.py` | revise prompt v1.2.0: `draft_json` full JSON instead of 60-char scene digest; rule 2 now "keep passing content exactly as written" | Root cause: digest-only input regressed untouched content every revision (language 0.8→0.75) | test_review_service (new regression test asserts full dialogue text reaches rendered prompt), b2/b7 contract tests | Low; golden fixture regenerated deterministically |
| `intelligence/.../review/service.py` | revise invocation passes `draft.model_dump_json()` (braces escaped for format_map) | Same root cause | test_review_service (73 tests) | Low |
| `tests/contracts/test_story_b7_review_gate.py` | version assertion 1.1.0→1.2.0 | Prompt version bump | b7 contracts | None |
| `tests/unit/intelligence/story/test_review_service.py` | +1 regression test | Prove fix | itself | None |
| 8 fixture/checksum files | prompt manifest hash cascade | Deterministic regeneration | B2–B7 contract tests 199 passed | None |

Targeted suites covering the changed region: 73 (review/revise/prompts) + 199 (contracts) + 35 (certification scripts) = all green.

## 4. C7 Root Cause (Phase D)

**Is provider/model truly the blocker? YES.**

All 8 layers verified PASS with DB evidence (`.tmp/studio-c7/candidate-16602f3-20260812-173708.db`, read-only):

1. input integrity PASS — frozen scenario, full artifact chain, no truncation
2. prompt integrity PASS — revise receives ALL findings incl. language + full draft (S2 fix, regression-tested)
3. routing integrity PASS — route_attempts_v3: 11/11 success, no fallback/retry/error, no silent model swap
4. parser integrity PASS — both drafts parse + validate; repair_count 0
5. review loop PASS — language 0.80 < 0.85 → BLOCKING finding → REJECTED → REVISING (real provenance)
6. revise loop PASS — revision changed output (0 dialogue → 8 lines), new hash, non-empty diff
7. evaluator determinism PASS — threshold 0.85 constant, same policy both iterations, no post-hoc mutation
8. artifact freshness PASS — each review references its own draft; approvals bind correct revision+hash

Model output quality is the failing layer: revised dialogue is third-person narration attributed to characters (e.g. "Mèo Mướp dùng móng vuốt sắc bén, Gấu Trắng dùng sức mạnh to lớn…"). Reviewer's 0.8 language score is a fair assessment. Three independent runs: 0.80/0.80, 0.80/0.75, 0.80/0.80 — same ceiling.

## 5. Provider Qualification (Phase E)

Controlled benchmark = full C7 slice per candidate, frozen S2 product code, identical input/prompts/evaluator/threshold; only binding model differs (via S3 env override).

| Provider | Model | Runs | Language mean | Min | Max | Pass rate | Verdict |
|---|---|---|---|---|---|---|---|
| ollama-local | ornith:9b | 3 | 0.79 | 0.75 | 0.80 | 0/3 | BELOW_BAR |
| ollama-local | qwen3.5:latest | 1 | — | — | — | 0/3 attempts (ideation SAFETY_PROHIBITED ×2, SCHEMA_FAILURE ×1) | NOT_VIABLE |
| ollama-local (cloud) | deepseek-v4-flash:cloud | 0 | — | — | — | unavailable (subscription required) | NOT_AVAILABLE |

Ranking: 1. ornith:9b (only full-chain executor), 2. qwen3.5:latest, 3. deepseek-v4-flash:cloud.
No candidate meets qualification (3/3 PASS or ≥4/5 with mean language ≥ 0.85). No promotion.

## 6. Selected Candidate

None. No available model clears the gate without changing evaluator/threshold (prohibited).

## 7. Fresh C7 Rerun

NOT_RUN — no qualified candidate (see c7_rerun.json). C7(S2) remains FAIL with first_broken_hop `c7.public_vertical_slice` / quality workflow REVISION_REQUIRED.

## 8. C8/C9

```text
C8: NOT_RUN_BY_STOP_CONDITION
C9: NOT_RUN_BY_STOP_CONDITION
```

## 9. Repository State

```text
HEAD:            694362c741b2005632d5efc03898c02710f02386 (S3)
branch:          chore/cleanup-stale-md-docs
worktree:        clean (only untracked artifacts/studio_roadmap_01/c7/ evidence)
new commits:     S3 = S2 + harness env override (certification tooling only)
remote:          LOCAL_ONLY (S2/S3 not pushed; not a technical blocker)
```

## 10. Evidence Paths

```text
artifacts/studio_roadmap_01/c7/s2_verification/git_state.json
artifacts/studio_roadmap_01/c7/s2_verification/environment.json
artifacts/studio_roadmap_01/c7/s2_verification/s2_full_suite.json
artifacts/studio_roadmap_01/c7/s2_verification/c7_root_cause_matrix.json
artifacts/studio_roadmap_01/c7/s2_verification/provider_model_matrix.json
artifacts/studio_roadmap_01/c7/s2_verification/c7_rerun.json
artifacts/studio_roadmap_01/c7/s2_verification/c8_c9_status.json
artifacts/studio_roadmap_01/c7/s2_verification/final_verdict.json
.tmp/fullsuite-s2-16602f3.log
.tmp/studio-c7/candidate-16602f3-20260812-173708.db   (C7 S2 failed run, preserved)
.tmp/studio-c7/candidate-694362c-qwen35-200502.db    (qwen3.5 qualification run, preserved)
artifacts/studio_roadmap_01/c7/evidence.json + REAL_VERTICAL_SLICE_GATE_VERDICT.md (C7 S2 FAIL)
```

## 11. Remaining Blockers

- **provider/model**: no locally available model reaches language ≥ 0.85 on real Vietnamese screenplays (ornith:9b ceiling 0.80; qwen3.5:latest 9.7B fails ideation; deepseek-v4-flash:cloud subscription-gated). Unblock requires a stronger local model (e.g. ≥14B strong-Vietnamese) or an authorized cloud subscription.
- Pre-existing 15 baseline test failures: unrelated to C7 (documented, reproduced at a25f34d).
