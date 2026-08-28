//! [`EncoderPort`] adapter over a live [`NvencSession`] (ban_ke_hoach_v1.md §8).
//!
//! PTS contract: the caller supplies take-relative, pause-compensated `pts_us`
//! (§12 single-clock rule); packets echo it so audio and video share one
//! gapless TakeClock timeline. See `service::run_encode_thread`.

use super::{EncodedPacket, EncoderPort, NvencConfig};
use crate::capture::CapturedFrame;

pub struct NvencEncoder {
    session: super::nvenc_session::NvencSession,
    force_idr_pending: bool,
}

impl NvencEncoder {
    pub fn open(config: &NvencConfig, device: &windows::Win32::Graphics::Direct3D11::ID3D11Device) -> Result<Self, String> {
        let session = super::nvenc_session::NvencSession::open(config, device)?;
        Ok(Self { session, force_idr_pending: false })
    }
}

impl EncoderPort for NvencEncoder {
    fn prepare(&mut self) -> Result<(), String> {
        Ok(()) // session is fully initialized at open
    }

    fn sequence_header(&self) -> Option<Vec<u8>> {
        Some(self.session.sequence_header().to_vec())
    }

    fn encode_frame(&mut self, frame: &mut CapturedFrame, pts_us: u64) -> Result<Vec<EncodedPacket>, String> {
        #[cfg(windows)]
        {
            let tex = frame.texture.as_ref().ok_or_else(|| {
                "NVENC_NO_TEXTURE: captured frame carried no D3D11 texture".to_string()
            })?;
            let force = std::mem::take(&mut self.force_idr_pending);
            self.session.encode_texture(tex, pts_us, force)
        }
        #[cfg(not(windows))]
        {
            Err(crate::encoder::NVENC_UNAVAILABLE.into())
        }
    }

    fn flush(&mut self) -> Result<Vec<EncodedPacket>, String> {
        self.session.flush()
    }

    fn request_idr(&mut self) {
        self.force_idr_pending = true;
    }

    fn encode_latency_ms_p50(&self) -> Option<f64> {
        self.session.latency_stats().0
    }

    fn encode_latency_ms_p95(&self) -> Option<f64> {
        self.session.latency_stats().1
    }

    fn is_hardware(&self) -> bool {
        true
    }

    fn backend_name(&self) -> &'static str {
        "NVENC"
    }
}
