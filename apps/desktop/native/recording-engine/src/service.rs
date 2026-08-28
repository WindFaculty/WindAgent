//! RecorderService — control-plane-facing state machine + pipeline owner
//! (ban_ke_hoach_v1.md §14, P10 hard cutover).
//!
//! ```text
//! idle → ready → recording ⇄ paused → finalizing → completed
//!                    │
//!                    └── any fatal error → error (after graceful finalize)
//! ```
//!
//! Cutover rules this module enforces:
//! - **Fail-closed**: `prepare` probes the host; without D3D11+WGC+NVENC+libav
//!   start is refused unless the operator opted into dev simulation
//!   (Principle H — mock is never the default).
//! - **Single writer**: exactly one mux thread owns the muxer + timeline;
//!   everyone else pushes [`MuxCommand`]s.
//! - **Pause = file boundary**: pausing closes the open segment; resume opens
//!   the next one. PTS stays gapless via [`TakeClock`] pause compensation.
//! - **Recording > AI**: preview degrades 2→1→0.5→off FPS under pressure;
//!   the capture/encode loop itself never throttles (§18).

use std::collections::VecDeque;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde_json::json;

use crate::audio::aac::{AacEncoderPort, AacOut};
use crate::audio::{AudioCapturePort, MockAudioCapture, PcmBlock, TrackKind};
use crate::capture::{CapturePort, MockCapture};
use crate::clock;
use crate::encoder::{EncodedPacket, EncoderPort, MockEncoder, NvencConfig};
use crate::ipc::{
    EngineEvent, EngineRequest, EngineResponse, MarkerRequest, MuteRequest,
    PrepareRequest, StartRequest, TelemetrySnapshot,
};
use crate::muxer::mock::MockMuxer;
use crate::muxer::timestamps::{RouteAction, SegmentRouter};
use crate::muxer::{MuxerPort, TrackId, TrackParams};
use crate::pipeline::{
    bounded_send, compose_snapshot, try_pop, EncoderControl, EventOut, MuxCommand,
    RollScheduler, SharedStats, TakeClock,
};
use crate::preview::{PreviewConfig, PreviewJpeg, PreviewSampler};
use crate::segment::recovery::{recover_take, scan_latest_take};
use crate::segment::timeline_writer::{rfc3339_now, TimelineWriter};

/// Queue depth for encoded packets waiting on the mux thread (~2 s of video).
const VIDEO_CMD_CAP: usize = 512;
/// Audio commands share the same queue; AAC blocks are small so this is roomy.
const AUDIO_CMD_CAP: usize = 2048;
/// Consecutive encoder failures tolerated before the take fail-closes.
const MAX_CONSECUTIVE_ENCODE_ERRORS: u32 = 30;
/// Status heartbeat period pushed to the control plane.
const HEARTBEAT_MS: u64 = 1_000;

// ─── Service state machine ──────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServiceState {
    Idle,
    /// A capability probe is running (heartbeat shows honest progress).
    Probing,
    /// Pipeline construction is running (WGC prepare + NVENC open).
    Preparing,
    Ready,
    Recording,
    Paused,
    Finalizing,
    Completed,
    /// Crash-recovery scan/rebuild is running.
    Recovering,
    Error,
}

impl ServiceState {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Idle => "idle",
            Self::Probing => "probing",
            Self::Preparing => "preparing",
            Self::Ready => "ready",
            Self::Recording => "recording",
            Self::Paused => "paused",
            Self::Finalizing => "finalizing",
            Self::Completed => "completed",
            Self::Recovering => "recovering",
            Self::Error => "error",
        }
    }

    /// States from which maintenance ops may run and whose identity must be
    /// restored afterwards (`Recording`/`Paused`/`Finalizing` are busy with a
    /// take and never enter transient states mid-flight).
    fn is_quiescent(self) -> bool {
        matches!(
            self,
            Self::Idle
                | Self::Ready
                | Self::Completed
                | Self::Error
                | Self::Probing
                | Self::Preparing
                | Self::Recovering
        )
    }
}

// ─── Host metrics (sampled at heartbeat rate) ───────────────────────────────

/// One sampled host-resource reading; `None` = source unavailable on host.
#[derive(Debug, Default)]
pub struct HostMetrics {
    pub gpu_util_pct: Option<f64>,
    pub vram_used_mb: Option<f64>,
    pub cpu_util_pct: Option<f64>,
    pub ram_used_mb: Option<f64>,
    pub gpu_temp_c: Option<f64>,
}

/// CPU busy-ratio sampler over GetSystemTimes deltas (needs two samples).
struct CpuSampler {
    prev_busy_100ns: u64,
    prev_total_100ns: u64,
    primed: bool,
}

impl CpuSampler {
    fn new() -> Self {
        Self { prev_busy_100ns: 0, prev_total_100ns: 0, primed: false }
    }

    #[cfg(windows)]
    fn sample(&mut self) -> Option<f64> {
        use windows_sys::Win32::Foundation::FILETIME;
        use windows_sys::Win32::System::Threading::GetSystemTimes;

        unsafe {
            let zero_ft = FILETIME { dwHighDateTime: 0, dwLowDateTime: 0 };
            let mut idle = zero_ft;
            let mut kernel = zero_ft;
            let mut user = zero_ft;
            if GetSystemTimes(&mut idle, &mut kernel, &mut user) == 0 {
                return None;
            }
            let ft_u64 = |f: &FILETIME| ((f.dwHighDateTime as u64) << 32) | f.dwLowDateTime as u64;
            let idle_t = ft_u64(&idle);
            let kernel_t = ft_u64(&kernel);
            let user_t = ft_u64(&user);
            // Kernel time includes idle; busy = (kernel + user) - idle.
            let total = kernel_t.saturating_add(user_t);
            let busy = total.saturating_sub(idle_t);
            if !self.primed {
                self.prev_busy_100ns = busy;
                self.prev_total_100ns = total;
                self.primed = true;
                return None;
            }
            let d_total = total.saturating_sub(self.prev_total_100ns);
            let d_busy = busy.saturating_sub(self.prev_busy_100ns);
            self.prev_busy_100ns = busy;
            self.prev_total_100ns = total;
            if d_total == 0 {
                return None;
            }
            Some(((d_busy as f64 / d_total as f64) * 100.0).clamp(0.0, 100.0))
        }
    }

    #[cfg(not(windows))]
    fn sample(&mut self) -> Option<f64> {
        None
    }
}

fn sample_host_metrics(cpu: &mut CpuSampler) -> HostMetrics {
    let cpu_util_pct = cpu.sample();
    let ram_used_mb = ram_used_mb();
    #[cfg(feature = "nvml")]
    let (gpu_util_pct, vram_used_mb, gpu_temp_c) = sample_gpu_metrics();
    #[cfg(not(feature = "nvml"))]
    let (gpu_util_pct, vram_used_mb, gpu_temp_c): (Option<f64>, Option<f64>, Option<f64>) =
        (None, None, None);

    HostMetrics { gpu_util_pct, vram_used_mb, cpu_util_pct, ram_used_mb, gpu_temp_c }
}

#[cfg(windows)]
fn ram_used_mb() -> Option<f64> {
    use windows_sys::Win32::System::SystemInformation::{GlobalMemoryStatusEx, MEMORYSTATUSEX};

    unsafe {
        let mut stat = MEMORYSTATUSEX {
            dwLength: std::mem::size_of::<MEMORYSTATUSEX>() as u32,
            dwMemoryLoad: 0,
            ullTotalPhys: 0,
            ullAvailPhys: 0,
            ullTotalPageFile: 0,
            ullAvailPageFile: 0,
            ullTotalVirtual: 0,
            ullAvailVirtual: 0,
            ullAvailExtendedVirtual: 0,
        };
        if GlobalMemoryStatusEx(&mut stat) != 0 {
            Some((stat.ullTotalPhys.saturating_sub(stat.ullAvailPhys)) as f64 / (1024.0 * 1024.0))
        } else {
            None
        }
    }
}

#[cfg(not(windows))]
fn ram_used_mb() -> Option<f64> {
    None
}

/// NVML-backed GPU readings. The `nvml` feature is on by default (§17/§18):
/// the wrapper binds the driver's own nvml.dll at runtime, so hosts without
/// an NVIDIA driver simply report `None` — no hard dependency.
#[cfg(all(windows, feature = "nvml"))]
fn sample_gpu_metrics() -> (Option<f64>, Option<f64>, Option<f64>) {
    use std::sync::OnceLock;
    static NVML: OnceLock<Option<nvml_wrapper::Nvml>> = OnceLock::new();
    let Some(nvml) = NVML.get_or_init(|| nvml_wrapper::Nvml::init().ok()) else {
        return (None, None, None);
    };
    let Ok(device) = nvml.device_by_index(0) else { return (None, None, None) };
    let util = device.utilization_rates().ok().map(|u| u.gpu as f64);
    let vram = device.memory_info().ok().map(|m| m.used as f64 / (1024.0 * 1024.0));
    let temp = device
        .temperature(nvml_wrapper::enum_wrappers::device::TemperatureSensor::Gpu)
        .ok()
        .map(|t| t as f64);
    (util, vram, temp)
}

// ─── Preview tap abstraction (decouples service from GPU internals) ─────────

/// Per-frame preview producer bound to the encode thread's D3D11 context.
pub trait PreviewTap: Send {
    fn process(&mut self, frame: &crate::capture::CapturedFrame) -> Result<PreviewJpeg, String>;
}

// ─── Port set (one take's pipeline ports, moved into worker threads) ───────

/// Everything a started take needs to run. Destructured once in
/// [`RecorderService::spawn_threads`] so each element moves into exactly one
/// thread closure (single-owner hot path).
struct PortSet {
    capture: Box<dyn CapturePort>,
    encoder: Box<dyn EncoderPort>,
    muxer: Box<dyn MuxerPort>,
    mic: Option<(Box<dyn AudioCapturePort>, Box<dyn AacEncoderPort>)>,
    system: Option<(Box<dyn AudioCapturePort>, Box<dyn AacEncoderPort>)>,
    preview: Option<Box<dyn PreviewTap>>,
    /// CodecPrivate for the §9 handshake — empty on the mock backend.
    extradata: SegmentExtradata,
}

// ─── Track layout ───────────────────────────────────────────────────────────

/// Stream layout fixed at take start — order defines MKV stream indexes.
fn tracks_spec(
    profile: &crate::EngineProfile,
    mic_channels: u32,
    sys_channels: u32,
) -> Vec<(TrackId, TrackParams)> {
    let mut spec = Vec::new();
    if profile.video.codec == "HEVC" {
        spec.push((
            TrackId::Video,
            TrackParams::VideoHevc {
                width: profile.video.width,
                height: profile.video.height,
                fps: profile.video.fps,
            },
        ));
    } else {
        spec.push((
            TrackId::Video,
            TrackParams::VideoH264 {
                width: profile.video.width,
                height: profile.video.height,
                fps: profile.video.fps,
            },
        ));
    }
    if profile.audio.microphone.enabled {
        spec.push((TrackId::Mic, TrackParams::Aac { sample_rate: 48_000, channels: mic_channels.max(1) }));
    }
    if profile.audio.system.enabled {
        spec.push((TrackId::System, TrackParams::Aac { sample_rate: 48_000, channels: sys_channels.max(1) }));
    }
    spec
}

