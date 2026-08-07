# Flow Project Mapping (Phase 13)

**Gate:** `VP13_FLOW_NAVIGATION_VERIFIED`
**Plan:** [04_phase_12_16_flow_browser_provider.md](../plans/04_phase_12_16_flow_browser_provider.md) §13.2
**Location:** `tools/windagent_tools/google_flow/project_manager.py`

## 1. Purpose

`FlowProjectManager` owns the durable WindAgent ↔ Google Flow project
mapping and its two-signal verification (plan 04 §13.2). It is deterministic
and offline — verification uses signals supplied by the caller (the UI port)
or a fake in tests.

## 2. Durable mapping

```text
project_id                 (WindAgent project identity)
production_revision_id
flow_project_id
flow_project_url_or_stable_locator
browser_session_id
last_verified_at
mapping_status
display_name               (never the sole identity)
```

Persisted as JSON under `{state_dir}/flow_project_mappings.json`.

## 3. Rules (plan 04 §13.2)

1. **Open before create** — `open_before_create` opens an existing project
   when a mapping exists; only creates when no mapping exists.
2. **Two-signal verification** — `verify_two_signals` confirms the correct
   project only when at least **two** independent expected signals appear in
   the observed signals. Fewer matches raise `FlowProjectVerificationError`.
3. **Display name is not identity** — `display_name` is deliberately excluded
   from the expected signal set; a display name alone can never verify.
4. **Missing project is a typed failure** — a `MISSING` mapping raises
   `FlowProjectMissingError`; WindAgent never auto-creates a replacement
   project and silently continues.

## 4. Statuses

```text
UNVERIFIED   initial mapping created
VERIFIED     confirmed by >= 2 independent signals
MISSING      project deleted/lost — typed failure, no auto-replace
STALE        (reserved) lease/age based staleness
ERROR        unexpected state
```

## 5. Contract

- Mapping survives reload (JSON persistence round-trip).
- Verification is commutative with reloads.
- Expected signals = `flow_project_id` + `flow_project_url` (when present);
  `display_name` is never a signal.
