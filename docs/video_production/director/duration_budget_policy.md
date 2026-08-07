# Duration Budget Policy (Phase 8)

- **Gate:** `VP8_DIRECTOR_FOUNDATION_VERIFIED`
- **Owner:** `intelligence/windagent_intelligence/video/director/duration.py`
- **Policy version:** `1.0.0`

## 1. Principles (plan §9.2)

1. Total shot duration must lie within the production constraint
   (`creative_brief.target_duration_seconds` ± tolerance).
2. Dialogue duration must fit its shot — otherwise a
   `DIALOGUE_DURATION_MISMATCH` issue is raised. Dialogue is **never silently
   cut**.
3. Transition/handle duration is computed explicitly, never hidden.
4. Rounding rule and frame-rate assumption are versioned with the policy.

## 2. Assumptions

| Parameter | Value | Meaning |
|---|---|---|
| `frame_rate` | 24 fps | Shot durations round to the nearest frame. |
| `dialogue_chars_per_second` | 8.0 | Reading-rate assumption for dialogue duration (conservative, Latin/CJK tolerant). |
| `line_pause_seconds` | 0.4 | Per-line pause added to dialogue duration. |
| `handle_seconds` | 0.5 | Lead-in + tail per shot (2 × 0.5 = 1.0 s overhead). |
| `total_tolerance` | ±10% | DIR-REQ-001 invariant: total within `target ± 10%`. |
| transitions | CUT 0.0 / FADE 0.6 / DISSOLVE 0.8 / WIPE 0.6 / MATCH_CUT 0.4 | Explicit per-transition time. |

## 3. Computations

```
dialogue_duration(text) = round_to_frame(len(text) / chars_per_second + line_pause)

shot_with_handles(planned) = round_to_frame(planned + 2 * handle_seconds)

total_timeline = round_to_frame(
    sum(shot_with_handles(shot)) + sum(transition(prev->next))
)

in_budget(total, target) = target*(1-tol) <= total <= target*(1+tol)
```

## 4. Enforcement (fail-closed vs soft issue)

- **Unknown entity/reference, missing coverage, unbound dialogue** → typed
  `ValidationFailureError` (the plan is invalid — no partial plan).
- **Total outside budget** → `DURATION_OVERFLOW` issue (blocking) + proposal.
- **Dialogue longer than its shot** → `DIALOGUE_DURATION_MISMATCH` issue
  (blocking) + proposal; the dialogue line REMAINS bound to the shot.

## 5. Change procedure

Bumping any assumption (frame rate, reading rate, tolerance, transitions)
requires a new policy version. The policy version is recorded on every plan
(`plan.metadata.duration_policy_version`) so a policy change invalidates
downstream artifacts deterministically (Phase 18 invalidation semantics).
