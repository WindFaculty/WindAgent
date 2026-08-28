//! Live recording pipeline — thread orchestration for the native cutover
//! (ban_ke_hoach_v1.md §10, §14).
//!
//! ```text
//! ┌───────────────────────────────┐        ┌────────────────────────────────┐
//! │ encode thread                 │        │ mux thread                     │
//! │  capture.poll_frame()         │ video  │  SegmentRouter (PTS routing)   │
//! │  → preview tap (GPU ≤2 FPS)   ├───────►│  LibavMuxer / MockMuxer        │
//! │  → NvencSession.encode_frame()│ packets│  segment roll @ IDR boundaries │
//! └───────────────────────────────┘        │  fsync + atomic rename         │
//! ┌─────────────┐  ┌──────────────┐        └────────────────────────────────┘
//! │ mic thread  │  │ system thread│  PCM     ▲ audio packets
//! │ WASAPI event│  │ WASAPI loopbk├──────────┤ (via AAC encode threads)
//! └─────────────┘  └──────────────┘          │
//!                                            │
//!            EncoderControl ◄────────────────┘  (force-IDR requests)
//!
//! All D3D11 immediate-context work stays on the encode thread. The muxer is
//! single-writer. Every producer pushes [`EngineEvent`]s into one outbound
//! queue drained by [`RecorderService::tick`].
//! ```

use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use crate::clock::{self, DriftTracker};
use crate::encoder::EncodedPacket;
use crate::ipc::{EngineEvent, TelemetrySnapshot};
use crate::muxer::{MuxedSegment, TrackId};
use crate::telemetry::Telemetry;

/// Shared outbound event queue (producers → `tick()`).
pub type EventOut = Arc<Mutex<VecDeque<EngineEvent>>>;

/// Cross-thread encoder nudges.
#[derive(Debug, Default)]
pub struct EncoderControl {
    /// Mux thread sets this when the next GOP must start a new segment.
    pub force_idr: AtomicBool,
    /// Cooperative stop signal for every worker thread.
    pub shutdown: AtomicBool,
    /// Pause spans: feeder threads idle (frames are NOT captured) while the
    /// mux thread closes the open segment; resume re-opens the next file.
    pub paused: AtomicBool,
}

impl EncoderControl {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn request_shutdown(&self) {
        self.shutdown.store(true, Ordering::SeqCst);
    }

    pub fn should_stop(&self) -> bool {
        self.shutdown.load(Ordering::SeqCst)
    }

    pub fn set_paused(&self, paused: bool) {
        self.paused.store(paused, Ordering::SeqCst);
    }

    pub fn is_paused(&self) -> bool {
        self.paused.load(Ordering::SeqCst)
    }
}

/// Take-wide clock shared with worker threads (QPC authority + pause spans).
/// Presentation time = QPC delta minus every completed pause span, so PTS
/// stays gapless across pause/resume while wall-clock elapsed grows larger.
#[derive(Debug)]
pub struct TakeClock {
    start_qpc: u64,
    paused_ticks_total: u64,
}

impl TakeClock {
    pub fn starting_now() -> Self {
        Self { start_qpc: clock::qpc_now(), paused_ticks_total: 0 }
    }

    /// Presentation microseconds for a QPC instant, pause-compensated.
    pub fn micros_at(&self, qpc: u64) -> u64 {
        clock::ticks_to_micros(
            qpc.saturating_sub(self.start_qpc).saturating_sub(self.paused_ticks_total),
        )
    }

    pub fn sec_at(&self, qpc: u64) -> f64 {
        self.micros_at(qpc) as f64 / 1_000_000.0
    }

    /// Fold one completed pause span (QPC ticks measured by the service
    /// between `pause` and `resume`) into compensation.
    pub fn apply_pause_ticks(&mut self, ticks: u64) {
        self.paused_ticks_total = self.paused_ticks_total.saturating_add(ticks);
    }
}

/// Commands accepted by the mux thread.
pub enum MuxCommand {
    Video(EncodedPacket),
    /// `samples` + `take_time_us` (pause-compensated) feed the per-track
    /// drift tracker (§12) — wall-clock here would read pause spans as drift.
    Audio { track: TrackId, packet: EncodedPacket, samples: u64, take_time_us: u64 },
    /// Timeline marker routed through the single-writer timeline thread.
    Marker(crate::segment::TimelineEvent),
}

/// Bounded channel helper — pushes block when full (quality-first backpressure
/// rather than silent drops); `try_push_for` gives up after a timeout and
/// reports a drop so telemetry stays honest.
pub fn bounded_send<T>(
    queue: &Mutex<VecDeque<T>>,
    value: T,
    cap: usize,
    timeout: Duration,
) -> Result<(), &'static str> {
    let deadline = std::time::Instant::now() + timeout;
    loop {
        if let Ok(mut q) = queue.lock() {
            if q.len() < cap {
                q.push_back(value);
                return Ok(());
            }
        }
        if std::time::Instant::now() >= deadline {
            return Err("QUEUE_FULL");
        }
        std::thread::sleep(Duration::from_millis(2));
    }
}

