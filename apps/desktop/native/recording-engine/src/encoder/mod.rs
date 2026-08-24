//! Encoder — Phase 9 (ban_ke_hoach_v1.md Section 16)
//!
//! D3D11 texture → NVENC (H.264/HEVC) → annex-B bitstream → libav muxer.

use serde::{Deserialize, Serialize};

pub trait EncoderPort: Send {
    fn prepare(&mut self) -> Result<(), String>;
    fn encode(&mut self, frame: &crate::capture::CapturedFrame) -> Result<EncodedPacket, String>;
    fn flush(&mut self) -> Result<Vec<EncodedPacket>, String>;
    fn is_hardware(&self) -> bool;
    fn backend_name(&self) -> &'static str;
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncodedPacket {
    pub pts_ms: u64,
    pub dts_ms: u64,
    pub is_keyframe: bool,
    pub data_len: usize,
    pub codec: String,
}

// ─── NVENC (hardware) ──────────────────────────────────────────────────────

pub struct NvencEncoder {
    pub codec: String,
    available: bool,
}

impl NvencEncoder {
    pub fn new(codec: String) -> Self {
        Self {
            codec,
            available: Self::probe_available(),
        }
    }

    #[cfg(target_os = "windows")]
    fn probe_available() -> bool {
        // Real probe: load nvEncodeAPI.dll and query NV_ENC_CAPS.
        false
    }

    #[cfg(not(target_os = "windows"))]
    fn probe_available() -> bool {
        false
    }
}

impl EncoderPort for NvencEncoder {
    fn prepare(&mut self) -> Result<(), String> {
        if !self.available {
            return Err("NVENC_UNAVAILABLE: hardware encoder not available".into());
        }
        Ok(())
    }

    fn encode(&mut self, frame: &crate::capture::CapturedFrame) -> Result<EncodedPacket, String> {
        self.prepare()?;
        Ok(EncodedPacket {
            pts_ms: frame.timestamp_ms,
            dts_ms: frame.timestamp_ms,
            is_keyframe: frame.timestamp_ms % 1000 == 0,
            data_len: (frame.data_len as f64 * 0.05) as usize, // ~20:1 compression mock
            codec: self.codec.clone(),
        })
    }

    fn flush(&mut self) -> Result<Vec<EncodedPacket>, String> {
        Ok(vec![])
    }

    fn is_hardware(&self) -> bool {
        true
    }

    fn backend_name(&self) -> &'static str {
        "NVENC"
    }
}

// ─── Mock (CI / non-Windows) ───────────────────────────────────────────────

pub struct MockEncoder {
    pub codec: String,
    prepared: bool,
}

impl MockEncoder {
    pub fn new(codec: String) -> Self {
        Self {
            codec,
            prepared: false,
        }
    }
}

impl EncoderPort for MockEncoder {
    fn prepare(&mut self) -> Result<(), String> {
        self.prepared = true;
        Ok(())
    }

    fn encode(&mut self, frame: &crate::capture::CapturedFrame) -> Result<EncodedPacket, String> {
        if !self.prepared {
            self.prepare()?;
        }
        Ok(EncodedPacket {
            pts_ms: frame.timestamp_ms,
            dts_ms: frame.timestamp_ms,
            is_keyframe: frame.timestamp_ms % 2000 == 0,
            data_len: 8192,
            codec: self.codec.clone(),
        })
    }

    fn flush(&mut self) -> Result<Vec<EncodedPacket>, String> {
        Ok(vec![])
    }

    fn is_hardware(&self) -> bool {
        false
    }

    fn backend_name(&self) -> &'static str {
        "MOCK"
    }
}
