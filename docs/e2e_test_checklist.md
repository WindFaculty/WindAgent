# E2E manual test checklist — WindAgent MVP

This is the canonical pre-release smoke checklist. Run every item
once after `git pull` on a fresh Windows machine before declaring a
new MVP build "good". Each item points at the script/command you can
run to verify, and what to look for.

## 0. Environment

- [ ] `scripts/healthcheck.ps1` exits 0
  - Expect 7+ PASS under `[CRIT]`, 0 FAIL.
  - WARN under `[OPT]` for Ollama / Rust / Tauri is acceptable for MVP.

## 1. Backend bring-up

- [ ] `scripts/dev_backend.ps1` (or `scripts/dev_backend.ps1 -Mock:$true`)
      starts uvicorn on `127.0.0.1:8765`
- [ ] Tail `artifacts/logs/backend.log` — first lines should include
      `using MockModelClient` (or `using OllamaModelClient`) and
      `backend ready — db=...`
- [ ] `GET /health` returns `{"status":"ok","phase":1,"service":"windagent-backend"}`
- [ ] `GET /api/health` (through Vite proxy) returns the same shape

## 2. Session + workflow happy path (mock mode)

- [ ] `POST /sessions` returns 201 with a `session_id`
- [ ] `POST /sessions/{id}/messages` with `"Mở Notepad và gõ Hello"`
      returns 202 with `workflow_id` and `step_count: 2`
- [ ] `GET /sessions/{id}` shows `status: "completed"` after ~1s
- [ ] `GET /sessions/{id}/workflow` shows 2 steps with
      `tool_name` = `open_app` then `type_text`
- [ ] `GET /tools` returns exactly 10 tool names (the whitelist)
- [ ] `artifacts/runs/{session_id}/events.jsonl` exists and contains
      >= 5 lines (one per event published on the bus)

## 3. WebSocket realtime stream

- [ ] `wscat -c ws://127.0.0.1:8765/ws/{session_id}` (or any WS client)
      connects successfully
- [ ] Sending a new message streams `planning_started` ->
      `planning_finished` -> `workflow_created` -> `step_started` (x2)
      -> `step_completed` (x2) -> `session_finished` in order
- [ ] Each frame is a JSON envelope matching
      `docs/event_protocol.md` (`event`, `timestamp`, `data`)

## 4. Frontend render

- [ ] `scripts/dev_desktop.ps1` (or `npm run dev`) starts Vite on
      `localhost:5173`
- [ ] Open `http://localhost:5173` — header shows
      "WindAgent — Local Desktop AI Agent"
- [ ] Chat panel renders the empty-state hint
- [ ] Click "New session" (or send any message) — session id appears
      in the status bar
- [ ] Type `"Mở Notepad và gõ Hello"` and press Send — workflow
      panel populates with 2 steps, both transition
      `pending → running → success`
- [ ] Tool call log (under chat) shows `open_app` and `type_text`
      with status `success` and a duration in ms

## 5. User controls (Stop / Pause / Resume / Retry)

- [ ] Send a longer message (e.g. "Mở Notepad, gõ Hello, chờ 3s,
      gõ World"). During the `wait` step, click **Pause**
      — the workflow halts at the next step boundary
- [ ] Click **Resume** — workflow continues
- [ ] Click **Stop** while running — remaining steps are marked
      `cancelled`, `session_finished.final_status == "cancelled"`
- [ ] Manually induce a tool failure (or wait for one in the real
      GUI) — Retry button enables; click it — workflow reruns from
      the failed step

## 6. Persistence

- [ ] `apps/backend/windagent.db` contains rows for the test session
      (`SELECT COUNT(*) FROM chat_sessions` returns >= 1)
- [ ] `apps/backend/windagent.db` execution_events table mirrors
      every envelope from the WS stream
- [ ] Stop the backend (`Ctrl+C`), restart it, then `GET /sessions/{id}`
      — still returns the same session (loaded from SQLite)
- [ ] `artifacts/runs/{session_id}/events.jsonl` still contains the
      full event timeline (independent of SQLite)

## 7. Safety

- [ ] `POST /sessions/{id}/messages` with content `"delete all my
      files"` — workflow is rejected (`step_count: 0`, planner falls
      back to rule-based parser which finds no match)
- [ ] In `WINDAGENT_PERMISSION_CONFIRM_BEFORE_TYPE=1`, sending a
      `type_text` step triggers a `permission_request` event and the
      UI dialog appears
- [ ] Clicking **Cancel** in the dialog marks the step `cancelled`
      and the workflow continues with the next step
- [ ] Clicking **Allow** runs the step normally

## 8. Cleanup

- [ ] `Ctrl+C` in the backend terminal — process exits within 5s
      (no hung uvicorn worker)
- [ ] `Ctrl+C` in the Vite terminal — process exits within 5s
- [ ] `scripts/healthcheck.ps1` still PASSes after restart

## Sign-off

```
Tester:    _______________
Date:      2026-__-__
Build:     v0.x.y (commit sha: ________)
Result:    [ ] PASS  [ ] PASS with notes  [ ] FAIL
Notes:
```

If any item fails, copy the relevant log line from
`artifacts/logs/backend.log` or the dev-server terminal into the
issue tracker, and reference `docs/mvp_release_note.md` §"Known
issues" before opening a bug — the failure may already be known.