// ─── Segment extradata (§9 lazy-header handshake inputs) ────────────────────

/// CodecPrivate staged into EVERY opened segment while its header is still
/// lazy. Video avcC/hvcC is built once per session from the NVENC sequence
/// params; each AAC track gets a 2-byte AudioSpecificConfig built from the
/// locked 48 kHz layout. Staging happens inside `MuxDriver::ensure_open`, so
/// the first packet of whichever track arrives first can flush the header.
#[derive(Debug, Default, Clone)]
struct SegmentExtradata {
    video_avcc_hvcc: Option<Vec<u8>>,
    audio_asc: Vec<(TrackId, Vec<u8>)>,
}

impl SegmentExtradata {
    fn is_empty(&self) -> bool {
        self.video_avcc_hvcc.is_none() && self.audio_asc.is_empty()
    }
}

/// avcC/hvcC record from an Annex-B sequence-header blob (`NvEncGetSequenceParams`).
/// Pure — unit-tested without any native dependency.
fn build_video_extradata(sequence_header_annex_b: &[u8], hevc: bool) -> Option<Vec<u8>> {
    use crate::muxer::tracks::{build_avcc, build_hvcc, split_annex_b};
    let nals = split_annex_b(sequence_header_annex_b);
    if hevc {
        build_hvcc(&nals)
    } else {
        build_avcc(&nals)
    }
}

/// One AudioSpecificConfig per Aac track in the segment spec. Fails closed on
/// a layout the ASC builder cannot express (contract bug, not runtime state).
fn collect_audio_asc(spec: &[(TrackId, TrackParams)]) -> Result<Vec<(TrackId, Vec<u8>)>, String> {
    use crate::muxer::tracks::build_aac_asc;
    let mut out = Vec::new();
    for (id, params) in spec {
        if let TrackParams::Aac { sample_rate, channels } = params {
            match build_aac_asc(*sample_rate, *channels) {
                Some(asc) => out.push((*id, asc)),
                None => {
                    return Err(format!(
                        "AAC_ASC_INVALID:{id:?}:{sample_rate}Hz/{channels}ch cannot be expressed as AudioSpecificConfig"
                    ));
                }
            }
        }
    }
    Ok(out)
}

// ─── Mux driver (runs ONLY on the mux thread) ───────────────────────────────

/// Single-writer owner of the muxer + timeline + segment routing.
struct MuxDriver {
    muxer: Box<dyn MuxerPort>,
    tracks_spec: Vec<(TrackId, TrackParams)>,
    router: SegmentRouter,
    scheduler: RollScheduler,
    control: Arc<EncoderControl>,
    stats: SharedStats,
    open_segment: Option<u32>,
    /// CodecPrivate staged into every opened segment (§9 handshake).
    extradata: SegmentExtradata,
    /// Packets held across an armed boundary until the IDR opens the next
    /// file (B-frame reorder window + late audio), tagged by their track.
    pending_next: Vec<(TrackId, EncodedPacket)>,
}

impl MuxDriver {
    fn new(
        muxer: Box<dyn MuxerPort>,
        tracks_spec: Vec<(TrackId, TrackParams)>,
        segment_seconds: u64,
        control: Arc<EncoderControl>,
        stats: SharedStats,
        extradata: SegmentExtradata,
    ) -> Self {
        Self {
            muxer,
            tracks_spec,
            router: SegmentRouter::new(),
            scheduler: RollScheduler::new(segment_seconds),
            control,
            stats,
            open_segment: None,
            extradata,
            pending_next: Vec::new(),
        }
    }

    /// Stage CodecPrivate into the freshly opened segment. Runs while the
    /// header is still lazy, so the first packet of ANY track (audio often
    /// beats NVENC's first packet under lookahead) flushes a valid header.
    /// Construction-time validation makes this infallible for native takes;
    /// a failure here is a contract bug and surfaces as a Warning once per
    /// segment instead of killing the take.
    fn stage_extradata(&mut self, events: &EventOut) {
        if self.extradata.is_empty() {
            return;
        }
        let mut failure: Option<String> = None;
        if let Some(avcc) = &self.extradata.video_avcc_hvcc {
            if let Err(e) = self.muxer.stage_video_extradata(avcc) {
                failure.get_or_insert_with(|| format!("video:{e}"));
            }
        }
        for (track, asc) in &self.extradata.audio_asc {
            if let Err(e) = self.muxer.stage_audio_extradata(*track, asc) {
                failure.get_or_insert_with(|| format!("audio/{:?}:{e}", track));
            }
        }
        if let Some(e) = failure {
            let _ = push_event(events, EngineEvent::Warning {
                message: format!("EXTRADATA_STAGE_FAILED:{e} — MKV header will refuse packets"),
            });
        }
    }

    fn ensure_open(
        &mut self,
        index: u32,
        take_id: &str,
        t_sec: f64,
        timeline: &mut TimelineWriter,
        events: &EventOut,
    ) -> Result<(), String> {
        if self.open_segment == Some(index) {
            return Ok(());
        }
        if self.open_segment.is_some() {
            self.close_current(take_id, t_sec, timeline, events)?;
        }
        self.muxer.open_segment(index, &self.tracks_spec)?;
        self.stage_extradata(events);
        self.open_segment = Some(index);
        let _ = push_event(events, EngineEvent::Timeline {
            take_id: take_id.to_string(),
            event_type: "SEGMENT_START".into(),
            t: t_sec,
        });
        let _ = timeline.append(&crate::segment::TimelineEvent {
            t: t_sec,
            event_type: "SEGMENT_START".into(),
            scene_id: None,
            cue_id: None,
            action_id: None,
            execution_id: None,
            marker_type: None,
            detail: format!("segment {index} opened"),
        });
        Ok(())
    }

    fn close_current(
        &mut self,
        take_id: &str,
        t_sec: f64,
        timeline: &mut TimelineWriter,
        events: &EventOut,
    ) -> Result<(), String> {
        if self.open_segment.is_none() {
            return Ok(());
        }
        let seg = self.muxer.close_segment()?;
        self.open_segment = None;
        // Report the committed file to the shared stats cell — the stop
        // summary and manifest are built from this list.
        if let Ok(mut s) = self.stats.lock() {
            s.segments_completed.push(seg.clone());
        }
        // Anything still pending belonged to the file that just closed —
        // dropping it here would corrupt PTS continuity, so it rides along
        // into whatever opens next (it was routed forward for a reason).
        self.pending_next.clear();
        let _ = timeline.append(&crate::segment::TimelineEvent {
            t: t_sec,
            event_type: "SEGMENT_END".into(),
            scene_id: None,
            cue_id: None,
            action_id: None,
            execution_id: None,
            marker_type: None,
            detail: format!("segment {} committed ({} bytes)", seg.index, seg.byte_len),
        });
        let _ = push_event(events, EngineEvent::Segment {
            take_id: take_id.to_string(),
            segment_index: seg.index,
            file_token: seg.file_token.clone(),
            byte_len: seg.byte_len,
            duration_sec: seg.duration_sec,
            is_playable: seg.is_playable,
        });
        Ok(())
    }

    /// Arm the roll when PTS nears the next nominal boundary (§9: never cut
    /// mid-GOP — force-IDR first, route the resulting keyframe into the new
    /// file). The margin formula mirrors [`RollScheduler::arm_next`].
    fn maybe_arm_roll(&mut self, pkt_pts_us: u64) {
        if self.router.is_roll_armed() || self.control.should_stop() {
            return;
        }
        let seg_len_us = self.scheduler.segment_seconds.saturating_mul(1_000_000);
        let next_boundary = (self.router.segment_index as u64 + 1).saturating_mul(seg_len_us);
        // ~3 frames covers 30 fps + jitter; the IDR gates the actual cut so an
        // early arm can never split a GOP, only delay one by <100 ms.
        let margin_us = 3 * 33_333u64;
        if pkt_pts_us.saturating_add(margin_us) >= next_boundary {
            self.scheduler.arm_next(self.router.segment_index, &self.control); // sets force_idr
            self.router.request_roll(next_boundary);
        }
    }

    /// Shared routing for any track (§9): PTS decides membership; keyframes
    /// open files; non-keyframes past an armed boundary wait for its IDR.
    fn route_and_write(
        &mut self,
        track: TrackId,
        pkt: EncodedPacket,
        take_id: &str,
        t_now_sec: f64,
        timeline: &mut TimelineWriter,
        events: &EventOut,
    ) -> Result<(), String> {
        if track == TrackId::Video {
            self.maybe_arm_roll(pkt.pts_us);
        }
        match self.router.route(&pkt) {
            RouteAction::Current => {
                self.ensure_open(self.router.segment_index, take_id, t_now_sec, timeline, events)?;
                self.muxer.write_packet(track, &pkt)?;
            }
            RouteAction::RollTo(index) => {
                self.ensure_open(index, take_id, t_now_sec, timeline, events)?;
                self.muxer.write_packet(track, &pkt)?;
                // Drain everything held back across the boundary, videos first
                // so their decode order lands right behind the IDR.
                let held = std::mem::take(&mut self.pending_next);
                held.into_iter().for_each(|(t, p)| {
                    let _ = self.muxer.write_packet(t, &p);
                });
            }
            RouteAction::HoldForNext => {
                self.pending_next.push((track, pkt));
            }
        }
        Ok(())
    }
}

// ─── RecorderService ────────────────────────────────────────────────────────

pub struct RecorderService {
    allow_mock: bool,
    state: ServiceState,
    error: Option<String>,

    profile: crate::EngineProfile,
    output_root: String,
    execution_plan_id: String,
    take_id: String,
    take_dir: PathBuf,
    backend: String,

    events: EventOut,
    stats: SharedStats,
    control: Option<Arc<EncoderControl>>,
    clock: Option<Arc<Mutex<TakeClock>>>,
    cmd_q: Option<Arc<Mutex<VecDeque<MuxCommand>>>>,
    threads: Vec<std::thread::JoinHandle<()>>,

    mic_muted: Arc<AtomicBool>,
    system_muted: Arc<AtomicBool>,

    paused_at_qpc: Option<u64>,
    last_status_ms: u64,
    stopping: bool,
    cpu_sampler: CpuSampler,
}

impl RecorderService {
    /// Production constructor — mock backend only via the env opt-in.
    pub fn new() -> Self {
        let allow_mock = std::env::var("WINDAGENT_RECORDER_ALLOW_MOCK")
            .map(|v| v == "1")
            .unwrap_or(false);
        Self::with_allow_mock(allow_mock)
    }

    /// Test/dev constructor with explicit simulation consent.
    pub fn with_allow_mock(allow_mock: bool) -> Self {
        Self {
            allow_mock,
            state: ServiceState::Idle,
            error: None,
            profile: crate::EngineProfile::default(),
            output_root: String::new(),
            execution_plan_id: String::new(),
            take_id: String::new(),
            take_dir: PathBuf::new(),
            backend: "mock".into(),
            events: Arc::new(Mutex::new(VecDeque::new())),
            stats: Arc::new(Mutex::new(crate::pipeline::PipelineStats::default())),
            control: None,
            clock: None,
            cmd_q: None,
            threads: Vec::new(),
            mic_muted: Arc::new(AtomicBool::new(false)),
            system_muted: Arc::new(AtomicBool::new(false)),
            paused_at_qpc: None,
            last_status_ms: 0,
            stopping: false,
            cpu_sampler: CpuSampler::new(),
        }
    }

