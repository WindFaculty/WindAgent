# Flow Pre-Submit Guard (Phase 14)

**Gate:** `VP14_FLOW_IMAGE_GENERATION_VERIFIED`
**Plan:** [04_phase_12_16_flow_browser_provider.md](../plans/04_phase_12_16_flow_browser_provider.md) §18.1
**Location:** `tools/windagent_tools/google_flow/pre_submit_guard.py`

## 1. Purpose

`PreSubmitGuard` is the fail-closed gate that runs immediately before any
submit click (plan 04 §18.1). A single failed condition blocks the submit —
the generator raises `FlowPreSubmitBlockedError` and **no click is issued**.

## 2. Conditions (plan 04 §18.1)

| Condition | Check |
|---|---|
| request schema / hash | `request_hash` is 64-hex sha256; project/revision present |
| project mapping healthy | WindAgent ↔ Flow project mapping exists & verified |
| session healthy | browser session HEALTHY |
| references approved | required references are APPROVED (per role) |
| upload hash matches | reference upload hash matches the canonical store |
| operation supported | provider capability matrix contains the operation |
| candidate limit | `1 <= candidate_limit <= max_candidates` (default 8) |
| cost/quota policy | `max_cost_credits` within policy or explicit test approval |
| pre-submit evidence | pre-submit screenshot/evidence hash exists (§13.3.7) |

## 3. Result

```python
PreSubmitVerdict(ok: bool, reasons: tuple[str, ...])
```

`ok == False` → the generator never reaches the submit click. Reasons are
typed and deterministic (fail closed, plan §18.1).

## 4. Contract

- Deterministic and offline (no browser call during the guard).
- `FlowPreSubmitBlockedError.reasons` records every blocking condition.
