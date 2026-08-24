//! RecorderService — the sidecar's request dispatcher (Phase 8/9).
//!
//! Owns one recording session end-to-end: state machine, real ffmpeg
//! processes when the host supports them, a gated mock simulation otherwise,
//! and the crash-safe on-disk timeline. `bin/recorder.rs` feeds it stdin
//! requests and forwards every returned event to stdout as JSONL.

use std::path::PathBuf;
use std::time::Instant;

use crate::capture::ffmpeg_capture::{FfmpegCaptureConfig, FfmpegSegmentCapture};
use crate::ipc::{
    EngineCapabilities, EngineEvent, EngineRequest, EngineResponse, MarkerRequest, PrepareRequest,
    StartRequest,
};
use crate::preview::ffmpeg_preview::FfmpegPreview;
use crate::probe;
use crate::segment::{Segmenter, TimelineEvent};
use crate::segment::timeline_writer::{write_manifest, TimelineWriter};
use crate::telemetry::Telemetry;
use crate::EngineProfile;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServiceState {
    Idle,
    Prepared,
    Recording,
    Paused,
    Stopped,
}

impl ServiceState {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Idle => "IDLE",
            Self::Prepared => "PREPARED",
            Self::Recording => "RECORDING",
            Self::Paused => "PAUSED",
            Self::Stopped => "STOPPED",
        }
    }
}

/// Mock simulation is opt-in via env at construction — production never
/// silently fakes a take. Tests flip the public flag directly instead of the
/// environment (process-wide env races across parallel tests).
fn mock_allowed() -> bool {
    std::env::var("WINDAGENT_RECORDER_ALLOW_MOCK")
        .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
        .unwrap_or(false)
}

/// Capability probe — injectable so tests can freeze a deterministic
/// environment instead of re-detecting the host's real ffmpeg.
type ProbeFn = Box<dyn Fn(Option<&std::path::Path>) -> EngineCapabilities + Send>;

pub struct RecorderService {
    pub caps: EngineCapabilities,
    /// Dev/CI-only simulation mode; see [`mock_allowed`].
    pub allow_mock: bool,
    probe: ProbeFn,
    state: ServiceState,
    profile: Option<EngineProfile>,
    prepare: Option<PrepareRequest>,
    take_id: Option<String>,
    started_at: Option<Instant>,
    paused_at: Option<Instant>,
    paused_total_ms: u64,

    capture: Option<FfmpegSegmentCapture>,
    preview: Option<FfmpegPreview>,
    timeline: Option<TimelineWriter>,
    segmenter: Segmenter,
    telemetry: Telemetry,
    reported_segments: u32,
    last_status_ms: u64,
    take_dir: Option<PathBuf>,
}

impl RecorderService {
    pub fn new() -> Self {
        Self {
            caps: EngineCapabilities::default(),
            allow_mock: mock_allowed(),
            probe: Box::new(probe::probe_capabilities),
            state: ServiceState::Idle,
            profile: None,
            prepare: None,
            take_id: None,
            started_at: None,
            paused_at: None,
            paused_total_ms: 0,
            capture: None,
            preview: None,
            timeline: None,
            segmenter: Segmenter::new(5),
            telemetry: Telemetry::default(),
            reported_segments: 0,
            last_status_ms: 0,
            take_dir: None,
        }
    }

    /// Fresh probe — used by the `capabilities` request.
    pub fn refresh_capabilities(&mut self, output_dir: Option<&std::path::Path>) {
        self.caps = (self.probe)(output_dir);
    }

