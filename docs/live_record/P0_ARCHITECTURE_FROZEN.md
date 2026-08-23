# LIVE_RECORD_P0_ARCHITECTURE_FROZEN — Gate Evidence

> Status: **FROZEN** — Phase 0 baseline locked.
> Source Plan: `ban_ke_hoach_v1.md` Section 3.
> Date: 2026-08-23

This document is the single gate marker. All contracts below are **immutable** after this point; changes require a new ADR and version bump.

## 1. Four Frozen Subsystems

| Subsystem | Location | Boundary File |
|---|---|---|
| **Live Recording Domain** | `frontend/app/src/features/live-record/domain/` | `types.ts`, `stateMachine.ts`, `validation.ts` |
| **Live Director** | `frontend/app/src/features/live-record/live-director/` | `types.ts`, `contracts/directorTools.ts` |
| **Native Recording Engine** | `apps/desktop/native/recording-engine/` + `frontend/.../native/` | `contracts/recordingEngine.ts`, `contracts/ipc.ts` |
| **Recording UI** | `frontend/app/src/features/live-record/pages/` + `components/` + `hooks/` | `LiveRecordPage.tsx`, `useLiveRecord.ts` (UI-only) |

Rule: no logic from Domain/Director/Engine may be inlined into `useLiveRecord.ts` or `src-tauri/src/lib.rs` god file.

## 2. Required Contracts (must exist)

- [x] **Domain contract** — `docs/live_record/domain_contract.md` + `domain/types.ts`
- [x] **State machine** — `docs/live_record/state_machine.md` + `domain/stateMachine.ts`
- [x] **IPC contract** — `docs/live_record/ipc_contract.md` + `contracts/ipc.ts`
- [x] **Gemini tool contract** — `docs/live_record/tool_contract.md` + `contracts/directorTools.ts`
- [x] **Recording engine contract** — `docs/live_record/recording_engine_contract.md` + `contracts/recordingEngine.ts`
- [x] **Security boundary** — `docs/live_record/security_boundary.md`

## 3. P0 Freeze Invariants

- Episode is source of truth: `episode_revision != execution_plan.episode_revision → RECORDING_PLAN_STALE → BLOCKED`.
- `LIVE_DIRECTOR` vs `RECORDING_PREPARER` vs `NARRATION_TTS` are distinct roles resolved via Provider routing; UI requests role, not provider/model.
- Gemini tool allowlist is closed; any raw `shell/write_file/open_url/click/powershell` is denied at dispatcher before execution.
- Recording engine lifecycle independent of Gemini session (Principle D).
- Two pipelines: Recording 60 FPS vs AI observation 1–2 FPS downscaled (Principle E).
- `audio_enabled=false` in P0 (Principle F).

## 4. Verification

```bash
npm --prefix frontend/app run typecheck
npm --prefix frontend/app run test -- src/features/live-record/__tests__/p0Contracts.test.ts
cargo check --manifest-path apps/desktop/src-tauri/Cargo.toml
cargo test live_record --manifest-path apps/desktop/src-tauri/Cargo.toml
cargo check --manifest-path apps/desktop/native/recording-engine/Cargo.toml
```

Rust-side evidence: `live_record/` mirrors the frozen contract two-way — 12-state transition table (`state.rs` ↔ `domain/stateMachine.ts`), request/status payload types (`types.rs` ↔ `contracts/ipc.ts`), all 8 recorder commands registered and driving the state machine (`commands.rs`), with 17 gate tests (`tests.rs`) mirroring `p0Contracts.test.ts`.

Gate passes when all five checks are green and no contract file has been mutated without version bump.
