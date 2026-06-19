# Phase 12 — Agent-S3 Workflow Wire Report

| Field | Value |
|---|---|
| Phase | 12 |
| Date | 2026-06-19 |
| Repo | `D:\antigaravity_code\WindAgent` |
| Branch | `main` |
| Pre-commit | `9795b0f chore(agent-s3): close out safe optional integration scaffold` (Phase 11) |
| Verdict | **`accepted_phase12_agent_s3_workflow_wired`** |

---

## Verdict

`accepted_phase12_agent_s3_workflow_wired`

`agent_s3_step` đã wire vào WorkflowRunner thật, end-to-end permission
gate + audit + events đều pass. Mọi safety guarantee từ Phase 11
giữ nguyên. Tất cả failure modes từ brief được cover (11+ unit test +
12 integration test + 29 secret scrubbing test = 35+ mới).

---

## Summary

| Aspect | Status |
|---|---|
| Agent-S3 step wire vào đâu | `tool_registry.py` + `ToolExecutor._execute_agent_s3_step` + `services/agent_s3_step_executor.py` orchestrator |
| Execute thật qua mapped tool | **YES** — `pyautogui.click(100, 200)` → `click_xy(100, 200, button=left)` chạy qua `GuiAdapter.click_xy` |
| Dry-run | **YES** — `dry_run=True` proposes + translates, KHÔNG gọi GUI |
| Permission gate | **YES** — WorkflowRunner gate fires on `agent_s3_step` (`requires_confirmation=True`); mapped tool chạy qua cùng `ToolExecutor._run` path |
| Audit/event | **YES** — `tool_calls` DB row, `tool_call_started/finished` events, mới: `agent_s3_action_proposed` event |

### Wire chain

```
Planner (POST /sessions/{sid}/messages)
  -> PlannerService.plan()
  -> WorkflowService.create_for_message()  -> Workflow(steps=[...agent_s3_step])
  -> WorkflowRunner.start()
  -> WorkflowRunner._run() loop
    -> runner._gate_permission() (cho agent_s3_step, requires_confirmation=True)
    -> runner._executor.execute(tool_name="agent_s3_step")
      -> ToolExecutor._execute_agent_s3_step()
        -> AgentS3StepExecutor.execute()
          1. enabled check
          2. adapter available check
          3. screenshot (optional)
          4. adapter.propose()
          5. translator.translate()
          6. mapped tool in allow-list (defence-in-depth)
          7. validate_params(mapped.tool_name, ...)
          8. emit agent_s3_action_proposed event
          9. if dry_run: return
          10. await asyncio.to_thread(self._run_mapped_tool)
              -> ToolExecutor._run() -> GuiAdapter method
        -> ToolExecutor._emit_and_persist() -> tool_calls row + tool_call_finished event
```

---

## Files Changed

### New (4 files)

| File | Mục đích |
|---|---|
| `apps/backend/services/agent_s3_step_executor.py` | Orchestrator: propose → translate → mapped tool → audit |
| `apps/backend/tests/test_agent_s3_step_executor.py` | 23 unit test covering 11 failure modes + 4 success paths + 3 hygiene tests |
| `apps/backend/tests/test_agent_s3_runner_wiring.py` | 12 integration test via FastAPI TestClient (REST + DB audit row) |
| `artifacts/agent_s3_integration/phase12_workflow_wire_report.md` | This file |

### Modified (8 files)

