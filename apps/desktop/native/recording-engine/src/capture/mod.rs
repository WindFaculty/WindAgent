//! Capture pipeline — Phase 8 (ban_ke_hoach_v1.md Section 16)
//!
//! Windows Graphics Capture (WGC) → D3D11 texture.
//! Two outputs:
//!   - Recording path: 60 FPS full-res → NVENC
//!   - Preview path:   1–2 FPS downscaled 1280×720 JPEG → Gemini (via Tauri preview event)
//!
//! Raw 1080p60 frames never cross Tauri IPC — only metrics + preview frames.

pub mod ffmpeg_capture;

use serde::{Deserialize, Serialize};

/// Abstract capture port — data plane boundary.
pub trait CapturePort: Send {
    fn prepare(&mut self) -> Result<(), String>;
    fn start(&mut self) -> Result<(), String>;
    fn stop(&mut self) -> Result<(), String>;
    /// Poll next captured frame (mock returns synthetic frame).
    fn poll_frame(&mut self) -> Option<CapturedFrame>;
    fn is_available(&self) -> bool;
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapturedFrame {
    pub width: u32,
    pub height: u32,
    pub fps: u32,
    /// Mock: raw BGRA bytes would be here; in real WGC this is a D3D11 texture handle.
    pub data_len: usize,
    pub timestamp_ms: u64,
}

// ─── WGC (real) ────────────────────────────────────────────────────────────

/// Windows Graphics Capture backend — real implementation is Windows-only.
/// On non-Windows or without WGC, `is_available() → false` and the engine
/// fail-closes into BLOCKED (P0/P1 policy).
pub struct WgcCapture {
    pub resolution: (u32, u32),
    pub fps: u32,
    #[allow(dead_code)]
    available: bool,
}

impl WgcCapture {
    pub fn new(resolution: (u32, u32), fps: u32) -> Self {
        Self {
            resolution,
            fps,
            // Probe at construction — real probe would call
            // `GraphicsCaptureItem::TryCreateFromWindow` + D3D11 device creation.
            available: Self::probe_available(),
        }
    }

    #[cfg(target_os = "windows")]
    fn probe_available() -> bool {
        // Real probe: check Windows version ≥ 10.0.17763 and D3D11 device.
        // For now, report unavailable until the sidecar links against windows crate.
        false
    }

    #[cfg(not(target_os = "windows"))]
    fn probe_available() -> bool {
        false
    }
}

impl CapturePort for WgcCapture {
    fn prepare(&mut self) -> Result<(), String> {
        if !self.is_available() {
            return Err("WGC_UNAVAILABLE: Windows Graphics Capture not available on this host".into());
        }
        Ok(())
    }

    fn start(&mut self) -> Result<(), String> {
        self.prepare()?;
        Ok(())
    }

    fn stop(&mut self) -> Result<(), String> {
        Ok(())
    }

    fn poll_frame(&mut self) -> Option<CapturedFrame> {
        // Real: wait for WGC frame arrival via D3D11.
        None
    }

    fn is_available(&self) -> bool {
        self.available
    }
}

// ─── Mock (for tests / CI without Windows) ─────────────────────────────────

pub struct MockCapture {
    pub resolution: (u32, u32),
    pub fps: u32,
    started: bool,
    frame_counter: u64,
}

impl MockCapture {
    pub fn new(resolution: (u32, u32), fps: u32) -> Self {
        Self {
            resolution,
            fps,
            started: false,
            frame_counter: 0,
        }
    }
}

impl CapturePort for MockCapture {
    fn prepare(&mut self) -> Result<(), String> {
        Ok(())
    }

    fn start(&mut self) -> Result<(), String> {
        self.started = true;
        Ok(())
    }

    fn stop(&mut self) -> Result<(), String> {
        self.started = false;
        Ok(())
    }

    fn poll_frame(&mut self) -> Option<CapturedFrame> {
        if !self.started {
            return None;
        }
        self.frame_counter += 1;
        Some(CapturedFrame {
            width: self.resolution.0,
            height: self.resolution.1,
            fps: self.fps,
            data_len: (self.resolution.0 * self.resolution.1 * 4) as usize,
            timestamp_ms: self.frame_counter * (1000 / self.fps as u64),
        })
    }

    fn is_available(&self) -> bool {
        true
    }
}