    fn now_ms(&self) -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0)
    }

    fn elapsed_sec(&self) -> f64 {
        let Some(started) = self.started_at else {
            return 0.0;
        };
        let live_paused = match (self.paused_at, self.state) {
            (Some(paused), ServiceState::Paused) => {
                paused.elapsed().as_millis() as u64
            }
            _ => 0,
        };
        let total_ms =
            started.elapsed().as_millis() as u64 - live_paused - self.paused_total_ms;
        total_ms as f64 / 1000.0
    }

    fn timeline_t(&self) -> f64 {
        // Monotonic by construction: elapsed only ever grows within a take.
        self.elapsed_sec()
    }

    fn nvenc_status(&self) -> &'static str {
        match &self.capture {
            Some(cap) if cap.is_running() => {
                if cap.nvenc_confirmed() {
                    "ENCODING"
                } else {
                    "IDLE"
                }
            }
            Some(_) => "ERROR",
            None => match self.caps.engine_available {
                true => "IDLE",
                false => "UNAVAILABLE",
            },
        }
    }

    fn status_event(&self) -> EngineEvent {
        let frames_captured = self
            .capture
            .as_ref()
            .map(|c| c.frames_seen())
            .unwrap_or_else(|| {
                if self.caps.engine_available {
                    0
                } else {
                    (self.elapsed_sec() * self.profile_fallback_fps()) as u64
                }
            });
        EngineEvent::Status {
            state: self.state.as_str().into(),
            elapsed_sec: self.elapsed_sec(),
            frames_captured,
            frames_encoded: frames_captured,
            frames_dropped: 0,
            dropped_pct: 0.0,
            bitrate_mbps: self.bitrate_estimate_mbps(),
            nvenc_status: Some(self.nvenc_status().into()),
        }
    }

    fn profile_fallback_fps(&self) -> f64 {
        self.profile.as_ref().map(|p| p.fps).unwrap_or(60) as f64
    }

    fn bitrate_estimate_mbps(&self) -> f64 {
        let Some(profile) = &self.profile else {
            return 0.0;
        };
        let bitrate = FfmpegCaptureConfig::default_bitrate(profile.resolution, profile.fps);
        let trimmed = bitrate.trim_end_matches(['M', 'm']);
        trimmed.parse::<f64>().unwrap_or(0.0)
    }

    fn push_timeline(
        &mut self,
        event_type: &str,
        detail: &str,
        extra: impl FnOnce(&mut TimelineEvent),
    ) -> Vec<EngineEvent> {
        let mut event = TimelineEvent {
            t: self.timeline_t(),
            event_type: event_type.into(),
            scene_id: None,
            cue_id: None,
            action_id: None,
            execution_id: None,
            marker_type: None,
            detail: detail.into(),
        };
        extra(&mut event);
        if let Some(writer) = self.timeline.as_mut() {
            if let Err(e) = writer.append(&event) {
                return vec![EngineEvent::Error { message: e }];
            }
        }
        self.segmenter.push_timeline(event.clone());
        vec![EngineEvent::Timeline {
            take_id: self.take_id.clone().unwrap_or_default(),
            event_type: event.event_type,
            t: event.t,
        }]
    }

    // ── Operation handlers ────────────────────────────────────────────────

    pub fn handle(&mut self, req: EngineRequest) -> (EngineResponse, Vec<EngineEvent>) {
        let op = req.op_name();
        match req {
            EngineRequest::Capabilities => {
                let dir = self.take_dir.clone();
                self.refresh_capabilities(dir.as_deref());
                (
                    EngineResponse::ok(op, serde_json::to_value(&self.caps).unwrap_or_default()),
                    vec![],
                )
            }
            EngineRequest::Prepare(prepare) => self.prepare(prepare),
            EngineRequest::Start(start) => self.start(start),
            EngineRequest::Pause => self.pause(),
            EngineRequest::Resume => self.resume(),
            EngineRequest::Stop => self.stop(),
            EngineRequest::Status => (
                EngineResponse::ok(op, serde_json::to_value(self.status_event()).unwrap_or_default()),
                vec![],
            ),
            EngineRequest::Marker(marker) => self.marker(marker),
        }
    }

    fn prepare(&mut self, prepare: PrepareRequest) -> (EngineResponse, Vec<EngineEvent>) {
        if self.state != ServiceState::Idle && self.state != ServiceState::Stopped {
            return self.err("prepare", "ENGINE_ALREADY_PREPARED", format!("state={}", self.state.as_str()));
        }
        let dir = PathBuf::from(&prepare.output_dir);
        if dir.as_os_str().is_empty() {
            return self.err("prepare", "ENGINE_PREPARE_REJECTED", "output_dir required");
        }
        if let Err(e) = prepare.profile.validate() {
            return self.err("prepare", "ENGINE_PROFILE_REJECTED", e);
        }

        self.refresh_capabilities(Some(&dir));
        let usable = self.caps.engine_available || self.allow_mock;
        if !usable {
            return EngineResponse::ok(
                "prepare",
                serde_json::json!({
                    "prepared": false,
                    "backend": self.caps.backend,
                    "blockers": self.caps.blockers,
                }),
            ).with_events(vec![EngineEvent::Error {
                message: format!(
                    "ENGINE_UNAVAILABLE: {}",
                    self.caps.blockers.join(", ")
                ),
            }]);
        }
        if std::fs::create_dir_all(&dir).is_err() {
            return self.err("prepare", "ENGINE_OUTPUT_DIR_FAILED", "cannot create output_dir");
        }

        let segment_seconds = prepare.profile.segment_minutes as u64 * 60;
        self.segmenter = Segmenter::new(prepare.profile.segment_minutes);
        self.profile = Some(prepare.profile.clone());
        self.prepare = Some(prepare);
        self.telemetry = Telemetry::default();
        self.reported_segments = 0;
        self.state = ServiceState::Prepared;

        EngineResponse::ok(
            "prepare",
            serde_json::json!({
                "prepared": true,
                "backend": self.caps.backend,
                "segment_seconds": segment_seconds,
                "blockers": [],
            }),
        )
        .with_events(vec![])
    }

    fn start(&mut self, start: StartRequest) -> (EngineResponse, Vec<EngineEvent>) {
        if self.state != ServiceState::Prepared {
            return self.err(
                "start",
                "ENGINE_NOT_PREPARED",
                format!("state={}", self.state.as_str()),
            );
        }
        let prepare = match &self.prepare {
            Some(p) => p.clone(),
            None => return self.err("start", "ENGINE_NOT_PREPARED", "no prepared session"),
        };

        // The IPC mirror types `take_id` as String; empty means "generate".
        let take_id = if start.take_id.is_empty() {
            format!("take_{}", self.now_ms())
        } else {
            start.take_id.clone()
        };
        self.take_id = Some(take_id.clone());
        let take_dir = PathBuf::from(&prepare.output_dir);

        match TimelineWriter::create(&take_dir) {
            Ok(w) => self.timeline = Some(w),
            Err(e) => return self.err("start", "TIMELINE_CREATE_FAILED", e),
        }
        self.take_dir = Some(take_dir.clone());
        self.started_at = Some(Instant::now());
        self.paused_total_ms = 0;
        self.paused_at = None;
        self.segmenter.start_take(&take_id, self.now_ms());

        let mut events = Vec::new();
        if self.caps.engine_available {
            let ffmpeg_path = PathBuf::from(
                self.caps.ffmpeg_path.clone().unwrap_or_else(|| "ffmpeg".into()),
            );
            let codec = if self.caps.nvenc_h264_available {
                "H264"
            } else {
                "HEVC"
            };
            let config = FfmpegCaptureConfig {
                ffmpeg_path,
                fps: prepare.profile.fps,
                codec: codec.into(),
                resolution: prepare.profile.resolution,
                segment_seconds: prepare.profile.segment_minutes as u64 * 60,
                bitrate: FfmpegCaptureConfig::default_bitrate(
                    prepare.profile.resolution,
                    prepare.profile.fps,
                ),
                output_dir: take_dir.clone(),
            };
            let mut capture = FfmpegSegmentCapture::new(config);
            if let Err(e) = capture.start(0) {
                self.timeline = None;
                return self.err("start", "FFMPEG_CAPTURE_FAILED", e);
            }
            events.push(EngineEvent::Warning {
                message: "NVENC_CONFIRMATION_PENDING".into(),
            });

            let preview_path = PathBuf::from(
                self.caps.ffmpeg_path.clone().unwrap_or_else(|| "ffmpeg".into()),
            );
            let preview_size = (1280u32, 720u32);
            match FfmpegPreview::spawn(&preview_path, 2.min(prepare.profile.fps), preview_size)
            {
                Ok(preview) => self.preview = Some(preview),
                Err(e) => events.push(EngineEvent::Warning {
                    message: format!("PREVIEW_DEGRADED: {e}"),
                }),
            }
            self.capture = Some(capture);
        } else {
            events.push(EngineEvent::Warning {
                message: "MOCK_PIPELINE_ACTIVE: no real capture backend".into(),
            });
        }

        events.splice(
            0..0,
            self.push_timeline("SESSION_START", "take started", |e| {
                e.execution_id = Some(take_id.clone());
            }),
        );
        self.state = ServiceState::Recording;
        (
            EngineResponse::ok(
                "start",
                serde_json::json!({
                    "take_id": take_id,
                    "backend": self.caps.backend,
                }),
            ),
            events,
        )
    }

    fn pause(&mut self) -> (EngineResponse, Vec<EngineEvent>) {
        if self.state != ServiceState::Recording {
            return self.err("pause", "ENGINE_NOT_RECORDING", format!("state={}", self.state.as_str()));
        }
        let mut events = self.finalize_open_segments();
        if let Some(mut preview) = self.preview.take() {
            preview.shutdown();
        }
        if let Some(mut capture) = self.capture.take() {
            if let Err(e) = capture.shutdown() {
                events.push(EngineEvent::Error { message: e });
            }
        }
        self.paused_at = Some(Instant::now());
        self.state = ServiceState::Paused;
        events.push(self.status_event());
        (EngineResponse::ok("pause", serde_json::json!({"paused": true})), events)
    }

    fn resume(&mut self) -> (EngineResponse, Vec<EngineEvent>) {
        if self.state != ServiceState::Paused {
            return self.err("resume", "ENGINE_NOT_PAUSED", format!("state={}", self.state.as_str()));
        }
        if let Some(paused_at) = self.paused_at.take() {
            self.paused_total_ms += paused_at.elapsed().as_millis() as u64;
        }

        let mut events = Vec::new();
        if self.caps.engine_available {
            let continue_number = self
                .take_dir
                .as_deref()
                .map(crate::capture::ffmpeg_capture::scan_segment_files)
                .unwrap_or_default()
                .len() as u32;

            let prepare = self.prepare.clone().unwrap_or_else(|| PrepareRequest {
                execution_plan_id: String::new(),
                execution_plan_hash: String::new(),
                episode_id: String::new(),
                output_dir: String::new(),
                profile: EngineProfile::default(),
            });
            let ffmpeg_path = PathBuf::from(
                self.caps.ffmpeg_path.clone().unwrap_or_else(|| "ffmpeg".into()),
            );
            let codec = if self.caps.nvenc_h264_available { "H264" } else { "HEVC" };
            let config = FfmpegCaptureConfig {
                ffmpeg_path,
                fps: prepare.profile.fps,
                codec: codec.into(),
                resolution: prepare.profile.resolution,
                segment_seconds: prepare.profile.segment_minutes as u64 * 60,
                bitrate: FfmpegCaptureConfig::default_bitrate(
                    prepare.profile.resolution,
                    prepare.profile.fps,
                ),
                output_dir: self.take_dir.clone().unwrap_or_default(),
            };
            let mut capture = FfmpegSegmentCapture::new(config);
            if let Err(e) = capture.start(continue_number) {
                return self.err("resume", "FFMPEG_RESUME_FAILED", e);
            }
            self.capture = Some(capture);

            let preview_path = PathBuf::from(
                self.caps.ffmpeg_path.clone().unwrap_or_else(|| "ffmpeg".into()),
            );
            if let Ok(preview) = FfmpegPreview::spawn(&preview_path, 2, (1280, 720)) {
                self.preview = Some(preview);
            }
            events.push(EngineEvent::Warning {
                message: format!("RESUMED_AT_SEGMENT_{continue_number}"),
            });
        }
        self.state = ServiceState::Recording;
        events.push(self.status_event());
        (
            EngineResponse::ok("resume", serde_json::json!({"resumed": true})),
            events,
        )
    }

    fn stop(&mut self) -> (EngineResponse, Vec<EngineEvent>) {
        if self.state != ServiceState::Recording && self.state != ServiceState::Paused {
            return self.err("stop", "ENGINE_NOT_ACTIVE", format!("state={}", self.state.as_str()));
        }
        if self.state == ServiceState::Paused {
            if let Some(paused_at) = self.paused_at.take() {
                self.paused_total_ms += paused_at.elapsed().as_millis() as u64;
            }
        }
        let mut events = self.finalize_open_segments();
        if let Some(mut preview) = self.preview.take() {
            preview.shutdown();
        }
        if let Some(mut capture) = self.capture.take() {
            if let Err(e) = capture.shutdown() {
                events.push(EngineEvent::Error { message: e });
            }
        }

        events.extend(self.push_timeline("SESSION_END", "take stopped", |_| {}));
        let manifest = self.manifest_now();
        if let Some(dir) = &self.take_dir {
            if let Err(e) = write_manifest(dir, &manifest) {
                events.push(EngineEvent::Error { message: e });
            }
        }
        self.state = ServiceState::Stopped;
        events.push(self.status_event());
        (
            EngineResponse::ok(
                "stop",
                serde_json::json!({
                    "take_id": self.take_id.clone().unwrap_or_default(),
                    "segments": manifest.segments.len(),
                    "manifest_ref": manifest.timeline_ref,
                }),
            ),
            events,
        )
    }

    fn marker(&mut self, marker: MarkerRequest) -> (EngineResponse, Vec<EngineEvent>) {
        if self.state != ServiceState::Recording && self.state != ServiceState::Paused {
            return self.err(
                "marker",
                "RECORDER_MARKER_REJECTED",
                format!(
                    "markers require RECORDING/PAUSED, current {}",
                    self.state.as_str()
                ),
            );
        }
        if marker.marker_type.is_empty() {
            return self.err("marker", "RECORDER_MARKER_REJECTED", "marker_type required");
        }
        let marker_type = marker.marker_type.clone();
        let events = self.push_timeline("MARKER", "operator/director marker", |e| {
            e.marker_type = Some(marker_type.clone());
            e.cue_id = marker.cue_id.clone();
            e.action_id = marker.action_id.clone();
        });
        (
            EngineResponse::ok("marker", serde_json::json!({"ack": true})),
            events,
        )
    }

    // ── Background work between requests ─────────────────────────────────

    /// Called from the main loop ~every 250 ms while the sidecar lives.
    pub fn tick(&mut self) -> Vec<EngineEvent> {
        if self.state != ServiceState::Recording {
            return vec![];
        }
        let mut events = Vec::new();

        // Unexpected process death → loud error, never silent stall.
        let capture_dead = self
            .capture
            .as_ref()
            .map(|c| !c.is_running())
            .unwrap_or(false);
        if capture_dead && self.caps.engine_available {
            let tail = self.capture.as_ref().map(|c| c.stderr_tail()).unwrap_or_default();
            events.push(EngineEvent::Error {
                message: format!("FFMPEG_EXITED_UNEXPECTEDLY: {}", tail.lines().last().unwrap_or("")),
            });
            if let Some(mut capture) = self.capture.take() {
                capture.kill();
            }
            if let Some(mut preview) = self.preview.take() {
                preview.shutdown();
            }
            self.state = ServiceState::Stopped;
            events.push(self.status_event());
            return events;
        }

        // New completed segments on disk.
        events.extend(self.finalize_open_segments());

        // Preview frames (≤2 FPS, JPEG base64).
        let take_id = self.take_id.clone().unwrap_or_default();
        let now_stamp = self.now_ms();
        if let Some(preview) = self.preview.as_mut() {
            while let Some(frame) = preview.try_poll_frame() {
                events.push(EngineEvent::Preview {
                    take_id: take_id.clone(),
                    width: preview.size.0,
                    height: preview.size.1,
                    data_len: frame.data_len,
                    timestamp_ms: now_stamp,
                    jpeg_base64: frame.jpeg_base64,
                });
            }
        }

        // Status heartbeat at ~1 Hz.
        let now = self.now_ms();
        if now.saturating_sub(self.last_status_ms) >= 1000 {
            self.last_status_ms = now;
            events.push(self.status_event());
        }
        events
    }

    /// Announce every on-disk segment that has not been reported yet.
    fn finalize_open_segments(&mut self) -> Vec<EngineEvent> {
        let take_id = self.take_id.clone().unwrap_or_default();
        let files = self
            .take_dir
            .as_deref()
            .map(crate::capture::ffmpeg_capture::scan_segment_files)
            .unwrap_or_default();

        let mut events = Vec::new();
        for (index, path) in files {
            if index < self.reported_segments {
                continue;
            }
            self.reported_segments = index + 1;
            let size_bytes = std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
            let playable = size_bytes > 0;
            let t_now = self.timeline_t();
            let now_ms = self.now_ms();
            let info = self.segmenter.roll_segment(&take_id, now_ms);
            if let Some(writer) = self.timeline.as_mut() {
                let _ = writer.append(&TimelineEvent {
                    t: t_now,
                    event_type: "SEGMENT_END".into(),
                    scene_id: None,
                    cue_id: None,
                    action_id: None,
                    execution_id: None,
                    marker_type: None,
                    detail: format!(
                        "segment {} finalized ({} bytes)",
                        index, size_bytes
                    ),
                });
            }
            let _ = info; // segmenter bookkeeping only; tokens come from the scan
            events.push(EngineEvent::Segment {
                take_id: take_id.clone(),
                segment_index: index,
                file_token: format!("{take_id}/segment_{index:04}.mkv"),
                is_playable: playable,
            });
        }
        events
    }

    fn manifest_now(&self) -> crate::SegmentManifest {
        let take_id = self.take_id.clone().unwrap_or_default();
        let plan_id = self
            .prepare
            .as_ref()
            .map(|p| p.execution_plan_id.clone())
            .unwrap_or_default();
        self.segmenter.manifest(&take_id, &plan_id)
    }

    fn err(&self, op: &str, code: &str, message: impl Into<String>) -> (EngineResponse, Vec<EngineEvent>) {
        (
            EngineResponse::err(op, code, message),
            vec![],
        )
    }
}

