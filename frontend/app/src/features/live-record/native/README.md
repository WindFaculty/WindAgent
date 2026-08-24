# Native Recording Engine — Phase 0 Frozen

> Gate: `LIVE_RECORD_P0_ARCHITECTURE_FROZEN`

Subsystem: **Native Recording Engine**

Separation enforced:
- **Tauri = control plane** (`apps/desktop/src-tauri/src/lib.rs` + `live_record/` module). Exposes ONLY the 7 commands in `contracts/ipc.ts`.
- **Recording sidecar = data plane** (`apps/desktop/native/recording-engine/`). Owns WGC → D3D11 → NVENC → libavformat → MKV segmented pipeline.
- Raw 1080p60 frames never cross Tauri IPC. Only preview frames + metrics/events.
- Audio abstraction `AudioCapturePort` exists but `audio_enabled=false` in P0 (WASAPI later).

Status (updated after P1/P2 closure):
- The sidecar is a **real data plane** — ffmpeg `ddagrab` capture → NVENC
  (`h264_nvenc`/`hevc_nvenc`) → segmented MKV (5/10 min) + flushed
  `timeline.jsonl` + manifest recovery, driven over JSONL stdio IPC.
- Direct WGC/D3D11/NVENC/libav API linkage remains behind the empty
  `wgc`/`nvenc` cargo features; the ffmpeg path is the shipping pipeline.
- The sidecar is bundled with the desktop app via Tauri
  `bundle.externalBin` (build it with `npm run build:sidecar` in
  `apps/desktop`).

See:
- `contracts/recordingEngine.ts`
- `contracts/ipc.ts`
- `apps/desktop/native/recording-engine/README.md`