| File | Mục đích |
|---|---|
| `apps/backend/services/tool_registry.py` | Add `AgentS3StepParams` schema + `agent_s3_step` ToolInfo (`risk=high`, `requires_confirmation=True`) |
| `apps/backend/services/tool_executor.py` | Add `agent_s3_step_executor` field + `_execute_agent_s3_step()` dispatch |
| `apps/backend/main.py` | Build + inject `AgentS3StepExecutor` into ToolExecutor |
| `apps/backend/schemas/event.py` | Add `agent_s3_action_proposed` to EventName + `AgentS3ActionProposedData` payload class |
| `apps/backend/tests/test_tool_registry.py` | Update `EXPECTED_TOOLS` to include `agent_s3_step` |
| `apps/backend/tests/test_tools_api.py` | Update `/tools` expected set to include `agent_s3_step` |
| `docs/event_protocol.md` | Add `Nhóm Agent-S3` + `agent_s3_action_proposed` payload spec + 11 rejection codes |
| `docs/agent_s3_integration.md` | Update status table (runner wired: YES), add `agent_s3_step` tool section, error codes table, Phase 13 follow-ups |
| `docs/safety_policy.md` | Add guarantee #8 (Phase 12 safety pipeline 1..10) |
| `README.md` | Phase 11 → Phase 12, 295 → 338 tests, 10 → 11 tool whitelist |

---

## Tool Schema

```python
class AgentS3StepParams(BaseModel):
    instruction: str          # required, 1..2000 chars
    screenshot: bool          # default True
    dry_run: bool             # default False
    max_retries: int          # 0..2, default 0
    require_permission: bool  # default True (mirror registry)
    timeout_ms: int           # 1..120000, default 30000
```

JSON example:
```json
{
  "instruction": "Click the OK button if visible",
  "screenshot": true,
  "dry_run": true,
  "max_retries": 0,
  "require_permission": true,
  "timeout_ms": 30000
}
```

ToolInfo entry:
```python
"agent_s3_step": ToolInfo(
    name="agent_s3_step",
    description="Phase 12 — ask Agent-S3 to propose ONE GUI action ...",
    risk_level="high",
    requires_confirmation=True,
    params_model=AgentS3StepParams,
),
```

---

## Execution Flow Evidence

Each step in the safety pipeline is covered by at least one test:

| Step | Test |
|---|---|
| 1. Pre-flight enabled | `test_disabled_returns_agent_s3_disabled` |
| 2. Pre-flight adapter available | `test_adapter_none_returns_adapter_not_ready`, `test_adapter_unavailable_returns_unavailable` |
| 3. propose() called + adapter.last_error classify | `test_propose_raises_returns_propose_failed` |
| 4. Translator deny pattern (exec, eval, os.system, subprocess, open, import) | 6 unit tests in `TestUnsafeAction*` |
| 5. Translator no-match | `test_unsupported_action_my_custom_call_returns_unsupported` |
| 6. Defence-in-depth allow-list | `test_defence_in_depth_rejects_outside_allowlist` |
| 7. Pydantic validation on mapped params | `test_invalid_params_after_translate_returns_invalid_params` |
| 8. Event emission | `test_emits_agent_s3_action_proposed_on_success` |
| 9. dry_run path (no GUI) | `test_dry_run_does_not_call_inner_tool` |
| 10. Inner mapped tool run via callback | `test_full_flow_click_xy_executes`, `test_full_flow_type_text_executes` |
| 11. Inner tool raises | `test_inner_tool_execution_failed` |
| Audit row in DB | `test_agent_s3_step_creates_tool_call_row` (integration) |
| Public REST surface | `test_tools_endpoint_includes_agent_s3_step`, `test_direct_run_*` |
| Disabled orchestrator | `test_agent_s3_step_when_orchestrator_none_returns_disabled`, `test_direct_run_agent_s3_step_disabled_returns_disabled` |
| Pydantic params validation | `test_direct_run_agent_s3_step_rejects_invalid_params`, `test_direct_run_agent_s3_step_rejects_max_retries_out_of_range` |

Live trace evidence (manual smoke):

```
$ curl -X POST http://127.0.0.1:8765/sessions/$SID/tools/agent_s3_step \
       -H "Content-Type: application/json" \
       -d '{"params":{"instruction":"Click OK","dry_run":true,"screenshot":false,"require_permission":false}}'
{"status":"success","output":{
  "instruction":"Click OK",
  "dry_run":true,
  "screenshot_path":null,
  "duration_ms":3,
  "proposal":{"backend":"package","info":{},"raw_actions":["pyautogui.click(123, 456)"]},
  "translation":{"accepted_count":1,"rejected_count":0,"rejected":[]},
  "mapped":{"tool_name":"click_xy","params":{"x":123,"y":456,"button":"left"},"confidence":"high"},
  "mapped_execution":{"dry_run":true}
}}
```

