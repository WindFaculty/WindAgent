# Flow UI State Machine (Phase 13)

**Gate:** `VP13_FLOW_NAVIGATION_VERIFIED`
**Plan:** [04_phase_12_16_flow_browser_provider.md](../plans/04_phase_12_16_flow_browser_provider.md) §12
**Location:** `tools/windagent_tools/google_flow/state_machine.py`

## 1. Purpose

`FlowUiStateMachine` models the observable Google Flow UI as a typed,
deterministic state machine. Classification never relies on a single
selector: a state is inferred from the URL + semantic markers + visible
controls together (plan 04 §12). No browser or network call happens while
classifying — the machine is fully offline and deterministic.

## 2. States (11)

```text
UNKNOWN
SIGNED_OUT
READY
PROJECT_OPEN
EDITOR_READY
CONFIGURED
SUBMIT_READY
GENERATING
RESULT_READY
ERROR
HUMAN_ACTION_REQUIRED
```

## 3. Transitions

Every `FlowStateTransition` carries (plan 04 §12):

| Field | Meaning |
|---|---|
| `name` | stable transition id (e.g. `ready_to_project_open`) |
| `from_state` / `to_state` | typed `FlowUiState` pair |
| `precondition` | observable precondition (semantic) |
| `bounded_action` | typed bounded action name — never a raw command |
| `postcondition` | observable postcondition |
| `timeout_seconds` | bounded timeout for the action |
| `retry_classification` | `RETRYABLE` (transient) vs `NOT_RETRYABLE` (deterministic → fail closed) |
| `evidence` | evidence contract (default `snapshot_hash`) |
| `recovery_state` | optional recovery / human state |

Built-in transitions:

```text
SIGNED_OUT    → READY          (account_ready_check, NOT_RETRYABLE)
READY         → PROJECT_OPEN   (open_project, RETRYABLE)
READY         → PROJECT_OPEN   (create_project, NOT_RETRYABLE)
PROJECT_OPEN  → EDITOR_READY   (open_create_workspace, RETRYABLE)
EDITOR_READY  → CONFIGURED     (configure_generation, NOT_RETRYABLE)
CONFIGURED    → SUBMIT_READY   (read_back_config, NOT_RETRYABLE)
SUBMIT_READY  → GENERATING     (submit_generation — Phase 14 approval flow)
GENERATING    → RESULT_READY   (poll_result, RETRYABLE)
```

The `SUBMIT_READY → GENERATING` transition exists in the machine table for
Phase 14, but **Phase 13 navigation never executes it** — the navigator stops
at `SUBMIT_READY` and captures pre-submit evidence.

## 4. Classification rules

`classify(observation)` applies the most-specific rule first:

1. `HUMAN_ACTION_REQUIRED` — captcha / "verify you are human" / email check markers
2. `ERROR` — error markers + a visible retry control
3. `SIGNED_OUT` — sign-in markers on the canonical domain
4. `RESULT_READY` — result/candidates markers + download control
5. `GENERATING` — generating/in-progress markers
6. `SUBMIT_READY` — submit/generate control, not in configured marker state
7. `CONFIGURED` — configured marker + submit/generate control
8. `EDITOR_READY` — editor URL / create marker / workspace control
9. `PROJECT_OPEN` — project URL + canvas/create/open signals
10. `READY` — canonical domain + create/import control
11. `UNKNOWN` — no rule matched (fail closed)

A URL alone is never sufficient — the unit test
`test_state_machine_never_single_signal` proves a bare URL classifies as
`UNKNOWN`.

## 5. Contract

- 11 states exactly; ≥ 8 transitions, each with all seven transition fields.
- Deterministic and offline: no subprocess, no network, no sys.path mutation.
- Multi-signal classification (URL + markers + controls).
