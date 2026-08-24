# LIVE_RECORD_P1 — Implementation Status & Gate Evidence

> Status: **P1 IMPLEMENTED** — Phases A→F của kế hoạch hoàn tất trên working tree.
> Baseline: `P0_ARCHITECTURE_FROZEN.md` (không thay đổi, vẫn bất biến).
> Date: 2026-08-24

## 1. Trạng thái các phase

| Phase | Phạm vi | Trạng thái |
|---|---|---|
| **A** | Backend token Google Live thật (`mint_remote`) + action dispatch endpoints (`prepare`/`execute`/`result`) | ✅ Done |
| **B** | Native engine sidecar Rust: ffmpeg `ddagrab` → `h264_nvenc` → MKV segmented, preview JPEG ≤1280×720 @≤2FPS, timeline.jsonl, Tauri `EngineHost` | ✅ Code + unit tests; còn nợ smoke máy thật (mục 4) |
| **C** | Code playback executor desktop-side Rust (`playback_execute_code`: TYPE pacing 15–40 cps / PASTE clipboard, sha256 before/after gate) | ✅ Done |
| **D** | TS Director client nói BidiGenerateContent thật: setup/sessionResumption/toolCall/toolResponse/realtimeInput.mediaChunks + `actionExecutor.ts` | ✅ Done |
| **E** | UI cutover: `useLiveRecorderSession`, DirectorPanel, PreflightChecklist (14 guard), preview thật, nút "Chuẩn bị ghi hình" từ EpisodeWorkspace | ✅ Done |
| **F** | Failure policy 3 lớp + E2E director loop + gate evidence này | ✅ Done |

## 2. Failure policy (Section 18)

`core/windagent_core/domain/live_record/failure_policy.py` — mirror frozen bảng
`FAILURE_POLICIES` của `domain/stateMachine.ts`. Mọi lỗi runtime thuộc đúng một lớp:

- `RECOVERABLE` → `RETRY_RESUME` (resume qua sessionResumption handle, không replay action nhờ idempotency_key bám plan),
- `OPERATOR_REQUIRED` → `PAUSE_REQUEST_OPERATOR`,
- `FATAL` → `STOP_FINALIZE`.

Lỗi không nhận diện được fail-closed về `OPERATOR_REQUIRED` — tự động hoá dừng,
take giữ nguyên cho người quyết định.

## 3. Gate evidence LR_P1..LR_P9 (receipt lệnh chạy thật)

Máy chạy: Windows 11, `.venv\Scripts\python.exe`, cargo stable. Ngày: 2026-08-24.

| Gate | Nội dung | Lệnh | Receipt |
|---|---|---|---|
| **LR_P1** | Domain contracts TS đóng băng (types/state machine/tool allowlist) | `npx vitest run src/features/live-record` (frontend/app) | **23 passed** (2 files) |
| **LR_P2** | Python domain: lifecycle FROZEN-bất biến, plan hash, lineage | `.venv/Scripts/python -m pytest tests/unit/domain/live_record -q` | **53 passed** |
| **LR_P3** | API V3 live record: plans lifecycle, takes, events, staleness | `.venv/Scripts/python -m pytest tests/contracts/api/test_live_record_v3_api.py tests/contracts/api/test_live_record_actions_api.py -q` | passed (trong tổng 73) |
| **LR_P4** | Failure policy 3 lớp + unknown fail-closed | `.venv/Scripts/python -m pytest tests/unit/domain/live_record/test_live_record_failure_policy.py -q` | passed (trong tổng 73) |
| **LR_P5** | E2E director loop: FakeGeminiLiveServer ↔ harness ↔ full app — mini episode 3 scene, 0 unapproved action, hash verify, ACTION_TAMPERED khi sửa hash | `.venv/Scripts/python -m pytest tests/e2e/test_live_record_e2e.py -q` | **2 passed** |
| **LR_P6** | Rust engine: state machine 12 trạng thái + gate tests + mock pipeline + sidecar lifecycle (EOF shutdown) | `cargo test --release --manifest-path apps/desktop/native/recording-engine/Cargo.toml` | xem mục 4.1 |
| **LR_P7** | Tauri host: engine_host JSONL↔event bridge + playback executor hash/pacing gates | `cargo test live_record --manifest-path apps/desktop/src-tauri/Cargo.toml` | **25 passed** |
| **LR_P8** | TS Director client BidiGenerateContent (setup/toolCall/resumption shapes) | nằm trong LR_P1 vitest run | passed |
| **LR_P9** | Typecheck toàn app sau cutover UI | `npm run typecheck` (frontend/app) | exit 0, 0 error |

Receipt gộp LR_P2+P3+P4+P5:

```
.venv/Scripts/python.exe -m pytest tests/unit/domain/live_record \
  tests/contracts/api/test_live_record_v3_api.py \
  tests/contracts/api/test_live_record_actions_api.py \
  tests/e2e/test_live_record_e2e.py -q
→ 73 passed in 5.53s
```

## 4. Nợ đã biết (không chặn code-complete)

### 4.1 Sidecar lifecycle regression — ĐÃ FIX (2026-08-24)

Smoke release phát hiện sidecar **không thoát sau khi host đóng stdin** (host
`EngineHost::shutdown()` sẽ treo ở `child.wait()`). Hai nguyên nhân xếp lớp:

1. `bin/recorder.rs`: reader thread giữ một `StdoutLock` dài hạn trong khi main
   loop sở hữu lock của riêng nó — `Stdout` dùng reentrant lock chỉ cho phép
   re-entrant **trong cùng thread**, nên reader deadlock trước khi kịp thấy EOF.
   Fix: chỉ lock stdout ngắn hạn trong nhánh ghi lỗi.
2. Regression test spawn sidecar **song song** trong cùng process test —
   Windows handle inheritance khiến process con kế thừa write-end của stdin
   pipe của nhau, không process nào thấy EOF. Fix: các scenario chạy tuần tự
   trong một test duy nhất (`tests/sidecar_lifecycle.rs`).

1. **Smoke máy thật sidecar release** (bổ sung LR_P6): build `--release` rồi chạy
   probe + record 15s theo `scripts/live_record/soak.md` — cần GPU RTX 5060 ở
   phiên tương tác; unit tests đã che mock pipeline.
2. **Smoke Google thật**: bootstrap session với credential Providers thật để nhận
   ephemeral token và mở WS setup thành công (manual, ngoài pytest).
3. Soak ≥ 15 phút theo `scripts/live_record/soak.md` trước khi mở production.
