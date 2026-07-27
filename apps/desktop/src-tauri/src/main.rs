// Phase 6 — Tauri shell entrypoint (Rust).
//
// Run locally (requires Rust toolchain):
//   cargo install tauri-cli
//   cargo tauri dev
//
// The desktop shell talks only to the canonical Architecture V2 API.
// Start it separately with `scripts/dev_api.ps1` during local development.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    windagent_desktop_lib::run()
}