    pub fn state(&self) -> ServiceState {
        self.state
    }

    // ── request dispatch ────────────────────────────────────────────────────

    pub fn handle(&mut self, request: EngineRequest) -> (EngineResponse, Vec<EngineEvent>) {
        let resp = match request {
            EngineRequest::Capabilities => self.op_capabilities(),
            EngineRequest::Sources => self.op_sources(),
            EngineRequest::Prepare(p) => self.op_prepare(p),
            EngineRequest::Start(s) => self.op_start(s),
            EngineRequest::Pause => self.op_pause(),
            EngineRequest::Resume => self.op_resume(),
            EngineRequest::Stop => self.op_stop(),
            EngineRequest::Status => {
                let snap = self.snapshot_now();
                EngineResponse::ok("status", serde_json::to_value(snap).unwrap_or_default())
            }
            EngineRequest::Marker(m) => self.op_marker(m),
            EngineRequest::Mute(m) => self.op_mute(m),
            EngineRequest::Recover { output_dir } => self.op_recover(output_dir),
        };
        (resp, self.drain_events())
    }

    /// Heartbeat + event drain called by the sidecar main loop (~250 ms).
    pub fn tick(&mut self) -> Vec<EngineEvent> {
        // Worker-thread liveness: an unexpected exit fail-closes the take.
        if !self.stopping && !self.threads.is_empty() && self.threads.iter().any(|j| j.is_finished()) {
            let msg = "ENGINE_THREAD_DIED: a pipeline worker exited unexpectedly".to_string();
            let _ = push_event(&self.events, EngineEvent::Error { message: msg.clone() });
            self.error = Some(msg);
            self.graceful_stop(ServiceState::Error);
        }

        let mut out = self.drain_events();
        if matches!(self.state, ServiceState::Recording | ServiceState::Paused | ServiceState::Finalizing)
            && !self.take_id.is_empty()
        {
            let now_ms = clock::qpc_now_ms();
            if now_ms.saturating_sub(self.last_status_ms) >= HEARTBEAT_MS {
                self.last_status_ms = now_ms;
                let snap = self.snapshot_now();
                out.push(EngineEvent::Status { telemetry: snap });
            }
        }
        out
    }

    // ── ops ─────────────────────────────────────────────────────────────────

    fn op_capabilities(&mut self) -> EngineResponse {
        // Probing is visible: an active take keeps its state, a quiescent one
        // flips to `probing` for the duration and is restored afterwards.
        let prev = self.state.is_quiescent().then_some(self.state);
        if let Some(_) = prev {
            self.state = ServiceState::Probing;
        }
        let dir = (!self.output_root.is_empty()).then(|| PathBuf::from(&self.output_root));
        let caps = crate::probe::probe_capabilities(dir.as_deref());
        if let Some(prev) = prev {
            self.state = prev;
        }
        // Flat 1:1 mirror of [EngineCapabilities] — the control plane decodes
        // this straight into its NativeCapabilities with no remapping.
        EngineResponse::ok("capabilities", serde_json::to_value(&caps).unwrap_or_else(|_| json!({})))
    }

    /// §17 source picker data — real monitor/window enumeration, valid in
    /// every service state (read-only; never touches capture/encoder objects).
    fn op_sources(&mut self) -> EngineResponse {
        #[cfg(windows)]
        let payload = {
            use crate::capture::wgc::{list_monitors, list_windows};
            json!({
                "monitors": list_monitors()
                    .into_iter()
                    .map(|m| json!({
                        "kind": "DISPLAY",
                        "id": m.id,
                        "label": m.name,
                        "width": m.width,
                        "height": m.height,
                        "is_primary": m.is_primary,
                    }))
                    .collect::<Vec<_>>(),
                "windows": list_windows()
                    .into_iter()
                    .map(|w| json!({
                        "kind": "WINDOW",
                        "id": w.hwnd_token,
                        "label": w.title,
                        "process": w.process_name,
                    }))
                    .collect::<Vec<_>>(),
            })
        };
        #[cfg(not(windows))]
        let payload = json!({ "monitors": [], "windows": [] });
        EngineResponse::ok("sources", payload)
    }

    fn op_prepare(&mut self, p: PrepareRequest) -> EngineResponse {
        if !matches!(
            self.state,
            ServiceState::Idle | ServiceState::Ready | ServiceState::Completed | ServiceState::Error
        ) {
            return EngineResponse::err("prepare", "INVALID_STATE", format!("prepare refused in state {}", self.state.as_str()));
        }
        // Construction (device walk + probe + validation) is observable work.
        self.state = ServiceState::Preparing;
        if let Err(e) = p.profile.validate() {
            self.state = ServiceState::Error;
            return EngineResponse::err("prepare", "ENGINE_PROFILE_REJECTED", e);
        }
        let caps = crate::probe::probe_capabilities(Some(Path::new(&p.output_dir)));
        self.backend = if caps.engine_available {
            "wgc-nvenc-mkv".to_string()
        } else if self.allow_mock {
            "mock".to_string()
        } else {
            self.state = ServiceState::Error;
            return EngineResponse::err(
                "prepare",
                "PRECONDITION_FAILED",
                format!("native engine unavailable: {}", caps.blockers.join("; ")),
            );
        };
        self.profile = p.profile.clone();
        self.output_root = p.output_dir.clone();
        self.execution_plan_id = p.execution_plan_id.clone();
        self.error = None;
        self.state = ServiceState::Ready;
        EngineResponse::ok(
            "prepare",
            json!({
                "prepared": true,
                "backend": self.backend,
                "contract_version": crate::ENGINE_CONTRACT_VERSION,
                "blockers": caps.blockers,
                "output_dir": p.output_dir,
            }),
        )
    }

    fn op_start(&mut self, s: StartRequest) -> EngineResponse {
        if self.state != ServiceState::Ready {
            return EngineResponse::err("start", "INVALID_STATE", format!("start requires ready, got {}", self.state.as_str()));
        }
        self.take_id = s.take_id.clone();
        self.take_dir = Path::new(&self.output_root).join(&self.take_id);
        if let Err(e) = std::fs::create_dir_all(&self.take_dir) {
            return EngineResponse::err("start", "TAKE_DIR_FAILED", format!("{e}"));
        }
        let mut timeline = match TimelineWriter::create(&self.take_dir) {
            Ok(t) => t,
            Err(e) => return EngineResponse::err("start", "TIMELINE_CREATE_FAILED", e),
        };

        // Fresh shared cells for this take.
        self.stats = Arc::new(Mutex::new(crate::pipeline::PipelineStats::default()));
        let control = Arc::new(EncoderControl::new());
        self.control = Some(control.clone());
        self.clock = Some(Arc::new(Mutex::new(TakeClock::starting_now())));
        self.cmd_q = Some(Arc::new(Mutex::new(VecDeque::new())));
        self.stopping = false;
        self.paused_at_qpc = None;

        let built = match self.backend.as_str() {
            "mock" => self.build_mock_ports(),
            _ => self.build_native_ports(),
        };
        let ports = match built {
            Ok(p) => p,
            Err(e) => {
                self.state = ServiceState::Error;
                self.error = Some(e.clone());
                return EngineResponse::err("start", "PIPELINE_SPAWN_FAILED", e);
            }
        };

        // SESSION_START is the very first timeline line.
        let _ = timeline.append(&crate::segment::TimelineEvent {
            t: 0.0,
            event_type: "SESSION_START".into(),
            scene_id: None,
            cue_id: None,
            action_id: None,
            execution_id: Some(self.take_id.clone()),
            marker_type: None,
            detail: format!("backend={}", self.backend),
        });

        if let Err(e) = self.spawn_threads(ports, timeline, control) {
            self.state = ServiceState::Error;
            self.error = Some(e.clone());
            return EngineResponse::err("start", "PIPELINE_SPAWN_FAILED", e);
        }
        self.state = ServiceState::Recording;
        self.last_status_ms = clock::qpc_now_ms();
        EngineResponse::ok("start", json!({ "take_id": self.take_id, "backend": self.backend }))
    }

    fn op_pause(&mut self) -> EngineResponse {
        if self.state != ServiceState::Recording {
            return EngineResponse::err("pause", "INVALID_STATE", format!("pause requires recording, got {}", self.state.as_str()));
        }
        self.paused_at_qpc = Some(clock::qpc_now());
        if let Some(c) = &self.control {
            c.set_paused(true);
        }
        self.state = ServiceState::Paused;
        EngineResponse::ok("pause", json!({}))
    }

    fn op_resume(&mut self) -> EngineResponse {
        if self.state != ServiceState::Paused {
            return EngineResponse::err("resume", "INVALID_STATE", format!("resume requires paused, got {}", self.state.as_str()));
        }
        if let (Some(span_start), Some(clk)) = (self.paused_at_qpc.take(), &self.clock) {
            let span = clock::qpc_now().saturating_sub(span_start);
            if let Ok(mut c) = clk.lock() {
                c.apply_pause_ticks(span);
            }
        }
        if let Some(c) = &self.control {
            c.set_paused(false);
        }
        self.state = ServiceState::Recording;
        EngineResponse::ok("resume", json!({}))
    }

    fn op_stop(&mut self) -> EngineResponse {
        if !matches!(self.state, ServiceState::Recording | ServiceState::Paused | ServiceState::Error) {
            return EngineResponse::err("stop", "INVALID_STATE", format!("stop requires an active take, got {}", self.state.as_str()));
        }
        let summary = self.graceful_stop(ServiceState::Completed);
        EngineResponse::ok("stop", summary)
    }

    fn op_marker(&mut self, m: MarkerRequest) -> EngineResponse {
        // Mirrors the control-plane gate: markers are legal while paused too
        // (take-time stays monotonic through the pause via TakeClock).
        if !matches!(self.state, ServiceState::Recording | ServiceState::Paused) {
            return EngineResponse::err("marker", "INVALID_STATE", "markers require an active take");
        }
        let Some(q) = &self.cmd_q else {
            return EngineResponse::err("marker", "INVALID_STATE", "no active pipeline");
        };
        let t_sec = self.elapsed_sec_now();
        let ev = crate::segment::TimelineEvent {
            t: t_sec,
            event_type: "MARKER".into(),
            scene_id: None,
            cue_id: m.cue_id,
            action_id: m.action_id,
            execution_id: Some(self.execution_plan_id.clone()),
            marker_type: Some(m.marker_type),
            detail: String::new(),
        };
        if bounded_send(q, MuxCommand::Marker(ev), 4096, Duration::from_millis(500)).is_err() {
            return EngineResponse::err("marker", "MARKER_QUEUE_FULL", "command queue saturated");
        }
        EngineResponse::ok("marker", json!({ "t": t_sec }))
    }