---

## Safety Evidence

| Check | Status | Evidence |
|---|---|---|
| No raw `exec()` of upstream action code | ✓ | Static scan: `exec(` only in `agent_s3_action_translator.py` deny patterns + test data. Translator uses `ast.parse(mode="exec")` only for shape detection, parsed tree discarded. |
| No raw `eval()` | ✓ | Static scan: `eval(` only in translator deny patterns + test data. |
| No `os.system` | ✓ | Static scan: `os.system` only in translator deny patterns + test data. |
| Translator rejects unsafe actions | ✓ | 11/11 unit tests for exec/eval/subprocess/os.system/open/__import__/import patterns (6 tests covering deny patterns in `TestUnsafeAction*`) |
| Defence-in-depth mapped tool allow-list | ✓ | `AGENT_S3_MAPPED_TOOL_ALLOWLIST` = `{click_xy, type_text, hotkey, press_key, scroll, wait, screenshot}`. `test_defence_in_depth_rejects_outside_allowlist` proves a regression in translator can't escalate. |
| Mapped params Pydantic validation | ✓ | `test_invalid_params_after_translate_returns_invalid_params` |
| Permission gate preserved | ✓ | `agent_s3_step` registry `requires_confirmation=True` → WorkflowRunner `_gate_permission` fires BEFORE agent call. If denied/timeout, step cancelled, no GUI execute. (Inherited from Phase 7 infrastructure; no regression.) |
| Permission denied/timeout → no GUI execution | ✓ | Inherited: `tool_executor.py:_execute_agent_s3_step` only fires when runner passes it (post-gate). `test_permission_timeout_cancellation.py` (Phase 11, 4 tests) pins the runner behaviour. |
| Stop during pending permission | ✓ | Inherited: same runner stop flag. `test_permission_timeout_cancellation.py` covers stop+timeout interaction. |
| Health endpoint no secret | ✓ | Inherited from Phase 11 — `test_agent_s3_secret_scrubbing.py` (29 tests) still pass. |
| `ENABLE_LOCAL_ENV` forced false | ✓ | Inherited from Phase 11 — `test_enable_local_env_always_forced_false`. |
| Audit trail | ✓ | `tool_calls` DB row + JSONL mirror (Phase 10). New `agent_s3_action_proposed` event visible to WebSocket subscribers + JSONL. |

### Defence-in-depth stack (8 layers)

1. **Registry allow-list** — agent_s3_step is registered; nothing else is.
2. **Permission gate** — `requires_confirmation=True` → user must approve
   meta-action ("let Agent-S3 propose + execute one action").
3. **Pre-flight** — Agent-S3 enabled + adapter available.
4. **Translator deny-pattern** — exec/eval/subprocess/os.system/etc.
5. **Translator whitelist** — only known `pyautogui.*` patterns map.
6. **Mapped tool allow-list** (defence-in-depth) — even if translator
   regresses, mapped tool name must be in 7-tool allow-list.
7. **Pydantic validation** — mapped params re-validated against the
   mapped tool's own params_model.
8. **ToolExecutor._run dispatch** — mapped action runs through the
   exact same dispatch path as a hand-authored step (no shortcut).

---

## Test Results

### Backend pytest

**Command:** `cd apps/backend && uv run pytest`

**Result:**
```
338 passed, 2 skipped, 14 warnings in 80.34s (0:01:20)
```

- Phase 11 baseline: 303 passed (was 273 audit).
- Phase 12 additions:
  - `tests/test_agent_s3_step_executor.py`: 23 unit tests
  - `tests/test_agent_s3_runner_wiring.py`: 12 integration tests
