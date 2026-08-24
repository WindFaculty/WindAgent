//! Preview sampler — Principle E (ban_ke_hoach_v1.md Section 5)
//!
//! Recording: 1920×1080 @ 60 FPS → NVENC (full pipeline)
//! AI observation: 1–2 FPS, 1280×720 JPEG/WebP (downscaled, rate-limited)
//! Two pipelines diverge at D3D11 — raw frames never reach Gemini.

pub mod ffmpeg_preview;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PreviewFormat {
    Jpeg,
    WebP,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PreviewConfig {
    pub downscale: (u32, u32), // 1280×720
    pub fps: u32,              // 1 or 2
    pub format: PreviewFormat,
}

impl Default for PreviewConfig {
    fn default() -> Self {
        Self {
            downscale: (1280, 720),
            fps: 1,
            format: PreviewFormat::Jpeg,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PreviewFrame {
    pub width: u32,
    pub height: u32,
    pub format: PreviewFormat,
    pub data_len: usize, // JPEG bytes (mock)
    pub timestamp_ms: u64,
}

pub struct PreviewSampler {
    pub config: PreviewConfig,
    last_emit_ms: Option<u64>,
    pending: Option<PreviewFrame>,
}

impl PreviewSampler {
    pub fn new(config: PreviewConfig) -> Self {
        Self {
            config,
            last_emit_ms: None,
            pending: None,
        }
    }

    fn min_interval_ms(&self) -> u64 {
        if self.config.fps == 2 { 500 } else { 1000 }
    }

    /// Downscale a captured frame (mock: just re-tag size/format).
    pub fn sample(&mut self, frame: &crate::capture::CapturedFrame) -> PreviewFrame {
        PreviewFrame {
            width: self.config.downscale.0,
            height: self.config.downscale.1,
            format: self.config.format,
            data_len: 64 * 1024, // ~64KB JPEG mock
            timestamp_ms: frame.timestamp_ms,
        }
    }

    /// Stage a preview frame; caller should poll `consume()` at 1–2 FPS.
    pub fn stage(&mut self, frame: PreviewFrame) {
        self.pending = Some(frame);
    }

    pub fn should_emit(&self, now_ms: u64, force: bool) -> bool {
        if force { return true; }
        if self.pending.is_some() { return true; }
        match self.last_emit_ms {
            None => true,
            Some(last) => now_ms.saturating_sub(last) >= self.min_interval_ms(),
        }
    }

    pub fn consume(&mut self, now_ms: u64) -> Option<PreviewFrame> {
        let pending = self.pending.take()?;
        if let Some(last) = self.last_emit_ms {
            if now_ms.saturating_sub(last) < self.min_interval_ms() {
                // Rate-limit — put it back and drop this cycle (Gemini sees 1–2 FPS max)
                self.pending = Some(pending);
                return None;
            }
        }
        self.last_emit_ms = Some(now_ms);
        Some(pending)
    }

    pub fn reset(&mut self) {
        self.pending = None;
        self.last_emit_ms = None;
    }
}
