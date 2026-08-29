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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nvenc_config_from_profile_maps_frozen_quality() {
        let mut profile = crate::EngineProfile::default();
        profile.video.codec = "HEVC".into();
        profile.video.cq = 18;
        profile.video.preset = "P5".into();
        profile.video.multipass = "HALF_RES".into();
        profile.video.lookahead = 12;
        profile.video.spatial_aq = false;
        profile.video.temporal_aq = false;
        profile.video.b_frames = 2;
        profile.video.gop_frames = 240;
        profile.video.width = 1280;
        profile.video.height = 720;
        profile.video.fps = 30;

        let cfg = NvencConfig::from_profile(&profile);
        assert_eq!(cfg.codec, Codec::Hevc);
        assert_eq!(cfg.cq, 18);
        assert_eq!(cfg.preset, Preset::P5);
        assert_eq!(cfg.multipass, Multipass::HalfRes);
        assert_eq!(cfg.lookahead, 12);
        assert!(!cfg.spatial_aq);
        assert!(!cfg.temporal_aq);
        assert_eq!(cfg.b_frames, 2);
        assert_eq!(cfg.gop_frames, 240);
        assert_eq!(cfg.width, 1280);
        assert_eq!(cfg.height, 720);
        assert_eq!(cfg.fps, 30);
    }

    #[test]
    fn nvenc_config_defaults_are_quality_first() {
        let profile = crate::EngineProfile::default();
        let cfg = NvencConfig::from_profile(&profile);
        assert_eq!(cfg.codec, Codec::H264);
        assert_eq!(cfg.preset, Preset::P7);
        assert_eq!(cfg.multipass, Multipass::FullRes);
        assert_eq!(cfg.cq, 16);
        assert_eq!(cfg.b_frames, 0);
        assert_eq!(cfg.lookahead, 0);
    }

    #[test]
    fn nvenc_unavailable_is_fail_closed_prefix() {
        assert!(NVENC_UNAVAILABLE.starts_with("NVENC_UNAVAILABLE"));
        assert!(!NVENC_UNAVAILABLE.contains("software"));
        assert!(!NVENC_UNAVAILABLE.to_lowercase().contains("fallback"));
    }

    #[test]
    fn mock_encoder_is_not_hardware_and_flush_is_idempotent() {
        let mut enc = MockEncoder::new("H264".into());
        assert!(!enc.is_hardware());
        assert_eq!(enc.backend_name(), "MOCK");
        assert!(enc.flush().unwrap().is_empty());
        assert!(enc.flush().unwrap().is_empty());
        enc.request_idr();
        let frame = crate::capture::CapturedFrame::metadata(1920, 1080, crate::capture::SurfaceFormat::Bgra8, 0, 1);
        // Mock requires mutable frame even though it ignores texture
        let mut f = frame;
        let pkts = enc.encode_frame(&mut f, 16666).unwrap();
        assert_eq!(pkts[0].pts_us, 16666);
        assert!(pkts[0].is_keyframe); // forced IDR
    }

    #[test]
    fn direct_texture_path_has_no_cpu_readback_symbols() {
        // Static verification: production encoder must not call Map, staging, or
        // CPU frame byte copy before NvEncEncodePicture. This test scans its
        // own source file for forbidden symbols that would indicate a staging
        // readback regression.
        let src = include_str!("nvenc_session.rs");
        // The only Map allowed is NvEncMapInputResource / NvEncUnmapInputResource
        // and ID3D11DeviceContext::Map must not appear on the encode hot path.
        // Encoded packets are the only byte buffers; CapturedFrame owns the texture.
        assert!(!src.contains("ID3D11DeviceContext::Map"), "CPU Map forbidden on direct NVENC path");
        assert!(!src.contains("staging"), "staging texture forbidden");
        assert!(!src.contains("CPU_ACCESS"), "CPU readback forbidden");
        // Verify the new cleanup invariant is present in source
        assert!(src.contains("unmap_input_resource"), "encode error path must unmap");
    }

    #[test]
    fn encode_error_cleanup_is_present_in_source() {
        let src = include_str!("nvenc_session.rs");
        // After the fix, Err(e) from encode_picture must unmap single texture
        // (not leak) and SUCCESS lock failure must release mappings before err.
        let has_single_unmap_on_err = src.contains("Err(e) =>") && src.contains("unmap_input_resource");
        assert!(has_single_unmap_on_err, "encode error path must contain single-texture unmap");
        // Verify lock failure also releases before return
        assert!(src.contains("release_input_mappings();\n                        return Err(e)"), "lock failure must release before Err");
    }

    #[test]
    #[cfg(windows)]
    fn resolve_output_pts_preserves_zero() {
        // Repair Pass 1: zero PTS must remain valid, never conflated with unavailable.
        use crate::encoder::nvenc_session::NvencSession;
        assert_eq!(NvencSession::resolve_output_pts(0, 516646), 0, "zero must be preserved even when fallback non-zero");
        assert_eq!(NvencSession::resolve_output_pts(0, 0), 0);
        assert_eq!(NvencSession::resolve_output_pts(16666, 0), 16666);
        assert_eq!(NvencSession::resolve_output_pts(16666, 99999), 16666, "driver timestamp always authoritative");
        assert_eq!(NvencSession::resolve_output_pts(433316, 0), 433316);
        // Fallback is ignored on Windows — driver timestamp is authoritative even if fallback differs.
    }

    #[test]
    fn lock_packets_zero_pts_not_treated_as_absent() {
        // Static check that lock_packets no longer uses `!= 0` fallback logic.
        let src = include_str!("nvenc_session.rs");
        assert!(
            !src.contains("if lock.output_time_stamp != 0"),
            "lock_packets must not use `!= 0` to infer timestamp validity — zero is valid"
        );
        assert!(
            src.contains("resolve_output_pts"),
            "lock_packets must call resolve_output_pts helper"
        );
    }
}
