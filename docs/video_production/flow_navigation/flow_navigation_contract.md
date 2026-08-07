# Flow Navigation Contract (Phase 13)

**Gate:** `VP13_FLOW_NAVIGATION_VERIFIED`
**Plan:** [04_phase_12_16_flow_browser_provider.md](../plans/04_phase_12_16_flow_browser_provider.md) §13–§15
**Location:** `tools/windagent_tools/google_flow/navigation.py`

## 1. Purpose

`FlowNavigator` drives the Flow UI from its observed state to `SUBMIT_READY`
using **typed bounded actions** through a `FlowUiPort`, and **never submits a
generation** in Phase 13 (plan 04 §15). It is fully testable with a fake
`FlowUiPort` — no Flow production is required.

## 2. FlowUiPort (typed UI boundary)

```python
class FlowUiPort(Protocol):
    async def observe(self) -> FlowUiObservation: ...
    async def act(self, action: FlowUiAction) -> str: ...  # evidence hash
```

- The navigator never executes a raw browser command — it emits
  `FlowUiAction(operation=..., target=...)` typed operations only
  (`open` / `click` / `fill` / `select` / `upload` / `read`).
- The Phase 12 bounded browser runtime (`tools/windagent_tools/browser/`)
  implements this port against the real agent-browser binary in a later
  phase; tests use a scripted fake.

## 3. Navigation flow (plan 04 §13.3)

```text
observe → classify
  ├── SIGNED_OUT          → FlowNavigationStateError (Phase 16 human state)
  ├── HUMAN_ACTION_REQUIRED → FlowNavigationStateError (paused)
  ├── UNKNOWN             → FlowNavigationDriftError (fail closed)
  └── READY
       1. open the correct project (open-before-create, §13.2)
       2. open create workspace            → EDITOR_READY
       3. configure generation (§13.3.2–5): mode, reference upload,
          compiled prompt, model, duration, aspect ratio
       4. read back visible config (§13.3.6)
       5. capture pre-submit evidence hash (§13.3.7)
       → SUBMIT_READY (receipt.submitted is always False)
```

## 4. Receipts and evidence

Every step produces a `FlowNavigationStep` with `snapshot_hash` (evidence
hash from the port), `from_state`, `to_state`, `ok`, `error_class`. The final
`FlowNavigationReceipt` carries:

- `session_id`, `project_id`
- `target_state` / `reached_state`
- per-step evidence
- `pre_submit_evidence_hash` (sha256 of the final URL+markers+controls)
- `submitted: False` — navigation never submits
- `ok: reached_state == target_state and not submitted`

## 5. Drift detection (plan 04 §13.5)

- A postcondition mismatch after an action raises `FlowNavigationDriftError`
  and stops navigation at `ERROR` / `HUMAN_ACTION_REQUIRED`.
- No blind retry clicks: exactly one action attempt per step.
- Sanitized observation evidence is attached to the error `details`.
- Duplicate label, locale mismatch, missing control and unapproved upload
  paths are all surfaced as typed drift/verification errors.

## 6. Out of scope for Phase 13

- Actual submission (Phase 14 pre-submit guard + submit).
- Download / candidate acquisition (Phase 14/15).
- Human login / captcha takeover (Phase 16).
