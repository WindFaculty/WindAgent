# C7 Google Provider Qualification — Final Report (S4 = 7984dbe)

Date: 2026-08-12 · Evidence: `artifacts/studio_roadmap_01/c7/google_qualification/`

## Verdict

```
GOOGLE_API = PASS

GEMINI_3_5_FLASH_LITE = AVAILABLE
GEMMA_4_31B = AVAILABLE

BEST_WRITER = gemma-4-31b-it
BEST_REVIEWER = gemma-4-31b-it
BEST_PAIR = Q2 (gemma writer + gemma reviewer)

WRITER_PASS_RATE = 4/4 valid runs (gemma) | 2/5 (gemini, no dialogue)
LANGUAGE_MEDIAN = 0.95 (gemma self) / 0.90 (gemma cross-reviewed by gemini)
LANGUAGE_MIN = 0.90
LANGUAGE_MAX = 0.95

REVIEWER_REPEAT_SPREAD = 0.0 (gemma) / 0.05 (gemini)

ORNITH_BASELINE_MEAN = ~0.79 (range 0.75-0.85, 0 dialogue lines)
GOOGLE_SELECTED_MEAN/MEDIAN = 0.95 (median, +0.16 over ornith mean)

QUALITY_IMPROVEMENT = REAL on quality, BLOCKED on stability

FRESH_C7 = FAIL (8 attempts: 2 genuine gate PASSes, 0 full harness PASS)
C8 = NOT_RUN_BY_STOP_CONDITION
C9 = NOT_RUN_BY_STOP_CONDITION

FINAL_VERDICT = BLOCKED
```

## 1. Model that writes Vietnamese best

**gemma-4-31b-it**, decisively. 7-12 natural spoken-Vietnamese dialogue lines
per draft, distinct character voices, age-appropriate, no repetition or
truncation. Cross-reviewed median 0.90 (by gemini) / 0.95 (self).
gemini-3.5-flash-lite wrote **zero dialogue lines in 4/4 valid runs** — the
same defect class as ornith:9b. Its self-review (0.85) of that output was
lenient; the stable gemma reviewer scored it 0.7. Cross-review (§9) was
exactly the mechanism that exposed it.

## 2. Most stable reviewer

**gemma-4-31b-it**: repeat spread 0.0 over 10 reviews of the fixed artifact
(mean 0.9, std 0.0). gemini-3.5-flash-lite: spread 0.05 (at the allowed
max), Vietnamese content-correlated notes. Both pass §10; gemma is preferred.

## 3. Best pairing

Q2 (gemma/gemma): median 0.95, min 0.90, pass 4/4 valid, reviewer spread
0.0. Q3 (gemma/gemini) also qualified (median 0.90). Q4 (gemini/gemma) fails
— the writer defect, not the reviewer. Selected pair = Q2; both roles bind
gemma-4-31b-it, which the current product path supports (one canonical per
route). Mixed-pair routing is a hardening-phase recommendation.

## 4. Does C7 genuinely pass 0.85?

**Quality: yes, twice.** Attempt 1: initial draft reviewed 0.7 → REJECTED →
genuine revision → re-review PASS (0 findings) → the unchanged gate accepted
it. Attempt 6: first-pass review PASS (0 findings) → lock → COMPLETED,
READY_FOR_PRODUCTION. ornith/qwen never reached any of this.

**Certification: no.** The frozen harness never produced a full PASS:
- attempts 2,3,5,7: a single HTTP 503 on gemma-4-31b-it killed the run
  (one bound endpoint; the coordinator's cooldown excludes it, so the next
  selection finds no survivor and the node fails after ONE transient).
- attempt 6: completed end-to-end but the first draft passed immediately →
  no revision cycle → the harness's mandatory revision-chain checks failed.
- attempt 8: screenplay generation exceeded the harness's 45-min deadline.
- attempt 4: bible failed deterministic SAFETY_AGE_UNSUITABLE (model
  variance; fail-closed worked).

## 5. S4 code changes (required, evidence-backed)

S4 = 6b8f35e, S4.1 = 580214f, S4.2 = 7984dbe:
1. Google adapter: use `ProviderRequest.prompt` (API rejected empty
   contents), auth via `x-goog-api-key` header — **the `?key=` query param
   leaked the credential into httpx URL logs and C7 evidence.json (6
   occurrences; scrubbed). Rotate the key.**
2. EndpointAdapterResolver: native `google` protocol (300s timeout).
3. StoryModelBoundary bounded repair: largest-valid-object first-brace scan
   (gemma emits commentary before JSON).
4. C7 harness: `WINDAGENT_STUDIO_PROVIDER_VENDOR=google` seeding (credential
   encrypted at rest), google preflight, launcher whitelist/redaction.
5. Lock lineage: `_lock_inputs` now ships the full 9-type package lineage
   (was MANIFEST_MISSING_REF — only reachable with a gate-passing model).
All with unit tests; ruff clean; 46 orchestration + 324 story/providers +
35 certification tests pass. No thresholds, prompts, evaluator, or frozen
input changed.

## 6. Remaining blocker

Provider reliability / integration, not model quality: gemma-4-31b-it's 503
rate on long generations (~50% at this load/hour) kills the single-endpoint
product path instantly; generation latency can also exceed the harness
deadline. Hardening recommendations (after C7, per §15/§18 policy):
in-endpoint transient backoff or a second Google binding for same-model
failover; per-role routing; median-review gate; key rotation.

**Answer to the qualification question:** gemma-4-31b-it is fully capable of
replacing ornith:9b on QUALITY (gate passed genuinely, twice), but the
Google provider path as wired today cannot deliver a STABLE certification
run — C7 stays BLOCKED until the 503/latency reliability problem is
hardened. No threshold was lowered.
