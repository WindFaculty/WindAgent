# Live Record Soak Test — hướng dẫn thủ công (RTX 5060, Windows 11)

> Mục tiêu: chứng minh pipeline **direct** capture/encode thật (WGC → D3D11 →
> NVENC → libavformat → MKV segmented) giữ 60 FPS không drop trong ≥ 15 phút,
> với preview GPU song song và timeline đầy đủ — trước khi mở khoá ghi hình
> production (gate LIVE_RECORD_PRODUCTION_READY).

## Điều kiện tiên quyết

- Sidecar đã build release:
  ```powershell
  cargo build --release --manifest-path apps/desktop/native/recording-engine/Cargo.toml
  ```
  Binary: `apps/desktop/native/recording-engine/target/release/windagent-recorder.exe`
- FFmpeg **shared** DLLs (avformat-62 / avcodec-62 / avutil-60) nằm cạnh binary
  hoặc trỏ qua `WINDAGENT_LIBAV_DIR` — muxer load runtime, không static.
- GPU NVIDIA driver mới (RTX 5060 đã kiểm chứng; nvEncodeAPI64.dll trong System32).
- KHÔNG set `WINDAGENT_RECORDER_ALLOW_MOCK` (mock chỉ dành cho dev simulation).

## Bước 1 — Probe capabilities

Envelope V2 là tag+content: unit variant KHÔNG nhận `"args"`.

```powershell
$bin = "apps/desktop/native/recording-engine/target/release/windagent-recorder.exe"
'{"op":"capabilities"}' | & $bin
```

Nhận: `engine_available=true`, `backend="wgc-nvenc-mkv"`, `nvenc_available=true`,
`wgc_available=true`, `libav_runtime_found=true`, `disk_free_gb` thực tế.
Bất kỳ blocker nào → dừng, xử lý theo mã blocker trước khi chạy soak.

## Bước 2 — Ghi hình soak 15 phút

Wire protocol khớp `EngineRequest`
(`apps/desktop/native/recording-engine/src/ipc/mod.rs`):
op = `capabilities|prepare|start|pause|resume|stop|status|marker|mute|recover`.
Profile forwarded verbatim — engine validator là single source of truth.

```powershell
$out = "$env:TEMP\windagent_soak_$(Get-Date -Format yyyyMMdd_HHmmss)"
New-Item -ItemType Directory $out | Out-Null
$dirJson = ($out -replace '\\', '/')
$hash64 = "0" * 64

@'
{"op":"prepare","args":{"execution_plan_id":"plan_soak","execution_plan_hash":"__HASH__","episode_id":"ep_soak","output_dir":"__OUT__","profile":{"capture_source":{"kind":"DISPLAY","id":""},"video":{"width":1920,"height":1080,"fps":60,"encoder":"NVENC","codec":"H264","rate_control":"CQP","cq":16,"preset":"P7","multipass":"FULL_RES","lookahead":32,"spatial_aq":true,"temporal_aq":true,"b_frames":3,"gop_frames":120},"audio":{"microphone":{"enabled":true,"device_id":""},"system":{"enabled":true,"device_id":""},"sample_rate":48000,"codec":"AAC"},"container":{"format":"MKV","segment_minutes":5}}}}
{"op":"start","args":{"execution_plan_id":"plan_soak","take_id":"take_soak"}}
'@ -replace '__OUT__', $dirJson -replace '__HASH__', $hash64 | & $bin
```

Để chạy đủ 15 phút: giữ process sống (stdin không đóng). Sidecar phát telemetry
`Status` ~1 Hz (capture_fps/encode_fps/av_sync_error_ms/resource_stage đo thật)
và preview JPEG ≤1280×720 @≤2 FPS qua stdout JSONL.
Ghi lại: `frames_captured`, `frames_encoded`, `frames_dropped`, `dropped_pct`,
`resource_stage`.

Tiêu chí PASS:

| Chỉ số | Ngưỡng |
|---|---|
| dropped_pct trung bình | < 0.5% (gate tuyệt đối 0.1% cho production-ready) |
| encode_fps | ≈ 60 suốt take, không suy giảm giữa take |
| resource_stage | `normal`; nếu rơi `preview_degraded` thì recording FPS vẫn không đổi |
| segment MKV | mỗi 5 phút đúng 1 file mới + event `Segment` mỗi lần roll |
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
- stream layout: 1 video H264 + 2 audio AAC riêng biệt (mic, system — không mix),
- `timeline.jsonl` có cặp `SESSION_START` … `SESSION_END` và `SEGMENT_END` cho từng segment,
- `manifest.json` liệt kê đủ segment + hash nội dung,
- Không có `recorder://error` nào trong suốt phiên.

## Bước 4 — Smoke pause/resume + mute giữa chừng

Giữa phút 7–8: gửi `{"op":"mute","args":{"mic_muted":true,"system_muted":false}}`,
`{"op":"pause","args":{}}` rồi sau ~30s `{"op":"resume","args":{}}`.
Sau stop: timeline phải có `PAUSED`/`RESUMED`, track mic im lặng đúng khoảng mute
(kiểm bằng `ffprobe -af silencedetect`), tổng duration các segment vẫn khớp
thời gian thực trừ khoảng pause; không segment nào hỏng ở ranh giới pause.

## Bước 5 — Failure injection (crash recovery)

Kill -9 sidecar giữa take (không gửi stop). Khởi động lại sidecar và chạy:

```
{"op":"recover","args":{"output_dir":"__OUT__"}}
```

PASS khi: report liệt kê các segment COMPLETED (đủ IDR-opened, đọc được ffprobe),
bỏ segment tail dở dang, `manifest.json` được viết lại khớp danh sách segment
giữ lại, và các file giữ lại mở được trong ffprobe/vlc.

## Receipt

Sau mỗi lần chạy, dán receipt (lệnh + output tóm tắt + ngày) vào
`docs/live_record/P10_IMPLEMENTATION_STATUS.md` mục Gate evidence LR_P19.
