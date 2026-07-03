// Phase 6 — Tauri runtime library.
//
// Provides native system-metrics commands via Tauri IPC so the frontend
// can display real CPU / RAM / GPU numbers instead of random mock data.
//
// GPU strategy:
//   1. Try NVML (NVIDIA Management Library) for discrete GPU usage + VRAM.
//   2. If NVML is unavailable (no NVIDIA driver), fall back to zeros so the
//      UI still works gracefully.

use once_cell::sync::Lazy;
use serde::Serialize;
use std::fs::OpenOptions;
use std::io::Write;
use std::sync::Mutex;
use sysinfo::System;

/// Simple file logger for NVML debug output
fn log_to_file(msg: &str) {
    // Also write a test file on first call to verify file creation works
    static INIT: std::sync::Once = std::sync::Once::new();
    INIT.call_once(|| {
        let _ = std::fs::write(r"D:\antigaravity_code\WindAgent\apps\desktop\src-tauri\nvml_debug.log", "NVML debug log started\n");
        let _ = std::fs::write(r"nvml_debug.log", "NVML debug log started\n");
        let _ = std::fs::write(r".\nvml_debug.log", "NVML debug log started\n");
    });
    
    let paths = [
        r"D:\antigaravity_code\WindAgent\apps\desktop\src-tauri\nvml_debug.log",
        r"nvml_debug.log",
        r".\nvml_debug.log",
    ];
    for path in paths {
        if let Ok(mut file) = OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
        {
            let _ = writeln!(file, "{}", msg);
            break;
        }
    }
}

// Write a startup marker on first call to get_system_metrics
static STARTUP_MARKER: once_cell::sync::OnceCell<()> = once_cell::sync::OnceCell::new();
fn ensure_startup_marker() {
    STARTUP_MARKER.get_or_init(|| {
        let _ = std::fs::write(r"D:\antigaravity_code\WindAgent\apps\desktop\src-tauri\startup_marker.log", "Lib loaded\n");
        let _ = std::fs::write(r"startup_marker.log", "Lib loaded\n");
    });
}

// ─── Serde structs ────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct AppMetadata {
    pub name: &'static str,
    pub version: &'static str,
}

/// Real-time system metrics returned to the frontend on every poll.
#[derive(Debug, Serialize, Clone)]
pub struct SystemMetrics {
    /// CPU usage 0–100 (%)
    pub cpu: f32,
    /// RAM usage 0–100 (%)
    pub ram: f32,
    /// RAM used in GB
    pub ram_gb: f32,
    /// Total RAM in GB
    pub ram_total_gb: f32,
    /// Discrete GPU usage 0–100 (%). 0 when unavailable.
    pub gpu: f32,
    /// GPU name (e.g. "NVIDIA GeForce RTX 3060")
    pub gpu_name: String,
    /// VRAM used in GB. 0 when unavailable.
    pub vram_gb: f32,
    /// Total VRAM in GB. 0 when unavailable.
    pub vram_total_gb: f32,
    /// VRAM usage 0–100 (%). 0 when unavailable.
    pub vram: f32,
}

// ─── Globals ──────────────────────────────────────────────────────────────────

/// Cached sysinfo System struct (refreshes are cheap).
static SYS: Lazy<Mutex<System>> = Lazy::new(|| Mutex::new(System::new_all()));

// ─── Tauri commands ───────────────────────────────────────────────────────────

#[tauri::command]
fn app_metadata() -> AppMetadata {
    AppMetadata {
        name: env!("CARGO_PKG_NAME"),
        version: env!("CARGO_PKG_VERSION"),
    }
}

/// Reads real CPU, RAM, and NVIDIA discrete GPU metrics.
/// Called by the frontend every 2 seconds via `invoke("get_system_metrics")`.
#[tauri::command]
fn get_system_metrics() -> SystemMetrics {
    // Write startup marker on first call
    ensure_startup_marker();

    // ── CPU & RAM via sysinfo ─────────────────────────────────────────────────
    let (cpu_pct, ram_pct, ram_gb, ram_total_gb) = {
        let mut sys = SYS.lock().unwrap();
        sys.refresh_cpu_usage();
        sys.refresh_memory();

        let cpu: f32 = {
            let cpus = sys.cpus();
            if cpus.is_empty() {
                0.0
            } else {
                cpus.iter().map(|c| c.cpu_usage()).sum::<f32>() / cpus.len() as f32
            }
        };

        let total = sys.total_memory() as f32;
        let used = sys.used_memory() as f32;
        let ram_pct = if total > 0.0 { (used / total) * 100.0 } else { 0.0 };
        let ram_gb = used / 1_073_741_824.0;      // bytes → GB
        let ram_total_gb = total / 1_073_741_824.0;

        (cpu, ram_pct, ram_gb, ram_total_gb)
    };

    // ── NVIDIA GPU via NVML ───────────────────────────────────────────────────
    let gpu_info = read_nvidia_gpu();

    SystemMetrics {
        cpu: (cpu_pct * 10.0).round() / 10.0,
        ram: (ram_pct * 10.0).round() / 10.0,
        ram_gb: (ram_gb * 10.0).round() / 10.0,
        ram_total_gb: (ram_total_gb * 10.0).round() / 10.0,
        gpu: gpu_info.0,
        gpu_name: gpu_info.1,
        vram_gb: gpu_info.2,
        vram_total_gb: gpu_info.3,
        vram: gpu_info.4,
    }
}

