//! WASAPI microphone capture — one MKV track, event-driven (ban_ke_hoach_v1.md
//! §10, Phase 6).
//!
//! ```text
//! IMMDeviceEnumerator → default/selected CAPTURE endpoint
//!        → IAudioClient(SHARED + EVENTCALLBACK) → IAudioCaptureClient
//! ```
//!
//! No busy polling: a dedicated worker waits on the client event and pushes
//! interleaved f32 [`PcmBlock`]s into a bounded queue. The device's native mix
//! format is captured as-is (typically 48 kHz float); rate conversion to the
//! contract's 48 kHz happens in the AAC encode leg (`super::aac`), never by
//! mass-dropping frames (§12). A mono mic stays mono — no fake stereo (§10).
//!
//! Mute is enforced at the recorder, not on frontend meters (§11): muted
//! tracks keep delivering zeroed samples so PTS continuity survives toggles.

use super::{AudioCapturePort, AudioDeviceInfo, PcmBlock, TrackKind};

/// Production §10 microphone track.
pub struct WasapiMicrophone {
    #[cfg(windows)]
    stream: Option<crate::audio::device::wasapi::StreamHandle>,
    /// Negotiated format from the last successful `prepare` (preflight uses it).
    info: AudioDeviceInfo,
}

impl Default for WasapiMicrophone {
    fn default() -> Self {
        Self::new()
    }
}

impl WasapiMicrophone {
    pub fn new() -> Self {
        Self {
            #[cfg(windows)]
            stream: None,
            info: AudioDeviceInfo::default(),
        }
    }

    /// Blocks dropped because the 128-block queue overflowed between pipeline
    /// polls — fold into `audio_underruns` telemetry (§17 honesty rule).
    pub fn overflow_dropped(&self) -> u64 {
        #[cfg(windows)]
        {
            self.stream.as_ref().map(|s| s.overflow_dropped()).unwrap_or(0)
        }
        #[cfg(not(windows))]
        {
            0
        }
    }

    /// Last worker fault (e.g. `AUDIO_DEVICE_INVALIDATED:0x88890004`) — the
    /// pipeline polls this; nothing is synthesized into the block stream.
    pub fn last_error(&self) -> Option<String> {
        #[cfg(windows)]
        {
            self.stream.as_ref().and_then(|s| s.last_error())
        }
        #[cfg(not(windows))]
        {
            None
        }
    }
}

impl AudioCapturePort for WasapiMicrophone {
    /// Resolve the endpoint (`device_id` empty → default capture device) and
    /// initialize the event-driven client. Re-prepare cleanly replaces any
    /// previous stream — there are never two live workers.
    fn prepare(&mut self, device_id: &str) -> Result<AudioDeviceInfo, String> {
        #[cfg(windows)]
        {
            self.stream = None; // Drop first: joins any prior worker.
            let stream = crate::audio::device::open_microphone_stream(device_id)?;
            self.info = stream.info().clone();
            self.stream = Some(stream);
            Ok(self.info.clone())
        }
        #[cfg(not(windows))]
        {
            let _ = device_id;
            Err("WASAPI_UNSUPPORTED_OS".into())
        }
    }

    fn start(&mut self) -> Result<(), String> {
        #[cfg(windows)]
        {
            match self.stream.as_mut() {
                Some(stream) => stream.start(),
                None => Err("MIC_NOT_PREPARED".into()),
            }
        }
        #[cfg(not(windows))]
        {
            Err("MIC_NOT_PREPARED".into())
        }
    }

    fn stop(&mut self) -> Result<(), String> {
        #[cfg(windows)]
        {
            match self.stream.as_mut() {
                Some(stream) => stream.stop(),
                None => Ok(()), // idempotent like the mock port
            }
        }
        #[cfg(not(windows))]
        {
            Ok(())
        }
    }

    fn poll_block(&mut self) -> Option<PcmBlock> {
        #[cfg(windows)]
        {
            self.stream.as_mut().and_then(|s| s.poll())
        }
        #[cfg(not(windows))]
        {
            None
        }
    }

