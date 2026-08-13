# Browser Runtime Contract (Phase 12)

**Gate:** `VP12_BROWSER_RUNTIME_VERIFIED`
**Plan:** `../../tools/windagent_tools/browser/` (plan 04 đã retired) §7–§10
**Location:** `tools/windagent_tools/browser/`

## 1. Purpose

`BrowserRuntime` is the durable, bounded browser worker for WindAgent. It owns
one persistent browser session mapped 1:1 to one Chrome profile, executes only
typed bounded operations, records redacted evidence for every action, and
classifies session health without ever touching external generation production (gate §10).

The runtime **extends the existing `tools/windagent_tools/browser/` boundary**
(`agent_browser.py` command runner, URL validation, audit redaction,
`state_encryption.py`, `state_manager.py`). No parallel runtime package exists.

## 2. Module map

| Module | Responsibility | Reuses |
|---|---|---|
| `action_policy.py` | typed allow/deny matrix (plan §8.4) | `validate_navigation_url` |
| `session.py` | session metadata, profile lock lease, registry | — |
| `evidence_capture.py` | redacted evidence records (§8.5) | `BrowserAuditLogger` |
| `healthcheck.py` | offline health classification (§8.5) | `domain_matches`, `validate_navigation_url` |
| `runtime.py` | bounded worker: policy gate + evidence + health + cancel + reattach | `AgentBrowserClient`, `SubprocessAgentBrowserProcess` |
| `agent_browser.py` (existing) | argv-based command runner, timeout, process-tree kill, URL policy | — |

## 3. Session and profile model (plan §8.3)

- One WindAgent `session_id` maps to exactly one Chrome profile.
- The profile **path never travels through a message queue or a domain
  event** — only the opaque `profile_key` appears in registry metadata.
- Profiles at rest use the existing `state_encryption.py` AES-GCM control.
- `BrowserProfileLock` is a file-based exclusive lock with a lease
  (default 30 min). A second worker acquiring the same profile while the
  lease is valid raises `BrowserProfileLockError` (collision).
- A stale lock (lease expired) can be broken; the new worker acquires a fresh
  lease.
- Session metadata: `owner`, `created_at`, `last_health_at`, `state`, `lease`.
- Closing/reopening the browser never loses WindAgent job mapping (a separate
  durable record owned by WindAgent).

## 4. Bounded action lifecycle

```
typed operation
      ↓
BrowserActionPolicy.evaluate()   (fail closed)
      ↓
BrowserHealthCheck              (session must be HEALTHY)
      ↓
dispatch to AgentBrowserClient   (typed op -> client method)
      ↓
BrowserEvidenceRecorder         (redacted record, always)
```

Every action writes evidence with `action_id`, `session_id`, `operation`,
`target_semantics` (sanitized), `started_at` / `finished_at`, `result_state`,
`redacted_screenshot_hash`, `snapshot_hash`, `error_class` — for SUCCESS,
BLOCKED, FAILED, CANCELLED and TIMED_OUT alike.

## 5. Timeout / cancel / cleanup (plan §8.2)

- Every command runs through the existing argv-based runner with a hard
  timeout (`action_timeout_seconds`, default 60 s).
- `asyncio.wait_for` bounds each typed action; a timeout raises
  `BrowserActionTimeoutError` and records `TIMED_OUT` evidence.
- Cancellation is safe: `asyncio.CancelledError` records `CANCELLED` evidence
  and the existing process-tree kill (`SubprocessAgentBrowserProcess`) reaps
  the CLI + Chrome daemon on Windows.
- `runtime.stop()` closes the browser session and releases the profile lock.

## 6. Worker restart and reattach (plan §8.5 / §9)

- `BrowserSessionRegistry` persists metadata under
  `{workspace_root}/artifacts/browser_sessions/browser_sessions.json`.
- `runtime.reattach()` re-acquires the profile lock lease and reopens the
  browser client for an already-registered session — used after a worker
  restart without losing the session identity or WindAgent job mapping.

## 7. Health contract (plan §8.5)

A session is `HEALTHY` only when **all** of:

1. worker process alive;
2. browser reachable (live `session_health()` probe, or fake in tests);
3. current page domain inside the allowlist;
4. profile lock lease valid;
5. session not in `HUMAN_REQUIRED` state (then `DEGRADED`).

An empty domain allowlist fails closed (nothing is allowed until the runtime
is explicitly configured with allowed domains).

## 8. Testability (gate §10)

No Chrome or external generation production is required: the runtime accepts a fake process
port (`AgentBrowserProcessPort`) and a fake client factory. Tests cover
timeout, cancel, lock collision, domain allowlist, deny-class operations,
evidence redaction, worker restart/reattach and health classification.

## 9. Out of scope for Phase 12

- Flow-era navigation/image/video generation/human takeover flows (retired
  with the Flow browser runtime).
- Raw model-generated browser commands are never accepted (plan §8.4).
