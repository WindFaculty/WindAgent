# WindAgent — Agent Session Recovery Audit (Giai đoạn 25)

**Date:** 2026-07-13
**Repository:** WindFaculty/WindAgent (D:/code_ca_nhan/WindAgent)
**Branch:** main  — HEAD `84b20698cdc9b582218250afd4f2f21926a03e5c`
**Scope:** Global session store, socket manager, backend persistence, refresh/reconnect recovery, multi-session UX.

---

## I. Audit environment (factual baseline)

| Item | Value |
|------|-------|
| Remote | https://github.com/WindFaculty/WindAgent.git |
| Branch | `main` |
| Starting HEAD | `84b20698cdc9b582218250afd4f2f21926a03e5c` |
| `git status --short` | 13 modified + 6 untracked (incl. new `agentSessionStore.ts`, `agentSocketManager.ts`, `SessionNavigator.tsx`, `agentSessionRecovery.test.ts`, migration `2222ab020b94`) |
| Migration head | `2222ab020b94` (recovery columns) |
| Migration current (live DB) | `1111fa010a93` — **live `windagent.db` is NOT migrated** |
| Frontend pkg mgr | npm (package-lock.json) |
| Backend runtime | FastAPI + uvicorn, SQLite (`sqlite+aiosqlite`) |
| Test DB | temp file per test via conftest (`?timeout=30`), isolated from production |

Untracked/modified audit-relevant files were NOT overwritten; only the two new
test files and two source fixes were added.

---

## II. Implementation audit answers

1. **Session state ownership** — `apps/desktop/src/state/agentSessionStore.ts`
   (Zustand, `persist` to localStorage key `wa-agent-sessions-v1`). Single source
   of truth: `sessionsById` / `sessionOrder` / `activeSessionId` / `draftBySessionId`.
   No React `useReducer`/`useState` owns session data (`useAgentSession.ts` is
   read-only facade).

2. **`AgentWorkspace` unmount resets session?** — NO. `App.tsx:418-420` keeps
   `AgentWorkspace` mounted via `display:none` on tab switch. `useAgentSession`
   cleanup body is empty (`useAgentSession.ts:55-58`); unmount never resets.

3. **WebSocket created where?** — `agentSocketManager._doConnect` →
   `connectWs` in `api/client.ts:400` (one `WebSocket` per sessionId).

4. **WebSocket closed when?** — Only on: `disconnect(reason)` (intentional),
   terminal session status (completed/cancelled/error/interrupted),
   `beforeunload` (app shutdown). NOT on component unmount.

5. **Registry per sessionId?** — YES. `agentSocketManager.registry:
   Map<sessionId, ConnectionEntry>` (`agentSocketManager.ts:59`).

6. **Connect de-dup?** — YES. `connect()` returns existing promise /
   `pendingConnectPromise` (`agentSocketManager.ts:82-98`).

7. **Event ID / sequence?** — YES. `EventEnvelope.seq` stamped in
   `EventBus.publish` (`event_bus.py:58-75`), per-session monotonic.

8. **Seq assigned frontend or backend?** — **Backend** (EventBus at publish time).

9. **Messages/tool calls idempotent upsert?** — YES. `appendMessage`/`upsertMessage`
   and `appendToolCall`/`upsertToolCall` keyed by id; reducer drops `seq <= last`.

10. **Backend persists session/messages/tool calls/workflow?** — YES:
    `SessionService` → `ChatSessionORM`/`MessageORM`/`ToolCallORM`; events →
    `ExecutionEventORM` via publisher hook (`event_hooks.py`).

11. **Refresh recovers via snapshot or localStorage?** — **Snapshot** path exists
    (`/sessions/{id}/snapshot`) but was **NOT wired into the frontend**
    (`fetchSessionSnapshot` defined in client.ts:104 but never called).
    Was the real refresh-loss bug — now fixed.

12. **Reconnect gets missed events how?** — Cursor replay: WS `?after_seq=N`
    (`websocket.py:71-88`) and REST `/sessions/{id}/events?after_seq=N`
    (`recovery_service.replay_after` reads `execution_events`).

13. **Multiple concurrent sessions?** — YES. `sessionsById` keyed by id; socket
    registry per id; isolation confirmed by test (events never cross sessions).

14. **close / cancel / archive / delete semantics?** — Distinct (verified by
    `test_cancel_archive_delete_have_distinct_semantics`): cancel=stop+keep,
    archive=hide+keep, delete=gone (404).

---

## III. Flow diagram (actual)

