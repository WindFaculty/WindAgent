//! Real telemetry — measured counters only (ban_ke_hoach_v1.md §17).
//!
//! Every number here comes from an actual pipeline event; nothing is
//! hard-coded or estimated from profile assumptions. FPS uses a 2 s sliding
//! window; NVENC latency keeps a bounded ring for p50/p95.

use std::collections::VecDeque;

/// Quality-first degradation ladder (§18): recording pipeline NEVER degrades;
/// preview and director absorb load pressure first.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ResourceStage {
    #[default]
    Normal,
    /// GPU/encode headroom low → preview drops 2 → 1 → 0.5 FPS.
    PreviewDegraded,
    /// Still high → Gemini observation rate reduced.
    DirectorDegraded,
    /// Dangerous thermal/disk territory → warn / protective stop.
    Danger,
}

impl ResourceStage {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Normal => "normal",
            Self::PreviewDegraded => "preview_degraded",
            Self::DirectorDegraded => "director_degraded",
            Self::Danger => "danger",
        }
    }
}

#[derive(Debug, Default)]
pub struct Telemetry {
    pub frames_captured: u64,
    pub frames_submitted: u64,
    pub frames_encoded: u64,
    pub frames_dropped: u64,

    pub audio_underruns: u64,
    pub director_reconnects: u32,

    // Sliding windows (QPC micros)
    capture_events: VecDeque<u64>,
    encode_events: VecDeque<u64>,
    byte_events: VecDeque<(u64, u64)>, // (qpc_us, bytes)
    encode_latencies_ms: VecDeque<f64>,

    pub disk_free_gb: f64,
    pub stage: ResourceStage,
}

const WINDOW_US: u64 = 2_000_000;
const MAX_LATENCY_SAMPLES: usize = 512;

pub fn percentile(sorted: &[f64], p: f64) -> f64 {
    if sorted.is_empty() {
        return 0.0;
    }
    let idx = ((sorted.len() as f64 - 1.0) * p).round() as usize;
    sorted[idx.min(sorted.len() - 1)]
}

fn prune_window(window: &mut VecDeque<u64>, now_us: u64) {
    while let Some(&t) = window.front() {
        if now_us.saturating_sub(t) > WINDOW_US {
            window.pop_front();
        } else {
            break;
        }
    }
}

impl Telemetry {
    pub fn on_frame_captured(&mut self, qpc_us: u64) {
        self.frames_captured += 1;
        prune_window(&mut self.capture_events, qpc_us);
        self.capture_events.push_back(qpc_us);
    }

    pub fn on_frame_submitted(&mut self) {
        self.frames_submitted += 1;
    }

    pub fn on_frame_encoded(&mut self, qpc_us: u64) {
        self.frames_encoded += 1;
        prune_window(&mut self.encode_events, qpc_us);
        self.encode_events.push_back(qpc_us);
    }

    pub fn on_frame_dropped(&mut self) {
        self.frames_dropped += 1;
    }

    pub fn on_encode_latency_ms(&mut self, ms: f64) {
        self.encode_latencies_ms.push_back(ms);
        if self.encode_latencies_ms.len() > MAX_LATENCY_SAMPLES {
            self.encode_latencies_ms.pop_front();
        }
    }

    pub fn on_bytes_written(&mut self, qpc_us: u64, bytes: u64) {
        self.byte_events.push_back((qpc_us, bytes));
        if self.byte_events.len() > 4096 {
            self.byte_events.pop_front();
        }
    }

    pub fn on_audio_underrun(&mut self) {
        self.audio_underruns += 1;
    }

    pub fn dropped_pct(&self) -> f64 {
        if self.frames_captured == 0 {
            0.0
        } else {
            (self.frames_dropped as f64 / self.frames_captured as f64) * 100.0
        }
    }

    /// Read-only windowed rate (pruning happens on the write path so these
    /// getters stay callable through a shared reference).
    pub fn capture_fps(&self, now_us: u64) -> f64 {
        let recent =
            self.capture_events.iter().filter(|&&t| now_us.saturating_sub(t) <= WINDOW_US).count();
        recent as f64 * 1_000_000.0 / WINDOW_US as f64
    }

    pub fn encode_fps(&self, now_us: u64) -> f64 {
        let recent =
            self.encode_events.iter().filter(|&&t| now_us.saturating_sub(t) <= WINDOW_US).count();
        recent as f64 * 1_000_000.0 / WINDOW_US as f64
    }

