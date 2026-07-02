Bạn là senior Python/FastAPI desktop-agent engineer + safety-focused computer-use integration engineer.

Nhiệm vụ: triển khai Phase 12 cho repo WindAgent — wire Agent-S3 vào `WorkflowRunner` như một tool/workflow step thật, nhưng phải giữ safety architecture hiện tại.

Repo:
`D:\antigaravity_code\WindAgent`

Bối cảnh:
WindAgent đã đạt MVP readiness theo audit:

* Backend pytest xanh.
* Frontend build/typecheck/vitest xanh.
* Agent-S3 package mode đã enabled được.
* Adapter Agent-S3 đã instantiate được.
* Safe translator đã reject malicious inputs.
* Phase 11 dự kiến đã fix:

  * `/agent-s3/health` không leak secret.
  * docs Agent-S3 đã có.
  * README/safety policy không overclaim.

Mục tiêu Phase 12:
Cho phép workflow của WindAgent có thể gọi Agent-S3 trong một step có kiểm soát, ví dụ tool mới `agent_s3_step`, để Agent-S3 đề xuất một GUI action tiếp theo dựa trên instruction + screenshot. Action đó phải được WindAgent parse, validate, permission-gate, execute bằng tool whitelist, audit, và stream event như tool bình thường.

Không được làm:

* Không raw `exec()` Agent-S3 action code.
* Không `eval()`.
* Không cho Agent-S3 tự thao tác máy qua local env.
* Không bật `WINDAGENT_AGENT_S3_ENABLE_LOCAL_ENV=1`.
* Không bypass `PermissionService`.
* Không bypass `ToolExecutor`.
* Không refactor lớn toàn bộ runner.
* Không phá mock mode.
* Không bật Agent-S3 mặc định.
* Không push code.
* Không hardcode API key/model key.
* Không chạy GUI thật nếu chưa có safe mode/permission rõ ràng.

Kiến trúc bắt buộc:

User command
→ Planner tạo workflow có step `agent_s3_step`
→ WorkflowRunner chạy step tuần tự
→ ToolExecutor nhận `agent_s3_step`
→ AgentS3Adapter lấy screenshot/propose action
→ AgentS3ActionTranslator parse raw action
→ map sang WindAgent whitelisted tool
→ PermissionService quyết định approve/deny/require
→ ToolExecutor/GiAdapter thực thi action mapped
→ audit log + websocket events
→ return result cho workflow.

Agent-S3 chỉ được đề xuất action. WindAgent mới là nơi quyết định action có được thực thi không.

## 1. Đọc hiện trạng trước khi sửa

Đọc các file liên quan:

* `apps/backend/services/workflow_runner.py`
* `apps/backend/services/tool_executor.py`
* `apps/backend/services/tool_registry.py`
* `apps/backend/services/gui_adapter.py`
* `apps/backend/services/gui_grounding.py`
* `apps/backend/services/permission_service.py`
* `apps/backend/services/agent_s3_config.py`
* `apps/backend/services/agent_s3_adapter.py`
* `apps/backend/services/agent_s3_action_translator.py`
* `apps/backend/services/agent_s3_health.py`
* `docs/agent_s3_integration.md`
* `docs/event_protocol.md`
* `docs/api_contract.md`
* `docs/safety_policy.md`

Chạy:

```powershell
cd D:\antigaravity_code\WindAgent
git status --short
git diff --stat
```

Nếu Phase 11 chưa có hoặc `/agent-s3/health` vẫn leak secret, dừng lại và báo:
`blocked_phase12_requires_phase11_closeout`

## 2. Thiết kế tool `agent_s3_step`

Thêm hoặc hoàn thiện tool registry entry:

Tool name:
`agent_s3_step`

Purpose:
Cho Agent-S3 đề xuất và thực thi đúng 1 GUI action an toàn trong workflow hiện tại.

Schema đề xuất:

```json
{
  "instruction": "string, required",
  "screenshot": "boolean, optional, default true",
  "dry_run": "boolean, optional, default false",
  "max_retries": "integer, optional, default 0, max 2",
  "require_permission": "boolean, optional, default true",
  "timeout_ms": "integer, optional, default 30000, max 120000"
}
```

