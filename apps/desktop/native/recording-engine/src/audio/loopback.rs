//! WASAPI system-audio loopback capture — its own MKV track, event-driven
//! (ban_ke_hoach_v1.md §11, Phase 7).
//!
//! ```text
//! IMMDeviceEnumerator → default/selected RENDER endpoint
//!        → IAudioClient(SHARED + EVENTCALLBACK + AUDCLNT_STREAMFLAGS_LOOPBACK)
//!        → IAudioCaptureClient
//! ```
//!
//! A separate capture client from the mic — mic and system are **never
//! mixed** pre-record; the muxer receives Track 1 = Mic, Track 2 = System
//! (Principle E). Loopback semantics: packets appear only while something
//! renders — silence periods legitimately yield no packets, and PTS
//! continuity comes from the QPC stamp on each delivered block (§12), never
//! from synthesized filler.
//!
//! Mute is enforced at the recorder (§11): a muted system track keeps
//! delivering zeroed samples so the timeline stays continuous.

use super::{AudioCapturePort, AudioDeviceInfo, PcmBlock, TrackKind};

/// Production §11 system-loopback track.
pub struct WasapiLoopback {
    #[cfg(windows)]
    stream: Option<crate::audio::device::wasapi::StreamHandle>,
    /// Negotiated format from the last successful `prepare` (preflight uses it).
    info: AudioDeviceInfo,
}

impl Default for WasapiLoopback {
    fn default() -> Self {
        Self::new()
    }
}

impl WasapiLoopback {
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

    /// Last worker fault — the pipeline polls this; nothing is synthesized
    /// into the block stream.
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

impl AudioCapturePort for WasapiLoopback {
    /// Resolve the render endpoint (`device_id` empty → default render device)
    /// and initialize the loopback client. Re-prepare cleanly replaces any
    /// previous stream.
    fn prepare(&mut self, device_id: &str) -> Result<AudioDeviceInfo, String> {
        #[cfg(windows)]
        {
            self.stream = None; // Drop first: joins any prior worker.
            let stream = crate::audio::device::open_loopback_stream(device_id)?;
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
                None => Err("LOOPBACK_NOT_PREPARED".into()),
            }
        }
        #[cfg(not(windows))]
        {
            Err("LOOPBACK_NOT_PREPARED".into())
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

    /// `None` also during silent spans — expected loopback behavior, NOT an
    /// error; drift accounting continues from the next real packet's QPC.
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
        TrackKind::System
    }
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;
    use crate::audio::device;

    #[test]
    fn lifecycle_fails_closed_without_prepare() {
        let mut sys = WasapiLoopback::new();
        assert!(!sys.is_available());
        assert_eq!(sys.track(), TrackKind::System);
        assert!(sys.poll_block().is_none());
        assert_eq!(sys.start(), Err("LOOPBACK_NOT_PREPARED".to_string()));
        assert!(sys.stop().is_ok());
    }

    #[test]
    fn unknown_device_id_is_rejected_not_substituted() {
        if !device::wasapi_available() || !device::default_render_available() {
            eprintln!("skipping: no WASAPI render hardware on this host");
            return;
        }
        let mut sys = WasapiLoopback::new();
        let err = sys.prepare("WINDAGENT_DEFINITELY_NOT_A_REAL_DEVICE_ID").unwrap_err();
        assert!(err.contains("WASAPI_DEVICE_NOT_FOUND"), "{err}");
        assert!(!sys.is_available());
    }

    #[test]
    fn default_render_round_trip_when_present() {
        if !device::default_render_available() {
            eprintln!("skipping: no default render endpoint on this host");
            return;
        }
        let mut sys = WasapiLoopback::new();
        let info = sys.prepare("").expect("default render must prepare");
        assert!(info.available && info.channels >= 1 && info.sample_rate > 0);
        assert!(!info.device_id.is_empty());

        if sys.start().is_ok() {
            std::thread::sleep(std::time::Duration::from_millis(120));
            sys.set_muted(true); // mid-take toggle keeps PTS continuity
            std::thread::sleep(std::time::Duration::from_millis(60));
            sys.stop().expect("stop after start");
            // Silent hosts deliver zero blocks here — that is correct loopback
            // behavior, not a failure; whatever arrived must be well-formed.
            while let Some(block) = sys.poll_block() {
                assert_eq!(block.channels as usize * block.frames(), block.samples.len());
                assert_eq!(block.sample_rate, info.sample_rate);
            }
            assert!(
                sys.last_error().is_none(),
                "clean short capture must not fault: {:?}",
                sys.last_error()
            );
        } else {
            eprintln!("skipping start: exclusive-mode host or driver refusal");
        }
    }
}

#[cfg(all(test, not(windows)))]
mod tests {
    use super::*;

    #[test]
    fn fails_closed_off_windows() {
        let mut sys = WasapiLoopback::new();
        assert_eq!(sys.prepare(""), Err("WASAPI_UNSUPPORTED_OS".to_string()));
        assert_eq!(sys.start(), Err("LOOPBACK_NOT_PREPARED".to_string()));
        assert!(!sys.is_available());
        assert!(sys.poll_block().is_none());
        assert_eq!(sys.track(), TrackKind::System);
    }
}