    fn op_mute(&mut self, m: MuteRequest) -> EngineResponse {
        if !matches!(self.state, ServiceState::Recording | ServiceState::Paused) {
            return EngineResponse::err("mute", "INVALID_STATE", "mute requires an active take");
        }
        self.mic_muted.store(m.mic_muted, Ordering::SeqCst);
        self.system_muted.store(m.system_muted, Ordering::SeqCst);
        EngineResponse::ok("mute", json!({ "mic_muted": m.mic_muted, "system_muted": m.system_muted }))
    }

    fn op_recover(&mut self, output_dir: String) -> EngineResponse {
        let root = PathBuf::from(if output_dir.is_empty() { self.output_root.clone() } else { output_dir });
        if root.as_os_str().is_empty() {
            return EngineResponse::err("recover", "RECOVER_NO_OUTPUT_DIR", "no output directory known");
        }
        let Some(take) = scan_latest_take(&root) else {
            return EngineResponse::err("recover", "RECOVER_NO_TAKE_FOUND", format!("no recoverable take under {}", root.display()));
        };
        // The scan/rebuild is disk-bound and visible while it runs.
        let prev = self.state;
        self.state = ServiceState::Recovering;
        match recover_take(&take) {
            Ok(report) => {
                self.state = prev;
                EngineResponse::ok("recover", serde_json::to_value(&report).unwrap_or_default())
            }
            Err(e) => {
                self.state = prev;
                EngineResponse::err("recover", "RECOVERY_FAILED", e)
            }
        }
    }

    // ── pipeline construction ───────────────────────────────────────────────

    fn build_native_ports(&mut self) -> Result<PortSet, String> {
        #[cfg(windows)]
        {
            use crate::capture::d3d11_device::create_preferred_device;
            use crate::capture::wgc::WgcCapture;
            use crate::encoder::nvenc_encoder::NvencEncoder;
            use crate::muxer::libav::LibavMuxer;

            let bundle = create_preferred_device()?;
            // §6: ONE D3D11 device for WGC, NVENC and preview — zero-copy is
            // guaranteed by sharing the adapter's device, not by hoping two
            // NVIDIA-preferred walks land on the same one.
            let mut capture =
                WgcCapture::new(&self.profile.capture_source).with_shared_device(&bundle.device);
            capture.prepare().map_err(|e| format!("CAPTURE_PREPARE_FAILED:{e}"))?;

            let config = NvencConfig::from_profile(&self.profile);
            let nvenc = NvencEncoder::open(&config, &bundle.device)?;

            // §9 handshake input: avcC/hvcC built once from the session's
            // sequence params. Fail-closed at START — a take whose MKV header
            // could never be written must not begin.
            let seq = nvenc.sequence_header().unwrap_or_default();
            let hevc = config.codec == crate::encoder::Codec::Hevc;
            let video_avcc_hvcc = build_video_extradata(&seq, hevc).ok_or_else(|| {
                format!(
                    "NVENC_SEQUENCE_PARAMS_INVALID:{}-byte sequence header carried no complete {} parameter set",
                    seq.len(),
                    if hevc { "VPS/SPS/PPS" } else { "SPS/PPS" },
                )
            })?;
            let encoder: Box<dyn EncoderPort> = Box::new(nvenc);

            // Preview binds to the same device/context; failure degrades to
            // no-preview, never blocks the take (§13).
            let preview: Option<Box<dyn PreviewTap>> =
                crate::preview::gpu_preview::GpuPreviewPipeline::new(
                    &bundle.device,
                    &bundle.context,
                    &PreviewConfig::default(),
                )
                .ok()
                .map(|inner| Box::new(GpuPreviewAdapter { inner }) as Box<dyn PreviewTap>);

            let (mic, system) = self.build_audio_ports()?;
            let muxer: Box<dyn MuxerPort> = Box::new(LibavMuxer::new());
            Ok(PortSet {
                capture: Box::new(capture),
                encoder,
                muxer,
                mic,
                system,
                preview,
                extradata: SegmentExtradata {
                    video_avcc_hvcc: Some(video_avcc_hvcc),
                    // AudioSpecificConfigs are built in `spawn_threads` where
                    // the final channel layout is known.
                    audio_asc: Vec::new(),
                },
            })
        }
        #[cfg(not(windows))]
        {
            let _ = self;
            Err(crate::capture::WGC_UNAVAILABLE.into())
        }
    }

    /// Prepare both audio tracks up-front; a failed track degrades to None
    /// with a Warning (§24: audio loss must not kill the video take).
    fn build_audio_ports(
        &mut self,
    ) -> Result<
        (
            Option<(Box<dyn AudioCapturePort>, Box<dyn AacEncoderPort>)>,
            Option<(Box<dyn AudioCapturePort>, Box<dyn AacEncoderPort>)>,
        ),
        String,
    > {
        #[cfg(windows)]
        {
            use crate::audio::aac::MfAacEncoder;
            use crate::audio::loopback::WasapiLoopback;
            use crate::audio::microphone::WasapiMicrophone;

            const AUDIO_BITRATE_BPS: u32 = 160_000;
            let events = self.events.clone();
            let mk_track = |events: &EventOut,
                            kind: TrackKind,
                            enabled: bool,
                            device_id: &str|
             -> Option<(Box<dyn AudioCapturePort>, Box<dyn AacEncoderPort>)> {
                if !enabled {
                    return None;
                }
                let mut port: Box<dyn AudioCapturePort> = match kind {
                    TrackKind::Mic => Box::new(WasapiMicrophone::new()),
                    TrackKind::System => Box::new(WasapiLoopback::new()),
                };
                let info = match port.prepare(device_id) {
                    Ok(i) => i,
                    Err(e) => {
                        let _ = push_event(events, EngineEvent::Warning {
                            message: format!("AUDIO_TRACK_DISABLED:{kind:?}:{e}"),
                        });
                        return None;
                    }
                };
                match MfAacEncoder::new(&info, AUDIO_BITRATE_BPS) {
                    Ok(enc) => Some((port, Box::new(enc))),
                    Err(e) => {
                        let _ = push_event(events, EngineEvent::Warning {
                            message: format!("AUDIO_TRACK_DISABLED:AAC_{kind:?}:{e}"),
                        });
                        None
                    }
                }
            };
            let mic = mk_track(
                &events,
                TrackKind::Mic,
                self.profile.audio.microphone.enabled,
                &self.profile.audio.microphone.device_id.clone(),
            );
            let system = mk_track(
                &events,
                TrackKind::System,
                self.profile.audio.system.enabled,
                &self.profile.audio.system.device_id.clone(),
            );
            Ok((mic, system))
        }
        #[cfg(not(windows))]
        {
            let _ = self;
            Ok((None, None))
        }
    }

    fn build_mock_ports(&mut self) -> Result<PortSet, String> {
        let fps = self.profile.video.fps;
        let res = (self.profile.video.width, self.profile.video.height);
        let codec = self.profile.video.codec.clone();

        // Mock audio mirrors the profile's enable flags so mute/meter/drift
        // paths stay exercised in CI.
        let mk_mock = |enabled: bool, kind: TrackKind| -> Option<(Box<dyn AudioCapturePort>, Box<dyn AacEncoderPort>)> {
            enabled.then(|| (Box::new(MockAudioCapture::new(kind)) as Box<dyn AudioCapturePort>, Box::new(MockAacEncoder::new()) as Box<dyn AacEncoderPort>))
        };
        let mic = mk_mock(self.profile.audio.microphone.enabled, TrackKind::Mic);
        let system = mk_mock(self.profile.audio.system.enabled, TrackKind::System);

        Ok(PortSet {
            capture: Box::new(MockCapture::new(res, fps)),
            encoder: Box::new(MockEncoder::new(codec)),
            muxer: Box::new(MockMuxer::new()),
            mic,
            system,
            preview: None,
            extradata: SegmentExtradata::default(),
        })
    }

    fn spawn_threads(
        &mut self,
        ports: PortSet,
        timeline: TimelineWriter,
        control: Arc<EncoderControl>,
    ) -> Result<(), String> {
        let stats = self.stats.clone();
        let clock_cell = self.clock.clone().expect("clock set before spawn");
        let cmd_q: Arc<Mutex<VecDeque<MuxCommand>>> = self.cmd_q.clone().expect("cmd queue set");
        let events = self.events.clone();
        let take_id = self.take_id.clone();
        let take_dir_str = self.take_dir.display().to_string();
        let segment_seconds = self.profile.container.segment_minutes as u64 * 60;
        let fps = self.profile.video.fps;

        let PortSet { capture, encoder, muxer, mic, system, preview, mut extradata } = ports;

        let (mic_channels, sys_channels) = (
            mic.as_ref().map(|(_, a)| a.output_channels()).unwrap_or(2),
            system.as_ref().map(|(_, a)| a.output_channels()).unwrap_or(2),
        );
        let spec = tracks_spec(&self.profile, mic_channels, sys_channels);
        // §9 handshake: AudioSpecificConfigs need the final channel layout,
        // which is only known once the audio ports have been prepared. Fails
        // closed before any thread spawns.
        let asc = collect_audio_asc(&spec)?;
        extradata.audio_asc = asc;

        // ── encode thread ──
        let enc_control = control.clone();
        let enc_stats = stats.clone();
        let enc_clock = clock_cell.clone();
        let enc_cmd = cmd_q.clone();
        let enc_events = events.clone();
        let enc_take = take_id.clone();
        let sampler = PreviewSampler::new(PreviewConfig::default());
        self.threads.push(
            std::thread::Builder::new()
                .name("windagent-encode".into())
                .spawn(move || {
                    run_encode_thread(RunEncodeArgs {
                        capture,
                        encoder,
                        preview,
                        sampler,
                        control: enc_control,
                        stats: enc_stats,
                        clock: enc_clock,
                        cmd_q: enc_cmd,
                        events: enc_events,
                        take_id: enc_take,
                        fps,
                    })
                })
                .map_err(|e| format!("SPAWN_ENCODE_FAILED:{e}"))?,
        );

        // ── audio feeder threads ──
        for (pair, mute) in [(mic, self.mic_muted.clone()), (system, self.system_muted.clone())] {
            let Some((port, aac)) = pair else { continue };
            let kind = port.track();
            let a_control = control.clone();
            let a_stats = stats.clone();
            let a_clock = clock_cell.clone();
            let a_cmd = cmd_q.clone();
            let a_events = events.clone();
            self.threads.push(
                std::thread::Builder::new()
                    .name(format!("windagent-audio-{kind:?}").to_lowercase())
                    .spawn(move || {
                        run_audio_thread(RunAudioArgs {
                            port,
                            aac,
                            mute,
                            kind,
                            control: a_control,
                            stats: a_stats,
                            clock: a_clock,
                            cmd_q: a_cmd,
                            events: a_events,
                        })
                    })
                    .map_err(|e| format!("SPAWN_AUDIO_FAILED:{e}"))?,
            );
        }

        // ── mux thread (single writer: muxer + timeline) ──
        let m_control = control.clone();
        let m_stats = stats.clone();
        let m_clock = clock_cell.clone();
        let m_cmd = cmd_q.clone();
        let m_events = events.clone();
        let m_take = take_id.clone();
        let driver =
            MuxDriver::new(muxer, spec, segment_seconds, control.clone(), stats.clone(), extradata);
        self.threads.push(
            std::thread::Builder::new()
                .name("windagent-mux".into())
                .spawn(move || {
                    let args = RunMuxArgs {
                        take_id: m_take,
                        take_dir: take_dir_str,
                        cmd_q: m_cmd,
                        stats: m_stats,
                        clock: m_clock,
                        events: m_events,
                        control: m_control,
                    };
                    run_mux_thread(driver, timeline, args)
                })
                .map_err(|e| format!("SPAWN_MUX_FAILED:{e}"))?,
        );
        Ok(())
    }