    /// MB/s written over the trailing window (bytes delta ÷ time delta).
    pub fn disk_write_mbps(&self, now_us: u64) -> f64 {
        let mut first = None;
        let mut last = None;
        for &(t, b) in &self.byte_events {
            if now_us.saturating_sub(t) > WINDOW_US {
                continue;
            }
            if first.is_none() {
                first = Some((t, b));
            }
            last = Some((t, b));
        }
        match (first, last) {
            (Some((t0, b0)), Some((_, b1))) => {
                let dt_us = (now_us - t0).max(1);
                let db = b1.saturating_sub(b0);
                db as f64 / (dt_us as f64 / 1_000_000.0) / (1024.0 * 1024.0)
            }
            _ => 0.0,
        }
    }

    pub fn latency_p50(&self) -> Option<f64> {
        let mut v: Vec<f64> = self.encode_latencies_ms.iter().copied().collect();
        if v.is_empty() {
            None
        } else {
            v.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
            Some(percentile(&v, 0.50))
        }
    }

    pub fn latency_p95(&self) -> Option<f64> {
        let mut v: Vec<f64> = self.encode_latencies_ms.iter().copied().collect();
        if v.is_empty() {
            None
        } else {
            v.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
            Some(percentile(&v, 0.95))
        }
    }
}

/// RMS/Peak in dBFS for one PCM block (UI meter feed).
pub fn rms_peak_dbfs(samples: &[f32]) -> (f64, f64) {
    if samples.is_empty() {
        return (-120.0, -120.0);
    }
    let sum_sq: f64 = samples.iter().map(|s| (*s as f64) * (*s as f64)).sum();
    let rms = (sum_sq / samples.len() as f64).sqrt();
    let peak = samples.iter().fold(0.0f32, |m, s| m.max(s.abs()));
    let to_db = |v: f64| if v <= f64::EPSILON { -120.0 } else { 20.0 * v.log10() };
    (to_db(rms), to_db(peak as f64))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn percentiles_interpolate_over_ring() {
        assert_eq!(percentile(&[], 0.5), 0.0);
        assert_eq!(percentile(&[1.0], 0.99), 1.0);
        let mut v: Vec<f64> = (1..=100).map(|i| i as f64).collect();
        v.sort_by(|a, b| a.partial_cmp(b).unwrap());
        assert_eq!(percentile(&v, 0.5), 51.0); // round((100-1)*0.5)=50 → index 50 → value 51
        assert_eq!(percentile(&v, 0.95), 95.0); // round(99*0.95)=94 → 95
    }

    #[test]
    fn fps_window_counts_recent_only() {
        let mut t = Telemetry::default();
        let t0 = 10_000_000u64;
        // A real 60 fps stream: frames every ~16.7 ms. Measuring immediately
        // after the last event puts the full ~2 s spread inside the window.
        for i in 0..120 {
            t.on_frame_captured(t0 + i * 16_666);
        }
        let fps = t.capture_fps(t0 + 119 * 16_666 + 1);
        assert!((fps - 60.0).abs() < 2.0, "fps={fps}");
        // Events older than the window stop counting (the newest event sits
        // exactly on the window edge, so step one microsecond past it).
        assert_eq!(t.capture_fps(t0 + 119 * 16_666 + WINDOW_US + 1), 0.0);
    }

    #[test]
    fn dropped_pct_matches_contract_gate() {
        let mut t = Telemetry::default();
        for _ in 0..1000 {
            t.on_frame_captured(crate::clock::qpc_now());
            t.on_frame_encoded(crate::clock::qpc_now());
        }
        assert!(t.dropped_pct().abs() < f64::EPSILON);
        for _ in 0..1 {
            t.on_frame_dropped();
        }
        assert_eq!(t.dropped_pct(), 0.1);
    }

    #[test]
    fn rms_dbfs_scales_logarithmically() {
        let silence = vec![0.0f32; 480];
        assert_eq!(rms_peak_dbfs(&silence), (-120.0, -120.0));
        let full = vec![1.0f32; 480];
        let (rms, peak) = rms_peak_dbfs(&full);
        assert!((rms - 0.0).abs() < 1e-9 && (peak - 0.0).abs() < 1e-9);
        let half = vec![0.5f32; 480];
        let (rms, _) = rms_peak_dbfs(&half);
        assert!((rms - (-6.02)).abs() < 0.05, "rms={rms}");
    }
}
