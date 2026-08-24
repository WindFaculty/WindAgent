//! Audio capture — Section 18 (WASAPI)
//!
//! Principle F: audio is prepared as an abstraction (`AudioCapturePort`) but
//! `audio_enabled` stays false in P0/P1 — not blocking Live Record for audio.
//! The TTS stage will later generate narration audio from `timeline.jsonl`.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AudioBackend {
    Wasapi,
    Mock,
}

pub trait AudioCapturePort: Send {
    fn prepare(&mut self) -> Result<(), String>;
    fn start(&mut self) -> Result<(), String>;
    fn stop(&mut self) -> Result<(), String>;
    fn is_available(&self) -> bool;
    fn backend(&self) -> AudioBackend;
}

// ─── WASAPI (real, Windows-only) ───────────────────────────────────────────

pub struct WasapiCapture {
    available: bool,
}

impl WasapiCapture {
    pub fn new() -> Self {
        Self {
            available: Self::probe_available(),
        }
    }

    #[cfg(target_os = "windows")]
    fn probe_available() -> bool {
        false // until WASAPI is linked
    }

    #[cfg(not(target_os = "windows"))]
    fn probe_available() -> bool {
        false
    }
}

impl Default for WasapiCapture {
    fn default() -> Self {
        Self::new()
    }
}

impl AudioCapturePort for WasapiCapture {
    fn prepare(&mut self) -> Result<(), String> {
        // P0 policy: always disabled, so prepare is a no-op that succeeds
        // when audio_enabled == false. Callers check profile.audio_enabled first.
        Ok(())
    }

    fn start(&mut self) -> Result<(), String> {
        Err("WASAPI_DISABLED: audio_enabled is false in P0 (Principle F)".into())
    }

    fn stop(&mut self) -> Result<(), String> {
        Ok(())
    }

    fn is_available(&self) -> bool {
        self.available
    }

    fn backend(&self) -> AudioBackend {
        AudioBackend::Wasapi
    }
}

// ─── Mock ──────────────────────────────────────────────────────────────────

pub struct MockAudioCapture;

impl AudioCapturePort for MockAudioCapture {
    fn prepare(&mut self) -> Result<(), String> {
        Ok(())
    }

    fn start(&mut self) -> Result<(), String> {
        Err("MOCK_AUDIO_DISABLED: audio_enabled is false".into())
    }

    fn stop(&mut self) -> Result<(), String> {
        Ok(())
    }

    fn is_available(&self) -> bool {
        false
    }

    fn backend(&self) -> AudioBackend {
        AudioBackend::Mock
    }
}