    // ── lifecycle helpers ───────────────────────────────────────────────────

    /// Cooperative shutdown: signal → join → manifest. Returns the stop
    /// summary payload.
    fn graceful_stop(&mut self, final_state: ServiceState) -> serde_json::Value {
        self.stopping = true;
        self.state = ServiceState::Finalizing;
        if let Some(c) = &self.control {
            c.request_shutdown();
        }
        let threads = std::mem::take(&mut self.threads);
        for t in threads {
            let _ = t.join();
        }
        self.control = None;
        self.clock = None;
        self.cmd_q = None;

        // Manifest from the segments the mux thread reported.
        let entries: Vec<crate::SegmentEntry> = self
            .stats
            .lock()
            .map(|s| {
                s.segments_completed
                    .iter()
                    .map(|seg| crate::SegmentEntry {
                        index: seg.index,
                        file_token: seg.file_token.clone(),
                        duration_sec: seg.duration_sec,
                        byte_len: seg.byte_len,
                        is_playable: seg.is_playable,
                    })
                    .collect()
            })
            .unwrap_or_default();
        let total_bytes: u64 = entries.iter().map(|e| e.byte_len).sum();
        let segment_count = entries.len();
        if !self.take_dir.as_os_str().is_empty() {
            let manifest = crate::SegmentManifest {
                take_id: self.take_id.clone(),
                execution_plan_id: self.execution_plan_id.clone(),
                segments: entries,
                timeline_ref: format!("{}/timeline.jsonl", self.take_id),
                created_at: rfc3339_now(),
            };
            if let Err(e) = crate::segment::timeline_writer::write_manifest(&self.take_dir, &manifest) {
                let _ = push_event(&self.events, EngineEvent::Error { message: e });
            }
        }

        let snap = self.snapshot_now();
        let _ = push_event(&self.events, EngineEvent::Status { telemetry: snap });
        self.state = final_state;
        json!({
            "take_id": self.take_id,
            "backend": self.backend,
            "segments": segment_count,
            "total_bytes": total_bytes,
            "error": self.error,
        })
    }

    fn elapsed_sec_now(&self) -> f64 {
        let qpc = clock::qpc_now();
        self.clock
            .as_ref()
            .and_then(|c| c.lock().ok().map(|clk| clk.sec_at(qpc)))
            .unwrap_or(0.0)
    }

    fn snapshot_now(&mut self) -> TelemetrySnapshot {
        let host = sample_host_metrics(&mut self.cpu_sampler);
        let disk_free_gb = probe_disk_free_gb(&self.take_dir);
        let segment_index =
            self.stats.lock().map(|s| s.segments_completed.len() as u32).unwrap_or(0);
        let state_str = self.state.as_str().to_string();
        let take_id = self.take_id.clone();
        let backend = self.backend.clone();
        // A poisoned cell composes an empty snapshot rather than stalling the
        // heartbeat — status must keep flowing even while a worker wedged.
        match self.stats.lock() {
            Ok(s) => compose_snapshot(&s, &state_str, &take_id, segment_index, disk_free_gb, &host, &backend),
            Err(_) => compose_snapshot(
                &crate::pipeline::PipelineStats::default(),
                &state_str,
                &take_id,
                segment_index,
                disk_free_gb,
                &host,
                &backend,
            ),
        }
    }

    fn drain_events(&mut self) -> Vec<EngineEvent> {
        let mut out = Vec::new();
        if let Ok(mut q) = self.events.lock() {
            out.extend(q.drain(..));
        }
        out
    }
}

impl Default for RecorderService {
    fn default() -> Self {
        Self::new()
    }
}

fn probe_disk_free_gb(dir: &Path) -> f64 {
    let target = if dir.as_os_str().is_empty() { std::env::temp_dir() } else { dir.to_path_buf() };
    crate::probe::disk_free_bytes(&target)
        .map(|b| (b as f64 / 1_073_741_824.0 * 10.0).round() / 10.0)
        .unwrap_or(0.0)
}

/// Push an event without ever blocking producers (events are small; the
/// sidecar drains every ≤250 ms).
fn push_event(events: &EventOut, ev: EngineEvent) -> Result<(), String> {
    events
        .lock()
        .map(|mut q| q.push_back(ev))
        .map_err(|_| "EVENT_LOCK_POISONED".to_string())
}

// ─── Thread bodies ──────────────────────────────────────────────────────────

/// COM apartment for the encode thread (WGC/WinRT + MF activation need one).
#[cfg(windows)]
fn co_init_encode_thread() {
    use windows::Win32::System::Com::{CoInitializeEx, COINIT_MULTITHREADED};
    unsafe {
        // S_FALSE (already initialized another way) is harmless — the thread
        // exits soon and never calls CoUninitialize for a foreign apartment.
        let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
    }
}
#[cfg(not(windows))]
fn co_init_encode_thread() {}

struct RunEncodeArgs {
    capture: Box<dyn CapturePort>,
    encoder: Box<dyn EncoderPort>,
    preview: Option<Box<dyn PreviewTap>>,
    sampler: PreviewSampler,
    control: Arc<EncoderControl>,
    stats: SharedStats,
    /// Shared take clock — PTS authority so video shares the audio tracks'
    /// pause-compensated timeline (§12 single-clock rule).
    clock: Arc<Mutex<TakeClock>>,
    cmd_q: Arc<Mutex<VecDeque<MuxCommand>>>,
    events: EventOut,
    take_id: String,
    fps: u32,
}

fn run_encode_thread(args: RunEncodeArgs) {
    co_init_encode_thread();

    let RunEncodeArgs {
        mut capture,
        mut encoder,
        mut preview,
        mut sampler,
        control,
        stats,
        clock,
        cmd_q,
        events,
        take_id,
        fps,
    } = args;

    if let Err(e) = encoder.prepare() {
        let _ = push_event(&events, EngineEvent::Error { message: format!("ENGINE_ENCODE_FAILED:{e}") });
        control.request_shutdown();
        return;
    }
    if let Err(e) = capture.start() {
        let _ = push_event(&events, EngineEvent::Error { message: format!("ENGINE_CAPTURE_FAILED:{e}") });
        control.request_shutdown();
        return;
    }

    let frame_interval_us = 1_000_000u64 / fps.max(1) as u64;
    // A take opens on a keyframe by contract: the first MKV segment must be
    // independently decodable and the muxer's extradata handshake assumes an
    // IDR at pts 0.
    encoder.request_idr();
    let mut consecutive_errors: u32 = 0;
    // Last muxed video take-time — stale pre-pause frames (pts ≤ this) drop.
    let mut last_muxed_pts: Option<u64> = None;
    let mut preview_cycles: u64 = 0;

    loop {
        if control.should_stop() {
            break;
        }
        if control.is_paused() {
            std::thread::sleep(Duration::from_millis(8));
            continue;
        }
        if !capture.is_available() {
            let _ = push_event(&events, EngineEvent::Warning {
                message: "CAPTURE_SOURCE_LOST: capture backend reports unavailable — finalizing take".into(),
            });
            control.request_shutdown();
            break;
        }
        match capture.poll_frame() {
            Some(mut frame) => {
                // Take-clock authority (§12): presentation time excludes pause
                // spans so video shares the audio tracks' one gapless
                // timeline. A frame captured before a pause but polled after
                // resume carries an already-covered take time — dropping it
                // keeps DTS monotonic without re-recording excluded content.
                // Should the clock mutex ever be poisoned, the thread falls
                // back to its own cadence so the timeline stays increasing.
                let pts_rel = clock.lock()
                    .map(|c| c.micros_at(frame.qpc))
                    .unwrap_or_else(|_| last_muxed_pts.map_or(0, |last| last + frame_interval_us.max(1)));
                if last_muxed_pts.is_some_and(|last| pts_rel <= last) {
                    continue;
                }
                last_muxed_pts = Some(pts_rel);

                if let Ok(mut s) = stats.lock() {
                    s.telemetry.on_frame_captured(pts_rel);
                    s.capture_queue_depth = capture.pending_frames();
                }

                // Preview tap — pacing internal to the sampler; degradation
                // reacts to sustained pressure (§18), never to one slow frame.
                preview_cycles += 1;
                if let Some(prev) = preview.as_mut() {
                    let now_ms = clock::qpc_now_ms();
                    if sampler.should_emit(now_ms) {
                        match prev.process(&frame) {
                            Ok(jpeg) => {
                                sampler.mark_emitted(now_ms);
                                let b64 = base64_encode(&jpeg.jpeg);
                                let _ = push_event(&events, EngineEvent::Preview {
                                    take_id: take_id.clone(),
                                    width: jpeg.width,
                                    height: jpeg.height,
                                    data_len: jpeg.jpeg.len(),
                                    timestamp_ms: pts_rel / 1_000,
                                    jpeg_base64: b64,
                                });
                            }
                            Err(_) => {
                                // Preview must NEVER disturb recording (§13):
                                // mark emitted so a broken path isn't hammered
                                // faster than the rate gate allows.
                                sampler.mark_emitted(now_ms);
                            }
                        }
                    }
                    // Every ~5 s evaluate the degradation ladder.
                    if preview_cycles % (fps as u64 * 5) == 0 {
                        let degraded = stats.lock().ok().map_or(false, |s| {
                            s.telemetry.dropped_pct() > 5.0
                                || s.telemetry.latency_p95().is_some_and(|p| p > 40.0)
                        });
                        if degraded && sampler.rate() != crate::preview::PreviewRate::Off {
                            sampler.set_rate(sampler.rate().degrade());
                        }
                    }
                }

                if let Ok(mut s) = stats.lock() {
                    s.telemetry.on_frame_submitted();
                }

                let t0 = clock::qpc_now();
                let result = encoder.encode_frame(&mut frame, pts_rel);
                drop(frame); // release the pool texture promptly
                match result {
                    Ok(pkts) => {
                        let latency_ms = clock::ticks_to_sec(clock::qpc_now().saturating_sub(t0)) * 1000.0;
                        consecutive_errors = 0;
                        if let Ok(mut s) = stats.lock() {
                            s.telemetry.on_encode_latency_ms(latency_ms);
                            s.telemetry.on_frame_encoded(clock::qpc_now());
                        }
                        // Packets already carry take-relative PTS (§12) —
                        // route them straight to the mux queue.
                        for p in pkts {
                            if bounded_send(&cmd_q, MuxCommand::Video(p), VIDEO_CMD_CAP, Duration::from_secs(2)).is_err() {
                                if let Ok(mut s) = stats.lock() {
                                    s.telemetry.on_frame_dropped();
                                }
                                let _ = push_event(&events, EngineEvent::Warning {
                                    message: "VIDEO_QUEUE_FULL: mux fell behind; frame dropped".into(),
                                });
                            }
                        }
                        if let Ok(mut s) = stats.lock() {
                            s.encoder_queue_depth = cmd_q.lock().map(|q| q.len()).unwrap_or(0);
                        }
                    }
                    Err(e) => {
                        consecutive_errors += 1;
                        let _ = push_event(&events, EngineEvent::Warning {
                            message: format!(
                                "ENCODE_WARN({consecutive_errors}/{MAX_CONSECUTIVE_ENCODE_ERRORS}):{e}"
                            ),
                        });
                        if consecutive_errors >= MAX_CONSECUTIVE_ENCODE_ERRORS {
                            let _ = push_event(&events, EngineEvent::Error {
                                message: format!("ENGINE_ENCODE_FAILED:{e}"),
                            });
                            control.request_shutdown();
                            break;
                        }
                    }
                }
            }
            None => {
                std::thread::sleep(Duration::from_micros(frame_interval_us.min(4_000)));
            }
        }
    }

    // Flush lookahead/B-frame tail, then release capture.
    if let Ok(tail) = encoder.flush() {
        for p in tail {
            let _ = bounded_send(&cmd_q, MuxCommand::Video(p), VIDEO_CMD_CAP, Duration::from_secs(2));
        }
    }
    let _ = capture.stop();
}