Behavior:

* Nếu Agent-S3 disabled → fail rõ:

  * `AGENT_S3_DISABLED`
* Nếu dependency/config thiếu → fail rõ:

  * `AGENT_S3_UNAVAILABLE`
  * `AGENT_S3_MISCONFIGURED`
* Nếu adapter chưa initialised → fail rõ:

  * `AGENT_S3_ADAPTER_NOT_READY`
* Nếu translator reject → fail rõ:

  * `AGENT_S3_UNSAFE_ACTION`
  * `AGENT_S3_UNSUPPORTED_ACTION`
  * `AGENT_S3_PARSE_FAILED`
* Nếu permission denied/timeout → không execute action:

  * `PERMISSION_DENIED`
  * `PERMISSION_TIMEOUT`
* Nếu `dry_run=true`:

  * chỉ propose + translate
  * không execute GUI action
  * vẫn audit proposal
  * return mapped tool/action.

## 3. Execution flow bắt buộc trong `ToolExecutor`

Implement flow cho `agent_s3_step`:

1. Validate params.
2. Check Agent-S3 enabled/config/health.
3. Capture screenshot qua `GuiAdapter.screenshot()` nếu `screenshot=true`.
4. Gọi `AgentS3Adapter.propose_next_action(...)`.
5. Nhận:

   * raw action code/text
   * model/provider metadata
   * optional confidence.
6. Gọi `AgentS3ActionTranslator.translate(raw_action)`.
7. Nếu translator reject:

   * emit failed event
   * audit raw action đã scrub/limit length
   * return error.
8. Nếu translate thành mapped tool:

   * mapped tool phải nằm trong whitelist:

     * `click_xy`
     * `type_text`
     * `hotkey`
     * `press_key`
     * `scroll`
     * `wait`
     * `screenshot`
   * không cho map sang shell/file/network.
9. Chạy permission gate trước execute.
10. Nếu permission required:

* workflow phải chờ decision như tool thường.
* pause/stop/cancel phải vẫn hoạt động.

11. Nếu approve:

* execute mapped action bằng path hiện tại, không duplicate logic nếu có thể.

12. Emit events:

* `tool_call_started` cho `agent_s3_step`
* `agent_s3_action_proposed` nếu cần event mới
* `tool_call_started`/`tool_call_finished` cho mapped action nếu kiến trúc hiện tại hỗ trợ nested events; nếu không, ghi mapped action trong result.
* `tool_call_finished` hoặc `tool_call_failed` cho `agent_s3_step`.

13. Persist audit:

* instruction
* screenshot artifact path, nếu có
* raw action scrubbed/truncated
* translated action
* permission result
* execution result
* error code nếu fail.

Không log secret/API key.

## 4. Event protocol

Nếu thêm event mới, cập nhật `docs/event_protocol.md`.

Event đề xuất:
`agent_s3_action_proposed`

Payload:

```json
{
  "session_id": "...",
  "run_id": "...",
  "step_id": "...",
  "instruction": "...",
  "translated_tool": "click_xy",
  "translated_params": {},
  "safety_status": "accepted|rejected",
  "rejection_code": null,
  "dry_run": false
}
```

Không đưa API key, raw screenshot bytes, hoặc secret vào event.

Nếu không thêm event mới, phải document rõ Agent-S3 proposal nằm trong `tool_call_finished.result`.

## 5. Planner integration

Planner không bắt buộc phải tự chọn `agent_s3_step` ở phase đầu nếu rủi ro cao.

Nhưng cần làm tối thiểu:

* Tool registry cho planner biết `agent_s3_step` tồn tại khi enabled.
* Nếu disabled thì planner không nên chọn tool này.
* Nếu planner sinh `agent_s3_step` khi disabled, runner phải fail gracefully.
* Không để planner tự sinh raw Agent-S3 code.

Cập nhật docs hoặc prompt planner nếu có:

* Agent-S3 dùng cho GUI reasoning khi target không rõ.
* Mỗi `agent_s3_step` chỉ chạy 1 action.
* Tác vụ nhiều bước phải tạo nhiều step hoặc loop bounded ở phase sau, chưa làm auto-loop vô hạn.

