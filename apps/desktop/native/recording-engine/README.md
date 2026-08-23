# Recording Engine — Native Sidecar (Data Plane)

> Gate: `LIVE_RECORD_P0_ARCHITECTURE_FROZEN`

- Control plane: `apps/desktop/src-tauri/src/live_record/` (7 Tauri commands only)
- Data plane: this crate (`apps/desktop/native/recording-engine/`)

Pipeline (Phase 8-9):

```
WGC → D3D11 → (Preview Sampler 1-2 FPS 1280×720) → NVENC → libavformat MKV segmented → timeline.jsonl
```

Raw 1080p60 frames never cross IPC.

P0: skeleton only. Each `src/*/` holds a stub `mod.rs`.