/// Drain one item if present.
pub fn try_pop<T>(queue: &Mutex<VecDeque<T>>) -> Option<T> {
    queue.lock().ok().and_then(|mut q| q.pop_front())
}

/// Segment-roll scheduler — arms an IDR when elapsed time crosses the next
/// boundary. Lives beside the router on the mux thread.
///
/// Sequence per segment *k*: when a video packet's PTS reaches
/// `boundary_pts(k+1)` the scheduler sets `force_idr`; the encoder applies it
/// to the next frame; the router sees that keyframe and rolls files.
/// Segment duration therefore drifts by at most one frame — never mid-GOP.
#[derive(Debug)]
pub struct RollScheduler {
    /// Nominal seconds per segment (5 or 10 minutes).
    pub segment_seconds: u64,
    pending_boundary: Option<u64>,
}

impl RollScheduler {
    pub fn new(segment_seconds: u64) -> Self {
        Self { segment_seconds, pending_boundary: None }
    }

    /// Arm the roll at `segment_count + 1` nominal boundaries from take start.
    pub fn arm_next(&mut self, segments_so_far: u32, control: &EncoderControl) {
        let boundary_us = (segments_so_far as u64 + 1)
            .saturating_mul(self.segment_seconds)
            .saturating_mul(1_000_000);
        self.pending_boundary = Some(boundary_us);
        control.force_idr.store(true, Ordering::SeqCst);
    }

    /// True once a packet at-or-past the armed boundary has been observed.
    pub fn on_video_pts(&mut self, pts_us: u64) -> bool {
        match self.pending_boundary {
            Some(b) => pts_us >= b,
            None => false,
        }
    }
}

/// Per-take shared telemetry cell (worker threads write counters, `tick`
/// composes the snapshot).
#[derive(Debug, Default)]
pub struct PipelineStats {
    pub telemetry: Telemetry,
    pub mic_drift: DriftTracker,
    pub system_drift: DriftTracker,
    pub last_video_pts_us: Option<u64>,
    pub last_mic_pts_us: Option<u64>,
    pub av_sync_error_ms: f64,
    pub capture_queue_depth: usize,
    pub encoder_queue_depth: usize,
    pub bytes_written: u64,
    pub segments_completed: Vec<MuxedSegment>,
}

pub type SharedStats = Arc<Mutex<PipelineStats>>;

/// Compose the status snapshot pushed to the control plane at ~1 Hz.
pub fn compose_snapshot(
    stats: &PipelineStats,
    state: &str,
    take_id: &str,
    segment_index: u32,
    disk_free_gb: f64,
    host: &crate::service::HostMetrics,
    nvenc_status: &str,
) -> TelemetrySnapshot {
    let t = &stats.telemetry;
    let now_us = clock::qpc_now();
    TelemetrySnapshot {
        state: state.into(),
        elapsed_sec: match stats.last_video_pts_us {
            Some(pts) => pts as f64 / 1_000_000.0,
            None => 0.0,
        },
        take_id: take_id.into(),
        current_segment_index: segment_index,
        capture_fps: t.capture_fps(now_us),
        encode_fps: t.encode_fps(now_us),
        frames_captured: t.frames_captured,
        frames_submitted: t.frames_submitted,
        frames_encoded: t.frames_encoded,
        frames_dropped: t.frames_dropped,
        dropped_pct: t.dropped_pct(),
        capture_queue_depth: stats.capture_queue_depth,
        encoder_queue_depth: stats.encoder_queue_depth,
        bitrate_mbps: estimate_bitrate_mbps(stats),
        nvenc_latency_ms_p50: t.latency_p50(),
        nvenc_latency_ms_p95: t.latency_p95(),
        disk_write_mbps: t.disk_write_mbps(now_us),
        disk_free_gb,
        av_sync_error_ms: Some(stats.av_sync_error_ms).filter(|v| *v != 0.0),
        mic_drift_ppm: Some(stats.mic_drift.drift_ppm()).filter(|v| *v != 0.0),
        system_drift_ppm: Some(stats.system_drift.drift_ppm()).filter(|v| *v != 0.0),
        gpu_util_pct: host.gpu_util_pct,
        vram_used_mb: host.vram_used_mb,
        cpu_util_pct: host.cpu_util_pct,
        ram_used_mb: host.ram_used_mb,
        gpu_temp_c: host.gpu_temp_c,
        resource_stage: t.stage.as_str().into(),
        nvenc_status: Some(nvenc_status.into()),
        ..Default::default()
    }
}

fn estimate_bitrate_mbps(stats: &PipelineStats) -> f64 {
    let now_us = clock::qpc_now();
    // Encoded stream bitrate ≈ bytes hitting disk while a segment is actively
    // open (audio adds a small share); measured from real writes, not assumed.
    stats.telemetry.disk_write_mbps(now_us) * 8.0
}
