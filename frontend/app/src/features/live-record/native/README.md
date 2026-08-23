# Native Recording Engine — Phase 0 Frozen

> Gate: `LIVE_RECORD_P0_ARCHITECTURE_FROZEN`

Subsystem: **Native Recording Engine**

Separation enforced:
- **Tauri = control plane** (`apps/desktop/src-tauri/src/lib.rs` + `live_record/` module). Exposes ONLY the 7 commands in `contracts/ipc.ts`.
- **Recording sidecar = data plane** (`apps/desktop/native/recording-engine/`). Owns WGC → D3D11 → NVENC → libavformat → MKV segmented pipeline.
- Raw 1080p60 frames never cross Tauri IPC. Only preview frames + metrics/events.
- Audio abstraction `AudioCapturePort` exists but `audio_enabled=false` in P0 (WASAPI later).

P0 deliverable: contracts + crate skeleton only. Full WGC/NVENC impl lands in Phase 8–9.

See:
- `contracts/recordingEngine.ts`
- `contracts/ipc.ts`
- `apps/desktop/native/recording-engine/README.md`
