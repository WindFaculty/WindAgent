# Native Recording Engine — V2 Hard Cutover

> Gate: `LIVE_RECORD_V2_CONTRACT_FROZEN`

Subsystem: **Native Recording Engine**

Separation enforced:
- **Tauri = control plane** (`apps/desktop/src-tauri/src/live_record/`). Exposes
  ONLY the 10 commands in `contracts/ipc.ts` (prepare/start/pause/resume/stop/
  get_status/create_marker/mute/recover/get_capabilities). It never re-interprets
  encoder settings (Principle D) — the engine's validator is the single source of truth.
- **Recording sidecar = data plane** (`apps/desktop/native/recording-engine/`).
  Owns the direct Windows pipeline: WGC → D3D11 GPU surface → NVENC registered
  resource → libavformat → segmented MKV, plus WASAPI mic + system-loopback as
  separate MKV tracks.
- Raw 1080p60 frames never cross Tauri IPC. Only preview JPEGs (≤1280×720,
  ≤2 FPS), per-track audio meters, and measured telemetry.
- One clock authority: QPC stamps every PTS on both sides of the IPC.

Status (V2):
- The FFmpeg-CLI `ddagrab` path from P0/P1 is **removed from production** — it
  survives nowhere; FFmpeg shared DLLs are loaded at runtime only for
  muxing (`avformat`) and AAC encoding (`avcodec`).
- Production backend string is `wgc-nvenc-mkv`; it is reported only when the
  capability probe passes every stage (D3D11 hardware adapter + WGC OS support +
  NVENC session + WASAPI + libav runtime + writable output). Any failure is
  fail-closed: `engine_available=false` plus a human-readable `blockers` list,
  and recording is BLOCKED — there is no software fallback.
- A mock backend exists solely under `WINDAGENT_RECORDER_ALLOW_MOCK=1` for dev
  simulation; production builds must not set it.
- The sidecar ships via Tauri `bundle.externalBin`
  (`npm run build:sidecar` in `apps/desktop`); the libav runtime DLLs ship in
  `bundle.resources` (see `apps/desktop/src-tauri/resources/libav/README.md`).

See:
- `contracts/recordingEngine.ts` — frozen V2 profile mirrored Rust↔TS
- `contracts/ipc.ts` — frozen control-plane surface + event payloads
- `apps/desktop/native/recording-engine/README.md` — sidecar internals