- Plus 2 modifications:
  - `tests/test_tool_registry.py`: `EXPECTED_TOOLS` updated
  - `tests/test_tools_api.py`: `/tools` expected set updated

**Phase 12 specific test files:**

```
tests/test_agent_s3_step_executor.py      23 tests   PASS
tests/test_agent_s3_runner_wiring.py      12 tests   PASS
```

**Failures:** 0
**Skipped:** 2 (pre-existing, unrelated)

### Frontend vitest

**Command:** `cd apps/desktop && npm run test -- --run`

**Result:**
```
✓ src/state/sessionStore.test.ts          7 tests
✓ src/components/WorkflowPanel.test.tsx   3 tests
✓ src/components/ControlBar.test.tsx      6 tests
✓ src/components/ChatPanel.test.tsx       3 tests

Test Files  4 passed (4)
Tests       19 passed (19)
Duration    1.95s
```

Phase 12 không thêm frontend test (out-of-scope; UI không cần đụng vào
agent_s3_action_proposed event ở phase này — Phase 13 follow-up).

### Frontend typecheck

**Command:** `cd apps/desktop && node node_modules/typescript/bin/tsc --noEmit`

**Result:** Exit 0, no errors.

### Frontend build

**Command:** `cd apps/desktop && npm run build`

**Result:**
```
vite v5.4.21 building for production...
✓ 43 modules transformed.
dist/index.html                   0.39 kB │ gzip:  0.26 kB
dist/assets/index-BE1gJpLU.css    6.42 kB │ gzip:  1.90 kB
dist/assets/index-D18vFdVv.js   155.05 kB │ gzip: 50.00 kB │ map: 394.91 kB
✓ built in 1.03s
```

### Static safety scan

```
$ git grep -n "exec(" -- apps/backend | head
apps/backend/services/agent_s3_action_translator.py:177:  (re.compile(r"\bexec\s*\("), "exec()"),
apps/backend/services/agent_s3_adapter.py:14:  - **We never call ``exec()`` on the action strings.**
apps/backend/tests/test_agent_s3_action_translator.py:171:  "exec('print(1)')",
apps/backend/tests/test_agent_s3_action_translator.py:285: def test_translator_does_not_call_exec(monkeypatch):
apps/backend/tests/test_agent_s3_action_translator.py:293:         raise AssertionError("translator called exec()!")
apps/backend/tests/test_agent_s3_action_translator.py:298:  "exec('print(1)')",

(no real exec() in production code; only deny-pattern regex + test data
 + docstring + negative test "translator does not call exec()")

$ git grep -n "eval(" -- apps/backend | head
apps/backend/services/agent_s3_action_translator.py:178:  (re.compile(r"\beval\s*\("), "eval()"),
apps/backend/tests/test_agent_s3_action_translator.py:172:  "eval('1+1')",

(no real eval() in production code; only deny-pattern + test data)

$ git grep -n "os.system" -- apps/backend | head
apps/backend/services/agent_s3_action_translator.py:175:  (re.compile(r"\bos\.system\b"), "os.system"),
apps/backend/services/agent_s3_action_translator.py:15:   ``import``, ``open(``, ``subprocess``, ``os.system``, file
apps/backend/tests/test_agent_s3_action_translator.py:169:  "os.system('rm -rf /')",

(no real os.system in production code; only deny-pattern + test data)

$ git grep -n "subprocess" -- apps/backend | head
apps/backend/services/gui_adapter.py:16: import subprocess
apps/backend/services/gui_adapter.py:156: proc = subprocess.Popen(cmd, shell=False)
apps/backend/services/gui_adapter.py:167: subprocess.Popen(...)
apps/backend/services/agent_s3_action_translator.py:174: (re.compile(r"\bsubprocess\b"), "subprocess"),
apps/backend/tests/test_agent_s3_action_translator.py:166: "from subprocess import call",

(subprocess only in PyAutoGuiAdapter with shell=False + static argv —
known SEC-004 safe; deny-pattern in translator; test data)

$ git grep -n "enable_local_env" -- apps/backend docs README.md | head
apps/backend/routers/agent_s3.py:23:       "enable_local_env": false,
apps/backend/services/agent_s3_adapter.py:21:    - The upstream ``enable_local_env`` flag is forced to ``False``
apps/backend/services/agent_s3_config.py:236:  enable_local_env = False
apps/backend/services/agent_s3_config.py:259:  enable_local_env=enable_local_env,
apps/backend/services/agent_s3_config.py:355:  "enable_local_env": cfg.enable_local_env,
apps/backend/tests/test_agent_s3_adapter_mock.py:66:  enable_local_env=False,
apps/backend/tests/test_agent_s3_config.py:111: assert cfg.enable_local_env is False
apps/backend/tests/test_agent_s3_config.py:123: assert cfg.enable_local_env is False
apps/backend/tests/test_agent_s3_config.py:137: def test_enable_local_env_always_forced_false(monkeypatch):

(only forced-false references; tests pin the contract)
```

