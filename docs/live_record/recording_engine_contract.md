# Recording Engine Contract — Phase 0 Frozen

> Gate: `LIVE_RECORD_P0_ARCHITECTURE_FROZEN` | Code: `frontend/app/src/features/live-record/contracts/recordingEngine.ts` | Rust: `apps/desktop/native/recording-engine/`

## Pipeline

```
Windows Graphics Capture
        │
        ▼
      D3D11
        │
        ├─────────────► Preview Sampler → Gemini frames (1–2 FPS, 1280×720 JPEG/WebP)
        │
        ▼
      NVENC (H.264/HEVC)
        │
        ▼
    libavformat (MKV)
        │
        ▼
    MKV Segments (5 or 10 min)
        │
        ▼
  timeline.jsonl + manifest.json
```

## Invariants

- `audio_enabled=false` in P0 (WASAPI abstraction exists but not active).
- Encoding runs native; Tauri receives only preview frames + metrics/events.
- Segments: `take_0001/segment_0001.mkv ...` + `timeline.jsonl` + `manifest.json`; every segment independently playable (MKV chosen for crash recovery).
- Finalize: `validate → concat/remux → final.mkv/mp4`.

## Performance Gates (frozen as acceptance reference)

- Dropped frames < 0.1%
- No sustained CPU saturation (encoder sidecar)
- NVENC hardware encoder confirmed
- Preview < 200 ms delay
- Gemini sampling ≤ 2 FPS
- 30–60 min soak PASS

## Rust Crate Layout (not expanding `src-tauri/lib.rs`)

```
apps/desktop/native/recording-engine/
├── Cargo.toml
└── src/
    ├── lib.rs
    ├── capture/
    ├── encoder/
    ├── muxer/
    ├── segment/
    ├── preview/
    ├── telemetry/
    └── ipc/
```

Tauri is control plane; recording-engine is data plane.
