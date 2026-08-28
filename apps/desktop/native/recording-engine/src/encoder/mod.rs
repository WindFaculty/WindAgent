//! Encoder — direct NVENC (H.264/HEVC), zero-copy GPU input.
//! Gate: LIVE_RECORD_V2_CONTRACT_FROZEN (ban_ke_hoach_v1.md §8)
//!
//! ```text
//! ID3D11Texture2D → NvEncRegisterResource → NvEncMapInputResource
//!                 → NvEncEncodePicture   → NvEncLockBitstream → EncodedPacket
//! ```
//!
//! Principle C (fail-closed): when the NVIDIA driver or NVENC API is missing
//! the encoder reports [`NVENC_UNAVAILABLE`] and recording is blocked. There
//! is no x264/software fallback in production.
//!
//! `nvenc_api` holds the hand-written FFI surface for `nvEncodeAPI.dll`
//! (loaded at runtime from the driver store); `nvenc_session` owns one
//! encoding session's lifecycle. Both are Windows-only.

pub mod nvenc_api;
pub mod nvenc_encoder;
pub mod nvenc_session;

use serde::{Deserialize, Serialize};

/// Fail-closed error code surfaced to preflight when NVENC cannot start.
pub const NVENC_UNAVAILABLE: &str = "NVENC_UNAVAILABLE: direct NVENC not available";

/// One encoded bitstream packet (Annex-B). Bytes are real; PTS/DTS derive
/// from the QPC clock authority in microseconds since take start.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncodedPacket {
    pub pts_us: u64,
    pub dts_us: i64,
    pub is_keyframe: bool,
    pub data: Vec<u8>,
    pub codec: String,
}

/// Quality-first encoder settings — mirrors profile.video, translated to
/// NVENC parameters inside [`nvenc_session`].
#[derive(Debug, Clone, PartialEq)]
pub struct NvencConfig {
    pub codec: Codec,
    pub width: u32,
    pub height: u32,
    pub fps: u32,
    /// CQP quantization parameter (lower = better quality).
    pub cq: i32,
    pub preset: Preset,
    pub multipass: Multipass,
    pub lookahead: u32,
    pub spatial_aq: bool,
    pub temporal_aq: bool,
    pub b_frames: u32,
    pub gop_frames: u32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Codec {
    H264,
    Hevc,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Preset {
    P5,
    P6,
    P7,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Multipass {
    Disabled,
    HalfRes,
    FullRes,
}

impl NvencConfig {
    /// Translate a validated V2 profile into encoder settings.
    pub fn from_profile(profile: &crate::EngineProfile) -> Self {
        let v = &profile.video;
        Self {
            codec: match v.codec.as_str() {
                "HEVC" => Codec::Hevc,
                _ => Codec::H264,
            },
            width: v.width,
            height: v.height,
            fps: v.fps,
            cq: v.cq,
            preset: match v.preset.as_str() {
                "P5" => Preset::P5,
                "P6" => Preset::P6,
                _ => Preset::P7,
            },
            multipass: match v.multipass.as_str() {
                "DISABLED" => Multipass::Disabled,
                "HALF_RES" => Multipass::HalfRes,
                _ => Multipass::FullRes,
            },
            lookahead: v.lookahead,
            spatial_aq: v.spatial_aq,
            temporal_aq: v.temporal_aq,
            b_frames: v.b_frames,
            gop_frames: v.gop_frames,
        }
    }
}

/// Abstract encoder port. `encode_frame` consumes a captured GPU texture and
/// returns zero or more packets (B-frame reordering emits packets whose DTS
/// lags their PTS; the muxer routes by PTS so ordering stays correct).
///
/// Presentation time is supplied by the caller as take-relative,
/// pause-compensated `pts_us` (§12 single-clock rule — the TakeClock is the
/// only authority; encoders never derive timestamps from raw QPC themselves).
pub trait EncoderPort: Send {
    fn prepare(&mut self) -> Result<(), String>;
    fn encode_frame(&mut self, frame: &mut crate::capture::CapturedFrame, pts_us: u64) -> Result<Vec<EncodedPacket>, String>;
    fn flush(&mut self) -> Result<Vec<EncodedPacket>, String>;
    fn request_idr(&mut self);
    /// Annex-B parameter sets (SPS/PPS, +VPS for HEVC) captured at session
    /// init — the avcC/hvcC source for the MKV extradata handshake (§9).
    /// `None` = backend carries none (mock simulation).
    fn sequence_header(&self) -> Option<Vec<u8>> {
        None
    }
    fn encode_latency_ms_p50(&self) -> Option<f64> {
        None
    }
    fn encode_latency_ms_p95(&self) -> Option<f64> {
        None
    }
    fn is_hardware(&self) -> bool;
    fn backend_name(&self) -> &'static str;
}

// ─── Mock (dev/CI simulation only) ─────────────────────────────────────────

pub struct MockEncoder {
    pub codec: String,
    prepared: bool,
    force_idr: bool,
}

impl MockEncoder {
    pub fn new(codec: String) -> Self {
        Self { codec, prepared: false, force_idr: false }
    }
}

impl EncoderPort for MockEncoder {
    fn prepare(&mut self) -> Result<(), String> {
        self.prepared = true;
        Ok(())
    }

    fn encode_frame(
        &mut self,
        frame: &mut crate::capture::CapturedFrame,
        pts_us: u64,
    ) -> Result<Vec<EncodedPacket>, String> {
        if !self.prepared {
            self.prepare()?;
        }
        let keyframe = frame.frame_number % 120 == 0 || std::mem::take(&mut self.force_idr);
        Ok(vec![EncodedPacket {
            pts_us,
            dts_us: pts_us as i64,
            is_keyframe: keyframe,
            // Synthetic Annex-B-ish payload sized like real 1080p60 screen content.
            data: vec![0u8; 24_000],
            codec: self.codec.clone(),
        }])
    }

    fn flush(&mut self) -> Result<Vec<EncodedPacket>, String> {
        Ok(vec![])
    }

    fn request_idr(&mut self) {
        self.force_idr = true;
    }

    fn is_hardware(&self) -> bool {
        false
    }

    fn backend_name(&self) -> &'static str {
        "MOCK"
    }
}
