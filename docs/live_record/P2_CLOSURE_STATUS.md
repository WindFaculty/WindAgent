# Live Record — P2 Closure Status

> Ngày: 2026-08-24 · Tiền nhiệm: `P1_IMPLEMENTATION_STATUS.md`
> Phạm vi: đóng các gap còn lại của `ban_ke_hoach_v1.md` sau đánh giá P1.

## Những gì vòng này hoàn thành

### 1. Browser/Tool effector thật (Section 14) — LR_P5
- `POST /api/v3/live-record/plans/{id}/actions/{action_id}/execute-browser`:
  thực thi `BROWSER_NAVIGATION` / `BROWSER_ACTION` qua `BrowserSessionService`
  hiện có, session riêng scope theo plan (`live-record-{plan_id}`), mọi tham số
  resolve từ frozen payload bundle; verify `expected_after.url_contains`.
- `BrowserSessionService.click_semantic()` (locator text/css/@ref) và cờ
  `require_user_control` cho `click`/`scroll` để action agent-side của take
  không cần handoff user.
- `/execute` mở rộng nhận `TOOL_RUN` (ngữ nghĩa RUN_COMMAND).
- Desktop `actionExecutor.ts` bỏ stub "ticket==success": BROWSER_* gọi
  execute-browser, TOOL_RUN gọi /execute, đều report result + timeline event.

### 2. Token refresh cho take dài (Section 24 + §35)
- `POST /api/v3/live-record/sessions/{session_id}/token-refresh`: re-mint
  ephemeral token cùng model + plan_hash; fail-closed khi credential thiếu;
  metadata lưu `refresh_count`, token chỉ xuất hiện trong response POST.
- `LiveDirectorClient.refreshToken` hook: trước khi resume, nếu token hết hạn
  hoặc còn < 60s thì re-mint rồi mới reconnect (`updateEphemeralToken`).
- `useLiveDirector` wire callback qua api-client `refreshSessionToken`.

### 3. Privacy scan preflight (Section 23 + §33)
- Module `windagent_core.domain.live_record.privacy_scan`: quét payload
  bundles / narration / action metadata theo pattern (Google/OpenAI/AWS/GitHub/
  Slack/JWT/PEM/generic assignment) + exact-match credential đã cấu hình;
  findings luôn mask.
- `POST .../plans/{plan_id}/privacy-scan`.
- Preflight TS thêm guard fail-closed `PRIVACY_SCAN_FAILED` (chưa scan hoặc
  chưa PASS ⇒ BLOCKED); LiveRecordPage chạy scan một lần mỗi plan (native);
  checklist hiển thị dòng "Privacy scan đạt".

### 4. Sidecar bundling
- `apps/desktop/scripts/build-sidecar.ps1` + `npm run build:sidecar` → stage
  `src-tauri/binaries/windagent-recorder-<target-triple>.exe`; Tauri
  `bundle.externalBin = ["binaries/windagent-recorder"]`. Đã build + stage
  thành công trên máy Windows này.

### 5. CI gate + test bổ sung
- Job `live-record-client-gate` (frontend/app vitest + typecheck) và
  `live-record-native-gate` (cargo test crate + stage sidecar), wire vào
  final-evidence gate; cập nhật `test_ci_workflow.py`.
- Test mới: `__tests__/liveDirectorClient.test.ts` (setup wire shape,
  toolCall→toolResponse per-id, resumption handle qua reconnect, token refresh
  khi hết hạn); privacy scan unit tests; actions API tests cho browser/tool/
  refresh/privacy; preflight guard tests. Tổng: **pytest live-record 121 PASS
  · vitest frontend/app 79 PASS · cargo 20 PASS · tsc exit 0**.

## Gate mapping (plan §27 ↔ bằng chứng repo)

| Gate (plan §27) | Trạng thái | Bằng chứng |
|---|---|---|
| LR_P0_ARCHITECTURE | DONE | `docs/live_record/P0_ARCHITECTURE_FROZEN.md` |
| LR_P1_EPISODE_PLAN | DONE | plans/takes/sessions API + migration 0019 |
| LR_P2_PROVIDER_LIVE | DONE | `providers/google/live/*` + capability gate |
| LR_P3_DIRECTOR | DONE (nợ smoke Google thật) | e2e FakeGeminiLiveServer + client wire tests |
| LR_P4_CODE_PLAYBACK | DONE | native `playback.rs` hash-gated |
| LR_P5_BROWSER_TOOLS | **DONE (vòng này)** | execute-browser + click_semantic + TOOL_RUN |
| LR_P6_NATIVE_CAPTURE | PARTIAL* | ffmpeg ddagrab (không phải WGC-direct API) |
| LR_P7_NVENC | PARTIAL* | h264_nvenc qua ffmpeg; nợ GPU release smoke |
| LR_P8_SEGMENTED_MKV | DONE | segment rotation + timeline.jsonl flush |
| LR_P9_UI | DONE trên native path | mock store chỉ còn là web/dev fallback |
| LR_P10_E2E | PARTIAL | e2e golden-loop với fake Gemini server |
| LR_P11_PRODUCTION | PENDING | soak ≥15 phút + dropped-frame measurement chưa chạy |

(*) Quyết định kiến trúc ghi nhận: production path dùng ffmpeg subprocess thay
vì WGC/D3D11/NVENC API trực tiếp như §15–16. Chức năng đạt, cần ADR ngắn nếu
muốn chuẩn hoá vĩnh viễn hướng này.

## Việc còn lại để PRODUCTION READY
1. Soak 30–60 phút + đo dropped frames trên GPU thật (`scripts/live_record/soak.md`).
2. Smoke bootstrap Google thật (credential + `auth_tokens`) 1 lần.
3. E2E quay Episode thật 5–10 phút (§28) kèm receipt lineage/timeline.
4. Formatter policy §13: preflight đọc settings.json workspace (hiện mới hấp
   thụ ở preparer + after_hash gate).
