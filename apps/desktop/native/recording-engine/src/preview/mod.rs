//! GPU preview path — recording pipeline NEVER depends on it (ban_ke_hoach_v1.md §13).
//!
//! ```text
//! D3D11 texture → VideoProcessor downscale ≤1280×720 → staging readback
//!              → WIC JPEG encode → recorder://preview (base64, ≤2 FPS)
//! ```
//!
//! Priority ladder (Principle G + §18): under load the preview degrades
//! 2 → 1 → 0.5 FPS and can stop entirely — recording FPS never changes.
//!
//! CPU readback of the tiny 720p staging surface is the one sanctioned
//! exception to the zero-copy rule (§3-A).

pub mod gpu_preview;

use serde::{Deserialize, Serialize};

/// Preview rate stages (FPS). Recording quality is untouched by all of them.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PreviewRate {
    Off,
    HalfFps,
    OneFps,
    TwoFps,
}

impl PreviewRate {
    pub fn min_interval_ms(self) -> u64 {
        match self {
            Self::Off => u64::MAX,
            Self::HalfFps => 2_000,
            Self::OneFps => 1_000,
            Self::TwoFps => 500,
        }
    }

    /// Degradation order under load pressure: 2 → 1 → 0.5 → off.
    pub fn degrade(self) -> Self {
        match self {
            Self::TwoFps => Self::OneFps,
            Self::OneFps => Self::HalfFps,
            Self::HalfFps => Self::Off,
            Self::Off => Self::Off,
        }
    }

    /// Recovery after sustained headroom: off → 0.5 → 1 → 2.
    pub fn improve(self) -> Self {
        match self {
            Self::Off => Self::HalfFps,
            Self::HalfFps => Self::OneFps,
            Self::OneFps => Self::TwoFps,
            Self::TwoFps => Self::TwoFps,
        }
    }
}

impl Default for PreviewRate {
    fn default() -> Self {
        Self::TwoFps
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PreviewFormat {
    Jpeg,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PreviewConfig {
    pub downscale: (u32, u32), // ≤1280×720
    pub format: PreviewFormat,
    pub jpeg_quality: u32, // WIC quality [1..100]
}

impl Default for PreviewConfig {
    fn default() -> Self {
        Self { downscale: (1280, 720), format: PreviewFormat::Jpeg, jpeg_quality: 80 }
    }
}

/// Encoded preview frame ready for IPC emission.
#[derive(Debug, Clone)]
pub struct PreviewJpeg {
    pub jpeg: Vec<u8>,
    pub width: u32,
    pub height: u32,
    pub qpc: u64,
}

/// Rate limiter shared by every preview producer. `force` bypasses pacing
/// for explicit single-shot requests only.
pub struct PreviewSampler {
    pub config: PreviewConfig,
    rate: PreviewRate,
    last_emit_ms: Option<u64>,
}

impl PreviewSampler {
    pub fn new(config: PreviewConfig) -> Self {
        Self { config, rate: PreviewRate::default(), last_emit_ms: None }
    }

    pub fn rate(&self) -> PreviewRate {
        self.rate
    }

    pub fn set_rate(&mut self, rate: PreviewRate) {
        self.rate = rate;
    }

    pub fn should_emit(&mut self, now_ms: u64) -> bool {
        match self.last_emit_ms {
            None => true,
            Some(last) => now_ms.saturating_sub(last) >= self.rate.min_interval_ms(),
        }
    }

    pub fn mark_emitted(&mut self, now_ms: u64) {
        self.last_emit_ms = Some(now_ms);
    }

    pub fn reset(&mut self) {
        self.last_emit_ms = None;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn degradation_ladder_is_monotonic() {
        let mut r = PreviewRate::TwoFps;
        r = r.degrade();
        assert_eq!(r, PreviewRate::OneFps);
        r = r.degrade();
        assert_eq!(r, PreviewRate::HalfFps);
        r = r.degrade();
        assert_eq!(r, PreviewRate::Off);
        assert_eq!(r.degrade(), PreviewRate::Off);
        // Recovery path mirrors it back up.
        assert_eq!(PreviewRate::Off.improve(), PreviewRate::HalfFps);
        assert_eq!(PreviewRate::TwoFps.improve(), PreviewRate::TwoFps);
    }

    #[test]
    fn rate_gate_paces_emission() {
        let mut s = PreviewSampler::new(PreviewConfig::default());
        assert!(s.should_emit(1000));
        s.mark_emitted(1000);
        assert!(!s.should_emit(1200)); // <500 ms at TwoFps
        assert!(s.should_emit(1501));
        s.set_rate(PreviewRate::Off);
        s.mark_emitted(2000);
        assert!(!s.should_emit(u64::MAX - 1));
    }
}