impl Default for RecorderService {
    fn default() -> Self {
        Self::new()
    }
}

trait ResponseExt {
    fn with_events(self, events: Vec<EngineEvent>) -> (EngineResponse, Vec<EngineEvent>);
}

impl ResponseExt for EngineResponse {
    fn with_events(self, events: Vec<EngineEvent>) -> (EngineResponse, Vec<EngineEvent>) {
        (self, events)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn service_with_caps(engine_available: bool) -> RecorderService {
        let mut svc = RecorderService::new();
        let caps = EngineCapabilities {
            engine_available,
            backend: if engine_available {
                "ffmpeg-ddagrab-nvenc".into()
            } else {
                "mock".into()
            },
            ffmpeg_path: None,
            ffmpeg_version: None,
            ddagrab_available: engine_available,
            nvenc_h264_available: engine_available,
            nvenc_hevc_available: false,
            disk_free_gb: 10.0,
            output_writable: true,
            blockers: vec![],
        };
        svc.caps = caps.clone();
        // Freeze the injected environment — `prepare` must not silently
        // re-detect a real ffmpeg on hosts where one happens to be installed.
        svc.probe = Box::new(move |_| caps.clone());
        svc
    }

    fn prepare_request(output_dir: &str) -> PrepareRequest {
        PrepareRequest {
            execution_plan_id: "plan_1".into(),
            execution_plan_hash: "a".repeat(64),
            episode_id: "ep_1".into(),
            output_dir: output_dir.into(),
            profile: EngineProfile::default(),
        }
    }

    #[test]
    fn start_before_prepare_is_rejected() {
        let mut svc = service_with_caps(false);
        let (resp, _) = svc.handle(EngineRequest::Start(StartRequest {
            execution_plan_id: "plan_1".into(),
            take_id: "take_x".into(),
        }));
        match resp {
            EngineResponse::Err { code, .. } => assert_eq!(code, "ENGINE_NOT_PREPARED"),
            other => panic!("expected err, got {other:?}"),
        }
    }

    #[test]
    fn audio_profile_rejected_fail_closed() {
        let dir = std::env::temp_dir();
        let mut req = prepare_request(dir.to_string_lossy().as_ref());
        req.profile.audio_enabled = true;
        let mut svc = service_with_caps(true);
        let (resp, _) = svc.handle(EngineRequest::Prepare(req));
        match resp {
            EngineResponse::Err { code, .. } => assert_eq!(code, "ENGINE_PROFILE_REJECTED"),
            other => panic!("expected err, got {other:?}"),
        }
    }

    #[test]
    fn unavailable_backend_without_mock_flag_reports_blockers() {
        let dir = std::env::temp_dir().join(format!(
            "windagent_svc_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let mut svc = service_with_caps(false);
        let (resp, events) = svc.handle(EngineRequest::Prepare(prepare_request(
            dir.to_string_lossy().as_ref(),
        )));
        // Payload says prepared=false with the mock backend…
        match resp {
            EngineResponse::Ok { payload, .. } => {
                assert_eq!(payload["prepared"], false);
                assert_eq!(payload["backend"], "mock");
            }
            other => panic!("expected ok, got {other:?}"),
        }
        // …and the engine surfaces why.
        assert!(events
            .iter()
            .any(|e| matches!(e, EngineEvent::Error { message } if message.contains("ENGINE_UNAVAILABLE"))));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn mock_pipeline_full_lifecycle_writes_real_timeline() {
        let dir = std::env::temp_dir().join(format!(
            "windagent_svc_mock_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let mut svc = service_with_caps(false);
        svc.allow_mock = true; // dev/CI simulation, no env races
        let (prep, _) = svc.handle(EngineRequest::Prepare(prepare_request(
            dir.to_string_lossy().as_ref(),
        )));
        assert!(matches!(prep, EngineResponse::Ok { .. }), "{prep:?}");

        let (start, events) = svc.handle(EngineRequest::Start(StartRequest {
            execution_plan_id: "plan_1".into(),
            take_id: "take_mock1".into(),
        }));
        match start {
            EngineResponse::Ok { payload, .. } => {
                assert_eq!(payload["take_id"], "take_mock1");
            }
            other => panic!("expected ok, got {other:?}"),
        }
        assert_eq!(svc.state, ServiceState::Recording);
        assert!(events.iter().any(
            |e| matches!(e, EngineEvent::Timeline { event_type, .. } if event_type == "SESSION_START")
        ));

        let (marker, _) = svc.handle(EngineRequest::Marker(MarkerRequest {
            marker_type: "SCENE_CUT".into(),
            cue_id: Some("cue_2".into()),
            action_id: None,
        }));
        assert!(matches!(marker, EngineResponse::Ok { .. }));

        // Pause/resume round-trip keeps the machine coherent.
        let (pause, _) = svc.handle(EngineRequest::Pause);
        assert!(matches!(pause, EngineResponse::Ok { .. }));
        assert_eq!(svc.state, ServiceState::Paused);
        let (resume, _) = svc.handle(EngineRequest::Resume);
        assert!(matches!(resume, EngineResponse::Ok { .. }));

        let (stop, events) = svc.handle(EngineRequest::Stop);
        assert!(matches!(stop, EngineResponse::Ok { .. }), "{stop:?}");
        assert!(events.iter().any(
            |e| matches!(e, EngineEvent::Timeline { event_type, .. } if event_type == "SESSION_END")
        ));

        let timeline = std::fs::read_to_string(dir.join("timeline.jsonl")).unwrap();
        let types: Vec<String> = timeline
            .lines()
            .filter_map(|l| serde_json::from_str::<serde_json::Value>(l).ok())
            .filter_map(|v| v["type"].as_str().map(str::to_owned))
            .collect();
        assert_eq!(types.first().map(String::as_str), Some("SESSION_START"));
        assert_eq!(types.last().map(String::as_str), Some("SESSION_END"));
        assert!(types.iter().any(|t| t == "MARKER"));

        let manifest_text = std::fs::read_to_string(dir.join("manifest.json")).unwrap();
        let manifest: serde_json::Value = serde_json::from_str(&manifest_text).unwrap();
        assert_eq!(manifest["take_id"], "take_mock1");

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn timeline_is_monotonic_across_markers_and_segments() {
        let mut svc = service_with_caps(false);
        svc.take_id = Some("take_mono".into());
        svc.started_at = Some(Instant::now() - std::time::Duration::from_secs(3));
        svc.push_timeline("A", "", |_| {});
        svc.push_timeline("B", "", |_| {});
        let ts: Vec<f64> = svc.segmenter.timeline.iter().map(|e| e.t).collect();
        assert!(ts.windows(2).all(|w| w[1] >= w[0]), "monotonic: {ts:?}");
    }
}
