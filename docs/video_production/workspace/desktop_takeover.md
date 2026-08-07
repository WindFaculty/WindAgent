# Desktop Shell & Takeover Specification

## 1. Overview

The Desktop Shell (Tauri / Rust sidecar architecture) reuses Web client contracts and UI components while providing local OS window controls, system tray notifications, and browser session takeover capabilities.

## 2. Browser Takeover Protocol

1. **Headed Session Handoff**: When a worker process requires human intervention, Desktop triggers a headed browser session popup targeting the dedicated profile container.
2. **Profile & Secret Masking**: The Desktop app MUST NOT expose raw session profile paths, tokens, or browser cookies in local logs or UI inspector views.
3. **No Direct Backend Bundling**: The Desktop build reuses the unified API V2 client. It does NOT bundle independent database engines or duplicate backend state authorities.

## 3. Desktop Restart State Recovery

1. **State Preservation**: If the Desktop application crashes or restarts, server-side workflow execution remains unaffected.
2. **Re-connection Recovery**: Upon restart, Desktop queries `GET /snapshot` and resumes the SSE/WebSocket event stream from the last sequence cursor.