struct RunAudioArgs {
    port: Box<dyn AudioCapturePort>,
    aac: Box<dyn AacEncoderPort>,
    mute: Arc<AtomicBool>,
    kind: TrackKind,
    control: Arc<EncoderControl>,
    stats: SharedStats,
    clock: Arc<Mutex<TakeClock>>,
    cmd_q: Arc<Mutex<VecDeque<MuxCommand>>>,
    events: EventOut,
}

fn run_audio_thread(args: RunAudioArgs) {
    let RunAudioArgs { mut port, mut aac, mute, kind, control, stats, clock, cmd_q, events } = args;
    if let Err(e) = port.start() {
        let _ = push_event(&events, EngineEvent::Warning {
            message: format!("AUDIO_TRACK_DISABLED:{kind:?}:{e}"),
        });
        return;
    }
    let track_id: TrackId = kind.into();
    let mut aac_dead = false;
    let mut meter_counter: u64 = 0;
    // Last encoded take-time on this track — pre-pause blocks surfacing
    // after resume (pts ≤ this) drop instead of regressing DTS.
    let mut last_block_pts: Option<u64> = None;

    let send_outs = |outs: Vec<AacOut>,
                     samples: u64,
                     take_time_us: u64,
                     cmd_q: &Arc<Mutex<VecDeque<MuxCommand>>>,
                     stats: &SharedStats,
                     events: &EventOut|
     {
        for o in outs {
            let pkt = EncodedPacket {
                pts_us: o.pts_us,
                dts_us: o.pts_us as i64,
                is_keyframe: true,
                data: o.data,
                codec: "AAC".into(),
            };
            if bounded_send(
                cmd_q,
                MuxCommand::Audio { track: track_id, packet: pkt, samples, take_time_us },
                AUDIO_CMD_CAP,
                Duration::from_secs(2),
            )
            .is_err()
            {
                if let Ok(mut s) = stats.lock() {
                    s.telemetry.on_audio_underrun();
                }
                let _ = push_event(events, EngineEvent::Warning {
                    message: format!("AUDIO_QUEUE_FULL:{kind:?}: mux fell behind"),
                });
            }
        }
    };

    loop {
        if control.should_stop() {
            break;
        }
        if control.is_paused() {
            std::thread::sleep(Duration::from_millis(20));
            continue;
        }
        match port.poll_block() {
            Some(block) => {
                let block = if mute.load(Ordering::SeqCst) { silence_block(block) } else { block };

                // Meter feed (throttled ~10 Hz per track).
                meter_counter += 1;
                if meter_counter % 5 == 0 {
                    let (rms, peak) = crate::telemetry::rms_peak_dbfs(&block.samples);
                    let _ = push_event(&events, EngineEvent::AudioMeter {
                        track: kind_meter_name(kind).into(),
                        rms_dbfs: rms,
                        peak_dbfs: peak,
                        muted: mute.load(Ordering::SeqCst),
                    });
                }

                if !aac_dead {
                    // Take-relative time doubles as the drift-tracker clock —
                    // pause spans are already excluded from it.
                    let pts_rel = clock.lock().map(|c| c.micros_at(block.qpc)).unwrap_or(0);
                    // Stale-block guard: a block captured before a pause but
                    // polled after resume maps to an already-covered take
                    // time; feeding it would regress DTS and overlap content
                    // already on the timeline, so it drops (§12 single-clock).
                    if last_block_pts.is_some_and(|last| pts_rel <= last) {
                        continue;
                    }
                    last_block_pts = Some(pts_rel);
                    // §12 compensation: feed this track's smoothed drift to
                    // the encoder so content duration matches its QPC span.
                    // Accounting itself stays single-writer on the mux thread;
                    // here we only READ the estimate.
                    if let Ok(s) = stats.lock() {
                        let ppm = match track_id {
                            TrackId::Mic => s.mic_drift.drift_ppm(),
                            TrackId::System => s.system_drift.drift_ppm(),
                            TrackId::Video => 0.0,
                        };
                        aac.set_drift_ppm(ppm);
                    }
                    match aac.encode_block(&block, pts_rel) {
                        Ok(outs) => send_outs(outs, block.frames() as u64, pts_rel, &cmd_q, &stats, &events),
                        Err(e) => {
                            // §24: losing one audio track must not kill the
                            // take — disable encoding here, meters keep flowing.
                            aac_dead = true;
                            let _ = push_event(&events, EngineEvent::Warning {
                                message: format!("AUDIO_TRACK_DISABLED:{kind:?}:{e}"),
                            });
                        }
                    }
                }
            }
            None => {
                std::thread::sleep(Duration::from_millis(8));
            }
        }
    }

    // Tail: drain buffered blocks + flush the encoder.
    while !aac_dead {
        let Some(block) = port.poll_block() else { break };
        let block = if mute.load(Ordering::SeqCst) { silence_block(block) } else { block };
        if let Ok(pts_rel) = clock.lock().map(|c| c.micros_at(block.qpc)) {
            if let Ok(outs) = aac.encode_block(&block, pts_rel) {
                send_outs(outs, block.frames() as u64, pts_rel, &cmd_q, &stats, &events);
            }
        }
    }
    if !aac_dead {
        let now_take_us = clock.lock().map(|c| c.micros_at(clock::qpc_now())).unwrap_or(0);
        if let Ok(outs) = aac.drain() {
            send_outs(outs, 0, now_take_us, &cmd_q, &stats, &events);
        }
    }
    let _ = port.stop();
}

struct RunMuxArgs {
    take_id: String,
    take_dir: String,
    cmd_q: Arc<Mutex<VecDeque<MuxCommand>>>,
    stats: SharedStats,
    clock: Arc<Mutex<TakeClock>>,
    events: EventOut,
    #[allow(dead_code)]
    control: Arc<EncoderControl>,
}

fn run_mux_thread(mut driver: MuxDriver, mut timeline: TimelineWriter, args: RunMuxArgs) {
    let RunMuxArgs { take_id, take_dir, cmd_q, stats, clock, events, .. } = args;

    if let Err(e) = driver.muxer.prepare(&take_dir) {
        let _ = push_event(&events, EngineEvent::Error { message: format!("MKV_PREPARE_FAILED:{e}") });
        return;
    }

    let mut last_written_video_pts: Option<i64> = None;

    loop {
        if control_should_break(&driver.control) {
            break;
        }
        if driver.control.is_paused() {
            // Pause contract: close the open segment (pause == file boundary).
            // The next segment index is advanced HERE, exactly once per real
            // close — an IDR roll closes via ensure_open with the router
            // already having bumped the index.
            let t = now_sec(&clock);
            let was_open = driver.open_segment.is_some();
            if let Err(e) = driver.close_current(&take_id, t, &mut timeline, &events) {
                let _ = push_event(&events, EngineEvent::Error { message: format!("SEGMENT_CLOSE_FAILED:{e}") });
            }
            if was_open {
                driver.router.segment_index += 1;
            }
            std::thread::sleep(Duration::from_millis(8));
            continue;
        }
        match try_pop(&cmd_q) {
            Some(cmd) => {
                let t = now_sec(&clock);
                process_mux_command(&mut driver, cmd, &take_id, t, &mut timeline, &events, &stats, &mut last_written_video_pts);
            }
            None => std::thread::sleep(Duration::from_millis(4)),
        }
    }

    // Final drain — everything queued before shutdown must land on disk.
    while let Some(cmd) = try_pop(&cmd_q) {
        let t = now_sec(&clock);
        process_mux_command(&mut driver, cmd, &take_id, t, &mut timeline, &events, &stats, &mut last_written_video_pts);
    }
    let t = now_sec(&clock);
    if let Err(e) = driver.close_current(&take_id, t, &mut timeline, &events) {
        let _ = push_event(&events, EngineEvent::Error { message: format!("SEGMENT_CLOSE_FAILED:{e}") });
    }
    let _ = driver.muxer.finalize_take();
    let _ = timeline.append(&crate::segment::TimelineEvent {
        t,
        event_type: "SESSION_END".into(),
        scene_id: None,
        cue_id: None,
        action_id: None,
        execution_id: None,
        marker_type: None,
        detail: "take finalized".into(),
    });

    fn control_should_break(control: &Arc<EncoderControl>) -> bool {
        control.should_stop()
    }
    fn now_sec(clock: &Arc<Mutex<TakeClock>>) -> f64 {
        let qpc = clock::qpc_now();
        clock.lock().map(|c| c.sec_at(qpc)).unwrap_or(0.0)
    }
}

#[allow(clippy::too_many_arguments)]
fn process_mux_command(
    driver: &mut MuxDriver,
    cmd: MuxCommand,
    take_id: &str,
    t_now_sec: f64,
    timeline: &mut TimelineWriter,
    events: &EventOut,
    stats: &SharedStats,
    last_written_video_pts: &mut Option<i64>,
) {
    match cmd {
        MuxCommand::Marker(ev) => {
            let _ = timeline.append(&ev);
        }
        MuxCommand::Video(pkt) => {
            let pts_us = pkt.pts_us;
            // Monotonicity watchdog (§12): log-only — a regression never kills
            // a live take but must be visible in diagnostics.
            if last_written_video_pts.is_some_and(|p| pts_us as i64 + 200_000 < p) {
                let _ = push_event(events, EngineEvent::Warning {
                    message: format!(
                        "TIMESTAMP_REGRESSION: video {} after {}",
                        pts_us,
                        last_written_video_pts.unwrap_or(0)
                    ),
                });
            }
            *last_written_video_pts = Some(pts_us as i64);

            if let Err(e) =
                driver.route_and_write(TrackId::Video, pkt, take_id, t_now_sec, timeline, events)
            {
                let _ = push_event(events, EngineEvent::Error { message: format!("MKV_WRITE_FAILED:{e}") });
            }
            if let Ok(mut s) = stats.lock() {
                // on_bytes_written expects cumulative totals (it deltas the
                // window edges itself), so pass bytes_written directly.
                let bytes = driver.muxer.bytes_written();
                s.bytes_written = bytes;
                s.last_video_pts_us = Some(pts_us);
                s.telemetry.on_bytes_written(clock::qpc_now(), bytes);
            }
        }
        MuxCommand::Audio { track, packet, samples, take_time_us } => {
            let pts_us = packet.pts_us;
            if let Err(e) = driver.route_and_write(track, packet, take_id, t_now_sec, timeline, events) {
                let _ = push_event(events, EngineEvent::Error { message: format!("MKV_WRITE_FAILED:{e}") });
            }
            if let Ok(mut s) = stats.lock() {
                match track {
                    TrackId::Mic => s.mic_drift.on_packet_us(samples, take_time_us),
                    TrackId::System => s.system_drift.on_packet_us(samples, take_time_us),
                    TrackId::Video => {}
                }
                if track == TrackId::Mic {
                    s.last_mic_pts_us = Some(pts_us);
                }
                if let Some(vpts) = s.last_video_pts_us {
                    s.av_sync_error_ms = (vpts as f64 - pts_us as f64) / 1000.0;
                }
            }
        }
    }
}