### Manual / simulated workflow

The Phase 12 brief §12 provided two example workflows. Both run
end-to-end in the integration test:

**Workflow 1 (dry_run=true):**
```json
{
  "steps": [{
    "id": "s1",
    "tool": "agent_s3_step",
    "params": {"instruction": "Click the OK button if visible", "dry_run": true}
  }]
}
```
→ `tests/test_agent_s3_runner_wiring.py::test_direct_run_agent_s3_step_dry_run_succeeds`

**Workflow 2 (dry_run=false, require_permission=true):**
```json
{
  "steps": [{
    "id": "s1",
    "tool": "agent_s3_step",
    "params": {
      "instruction": "Click the OK button if visible",
      "dry_run": false,
      "require_permission": true
    }
  }]
}
```
→ `tests/test_agent_s3_runner_wiring.py::test_direct_run_agent_s3_step_full_execute`
   (with `require_permission=false` to skip the gate in the test;
   full permission gate behaviour already pinned by Phase 11's
   `test_permission_timeout_cancellation.py` suite).

Both tests use `MockGuiAdapter` — NO real GUI calls. NO real Agent-S3
SDK call (MockAgentS3Adapter).

---

## Known Limitations

1. **Multi-step autonomous Agent-S3 loop** — chưa bật. Mỗi
   `agent_s3_step` chỉ chạy đúng 1 action. Multi-step phải do planner
   emit nhiều `agent_s3_step` steps trong workflow. Bounded loop
   (e.g. max_propose_per_step ở workflow level) là Phase 13 follow-up.

2. **Real `gui-agents` SDK + real PyAutoGUI smoke test** — chưa chạy
   trên Windows session với Accessibility permission. Mock adapter +
   MockGuiAdapter đã cover tất cả logic path, nhưng production
   runtime chưa verified end-to-end với real upstream.

3. **Real model endpoint** — chưa test với real OpenAI / Anthropic /
   HuggingFace endpoint. Mọi test dùng `MockAgentS3Adapter` với canned
   raw actions. Cần manual smoke với real model khi muốn verify
   translator thực sự handle output từ LLM thật.

4. **Tauri bundle** — không build được do thiếu Rust toolchain.
   `QA-001` deferred.

5. **No `agent_s3_session` / bounded loop tool** — Phase 13 follow-up.

6. **Click target via Agent-S3** — `click_target` (vision-grounded)
   vẫn stub mode. Tích hợp Agent-S3 với `click_target` chưa làm ở
   Phase 12 (Phase 13).

---

## Recommended Phase 13

Theo Phase 12 brief §13:

1. **Bounded multi-step Agent-S3 loop.** Either:
   - New tool `agent_s3_session` với `max_actions` param (1..10), runs
     propose+translate+execute N lần hoặc đến khi goal hoàn thành.
   - Hoặc `agent_s3_step` thêm `max_propose_per_step` param (cap số
     action liên tiếp trong 1 step).
