// Phase 6 — Tauri shell entrypoint (Rust).
//
// Run locally (requires Rust toolchain):
//   cargo install tauri-cli
//   cargo tauri dev
//
// In Phase 9 we will also add a Python sidecar launcher so the backend
// starts automatically with the desktop app. For now, run the backend
// separately via apps/backend/scripts/dev_backend.ps1.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    windagent_desktop_lib::run()
}