fn silence_block(mut b: PcmBlock) -> PcmBlock {
    b.samples.iter_mut().for_each(|s| *s = 0.0);
    b
}

fn kind_meter_name(k: TrackKind) -> &'static str {
    match k {
        TrackKind::Mic => "mic",
        TrackKind::System => "system",
    }
}

fn base64_encode(data: &[u8]) -> String {
    use base64::Engine as _;
    base64::engine::general_purpose::STANDARD.encode(data)
}

// ─── GpuPreview adapter ─────────────────────────────────────────────────────

#[cfg(windows)]
struct GpuPreviewAdapter {
    inner: crate::preview::gpu_preview::GpuPreviewPipeline,
}

// SAFETY: the pipeline owns raw COM pointers, but a PreviewTap is only ever
// constructed on (and moved once into) the encode thread — the single owner
// of all D3D11 immediate-context work per the pipeline threading contract.
// It is never shared across threads.
#[cfg(windows)]
unsafe impl Send for GpuPreviewAdapter {}

#[cfg(windows)]
impl PreviewTap for GpuPreviewAdapter {
    fn process(&mut self, frame: &crate::capture::CapturedFrame) -> Result<PreviewJpeg, String> {
        self.inner.process(frame)
    }
}

// ─── Mock AAC (dev/CI only) ─────────────────────────────────────────────────

/// Emits one AAC-sized packet per input block with honest PTS progression.
struct MockAacEncoder {
    fed_frames: u64,
}

impl MockAacEncoder {
    fn new() -> Self {
        Self { fed_frames: 0 }
    }
}

impl AacEncoderPort for MockAacEncoder {
    fn encode_block(&mut self, block: &PcmBlock, pts_us_of_first_frame: u64) -> Result<Vec<AacOut>, String> {
        let frames = block.frames() as u64;
        let out = vec![AacOut {
            data: vec![0u8; (frames as usize) / 24], // ~48 kbps equivalent bulk
            pts_us: pts_us_of_first_frame,
            sample_count: frames,
        }];
        self.fed_frames += frames;
        Ok(out)
    }

    fn drain(&mut self) -> Result<Vec<AacOut>, String> {
        Ok(vec![])
    }

    fn output_sample_rate(&self) -> u32 {
        48_000
    }

    fn output_channels(&self) -> u32 {
        2
    }
}