```
UI action (send / control)
  -> useAgentSession (facade)           [no state ownership]
  -> agentSessionStore (global Zustand)
  -> api/client (REST: /sessions/...)
  -> backend SessionService / router
  -> Database (ChatSessionORM/MessageORM/ToolCallORM)
  -> ExecutionService / Hermes bridge (execution)
  -> EventBus.publish (stamps seq, persists to execution_events)
  -> WebSocket endpoint (/ws/{sid})  -> agentSocketManager
  -> agentEventReducer (idempotent apply)
  -> agentSessionStore (single source of truth)
  -> React UI (narrow selectors)
```

---

## IV. Test results (real execution, not read-only)

### Baseline (before fixes)
- Backend existing suite: **459 passed** (incl. `test_websocket.py`, `test_session_service.py`, `test_phase7_durable_recovery.py`).
- Frontend existing suite: **59 passed** (`agentSessionStore.test.ts` 25, `sessionStore.test.ts` 11, others).

### New tests written & executed
- `apps/backend/tests/test_phase_g25_session_recovery.py` — **4 passed**
  (snapshot+seq, cursor replay, multi-session isolation, cancel/archive/delete).
- `apps/desktop/src/state/agentSessionRecovery.test.ts` — **15 passed**
  (2.1 unmount/remount, 2.3 normalization, 2.4 message dedup, 2.5 tool-call
  dedup, 2.6 persistence safety, 3.1 connect dedup, 3.2 unmount-safe socket,
  refresh recovery wiring).

### Full regression after fixes
- Backend: **463 passed** (0 failed).
- Frontend: **74 passed** (0 failed).

---

## V. Bugs found & fixed

| # | Severity | Bug | Evidence | Fix |
|---|----------|-----|----------|-----|
| 1 | HIGH | Frontend refresh loses in-memory session state: `hydrateSession` only called `fetchSession`+`fetchSessionMessages`; `fetchSessionSnapshot`/`fetchSessionEvents` never called, so page refresh could not restore tool calls / replay cursor. | `agentSessionStore.ts` `hydrateSession` (old: lines 551-553, no snapshot/events call); grep: `fetchSessionSnapshot` defined but 0 callers. | `hydrateSession` now fetches snapshot (messages+tool_calls+`last_event_sequence`) then cursor-replays missed events via `fetchSessionEvents`. Verified by new test. |
| 2 | MEDIUM | Backend snapshot under-reports replay cursor: `get_session_snapshot` read `chat_sessions.last_event_sequence`, which the **native** path never updates (only the Hermes bridge does) → always 0. | New test `test_snapshot_returns_messages_and_sequence` failed asserting `last_event_sequence >= 1` (got 0). | `session_service.py:get_session_snapshot` now reads authoritative max seq from `execution_events` via `RecoveryManager.seed_seq`. Test now passes. |

Both fixes are minimal and covered by new tests. No other defects found — the
store, socket manager, dedup, persistence, and isolation were all verified
correct by test.

---

## VI. Remaining observations (not blocking, no code change)

- **Live DB not migrated:** `alembic` current is `1111fa010a93`; migration
  `2222ab020b94` (recovery columns) is present but not applied to `windagent.db`.
  Test suite uses temp DBs (`create_all`), so tests pass; production needs
  `alembic upgrade head`.
- **Snapshot omits `agent_id`** even though `chat_sessions.agent_id` is stored
  (noted in test assertion). Harmless for recovery, but a navigator relying on
  snapshot would need it added.
- **Snapshot does not include `workflow`** (returns `null`); workflow is
  re-derived from the live event stream. Acceptable but documented.

---

## VII. Exit gate (Giai đoạn 2) — PASS

```
workspace unmount preserves state        PASS (test 2.1, 15/15)
tab switching preserves state            PASS (App.tsx display:none mount)
no unintended session recreation          PASS (store dedup, socket dedup)
messages deduplicated                     PASS (test 2.4)
tool calls deduplicated                  PASS (test 2.5)
local persistence safe                    PASS (test 2.6: nav-only, corrupt-JSON safe)
store is single source of truth          PASS (test 2.3)
```

## Exit gate (Giai đoạn 3) — PASS

```
connect deduplication                    PASS (test 3.1)
UI unmount does not close socket         PASS (test 3.2)
reconnect replays missed events          PASS (backend test_reconnect_replays...)
multi-session isolation                  PASS (backend test_multi_session_isolation)
```

**Overall: refresh/reconnect session-loss defects are FIXED and verified by
real backend + frontend integration tests. All 537 tests pass.**
