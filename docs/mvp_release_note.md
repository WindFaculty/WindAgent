# WindAgent MVP Release Note

**Version:** 0.10.0
**Date:** 2026-06-19
**Status:** MVP Release Candidate — vertical slice end-to-end works.

## What this is

A local-first desktop AI agent. You type a natural-language command in
a Windows app, an LLM planner turns it into a workflow, a runner
executes the workflow against the live Windows desktop via PyAutoGUI,
and you watch the steps happen in realtime with Pause/Resume/Stop
controls. Everything runs locally: no cloud calls, no telemetry, your
desktop and your commands never leave the machine.

## Demo in 60 seconds

```powershell
# Terminal 1 — backend (mock mode, no Ollama needed)
powershell -ExecutionPolicy Bypass -File scripts\dev_backend.ps1

# Terminal 2 — frontend
powershell -ExecutionPolicy Bypass -File scripts\dev_desktop.ps1

# Browser — open http://localhost:5173, click "New session", then send:
#   "Mở Notepad và gõ Hello from local AI agent."
# Watch the workflow panel populate with 2 steps and the chat show
# tool_call_finished events.
```

Full walkthrough: `README.md`.

## Tính năng đã có (Features in this build)

### Core agent loop
- [x] Natural-language input → workflow (Qwen3 4B via Ollama, or
      mock client for offline dev)
- [x] JSON validation + one-shot repair prompt + rule-based fallback
- [x] Sequential workflow runner with strict state machine
- [x] Realtime step status stream via WebSocket
- [x] Session / message / workflow / step / tool-call / event SQLite
      persistence

### Desktop control (PyAutoGUI adapter)
- [x] `open_app` — notepad, calc, mspaint, edge, explorer
- [x] `open_url` — opens URL in Edge (forced)
- [x] `type_text` — auto-paste for non-ASCII (Vietnamese), type for ASCII
- [x] `hotkey`, `press_key`, `click_xy`, `scroll`
- [x] `screenshot` — saves PNG artifact under
      `artifacts/runs/{session_id}/screenshots/`
- [x] `wait` — sleep step
- [x] `click_target` — GUI-grounded click stub (Phase 8 mock; full
      vision needs Phase 8 follow-up)

### User control
- [x] Stop — cancels remaining steps immediately
- [x] Pause / Resume — pause between steps, runner idle-spins
- [x] Retry — re-run from failed step
- [x] Realtime workflow panel with status icons (pending / running /
      success / failed / cancelled)

### Safety
- [x] Tool whitelist enforced at planner + executor boundary
- [x] No shell command passthrough; `open_app` is a closed list
- [x] Per-tool risk classification (safe / medium / high)
- [x] Permission dialog for `type_text` when
      `WINDAGENT_PERMISSION_CONFIRM_BEFORE_TYPE=1`
- [x] Every tool call audited in DB + JSONL file

### Persistence
- [x] `apps/backend/windagent.db` — sessions, messages, workflows,
      steps, tool calls, events
- [x] `artifacts/runs/{session_id}/events.jsonl` — portable audit
      trail (one JSON per line, append-only)
- [x] `artifacts/logs/backend.log` — uvicorn + app log (via
      `dev_backend.ps1`)
- [x] Restart backend → all history reloads from SQLite

### Packaging / dev experience
- [x] `scripts/dev_backend.ps1` — uv-managed FastAPI launcher,
      mock by default
- [x] `scripts/dev_desktop.ps1` — Vite + Tauri launcher
- [x] `scripts/healthcheck.ps1` — 11-item env + service check,
      CRIT/OPT/INFO + PASS/WARN/FAIL/SKIP
- [x] `README.md` — 5-step quick start
- [x] `docs/e2e_test_checklist.md` — pre-release smoke checklist
- [x] `docs/error_handling_audit.md` — every failure mode +
      where it's caught + how it's surfaced

