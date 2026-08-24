# Live Record Soak Test — hướng dẫn thủ công (RTX 5060, Windows 11)

> Mục tiêu: chứng minh pipeline capture/encode thật (ffmpeg `ddagrab` → `h264_nvenc`
> → MKV segmented) giữ 60 FPS không drop trong ≥ 15 phút, với preview song song
> và timeline đầy đủ — trước khi mở khoá ghi hình production.

## Điều kiện tiên quyết

- ffmpeg 8.x **full build** trong PATH (`ffmpeg -version`); có filter `ddagrab`
  (`ffmpeg -hide_banner -filters | findstr ddagrab`) và encoder `h264_nvenc`
  (`ffmpeg -hide_banner -encoders | findstr nvenc`).
- GPU NVIDIA driver mới (RTX 5060 đã kiểm chứng).
- Sidecar đã build release:
  ```powershell
  cargo build --release --manifest-path apps/desktop/native/recording-engine/Cargo.toml
  ```
  Binary: `apps/desktop/native/recording-engine/target/release/windagent-recorder.exe`

## Bước 1 — Probe capabilities

```powershell
$bin = "apps/desktop/native/recording-engine/target/release/windagent-recorder.exe"
'{"op":"capabilities","args":{}}' | & $bin
```

Nhận: `engine_available=true`, `nvenc_h264_available=true` (hoặc hevc),
`ddagrab_available=true`, `disk_free_gb` thực tế. Nếu cả hai nvenc đều `false`
→ dừng, kiểm tra driver.

## Bước 2 — Ghi hình soak 15 phút

Wire protocol khớp `EngineRequest` (`apps/desktop/native/recording-engine/src/ipc/mod.rs`):
op = `capabilities|prepare|start|pause|resume|stop|status|marker`.

```powershell
$out = "$env:TEMP\windagent_soak_$(Get-Date -Format yyyyMMdd_HHmmss)"
New-Item -ItemType Directory $out | Out-Null
$dirJson = ($out -replace '\\', '/')
$hash64 = "0" * 64

@'
{"op":"prepare","args":{"execution_plan_id":"plan_soak","execution_plan_hash":"__HASH__","episode_id":"ep_soak","output_dir":"__OUT__","profile":{"resolution":[1920,1080],"fps":60,"codec":"H264","segment_minutes":5,"audio_enabled":false}}}
{"op":"start","args":{"execution_plan_id":"plan_soak","take_id":"take_soak"}}
'@ -replace '__OUT__', $dirJson -replace '__HASH__', $hash64 | & $bin
```

Để chạy đủ 15 phút: giữ process sống (stdin không đóng). Sidecar phát telemetry
`Status` ~1 Hz và preview JPEG ≤1280×720 @≤2 FPS qua stdout JSONL.
Ghi lại: `frames_captured`, `frames_dropped`, `dropped_pct`, `bitrate_mbps`.

Tiêu chí PASS:

| Chỉ số | Ngưỡng |
|---|---|
| dropped_pct trung bình | < 0.5% |
| bitrate ổn định | ±15% quanh giá trị đặt |
| segment MKV | mỗi 5 phút đúng 1 file mới |
| preview | JPEG hợp lệ liên tục, không stall > 3s |

## Bước 3 — Dừng & đối chiếu sản phẩm

```powershell
# gửi {"op":"stop","args":{}} vào stdin rồi close
ffprobe -v error -show_entries format=duration,size -of default=nw=1 $out\segment_0001.mkv
Get-Content $out\timeline.jsonl | Select-Object -First 5
Get-Content $out\manifest.json
```

Tiêu chí PASS:

- Mọi `segment_*.mkv` đọc được bằng ffprobe, duration ≈ segment_minutes (±2s),
- `timeline.jsonl` có cặp `SESSION_START` … `SESSION_END` và `SEGMENT_END` cho từng segment,
- `manifest.json` liệt kê đủ segment + hash nội dung,
- Không có `recorder://error` nào trong suốt phiên.

## Bước 4 — Smoke pause/resume giữa chừng (tuỳ chọn nâng cao)

Giữa phút 7–8: gửi `{"op":"pause","args":{}}` rồi sau ~30s
`{"op":"resume","args":{}}`. Sau stop: timeline phải có
`PAUSED`/`RESUMED`, tổng duration các segment vẫn khớp thời gian thực trừ khoảng
pause; không segment bị hỏng ở ranh giới pause.

## Receipt

Sau mỗi lần chạy, dán receipt (lệnh + output tóm tắt + ngày) vào
`docs/live_record/P1_IMPLEMENTATION_STATUS.md` mục Gate evidence LR_P6/LR_P9.
