# Recording Engine — Native Sidecar (Data Plane)

> Gate: `LIVE_RECORD_V2_CONTRACT_FROZEN`

- Control plane: `apps/desktop/src-tauri/src/live_record/` (10 Tauri commands only)
- Data plane: this crate (`apps/desktop/native/recording-engine/`)

Pipeline (V2 — direct APIs, no FFmpeg CLI):

```
Windows Graphics Capture
  → ID3D11Texture2D (GPU surface, D3D11 device on the NVIDIA adapter)
  → NVENC registered-resource encode (zero-copy; H264/HEVC, CQP quality-first)
  → libavformat segmented MKV master (5/10 min segments)
  + WASAPI mic track ──────────────────────┐   (separate tracks, never mixed)
  + WASAPI system loopback track ──────────┘
  → timeline.jsonl + per-take manifest (crash-safe recovery input)
```

- Preview: GPU downscale path samples ≤1280×720 JPEG at ≤2 FPS — the ONLY frame
  payload that ever crosses IPC. It degrades first under load; recording FPS never
  changes between takes.
- Clock: QPC is the single authority for every PTS (video + both audio tracks).
- Muxing/AAC: `muxer/libav_loader.rs` resolves avformat/avcodec/avutil via
  `LoadLibraryW` at runtime (8.x shared DLLs preferred) — nothing static.
- Protocol: JSONL stdio, tag+content envelope (`{"op":...,"args":...}`), exactly
  ONE response per request matched by `op`; unit variants carry no args.
- Capability probe (`probe.rs`) composes `engine_available` fail-closed from
  d3d11 && nvidia_adapter && wgc && nvenc && libav runtime && writable output.

Dev commands:
- `cargo build --release --bin windagent-recorder`
- Probe by hand: `printf '{"op":"capabilities"}\n' | target/release/windagent-recorder.exe`
- Regression suite: `cargo test`

Raw 1080p60 frames never leave this process except as NVENC bitstreams into MKV.