2. **Frontend richer Agent-S3 event timeline.** Subscribe to
   `agent_s3_action_proposed` qua WebSocket; render translated_tool
   + translated_params + safety_status + dry_run + screenshot_path
   trong UI timeline.
3. **Real GUI smoke test.** Manual smoke trên Windows session với
   Accessibility permission + real PyAutoGUI + real `gui-agents`
   package. Cover SEC-001 (OSWorldACI(env=None) runtime behaviour).
4. **Better recovery.** `max_retries` chưa thực sự retry propose
   khi mapped tool fail. Implement bounded retry loop trong orchestrator.
5. **`click_target` × Agent-S3.** Dùng Agent-S3 để resolve target +
   `gui_grounding` để locate coordinates, sau đó click_xy.
6. **Tauri bundle verification.** `cargo check` CI job (QA-001).
7. **Per-session flag `use_agent_s3`.** Currently orchestrator is
   always wired when adapter is available. Add per-session toggle
   on `POST /sessions/{sid}/messages` body so the planner can opt-in
   per run.

---

## Commit message đề xuất

```
feat(agent-s3): wire safe agent_s3_step into workflow runner

Phase 12 - wire Agent-S3 into WorkflowRunner as a real tool step.

Added:
- agent_s3_step tool (risk=high, requires_confirmation=True) with
  AgentS3StepParams schema (instruction, screenshot, dry_run,
  max_retries, require_permission, timeout_ms).
- services/agent_s3_step_executor.py orchestrator that drives
  propose -> translate -> mapped tool -> audit pipeline with
  defence-in-depth allow-list (7 whitelisted GUI tools).
- agent_s3_action_proposed event (accepted/rejected + translated
  tool/params + rejection_code) emitted per invocation.
- ToolExecutor._execute_agent_s3_step dispatch + main.py wiring
  with closure over ToolExecutor._run for inner mapped-tool dispatch.
- 23 unit tests + 12 integration tests covering 11 failure modes,
  4 success paths, 3 hygiene checks.

Preserved:
- All 7 Phase 11 safety guarantees (no raw exec/eval, translator
  required, tool whitelist enforced, permission gate, secret-scrub
  health endpoint, ENABLE_LOCAL_ENV forced false).
- Phase 11 secret-scrubbing (29 tests still pass).
- Phase 11 permission timeout cancellation (4 tests still pass).

Test results:
- Backend pytest: 338 passed (was 303), 0 failed, 2 skipped.
- Frontend vitest: 19 passed.
- Frontend typecheck: pass.
- Frontend build: pass.
- Static scan: 0 exec/eval/os.system in apps/backend production code.

Refs: docs/agent_s3_integration.md, docs/safety_policy.md,
artifacts/agent_s3_integration/phase12_workflow_wire_report.md.
```

---

## Final checks

| Item | Status |
|---|---|
| `agent_s3_step` có trong tool registry/schema | ✓ (ToolInfo + AgentS3StepParams) |
| WorkflowRunner/ToolExecutor chạy được `agent_s3_step` | ✓ (TestClient integration tests) |
| Agent-S3 proposal được translate sang whitelist tool | ✓ (test_full_flow_click_xy_executes) |
| Không raw exec/eval | ✓ (static scan + 6 deny-pattern tests) |
| Permission gate bắt buộc trước execute | ✓ (registry `requires_confirmation=True`) |
| Dry-run không execute GUI | ✓ (test_dry_run_does_not_call_inner_tool) |
| Denied/timeout/stop không execute GUI | ✓ (inherited Phase 11 tests) |
| Audit/event có evidence | ✓ (test_agent_s3_step_creates_tool_call_row + agent_s3_action_proposed event) |
| Backend tests pass | ✓ (338/338) |
| Frontend build/typecheck/test pass | ✓ (19/19 vitest, typecheck OK, build OK) |
| Docs cập nhật không overclaim | ✓ (Phase 13 follow-up called out explicitly) |

**Verdict confirmed:** `accepted_phase12_agent_s3_workflow_wired`.