## 6. Pause/Resume/Stop behavior

Bắt buộc đảm bảo:

* Nếu workflow đang chờ permission cho `agent_s3_step`, user stop thì action không execute.
* Nếu workflow pause trước execute, không execute cho đến resume.
* Nếu stop sau proposal nhưng trước approval, không execute.
* Nếu permission timeout, không execute.
* Nếu adapter call timeout, step fail sạch, không treo runner.

Thêm regression tests cho các case này nếu có test harness hiện tại.

## 7. Tests bắt buộc

Thêm tests backend:

### Config/disabled

* `agent_s3_step` khi `WINDAGENT_AGENT_S3_ENABLED=0` → `AGENT_S3_DISABLED`.
* Missing dependency/config → fail rõ, backend không crash.

### Dry run

* Fake Agent-S3 returns click action.
* `dry_run=true`.
* Assert:

  * translator chạy.
  * mapped action đúng.
  * GUI adapter không được click.
  * audit/event có proposal.

### Execute safe action

* Fake Agent-S3 returns click action.
* Permission auto-approve/mock approve.
* Assert:

  * mapped `click_xy` executed qua `GuiAdapter`.
  * raw action không exec trực tiếp.
  * audit có translated tool.
  * workflow step success.

### Unsafe action

* Fake Agent-S3 returns:

  * `os.system("calc")`
  * `subprocess.run(...)`
  * `open("x")`
  * `exec("...")`
  * `eval("...")`
  * `import os`
* Assert:

  * reject.
  * GUI action not executed.
  * error code đúng.
  * audit/event failed.

### Permission denied

* Fake safe click.
* Permission denied.
* Assert:

  * no GUI execution.
  * step failed/cancelled theo convention hiện tại.
  * event/audit đúng.

### Permission timeout/cancel

* Fake safe type/click.
* Permission timeout.
* Assert:

  * no GUI execution.
  * workflow không treo.
  * error code rõ.

### Stop during pending permission

* Start workflow with `agent_s3_step`.
* Enter permission pending.
* Stop run.
* Later approve should not execute.
* Assert no GUI execution.

### Planner/registry

* Tool registry includes `agent_s3_step` only when allowed hoặc marks availability correctly.
* Schema validation works.

Không cần dùng real Agent-S3 trong unit tests; dùng fake adapter/mock proposal để test safety và runner integration.

## 8. Frontend tối thiểu

Nếu frontend có tool/status panel:

* Hiển thị `agent_s3_step` trong tool list nếu backend trả về.
* Hiển thị event/result lỗi `AGENT_S3_*` rõ ràng.
* Không cần UI phức tạp.
* Không expose secret trong UI.
* Nếu có health panel, chỉ hiện:

  * enabled
  * package/external available
  * adapter initialised
  * configured booleans
  * last error scrubbed.

Chạy frontend tests/build sau khi sửa.

## 9. Docs update

Cập nhật:

* `docs/agent_s3_integration.md`
* `docs/event_protocol.md`
* `docs/api_contract.md`
* `docs/safety_policy.md`
* `README.md` nếu có feature matrix/status.

Docs phải ghi rõ:

* Phase 12 đã wire `agent_s3_step` vào workflow nếu test pass.
* `agent_s3_step` chỉ chạy 1 safe translated action mỗi step.
* Agent-S3 không được raw exec.
* Mọi action vẫn qua permission/audit.
* Multi-step autonomous Agent-S3 loop chưa bật nếu chưa implement.
* Mặc định disabled.

## 10. Static safety scan

Chạy:

```powershell
cd D:\antigaravity_code\WindAgent
git grep -n "exec(" -- apps/backend
git grep -n "eval(" -- apps/backend
git grep -n "os.system" -- apps/backend
git grep -n "subprocess" -- apps/backend
git grep -n "enable_local_env" -- apps/backend docs README.md
git grep -n "AGENT_S3" -- apps/backend
```

Nếu có `exec`/`eval`, xác minh:

