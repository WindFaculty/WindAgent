//! Audio capture — event-driven WASAPI, one track per source.
//! Gate: LIVE_RECORD_V2_CONTRACT_FROZEN (ban_ke_hoach_v1.md §10, §11)
//!
//! ```text
//! Mic:     IMMDeviceEnumerator → capture endpoint → IAudioClient → IAudioCaptureClient
//! System:  IMMDeviceEnumerator → render  endpoint → IAudioClient(+LOOPBACK flag)
//! ```
//!
//! Both run as separate event-driven clients (no busy polling); their blocks
//! become **separate MKV tracks** — never mixed pre-record (Principle E).
//! UI mute must act here, at the recorder, not only on frontend meters.

pub mod aac;
pub mod device;
pub mod loopback;
pub mod microphone;

/// QPC helpers shared with every track live in [`crate::clock`] (the single
/// media-clock authority); this alias keeps call sites readable.
pub use crate::clock;

use serde::{Deserialize, Serialize};

/// One interleaved PCM block delivered by an event-driven WASAPI client.
#[derive(Debug, Clone)]
pub struct PcmBlock {
    /// Interleaved f32 samples (`frames * channels`).
    pub samples: Vec<f32>,
    pub channels: u32,
    /// Device mix-format rate (shared mode is typically 48 kHz float).
    pub sample_rate: u32,
    /// QPC timestamp of the first frame in this block (clock authority).
    pub qpc: u64,
}

impl PcmBlock {
    pub fn frames(&self) -> usize {
        if self.channels == 0 { 0 } else { self.samples.len() / self.channels as usize }
    }
}

/// One encoded AAC packet ready for the muxer.
#[derive(Debug, Clone)]
pub struct EncodedAudioPacket {
    pub track: TrackKind,
    pub data: Vec<u8>,
    /// Presentation time in microseconds since take start (QPC-derived).
    pub pts_us: u64,
    /// PCM frames consumed to produce this packet (drift accounting).
    pub sample_count: u64,
    pub sample_rate: u32,
    pub channels: u32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TrackKind {
    Mic,
    System,
}

impl From<TrackKind> for crate::muxer::TrackId {
    fn from(k: TrackKind) -> Self {
        match k {
            TrackKind::Mic => Self::Mic,
            TrackKind::System => Self::System,
        }
    }
}

/// Device format reported after a successful probe/prepare (preflight uses it).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AudioDeviceInfo {
    pub available: bool,
    pub endpoint_name: String,
    pub device_id: String,
    pub channels: u32,
    pub sample_rate: u32,
    pub is_float: bool,
}

impl Default for AudioDeviceInfo {
    fn default() -> Self {
        Self {
            available: false,
            endpoint_name: String::new(),
            device_id: String::new(),
            channels: 0,
            sample_rate: 0,
            is_float: false,
        }
    }
}

/// Abstract audio capture port — implemented by [`microphone::WasapiMicrophone`]
/// and [`loopback::WasapiLoopback`] with identical lifecycle semantics.
///
/// Implementations MUST be event-driven internally (`AUDCLNT_SHAREMODE_SHARED`
/// + `SetEventHandle`); `poll_block` drains one queued block per call.
pub trait AudioCapturePort: Send {
    /// Resolve endpoint + initialize the client; returns the negotiated format.
    fn prepare(&mut self, device_id: &str) -> Result<AudioDeviceInfo, String>;
    fn start(&mut self) -> Result<(), String>;
    fn stop(&mut self) -> Result<(), String>;
    /// Drain one buffered PCM block, if any. Never busy-waits.
    fn poll_block(&mut self) -> Option<PcmBlock>;
    /// Recorder-level mute: enabled tracks keep running but deliver silence so
    /// PTS continuity survives mute toggles mid-take.
    fn set_muted(&mut self, muted: bool);
    fn is_available(&self) -> bool;
    fn track(&self) -> TrackKind;
}

// ─── Mock (dev/CI simulation only) ─────────────────────────────────────────

pub struct MockAudioCapture {
    track: TrackKind,
    started: bool,
    muted: bool,
    t: u64,
    last_emit: Option<std::time::Instant>,
}

impl MockAudioCapture {
    pub fn new(track: TrackKind) -> Self {
        Self { track, started: false, muted: false, t: 0, last_emit: None }
    }
}

impl AudioCapturePort for MockAudioCapture {
    fn prepare(&mut self, _device_id: &str) -> Result<AudioDeviceInfo, String> {
        Ok(AudioDeviceInfo {
            available: true,
            endpoint_name: "mock".into(),
            device_id: "mock".into(),
            channels: 2,
            sample_rate: 48_000,
            is_float: true,
        })
    }

    fn start(&mut self) -> Result<(), String> {
        self.started = true;
        Ok(())
    }

    fn stop(&mut self) -> Result<(), String> {
        self.started = false;
        Ok(())
    }

    fn poll_block(&mut self) -> Option<PcmBlock> {
        if !self.started {
            return None;
        }
        // Pace to a real ~20 ms block cadence so consumers can drain at
        // their own rhythm without spinning hot.
        const BLOCK_MS: u128 = 20;
        let now = std::time::Instant::now();
        match self.last_emit {
            Some(last) if now.duration_since(last).as_millis() < BLOCK_MS => return None,
            _ => self.last_emit = Some(now),
        }
        let frames = 960usize;
        let mut s = Vec::with_capacity(frames * 2);
        for n in 0..frames * 2 {
            let v = if self.muted { 0.0f32 } else { ((self.t + n as u64) % 4800) as f32 / 4800.0 - 0.5 };
            s.push(v * 0.1);
        }
        let block = PcmBlock { samples: s, channels: 2, sample_rate: 48_000, qpc: crate::clock::qpc_now() };
        self.t += frames as u64;
        Some(block)
    }

    fn set_muted(&mut self, muted: bool) {
        self.muted = muted;
    }

    fn is_available(&self) -> bool {
        true
    }

    fn track(&self) -> TrackKind {
        self.track
    }
}