### Test coverage
- [x] **184 backend tests** pass in ~45s (`uv run pytest`)
  - `test_api.py` — REST endpoints
  - `test_session_service.py` — session create / get / messages
  - `test_db_persistence.py` — SQLite round-trip
  - `test_event_bus.py` — pub/sub semantics
  - `test_event_jsonl.py` — JSONL audit writer (Phase 10)
  - `test_websocket.py` — live uvicorn WebSocket flow
  - `test_workflow_service.py` — intent parser + workflow creation
  - `test_workflow_runner.py` — Pause/Resume/Stop/Retry semantics
  - `test_tool_executor.py` + `test_tool_registry.py` +
    `test_tools_api.py` — tool pipeline
  - `test_permission_service.py` + `test_permissions_api.py` —
    Phase 7 permission gate
  - `test_model_client.py` + `test_planner_service.py` +
    `test_models_api.py` — Phase 4 planner
  - `test_click_target.py` + `test_gui_grounding.py` — Phase 8 stub
- [x] **19 frontend tests** pass in ~2s (`npm run test`)
  - `ChatPanel.test.tsx` — render + empty state + disabled
  - `WorkflowPanel.test.tsx` — render + null + populated
  - `ControlBar.test.tsx` — enable/disable + click handlers + API client
  - `sessionStore.test.ts` — reducer for events + plain actions
- [x] `npm run type-check` clean
- [x] `scripts/healthcheck.ps1` PASS on dev machine

## Tính năng chưa có (Out of scope for MVP)

These are intentionally deferred to post-MVP phases per
`ban_ke_hoach.md §Backlog`:

- GUI Actor vision thật (Qwen2.5-VL) — Phase 8 stub only
- Playwright browser automation
- Workflow editor (drag/drop, save template)
- Model manager UI (add / assign role / fallback)
- Plugin sandbox
- Multi-agent orchestration
- vLLM / llama.cpp context-64k
- Auto-update
- Tauri `.exe` bundle (Rust toolchain absent on dev machine; see Known issues)

## Known issues

| # | Issue | Workaround |
|---|---|---|
| 1 | `tauri build` fails: `cargo metadata: program not found` (no Rust toolchain on dev machine) | Run `scripts/dev_desktop.ps1` (Vite-only mode) for the MVP. Tauri bundle will be built on a Rust-capable machine. |
| 2 | `scripts/dev_desktop.ps1 -Tauri` flag sometimes hits `'tauri' is not recognized` due to PowerShell + npm + cmd.exe PATH propagation | Use `cd apps/desktop && npx tauri dev` from an interactive PowerShell. |
| 3 | PyAutoGUI requires an interactive desktop session; running the backend as a Windows service will fail at the first tool call that touches the screen | Run backend from a console session (RDP or local). |
| 4 | Mock mode records tool calls in memory only — there is no real screen interaction. The 2 demo phrases work; arbitrary commands only work with Ollama. | Use `-Mock:$false` after `ollama pull qwen3:4b-q4`. |
| 5 | SQLite `database is locked` can appear during teardown of the in-process WebSocket test (`test_pause_without_workflow_returns_404`) | Cosmetic; the test itself passes, the lock surfaces only during fixture cleanup. Will be fixed in a future pytest-asyncio / aiosqlite bump. |
| 6 | `wait` step blocks the runner thread for the configured seconds; Stop still works but other concurrent requests queue up | None — by design, intentional pause point for the user. |
| 7 | No disk-quota guard for `artifacts/runs/`; long sessions can fill disk | Operator's responsibility to monitor; add a logrotate-style cleanup later. |
| 8 | Repair prompt doubles worst-case planner latency on bad output | Acceptable for MVP; can add early-bail heuristic later. |
| 9 | `npm install` on Windows must use `--ignore-scripts` (esbuild postinstall chokes on the cmd.exe PATH) | The `dev_desktop.ps1` script already passes the flag. |

## Cách chạy demo (How to demo)

See `README.md §Hướng dẫn 5 bước`. Quick version:

