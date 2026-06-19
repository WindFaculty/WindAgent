// Phase 6 — Tauri runtime library.
//
// Minimal placeholder. The desktop app's logic lives in the React
// frontend (apps/desktop/src/). This crate is just the shell that
// wraps it in a native window.

use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct AppMetadata {
    pub name: &'static str,
    pub version: &'static str,
}

#[tauri::command]
fn app_metadata() -> AppMetadata {
    AppMetadata {
        name: env!("CARGO_PKG_NAME"),
        version: env!("CARGO_PKG_VERSION"),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![app_metadata])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}