    fn set_muted(&mut self, muted: bool) {
        #[cfg(windows)]
        if let Some(stream) = self.stream.as_mut() {
            stream.set_muted(muted);
        }
        #[cfg(not(windows))]
        {
            let _ = muted;
        }
    }

    /// False until a successful prepare; flips false again on device
    /// invalidation mid-take (fail-closed — availability is measured).
    fn is_available(&self) -> bool {
        #[cfg(windows)]
        {
            self.stream.as_ref().map(|s| s.is_available()).unwrap_or(false)
        }
        #[cfg(not(windows))]
        {
            false
        }
    }

    fn track(&self) -> TrackKind {
        TrackKind::Mic
    }
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;
    use crate::audio::device;

    #[test]
    fn lifecycle_fails_closed_without_prepare() {
        let mut mic = WasapiMicrophone::new();
        assert!(!mic.is_available());
        assert_eq!(mic.track(), TrackKind::Mic);
        assert!(mic.poll_block().is_none());
        assert_eq!(mic.start(), Err("MIC_NOT_PREPARED".to_string()));
        // stop before prepare is an idempotent no-op like the mock port.
        assert!(mic.stop().is_ok());
    }

    #[test]
    fn unknown_device_id_is_rejected_not_substituted() {
        if !device::wasapi_available() || !device::default_input_available() {
            eprintln!("skipping: no WASAPI input hardware on this host");
            return;
        }
        let mut mic = WasapiMicrophone::new();
        let err = mic.prepare("WINDAGENT_DEFINITELY_NOT_A_REAL_DEVICE_ID").unwrap_err();
        assert!(err.contains("WASAPI_DEVICE_NOT_FOUND"), "{err}");
        assert!(!mic.is_available());
    }

    #[test]
    fn default_device_round_trip_when_present() {
        if !device::default_input_available() {
            eprintln!("skipping: no default input endpoint on this host");
            return;
        }
        let mut mic = WasapiMicrophone::new();
        let info = mic.prepare("").expect("default input must prepare");
        assert!(info.available && info.channels >= 1 && info.sample_rate > 0);
        assert!(!info.device_id.is_empty());
        // AudioDeviceInfo (frozen mod.rs) has no PartialEq — compare fields.
        assert_eq!(info.device_id, mic.info.device_id);
        assert_eq!(info.channels, mic.info.channels);
        assert_eq!(info.sample_rate, mic.info.sample_rate);
        mic.stop().expect("stop after prepare");
        mic.set_muted(true); // pre-start mute toggle must not panic

        if mic.start().is_ok() {
            std::thread::sleep(std::time::Duration::from_millis(120));
            mic.set_muted(true);
            std::thread::sleep(std::time::Duration::from_millis(60));
            mic.stop().expect("stop after start");
            // Whatever arrived stays well-formed; queue drains without panic.
            while let Some(block) = mic.poll_block() {
                assert_eq!(block.channels as usize * block.frames(), block.samples.len());
                assert_eq!(block.sample_rate, info.sample_rate);
            }
            // 128-block cap cannot overflow in this short run.
            assert_eq!(mic.overflow_dropped(), 0);
        } else {
            eprintln!("skipping start: exclusive-mode host or driver refusal");
        }
    }

    #[test]
    fn re_prepare_replaces_stream_cleanly() {
        if !device::default_input_available() {
            eprintln!("skipping: no default input endpoint on this host");
            return;
        }
        let mut mic = WasapiMicrophone::new();
        let first = mic.prepare("").unwrap();
        let second = mic.prepare("").unwrap();
        assert_eq!(first.device_id, second.device_id);
        assert!(mic.is_available());
    }
}

#[cfg(all(test, not(windows)))]
mod tests {
    use super::*;

    #[test]
    fn fails_closed_off_windows() {
        let mut mic = WasapiMicrophone::new();
        assert_eq!(mic.prepare(""), Err("WASAPI_UNSUPPORTED_OS".to_string()));
        assert_eq!(mic.start(), Err("MIC_NOT_PREPARED".to_string()));
        assert!(!mic.is_available());
        assert!(mic.poll_block().is_none());
        assert!(mic.last_error().is_none());
        assert_eq!(mic.overflow_dropped(), 0);
    }
}
