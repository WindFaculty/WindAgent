//! Unified media clock — QPC is the single authority (ban_ke_hoach_v1.md §12).
//!
//! Video frames and every audio packet derive their presentation timestamps
//! from the same QueryPerformanceCounter origin so A/V cannot drift apart by
//! construction. Drift between a device's sample clock and QPC is *measured*
//! (`mic_drift_ppm` / `system_drift_ppm`) and compensated in timestamps —
//! never by mass-dropping audio frames.

#[cfg(windows)]
use windows_sys::Win32::System::Performance::QueryPerformanceCounter;

/// Raw monotonic tick counter.
#[inline]
pub fn qpc_now() -> u64 {
    #[cfg(windows)]
    unsafe {
        let mut v: i64 = 0;
        // Cannot realistically fail on Windows 8+.
        let _ = QueryPerformanceCounter(&mut v);
        v as u64
    }
    #[cfg(not(windows))]
    {
        std::time::Instant::now().elapsed().as_nanos() as u64
    }
}

/// Ticks per second for [`qpc_now`].
pub fn qpc_frequency() -> u64 {
    #[cfg(windows)]
    {
        // Cached — QueryPerformanceFrequency is constant per boot.
        static FREQ: std::sync::OnceLock<u64> = std::sync::OnceLock::new();
        *FREQ.get_or_init(|| {
            let mut freq: i64 = 0;
            // SAFETY: out-pointer only; cannot fail on supported Windows.
            unsafe { windows_sys::Win32::System::Performance::QueryPerformanceFrequency(&mut freq) };
            if freq > 0 { freq as u64 } else { 10_000_000 }
        })
    }
    #[cfg(not(windows))]
    {
        1_000_000_000
    }
}

/// Monotonic milliseconds since an arbitrary fixed origin.
#[inline]
pub fn now_ms() -> u64 {
    qpc_now_ms()
}

#[inline]
pub fn qpc_now_ms() -> u64 {
    (qpc_now() as f64 / qpc_frequency() as f64 * 1000.0) as u64
}

/// Convert a QPC delta to microseconds.
#[inline]
pub fn ticks_to_micros(ticks: u64) -> u64 {
    ((ticks as f64 / qpc_frequency() as f64) * 1_000_000.0) as u64
}

/// Convert a QPC delta to seconds (f64, for timeline t fields).
#[inline]
pub fn ticks_to_sec(ticks: u64) -> f64 {
    ticks as f64 / qpc_frequency() as f64
}

/// Convert a WinRT `TimeSpan` (100 ns units since boot — what WGC's
/// `SystemRelativeTime` reports) onto the QPC tick scale every other
/// timestamp in the engine uses.
#[inline]
pub fn hundred_ns_to_qpc_ticks(v: i64) -> u64 {
    let v = v.max(0) as u64;
    ((v as u128 * qpc_frequency() as u128) / 10_000_000) as u64
}

// ─── Recording-origin PTS math ──────────────────────────────────────────────

/// Origin anchor taken once at recording start; all stream PTS derive from it.
#[derive(Debug, Clone, Copy)]
pub struct ClockOrigin {
    start_qpc: u64,
}

impl ClockOrigin {
    pub fn new() -> Self {
        Self { start_qpc: qpc_now() }
    }

    /// Microseconds since recording start (PTS basis for every track).
    #[inline]
    pub fn micros_since(&self, qpc: u64) -> u64 {
        qpc.saturating_sub(self.start_qpc).min(u64::MAX)
            .checked_mul(1_000_000)
            .map(|n| n / qpc_frequency())
            .unwrap_or_else(|| ticks_to_micros(qpc.saturating_sub(self.start_qpc)))
    }

    /// Seconds since recording start (timeline events).
    #[inline]
    pub fn sec_since(&self, qpc: u64) -> f64 {
        ticks_to_sec(qpc.saturating_sub(self.start_qpc))
    }
}

impl Default for ClockOrigin {
    fn default() -> Self {
        Self::new()
    }
}

// ─── Drift measurement ──────────────────────────────────────────────────────