/// Returns (gpu_pct, gpu_name, vram_used_gb, vram_total_gb, vram_pct).
/// On any NVML error returns zeros and an empty name so the UI degrades
/// gracefully (shows 0% instead of crashing).
fn read_nvidia_gpu() -> (f32, String, f32, f32, f32) {
    use nvml_wrapper::Nvml;

    let nvml = match Nvml::init() {
        Ok(n) => n,
        Err(e) => {
            let msg = format!("[NVML] init failed: {:?}", e);
            eprintln!("{}", msg);
            log_to_file(&msg);
            return (0.0, "N/A".into(), 0.0, 0.0, 0.0);
        }
    };

    // Pick the *first discrete* GPU (index 0 is almost always the primary
    // dedicated card on a laptop/desktop with an iGPU).
    // To target a specific GPU, we skip any device whose name contains
    // "Intel" or "Microsoft" (software / integrated adapters that show up
    // as NVML devices in some edge cases are extremely rare, but we guard
    // anyway by iterating).
    let device_count = match nvml.device_count() {
        Ok(n) => n,
        Err(e) => {
            let msg = format!("[NVML] device_count failed: {:?}", e);
            eprintln!("{}", msg);
            log_to_file(&msg);
            return (0.0, "N/A".into(), 0.0, 0.0, 0.0);
        }
    };

    let msg = format!("[NVML] Found {} device(s)", device_count);
    eprintln!("{}", msg);
    log_to_file(&msg);

    for idx in 0..device_count {
        let device = match nvml.device_by_index(idx) {
            Ok(d) => d,
            Err(e) => {
                let msg = format!("[NVML] device_by_index({}) failed: {:?}", idx, e);
                eprintln!("{}", msg);
                log_to_file(&msg);
                continue;
            }
        };

        let name = device.name().unwrap_or_default();

        let msg = format!("[NVML] Device {}: name='{}'", idx, name);
        eprintln!("{}", msg);
        log_to_file(&msg);

        // Skip integrated / software adapters
        let name_lower = name.to_lowercase();
        if name_lower.contains("intel") || name_lower.contains("microsoft") {
            let msg = format!("[NVML] Device {} skipped (integrated/software)", idx);
            eprintln!("{}", msg);
            log_to_file(&msg);
            continue;
        }

        // GPU core utilisation (%)
        let gpu_pct = device
            .utilization_rates()
            .map(|u| u.gpu as f32)
            .unwrap_or(0.0);

        // VRAM
        let (vram_used_gb, vram_total_gb, vram_pct) = device
            .memory_info()
            .map(|m| {
                let used = m.used as f32 / 1_073_741_824.0;
                let total = m.total as f32 / 1_073_741_824.0;
                let pct = if total > 0.0 { (used / total) * 100.0 } else { 0.0 };
                (
                    (used * 10.0).round() / 10.0,
                    (total * 10.0).round() / 10.0,
                    (pct * 10.0).round() / 10.0,
                )
            })
            .unwrap_or((0.0, 0.0, 0.0));

        let msg = format!("[NVML] Device {} selected: gpu_pct={}, vram_used={}GB, vram_total={}GB, vram_pct={}", 
                  idx, gpu_pct, vram_used_gb, vram_total_gb, vram_pct);
        eprintln!("{}", msg);
        log_to_file(&msg);

        return (gpu_pct, name, vram_used_gb, vram_total_gb, vram_pct);
    }

    let msg = "[NVML] No discrete GPU found after filtering";
    eprintln!("{}", msg);
    log_to_file(msg);
    (0.0, "N/A".into(), 0.0, 0.0, 0.0)
}

// ─── App entry ────────────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![app_metadata, get_system_metrics])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}