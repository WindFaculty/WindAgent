# Live Director — Phase 0 Frozen

> Gate: `LIVE_RECORD_P0_ARCHITECTURE_FROZEN`

Subsystem: **Live Director**

Responsibilities frozen in P0:
- Owns the Gemini Live WebSocket client in **desktop TypeScript** (not Python API).
- Connects Desktop → Gemini directly via **ephemeral token** (no API key on device, one-session use).
- Sends screen frames at **1–2 FPS downscaled 1280×720 JPEG/WebP** (event-driven); recording pipeline retains 60 FPS independently.
- Understands only **constrained tools** from `contracts/directorTools.ts`; any raw shell/write/open tool is rejected at gate.
- Handles **session resumption** with `idempotency_key` + `execution_id` so no successful action is replayed.

Files in later phases:
- `LiveDirectorClient.ts`
- `LiveDirectorSession.ts`
- `FrameSampler.ts`
- `ToolCallDispatcher.ts`
- `CueContextBuilder.ts`
- `SessionResumptionManager.ts`

Contracts:
- `../contracts/directorTools.ts` — allowlist/denylist
- `../domain/types.ts` — `LiveExecutionPlan` + `PreparedAction`
- `types.ts` — connection + sampler configs (this folder)