```powershell
git clone <repo>
cd WindAgent
powershell -ExecutionPolicy Bypass -File scripts\healthcheck.ps1
# Expect: 7+ PASS, 0 FAIL (3 WARN OK: Ollama/Rust/Tauri optional)

# Terminal 1
powershell -ExecutionPolicy Bypass -File scripts\dev_backend.ps1

# Terminal 2
powershell -ExecutionPolicy Bypass -File scripts\dev_desktop.ps1

# Open http://localhost:5173 in your browser.
```

## Cách báo lỗi (How to report issues)

When filing an issue, include:

1. Output of `scripts/healthcheck.ps1` (paste the table).
2. Last 50 lines of `artifacts/logs/backend.log`.
3. If frontend: browser console (F12) errors + the exact URL you were on.
4. The `session_id` if you have one (visible in the StatusBar).
5. The exact command you sent to the agent.
6. The expected vs actual behaviour.

If the bug is reproducible without Ollama (i.e. in mock mode), say so —
it makes triage 10× faster.

For crash-class bugs, also attach the relevant lines from
`artifacts/runs/{session_id}/events.jsonl` (jq-friendly: `Get-Content
events.jsonl | ForEach-Object { $_ | ConvertFrom-Json }`).

## Acceptance criteria — final pass

Per `ban_ke_hoach.md §Phase 10 "Acceptance criteria cuối cùng cho MVP"`:

| Section | Criterion | Status |
|---|---|---|
| Core agent loop | User nhập lệnh tự nhiên từ UI | PASS |
| Core agent loop | Planner local Qwen3 4B tạo workflow JSON | PASS (with mock fallback) |
| Core agent loop | Workflow được validate | PASS (whitelist + Pydantic) |
| Core agent loop | Workflow chạy sequential | PASS |
| Core agent loop | Step status stream realtime | PASS (WebSocket) |
| Desktop control | Mở Notepad | PASS |
| Desktop control | Gõ text | PASS (ASCII + paste cho non-ASCII) |
| Desktop control | Mở Edge với URL | PASS |
| Desktop control | Screenshot artifact | PASS |
| User control | Stop | PASS |
| User control | Pause | PASS |
| User control | Resume | PASS |
| User control | Lỗi không crash app | PASS (runner exception path emits session_finished failed) |
| Local-first | Backend chạy local | PASS |
| Local-first | SQLite lưu local | PASS |
| Local-first | Qwen qua Ollama local | PASS (opt-in via `-Mock:$false`) |
| Local-first | Không gọi API cloud mặc định | PASS (mock + Ollama only) |
| Safety | Tool whitelist hoạt động | PASS |
| Safety | Không có shell command tự do | PASS |
| Safety | Permission event hoạt động | PASS |
| Safety | Audit log lưu tool call | PASS (DB + JSONL) |
| Persistence | Session được lưu | PASS |
| Persistence | Message được lưu | PASS |
| Persistence | Workflow step được lưu | PASS |
| Persistence | Tool call được lưu | PASS |
| Persistence | Event được lưu | PASS |
| Packaging/dev | Script chạy backend | PASS |
| Packaging/dev | Script chạy desktop | PASS |
| Packaging/dev | Healthcheck | PASS |
| Packaging/dev | README MVP | PASS |

**MVP verdict: SHIPPABLE** as a local-first demo + power-user tool.

## What's next (post-MVP backlog)

From `ban_ke_hoach.md §Backlog`:

- **P1** Workflow editor (drag/drop, save/load template)
- **P2** Model manager UI (add / assign role / fallback chain)
- **P3** GUI Actor thật (Qwen2.5-VL grounded clicks)
- **P4** Playwright browser automation
- **P5** Plugin / tool system with sandbox

## Credits

Phase 0–9 closeout reports:
- `artifacts/restructure_audit/phase{0..9}_closeout.md`
- `artifacts/restructure_audit/phase6_enhancement_closeout.md`

Specs:
- `docs/mvp_scope.md`
- `docs/event_protocol.md`
- `docs/api_contract.md`
- `docs/safety_policy.md`
- `docs/e2e_test_checklist.md` (new in Phase 10)
- `docs/error_handling_audit.md` (new in Phase 10)