/// Tracks one audio device's sample-clock drift against the QPC wall clock.
///
/// Every delivered packet reports `(device_samples_delivered, qpc)`; expected
/// samples are derived from elapsed QPC time at nominal rate. The ratio
/// converges to the device's true rate error in ppm.
#[derive(Debug, Default)]
pub struct DriftTracker {
    primed: bool,
    last_time_us: u64,
    samples_at_last_window: u64,
    total_samples: u64,
    /// Exponentially-smoothed drift estimate in parts-per-million.
    smoothed_ppm: f64,
}

impl DriftTracker {
    pub fn new() -> Self {
        Self::default()
    }

    /// Feed one delivered packet with its **take-relative** timestamp in
    /// microseconds (pause spans excluded). Measuring against wall-clock
    /// instead would report every pause as massive negative drift.
    pub fn on_packet_us(&mut self, samples_in_packet: u64, take_time_us: u64) {
        // First packet only primes the baselines — it defines t0 and the
        // sample counter the first ≥1 s window deltas against.
        if !self.primed {
            self.primed = true;
            self.last_time_us = take_time_us;
            self.total_samples = samples_in_packet;
            self.samples_at_last_window = samples_in_packet;
            return;
        }
        self.total_samples += samples_in_packet;
        let dt = (take_time_us.saturating_sub(self.last_time_us)) as f64 / 1_000_000.0;
        if dt >= 1.0 {
            // Recompute over ≥1 s windows to keep ppm stable.
            let ds = self.total_samples.saturating_sub(self.samples_at_last_window) as f64;
            let instant_ppm = (ds / dt - 48_000.0) / 48_000.0 * 1_000_000.0;
            // EMA α=0.25 — responsive but jitter-tolerant.
            self.smoothed_ppm = if self.smoothed_ppm == 0.0 {
                instant_ppm
            } else {
                self.smoothed_ppm * 0.75 + instant_ppm * 0.25
            };
            self.samples_at_last_window = self.total_samples;
            self.last_time_us = take_time_us;
        }
    }

    pub fn drift_ppm(&self) -> f64 {
        self.smoothed_ppm
    }

    /// |drift| beyond this warrants a warning event (≈72 ms/hour audible risk).
    pub fn is_significant(&self) -> bool {
        self.smoothed_ppm.abs() > 200.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn origin_pts_are_monotonic_and_start_at_zero() {
        let origin = ClockOrigin::new();
        let mut prev = 0u64;
        for _ in 0..100 {
            let pts = origin.micros_since(qpc_now());
            assert!(pts >= prev);
            prev = pts;
            std::thread::sleep(std::time::Duration::from_micros(50));
        }
    }

    #[test]
    fn drift_tracker_reports_zero_for_nominal_rate() {
        let mut d = DriftTracker::new();
        // Simulate exactly-48000 packets arriving on nominal take-time.
        for sec in 0..5u64 {
            d.on_packet_us(48_000, (sec + 1) * 1_000_000);
        }
        assert!(d.drift_ppm().abs() < 1.0, "ppm={}", d.drift_ppm());
    }

    #[test]
    fn drift_tracker_detects_fast_clock() {
        let mut d = DriftTracker::new();
        // Device delivers 1% fast (48480 samples per second) ⇒ 10 000 ppm.
        for sec in 0..10u64 {
            d.on_packet_us(48_480, (sec + 1) * 1_000_000);
        }
        assert!(d.drift_ppm() > 9_000.0 && d.drift_ppm() < 11_000.0, "ppm={}", d.drift_ppm());
        assert!(d.is_significant());
    }

    #[test]
    fn drift_tracker_ignores_pause_spans() {
        let mut d = DriftTracker::new();
        // A 2 s wall-clock pause happens between the 2nd and 3rd packets, but
        // the feeder is idle while paused so TAKE-TIME stays evenly spaced —
        // the tracker must read zero drift, not a giant negative spike.
        d.on_packet_us(48_000, 0);
        d.on_packet_us(48_000, 1_000_000);
        d.on_packet_us(48_000, 2_000_000); // arrives right after resume
        assert!(d.drift_ppm().abs() < 1.0, "ppm={}", d.drift_ppm());
    }
}