// ─── Tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ipc::{MarkerRequest, MuteRequest};

    /// Unique scratch dir per test run — recovery scans by mtime so sharing
    /// a root across tests would make `scan_latest_take` order flaky.
    fn temp_root(tag: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "windagent_svc_{tag}_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&root).unwrap();
        root
    }

    fn err_code(resp: &EngineResponse) -> String {
        match resp {
            EngineResponse::Err { code, .. } => code.clone(),
            other => panic!("expected Err response, got {other:?}"),
        }
    }

    fn ok_op(resp: &EngineResponse) -> String {
        match resp {
            EngineResponse::Ok { op, .. } => op.clone(),
            other => panic!("expected Ok response, got {other:?}"),
        }
    }

    fn prepare_req(root: &Path) -> PrepareRequest {
        PrepareRequest {
            execution_plan_id: "plan-1".into(),
            execution_plan_hash: "deadbeef".into(),
            episode_id: "ep-1".into(),
            output_dir: root.display().to_string(),
            profile: crate::EngineProfile::default(),
        }
    }

    #[test]
    fn start_before_prepare_is_invalid_state() {
        let mut s = RecorderService::with_allow_mock(true);
        let (resp, _) = s.handle(EngineRequest::Start(StartRequest {
            execution_plan_id: "plan-1".into(),
            take_id: "take_x".into(),
        }));
        assert_eq!(err_code(&resp), "INVALID_STATE");
    }

    #[test]
    fn pause_resume_stop_outside_take_are_rejected() {
        let mut s = RecorderService::with_allow_mock(true);
        assert_eq!(err_code(&s.handle(EngineRequest::Pause).0), "INVALID_STATE");
        assert_eq!(err_code(&s.handle(EngineRequest::Resume).0), "INVALID_STATE");
        assert_eq!(err_code(&s.handle(EngineRequest::Stop).0), "INVALID_STATE");
    }

    #[test]
    fn profile_violations_are_rejected_even_with_mock_consent() {
        let root = temp_root("badprofile");
        let mut s = RecorderService::with_allow_mock(true);
        let mut req = prepare_req(&root);
        req.profile.video.encoder = "x264".into(); // software fallback — never
        let (resp, _) = s.handle(EngineRequest::Prepare(req));
        assert_eq!(err_code(&resp), "ENGINE_PROFILE_REJECTED");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn markers_require_an_active_take() {
        let mut s = RecorderService::with_allow_mock(true);
        let (resp, _) = s.handle(EngineRequest::Marker(MarkerRequest {
            marker_type: "SCENE".into(),
            cue_id: None,
            action_id: None,
        }));
        assert_eq!(err_code(&resp), "INVALID_STATE");
    }

    #[test]
    fn capabilities_always_answer() {
        let mut s = RecorderService::with_allow_mock(true);
        let (resp, _) = s.handle(EngineRequest::Capabilities);
        assert_eq!(ok_op(&resp), "capabilities");
    }

    #[test]
    fn sources_op_is_total_and_leaves_state_untouched() {
        let mut s = RecorderService::with_allow_mock(true);
        // Valid before prepare…
        let (resp, events) = s.handle(EngineRequest::Sources);
        assert!(events.is_empty());
        assert_eq!(ok_op(&resp), "sources");
        let payload = match &resp {
            EngineResponse::Ok { payload, .. } => payload.clone(),
            other => panic!("expected Ok response, got {other:?}"),
        };
        assert!(payload["monitors"].is_array());
        assert!(payload["windows"].is_array());
        assert_eq!(s.state(), ServiceState::Idle);
        // …and mid-lifecycle: enumeration never disturbs an active take.
        let root = temp_root("sources_state");
        let (prep, _) = s.handle(EngineRequest::Prepare(prepare_req(&root)));
        assert_eq!(ok_op(&prep), "prepare");
        let (start, _) = s.handle(EngineRequest::Start(StartRequest {
            execution_plan_id: "plan_sources".into(),
            take_id: String::new(),
        }));
        assert_eq!(ok_op(&start), "start");
        let (_, events) = s.handle(EngineRequest::Sources);
        // The sources OP itself synthesizes nothing; a mid-take call drains
        // whatever live pipeline threads emitted in the meantime (Timeline/
        // Status/AudioMeter…) — that forwarding is the design, not a leak.
        // Only a pipeline ERROR here would mean enumeration disturbed the take.
        assert!(
            !events.iter().any(|e| matches!(e, EngineEvent::Error { .. })),
            "sources op surfaced pipeline errors: {events:?}"
        );
        assert_eq!(s.state(), ServiceState::Recording);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn mock_take_lifecycle_pause_boundary_produces_segments_manifest_timeline() {
        let root = temp_root("lifecycle");
        let mut s = RecorderService::with_allow_mock(true);

        let (prep, _) = s.handle(EngineRequest::Prepare(prepare_req(&root)));
        assert_eq!(ok_op(&prep), "prepare");

        let (start, _) = s.handle(EngineRequest::Start(StartRequest {
            execution_plan_id: "plan-1".into(),
            take_id: "take_lifecycle".into(),
        }));
        assert_eq!(ok_op(&start), "start");
        assert_eq!(s.state(), ServiceState::Recording);

        let (_, events) = s.handle(EngineRequest::Mute(MuteRequest {
            mic_muted: true,
            system_muted: false,
        }));
        assert!(events.is_empty(), "mute is silent when accepted");

        let (mk, _) = s.handle(EngineRequest::Marker(MarkerRequest {
            marker_type: "CUE_START".into(),
            cue_id: Some("c1".into()),
            action_id: None,
        }));
        assert_eq!(ok_op(&mk), "marker");

        // Record briefly, then PAUSE — the contract says pause closes the
        // open segment (file boundary).
        std::thread::sleep(Duration::from_millis(600));
        let (pause, _) = s.handle(EngineRequest::Pause);
        assert_eq!(ok_op(&pause), "pause");

        // Wait out the mux thread's close of segment 0.
        let deadline = std::time::Instant::now() + Duration::from_secs(5);
        let mut saw_segment_close = false;
        while std::time::Instant::now() < deadline && !saw_segment_close {
            for ev in s.tick() {
                if let EngineEvent::Segment { segment_index: 0, is_playable: true, .. } = ev {
                    saw_segment_close = true;
                }
            }
            std::thread::sleep(Duration::from_millis(25));
        }
        assert!(saw_segment_close, "pause must commit an open segment");

        let (resume, _) = s.handle(EngineRequest::Resume);
        assert_eq!(ok_op(&resume), "resume");
        std::thread::sleep(Duration::from_millis(400));

        let (stop, events) = s.handle(EngineRequest::Stop);
        assert_eq!(ok_op(&stop), "stop");
        assert_eq!(s.state(), ServiceState::Completed);
        assert!(
            events.iter().any(|ev| matches!(ev, EngineEvent::Segment { segment_index: 1, .. })),
            "post-resume recording opens a second segment; got {events:?}"
        );

        // Crash-safety artifacts on disk.
        let take_dir = root.join("take_lifecycle");
        let manifest = std::fs::read_to_string(take_dir.join("manifest.json")).unwrap();
        assert!(manifest.contains("\"segments\""), "manifest={manifest}");
        let timeline = std::fs::read_to_string(take_dir.join("timeline.jsonl")).unwrap();
        assert!(timeline.contains("SESSION_START"));
        assert!(timeline.contains("SESSION_END"));
        assert_eq!(timeline.matches("SEGMENT_END").count(), 2, "two committed segments");
        // Committed files carry the EBML magic; no .tmp tail survives stop.
        assert_eq!(std::fs::read(take_dir.join("segment_0000.mkv")).unwrap()[..4], crate::muxer::mock::EBML_MAGIC);
        assert!(!take_dir.join("segment_0001.mkv.tmp").exists());

        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn recover_without_any_take_reports_not_found() {
        let root = temp_root("recover_empty");
        let mut s = RecorderService::with_allow_mock(true);
        let (resp, _) = s.handle(EngineRequest::Recover { output_dir: root.display().to_string() });
        assert_eq!(err_code(&resp), "RECOVER_NO_TAKE_FOUND");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn service_state_strings_cover_every_variant() {
        use ServiceState::*;
        for (st, s) in [
            (Idle, "idle"),
            (Probing, "probing"),
            (Preparing, "preparing"),
            (Ready, "ready"),
            (Recording, "recording"),
            (Paused, "paused"),
            (Finalizing, "finalizing"),
            (Completed, "completed"),
            (Recovering, "recovering"),
            (Error, "error"),
        ] {
            assert_eq!(st.as_str(), s);
        }
    }

    #[test]
    fn capabilities_probe_restores_quiescent_state() {
        let mut s = RecorderService::with_allow_mock(true);
        assert_eq!(s.state(), ServiceState::Idle);
        let (resp, _) = s.handle(EngineRequest::Capabilities);
        assert_eq!(ok_op(&resp), "capabilities");
        // The probe is synchronous — by response time the quiescent state is
        // restored; `probing` was only observable on the heartbeat in between.
        assert_eq!(s.state(), ServiceState::Idle);
    }

    #[test]
    fn prepare_success_reaches_ready_and_failure_lands_in_error() {
        let root = temp_root("prepare_states");
        let mut s = RecorderService::with_allow_mock(true);

        let mut bad = prepare_req(&root);
        bad.profile.video.fps = 999_999; // violates the frozen profile rules
        let (resp, _) = s.handle(EngineRequest::Prepare(bad));
        assert_eq!(err_code(&resp), "ENGINE_PROFILE_REJECTED");
        assert_eq!(s.state(), ServiceState::Error, "stuck-in-preparing is a lie");

        let (resp, _) = s.handle(EngineRequest::Prepare(prepare_req(&root)));
        assert_eq!(ok_op(&resp), "prepare");
        assert_eq!(s.state(), ServiceState::Ready);
        let _ = std::fs::remove_dir_all(&root);
    }


    // ── §9 extradata handshake ─────────────────────────────────────────────

    /// Synthetic Annex-B SPS/PPS pair (same bytes as the tracks.rs fixtures).
    const SPS: &[u8] = &[0x67, 0x64, 0x00, 0x28, 0xAC, 0xD9, 0x40, 0x50];
    const PPS: &[u8] = &[0x68, 0xEB, 0xEC, 0xB2, 0x2C];

    #[test]
    fn build_video_extradata_parses_h264_and_hevc_sequence_headers() {
        let mut h264_au = vec![0, 0, 0, 1];
        h264_au.extend_from_slice(SPS);
        h264_au.extend_from_slice(&[0, 0, 1]);
        h264_au.extend_from_slice(PPS);
        let avcc = build_video_extradata(&h264_au, false).expect("avcC from SPS+PPS");
        assert_eq!(avcc[0], 1); // configurationVersion

        // HEVC needs VPS+SPS+PPS.
        let vps: &[u8] = &[0x40, 0x01, 0x0C, 0x01, 0xFF, 0xFF, 0x01, 0x60, 0x00, 0x00, 0x03, 0x00, 0x90, 0x00, 0x00, 0x03, 0x00, 0x00, 0x03, 0x00, 0x78, 0xBB, 0x1E];
        let hevc_sps: &[u8] = &[0x42, 0x01, 0x01, 0x01, 0x60, 0x00, 0x00, 0x03, 0x00, 0x90, 0x00, 0x00, 0x03, 0x00, 0x00, 0x03, 0x00, 0x78, 0xA0, 0x03, 0xC0, 0x80, 0x10, 0xE2, 0xDF, 0xAE, 0x58];
        let hevc_pps: &[u8] = &[0x44, 0x01, 0xC1, 0x72, 0xB4, 0x62, 0x60];
        let mut hevc_au = vec![0, 0, 0, 1];
        hevc_au.extend_from_slice(vps);
        hevc_au.extend_from_slice(&[0, 0, 0, 1]);
        hevc_au.extend_from_slice(hevc_sps);
        hevc_au.extend_from_slice(&[0, 0, 0, 1]);
        hevc_au.extend_from_slice(hevc_pps);
        let hvcc = build_video_extradata(&hevc_au, true).expect("hvcC from VPS+SPS+PPS");
        assert_eq!(hvcc[22], 3); // numOfArrays

        // Garbage fails closed — a header-less MKV must never be produced.
        assert!(build_video_extradata(&[0xDE, 0xAD], false).is_none());
        assert!(build_video_extradata(&[], true).is_none());
        // An H264 blob asked to build hvcC finds no VPS/SPS/PPS types.
        assert!(build_video_extradata(&h264_au, true).is_none());
    }

    #[test]
    fn collect_audio_asc_covers_every_aac_track_and_fails_closed() {
        let spec = vec![
            (
                TrackId::Video,
                TrackParams::VideoH264 { width: 1920, height: 1080, fps: 60 },
            ),
            (TrackId::Mic, TrackParams::Aac { sample_rate: 48_000, channels: 1 }),
            (TrackId::System, TrackParams::Aac { sample_rate: 48_000, channels: 2 }),
        ];
        let asc = collect_audio_asc(&spec).expect("48 kHz mono/stereo are expressible");
        assert_eq!(asc.len(), 2);
        assert_eq!(asc[0].0, TrackId::Mic);
        assert_eq!(asc[1].0, TrackId::System);

        // A rate outside the AAC table cannot be staged — contract bug, fail
        // closed before threads spawn rather than mid-take.
        let bad = vec![(TrackId::Mic, TrackParams::Aac { sample_rate: 12_345, channels: 2 })];
        let err = collect_audio_asc(&bad).unwrap_err();
        assert!(err.starts_with("AAC_ASC_INVALID"), "{err}");
    }

    /// Records every MuxerPort call so the driver's per-segment handshake can
    /// be asserted without libav DLLs.
    struct RecordingMuxer {
        log: Arc<Mutex<Vec<String>>>,
    }

    impl RecordingMuxer {
        fn new(log: Arc<Mutex<Vec<String>>>) -> Self {
            Self { log }
        }
    }

    impl MuxerPort for RecordingMuxer {
        fn prepare(&mut self, _output_dir: &str) -> Result<(), String> {
            Ok(())
        }
        fn open_segment(&mut self, index: u32, _tracks: &[(TrackId, TrackParams)]) -> Result<(), String> {
            self.log.lock().unwrap().push(format!("open:{index}"));
            Ok(())
        }
        fn stage_video_extradata(&mut self, data: &[u8]) -> Result<(), String> {
            self.log.lock().unwrap().push(format!("stage_video:{}", data.len()));
            Ok(())
        }
        fn stage_audio_extradata(&mut self, track: TrackId, data: &[u8]) -> Result<(), String> {
            self.log.lock().unwrap().push(format!("stage_audio:{}:{}", track.as_str(), data.len()));
            Ok(())
        }
        fn write_packet(&mut self, track: TrackId, _packet: &EncodedPacket) -> Result<(), String> {
            self.log.lock().unwrap().push(format!("write:{}", track.as_str()));
            Ok(())
        }
        fn close_segment(&mut self) -> Result<crate::muxer::MuxedSegment, String> {
            self.log.lock().unwrap().push("close".into());
            Ok(crate::muxer::MuxedSegment {
                index: 0,
                file_token: "take_x/segment_0000.mkv".into(),
                duration_sec: 0.0,
                byte_len: 0,
                is_playable: true,
            })
        }
        fn finalize_take(&mut self) -> Result<(), String> {
            Ok(())
        }
    }

    #[test]
    fn muxdriver_stages_codec_private_into_every_segment_before_first_packet() {
        let events: EventOut = Arc::new(Mutex::new(VecDeque::new()));
        let mut timeline =
            TimelineWriter::create(&temp_root("extradata_handshake")).expect("timeline");
        let stats: crate::pipeline::SharedStats = Arc::new(Mutex::new(Default::default()));

        let spec = vec![
            (
                TrackId::Video,
                TrackParams::VideoH264 { width: 1920, height: 1080, fps: 60 },
            ),
            (TrackId::Mic, TrackParams::Aac { sample_rate: 48_000, channels: 1 }),
        ];
        let extradata = SegmentExtradata {
            video_avcc_hvcc: Some(vec![0xAA; 24]),
            audio_asc: vec![(TrackId::Mic, vec![0x11, 0x88])],
        };
        let log = Arc::new(Mutex::new(Vec::<String>::new()));
        let mut driver = MuxDriver::new(
            Box::new(RecordingMuxer::new(log.clone())),
            spec,
            300,
            Arc::new(EncoderControl::new()),
            stats.clone(),
            extradata,
        );

        // First segment opens (as it would when the first packet arrives);
        // staging must land between open_segment and the first write.
        driver.ensure_open(0, "take_x", 0.0, &mut timeline, &events).unwrap();
        let pkt = EncodedPacket {
            pts_us: 0,
            dts_us: 0,
            is_keyframe: true,
            data: vec![0u8; 4],
            codec: "H264".into(),
        };
        driver.route_and_write(TrackId::Video, pkt, "take_x", 0.5, &mut timeline, &events).unwrap();
        // Roll boundary: ensure_open closes segment 0 and re-stages into 1 —
        // every MKV file must carry its own CodecPrivate to be playable alone.
        driver.ensure_open(1, "take_x", 300.5, &mut timeline, &events).unwrap();
        drop(driver);

        assert_eq!(
            *log.lock().unwrap(),
            vec![
                "open:0".to_string(),
                "stage_video:24".to_string(),
                "stage_audio:mic:2".to_string(),
                "write:video".to_string(),
                "close".to_string(),
                "open:1".to_string(),
                "stage_video:24".to_string(),
                "stage_audio:mic:2".to_string(),
            ],
            "staging must sit between open_segment and the first packet, and repeat per segment"
        );

        // Empty extradata (mock path): no staging calls at all.
        let log_empty = Arc::new(Mutex::new(Vec::<String>::new()));
        let mut driver_empty = MuxDriver::new(
            Box::new(RecordingMuxer::new(log_empty.clone())),
            vec![],
            300,
            Arc::new(EncoderControl::new()),
            stats,
            SegmentExtradata::default(),
        );
        driver_empty.ensure_open(0, "take_x", 0.0, &mut timeline, &events).unwrap();
        drop(driver_empty);
        assert_eq!(*log_empty.lock().unwrap(), vec!["open:0".to_string()]);

        let warnings: Vec<String> = events
            .lock()
            .unwrap()
            .drain(..)
            .filter_map(|ev| match ev {
                EngineEvent::Warning { message } => Some(message),
                _ => None,
            })
            .collect();
        assert!(
            warnings.iter().all(|m| !m.starts_with("EXTRADATA_STAGE_FAILED")),
            "handshake must not warn: {warnings:?}"
        );
        let _ = std::fs::remove_dir_all(temp_root("extradata_handshake"));
    }
}