* Không dùng với raw Agent-S3 action.
* Nếu là unrelated/test-safe, ghi rõ trong report.

## 11. Test commands bắt buộc

Backend:

```powershell
cd D:\antigaravity_code\WindAgent\apps\backend
uv run pytest --timeout=15
```

Nếu timeout plugin không có:

```powershell
uv run pytest
```

Frontend:

```powershell
cd D:\antigaravity_code\WindAgent\apps\desktop
npm run test -- --run
node node_modules/typescript/bin/tsc --noEmit
npm run build
```

Root:

```powershell
cd D:\antigaravity_code\WindAgent
git status --short
git diff --stat
```

Không được claim pass nếu command chưa chạy.

## 12. Manual simulated workflow

Tạo hoặc dùng test để mô phỏng workflow:

```json
{
  "steps": [
    {
      "id": "s1",
      "tool": "agent_s3_step",
      "params": {
        "instruction": "Click the OK button if visible",
        "dry_run": true
      }
    }
  ]
}
```

Sau đó test execute mock:

```json
{
  "steps": [
    {
      "id": "s1",
      "tool": "agent_s3_step",
      "params": {
        "instruction": "Click the OK button if visible",
        "dry_run": false,
        "require_permission": true
      }
    }
  ]
}
```

Không chạy GUI thật trong manual test nếu không cần; dùng mock adapter.

## 13. Report cuối phase

Tạo:
`artifacts/agent_s3_integration/phase12_workflow_wire_report.md`

Report phải có:

# Phase 12 — Agent-S3 Workflow Wire Report

## Verdict

Một trong:

* `accepted_phase12_agent_s3_workflow_wired`
* `partial_phase12_dry_run_only`
* `blocked_phase12_safety_failure`
* `blocked_phase12_runner_integration_failure`
* `blocked_phase12_tests_failed`
* `blocked_phase12_phase11_missing`

## Summary

* Agent-S3 step đã wire vào đâu.
* Có execute thật qua mapped tool chưa.
* Có dry-run không.
* Có permission gate không.
* Có audit/event không.

## Files Changed

Bảng file + mục đích.

## Tool Schema

Schema `agent_s3_step`.

## Execution Flow Evidence

Mô tả evidence từ test:

* propose action
* translate
* permission
* execute mapped tool
* audit/event.

## Safety Evidence

* Không raw exec/eval.
* Unsafe actions rejected.
* Permission denied không execute.
* Timeout/cancel không execute.
* Secret không leak.

## Test Results

* Backend pytest result.
* Frontend vitest/typecheck/build result.
* Static scan result.
* Manual/simulated workflow result.

## Known Limitations

Ghi rõ:

* Multi-step autonomous Agent-S3 loop đã làm hay chưa.
* Real GUI mode đã test hay chưa.
* Real model endpoint đã test hay chỉ mock.
* Tauri bundle chưa test nếu thiếu Rust.

## Recommended Phase 13

Đề xuất:

* Bounded multi-step Agent-S3 loop.
* Frontend richer Agent-S3 event timeline.
* Real GUI smoke test.
* Tauri bundle verification.
* Better recovery after failed Agent-S3 proposal.

## 14. Final response

Trả về cho user:

* Verdict.
* Test result.
* Report path.
* Danh sách file sửa.
* Có còn blocker không.
* Commit message đề xuất nếu xanh:

`feat(agent-s3): wire safe agent_s3_step into workflow runner`

Điều kiện pass Phase 12:

* `agent_s3_step` có trong tool registry/schema.
* WorkflowRunner/ToolExecutor chạy được `agent_s3_step`.
* Agent-S3 proposal được translate sang whitelist tool.
* Không raw exec/eval.
* Permission gate bắt buộc trước execute.
* Dry-run không execute GUI.
* Denied/timeout/stop không execute GUI.
* Audit/event có evidence.
* Backend tests pass.
* Frontend build/typecheck/test pass hoặc lỗi môi trường rõ ràng.
* Docs cập nhật không overclaim.

Bắt đầu bằng cách kiểm tra Phase 11 đã hoàn tất và đọc code hiện tại trước khi sửa.
