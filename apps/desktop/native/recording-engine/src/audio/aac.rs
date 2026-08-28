//! Media Foundation AAC-LC encoding leg for both audio tracks
//! (ban_ke_hoach_v1.md §10/§11 capture → encode, §12 timestamps).
//!
//! ```text
//! PcmBlock (mix-rate f32)
//!   → [linear resampler]  → 48 kHz f32     (RATE POLICY: contract locks 48 kHz)
//!   → [clamp·scale]       → interleaved s16 (MF AAC MFTs reject float input)
//!   → MFTransform(sync)   → raw AAC-LC frames, 1024 samples each
//! ```
//!
//! Design notes:
//! - **s16 conversion done here**, deliberately — avoids Media Foundation's
//!   float-input quirks; the cost is a trivial clamp·scale pass.
//! - **Linear interpolation** is acceptable for v1 (device mix rates are
//!   typically already 48 kHz, so the resampler is usually bypassed);
//!   polyphase is the noted upgrade path if drift compensation ever demands
//!   it (§12: compensate by resampling, never by mass-dropping frames).
//! - **Mono stays mono** (§10) — chanCfg=1 flows through untouched; no fake
//!   stereo. Channel counts outside [1,2] are rejected fail-closed.
//! - **PTS math**: packet `n` starts at absolute input frame `n × 1024`; the
//!   MFT emits packets with multi-block latency, so each packet is stamped
//!   against the recorded block that actually *contains* its first sample
//!   ([`PtsBook`] anchor ring). Loopback silence gaps restart the timeline at
//!   the resuming block's QPC — wall-clock placement stays honest (§12), and
//!   drift accounting reads true offsets back out via `sample_count`.
//! - `drain()` flushes whatever complete frames exist; a trailing partial
//!   (<1024 frames) is **not padded** in v1 — at most ≈21 ms of tail audio
//!   is omitted, documented rather than silently fabricated.

use super::AudioDeviceInfo;

// ─── Contract constants ─────────────────────────────────────────────────────

/// Locked output rate — mirrors `audio.sample_rate` validation in
/// [`crate::EngineProfile::validate`] (only 48 000 passes).
pub const AAC_OUTPUT_SAMPLE_RATE: u32 = 48_000;

/// AAC-LC constant frame size in input samples per encoded packet.
pub const AAC_FRAME_FRAMES: u64 = 1024;

/// Drift compensation engages only beyond this |ppm| — below it the squeeze
/// would resample every block for inaudible gain (25 ppm ≈ 1.5 ms/minute).
const DRIFT_COMPENSATION_MIN_PPM: f64 = 25.0;

// ─── Public API ─────────────────────────────────────────────────────────────

/// True when a synchronous Media Foundation PCM→AAC MFT exists on this host
/// (`MFTEnumEx` with 48 kHz stereo PCM in / AAC out, then `MFShutdown`).
///
/// Hardware-dependent probe: degrades to `false` without panicking; preflight
/// turns `false` into the explicit `AAC_ENCODER_UNAVAILABLE` blocker (§15).
pub fn mf_aac_encoder_present() -> bool {
    #[cfg(windows)]
    {
        probe_mf_aac()
    }
    #[cfg(not(windows))]
    {
        false
    }
}

/// One encoded AAC packet ready for the muxer (raw AAC, payload-type 0 — no
/// ADTS headers; Matroska wants raw frames, see `muxer::tracks::build_aac_asc`).
#[derive(Debug, Clone)]
pub struct AacOut {
    pub data: Vec<u8>,
    /// Microseconds since take start (QPC-derived anchor, §12).
    pub pts_us: u64,
    /// PCM frames consumed to produce this packet (always 1024 — drift
    /// accounting sums these against wall-clock to expose device drift).
    pub sample_count: u64,
}

/// Abstract AAC encoder port (mirrors [`crate::encoder::EncoderPort`]
/// semantics on the audio side).
pub trait AacEncoderPort: Send {
    /// Encode one PCM block; `pts_us_of_first_frame` anchors this block's QPC
    /// timeline. Returns every complete packet the MFT emitted.
    fn encode_block(
        &mut self,
        block: &super::PcmBlock,
        pts_us_of_first_frame: u64,
    ) -> Result<Vec<AacOut>, String>;
    /// Flush complete buffered frames. A trailing partial frame is dropped by
    /// design (module docs) — never an error.
    fn drain(&mut self) -> Result<Vec<AacOut>, String>;
    /// Contract-locked output rate (always [`AAC_OUTPUT_SAMPLE_RATE`]).
    fn output_sample_rate(&self) -> u32;
    fn output_channels(&self) -> u32;
    /// Latest device-clock drift estimate in ppm vs the take clock (§12).
    /// Encoders that compensate squeeze/stretch their input so content
    /// duration matches its QPC span; the default ignores it.
    fn set_drift_ppm(&mut self, _ppm: f64) {}
}

// ─── Pure DSP helpers (unit-tested on every platform) ──────────────────────

/// Cheap symmetric clamp·scale: [-1,1] → [-32767, 32767], rounded.
/// Out-of-range inputs clamp — never wrap. NaN maps to silence (0), matching
/// how a broken float sample should sound rather than an edge value.
pub fn f32_to_s16_clamped(v: f32) -> i16 {
    if v.is_nan() {
        return 0;
    }
    (v.clamp(-1.0, 1.0) * 32_767.0).round() as i16
}

/// Interleaved f32 → little-endian s16 bytes (per-channel clamp·scale).
pub fn f32_to_s16_bytes(samples: &[f32]) -> Vec<u8> {
    let mut out = Vec::with_capacity(samples.len() * 2);
    for v in samples {
        out.extend_from_slice(&f32_to_s16_clamped(*v).to_le_bytes());
    }
    out
}

/// Per-channel linear-interpolation resampler (v1 quality tier).
///
/// Identity passthrough when rates match. Output length is ceil-scaled, so
/// `44_100 → 48_000` lands within 1 frame of exact ratio math. Polyphase is
/// the upgrade path if drift-compensation quality ever demands it (§12).
pub fn linear_resample(samples: &[f32], channels: usize, in_rate: u32, out_rate: u32) -> Vec<f32> {
    if channels == 0 || in_rate == out_rate || in_rate == 0 || samples.is_empty() {
        return samples.to_vec();
    }
    let in_frames = samples.len() / channels;
    let out_frames =
        ((in_frames as u64 * out_rate as u64) + in_rate as u64 - 1) / in_rate as u64;
    let mut out = vec![0.0f32; out_frames as usize * channels];
    for c in 0..channels {
        for i in 0..out_frames as usize {
            let src_pos = i as f64 * in_rate as f64 / out_rate as f64;
            let i0 = (src_pos.floor() as usize).min(in_frames - 1);
            let i1 = (i0 + 1).min(in_frames - 1);
            let frac = (src_pos - i0 as f64) as f32;
            let s0 = samples[i0 * channels + c];
            let s1 = samples[i1 * channels + c];
            out[i * channels + c] = s0 + (s1 - s0) * frac;
        }
    }
    out
}

/// Drift-compensation scale for one delivered chunk (pure, unit-tested).
///
/// A device running +ppm delivers more frames than the QPC span nominally
/// holds; squeezing by `1e6/(1e6+ppm)` makes the encoded content's duration
/// equal its true wall-clock span. Negative ppm stretches symmetrically.
pub fn compensated_frame_count(delivered_frames: u64, ppm: f64) -> u64 {
    ((delivered_frames as f64) * 1_000_000.0 / (1_000_000.0 + ppm)).round() as u64
}

/// Arbitrary-ratio linear resampler — the drift-compensation primitive (§12).
/// `scale` is output-frames-per-input-frame around 1.0 (±a few hundred ppm).
pub(crate) fn linear_resample_scaled(
    samples: &[f32],
    channels: usize,
    scale: f64,
) -> Vec<f32> {
    if channels == 0 || samples.is_empty() {
        return samples.to_vec();
    }
    let in_frames = samples.len() / channels;
    let out_frames = ((in_frames as f64) * scale).round().max(1.0) as usize;
    let mut out = vec![0.0f32; out_frames * channels];
    if out_frames == in_frames {
        // Sub-rounding identity — copy verbatim, no interpolation smear.
        out.copy_from_slice(samples);
        return out;
    }
    let step = (in_frames - 1) as f64 / (out_frames - 1).max(1) as f64;
    for c in 0..channels {
        for i in 0..out_frames {
            let src_pos = i as f64 * step;
            let i0 = src_pos.floor() as usize;
            let i1 = (i0 + 1).min(in_frames - 1);
            let frac = (src_pos - i0 as f64) as f32;
            let s0 = samples[i0 * channels + c];
            let s1 = samples[i1 * channels + c];
            out[i * channels + c] = s0 + (s1 - s0) * frac;
        }
    }
    out
}

/// Frame→time bookkeeping that stamps every emitted AAC packet (pure, unit-
/// tested, §12).
///
/// A sync MF AAC MFT emits packets with **multi-block latency**: by the time
/// a packet surfaces, its first sample may sit in a block fed several
/// `encode_block` calls ago. Stamping against only "the most recent block"
/// clamps every such packet to one identical PTS — duplicated, non-monotonic
/// timestamps observed on real hardware. [`PtsBook`] instead keeps an ordered
/// ring of per-block anchors `(first_absolute_frame, pts_us)` and resolves
/// each packet against the block that actually *contains* its first sample:
///
/// ```text
/// pts = anchor_pts + (packet_start − anchor_first) × 1e6 / 48_000
/// ```
///
/// Within a block this is exact 48 kHz interpolation; across loopback silence
/// gaps the resuming block's QPC anchor restarts the timeline at true wall
/// clock (§12). Anchors are pruned once provably unreachable — some later
/// anchor sits at or below the smallest frame any future packet can start at —
/// so memory stays bounded by the encoder's real emission lag, however deep
/// the MFT buffers.
#[derive(Debug, Default)]
struct PtsBook {
    /// Per-accepted-block anchors, oldest first; the stream's first block
    /// always records `first_absolute_frame == 0`.
    anchors: std::collections::VecDeque<(u64, u64)>,
    /// Complete packets emitted so far — packet n starts at frame n×1024.
    packets_emitted: u64,
}

impl PtsBook {
    /// Record one accepted block: `first_frame` is its first sample's absolute
    /// position in the post-resample 48 kHz domain, `pts_us` its QPC-derived
    /// timestamp. Callers pass monotonically non-decreasing PTS — guaranteed
    /// by construction because every block carries a fresh QPC stamp.
    fn record_block(&mut self, first_frame: u64, pts_us: u64) {
        self.anchors.push_back((first_frame, pts_us));
        // Prune front anchors no future packet can ever resolve against:
        // once anchors[1] starts at-or-below the smallest future start
        // frame, the resolver (scanning newest→oldest) can never reach them.
        let min_future_start = self.packets_emitted * AAC_FRAME_FRAMES;
        while self.anchors.len() > 1 && self.anchors[1].0 <= min_future_start {
            self.anchors.pop_front();
        }
    }

    /// Stamp and count the next complete packet (start = emitted×1024).
    fn next_packet_pts(&mut self) -> u64 {
        let start = self.packets_emitted * AAC_FRAME_FRAMES;
        self.packets_emitted += 1;
        match self.anchors.iter().rev().find(|&&(f, _)| f <= start) {
            Some(&(f, pts)) => {
                pts.saturating_add((start - f) * 1_000_000 / AAC_OUTPUT_SAMPLE_RATE as u64)
            }
            // Defensive: reachable only before any block was recorded, which
            // cannot produce output anyway.
            None => self.anchors.front().map(|&(_, p)| p).unwrap_or(0),
        }
    }
}

// ─── Encoder ───────────────────────────────────────────────────────────────

/// Production [`AacEncoderPort`] backed by a synchronous Media Foundation
/// AAC-LC MFT (activated via `MFTEnumEx`). Non-Windows hosts get the same
/// type failing closed with `MF_UNSUPPORTED_OS`.
pub struct MfAacEncoder {
    output_channels: u32,
    /// Sticky fault — once set, every later call replays it (fail-closed, no
    /// half-alive encoder).
    failed: Option<String>,
    /// Absolute input frames fed to the MFT (post-resample, 48 kHz domain).
    total_input_frames: u64,
    /// Latest device-clock drift estimate (ppm vs take clock) — drives the
    /// §12 squeeze/stretch in `encode_block`. Updated via `set_drift_ppm`.
    drift_ppm: f64,
    /// Packet stamping state — anchor ring + emission counter ([`PtsBook`]).
    book: PtsBook,

    #[cfg(windows)]
    inner: Option<mf::MfSession>,
}

/// Manual `Debug` — the MF session is not `Debug` (COM handle), so only
/// observable encoder state is reported.
impl std::fmt::Debug for MfAacEncoder {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("MfAacEncoder")
            .field("output_channels", &self.output_channels)
            .field("failed", &self.failed)
            .field("total_input_frames", &self.total_input_frames)
            .field("packets_emitted", &self.book.packets_emitted)
            .field("anchor_ring_depth", &self.book.anchors.len())
            .finish_non_exhaustive()
    }
}

impl MfAacEncoder {
    /// Validate → activate the first synchronous PCM→AAC MFT → configure
    /// input (PCM s16 @ 48 kHz) and output (raw AAC, payload type 0, target
    /// bitrate). Pure validations run before any OS call so they behave
    /// identically on every platform.
    pub fn new(input: &AudioDeviceInfo, target_bitrate_bps: u32) -> Result<Self, String> {
        // §10: mono stays mono; anything beyond stereo is rejected instead of
        // silently up/down-mixed.
        if input.channels == 0 || input.channels > 2 {
            return Err(format!("AAC_UNSUPPORTED_CHANNEL_COUNT:{}", input.channels));
        }
        if input.sample_rate == 0 {
            return Err("AAC_INVALID_INPUT_RATE:0".into());
        }
        if !(32_000..=512_000).contains(&target_bitrate_bps) {
            return Err(format!("AAC_BITRATE_OUT_OF_RANGE:{target_bitrate_bps}"));
        }

        #[cfg(windows)]
        {
            let session = mf::MfSession::activate(input.channels, target_bitrate_bps)?;
            Ok(Self {
                output_channels: input.channels,
                failed: None,
                total_input_frames: 0,
                drift_ppm: 0.0,
                book: PtsBook::default(),
                inner: Some(session),
            })
        }
        #[cfg(not(windows))]
        {
            let _ = (input.channels, input.sample_rate, target_bitrate_bps);
            Err("MF_UNSUPPORTED_OS".into())
        }
    }

    fn fail(&mut self, msg: String) -> String {
        self.failed = Some(msg.clone());
        msg
    }

    /// Feed one converted s16 block, then pull every packet the MFT completed.
    fn encode_converted(
        &mut self,
        s16: &[u8],
        frames_fed: u64,
        pts_us_of_first_frame: u64,
    ) -> Result<Vec<AacOut>, String> {
        #[cfg(windows)]
        {
            let session = match self.inner.as_ref() {
                Some(s) => s,
                None => return Err(self.fail("AAC_ENCODER_NOT_INITIALIZED".into())),
            };
            if let Err(e) = session.process_input(s16, frames_fed, pts_us_of_first_frame) {
                return Err(self.fail(e));
            }
        }
        #[cfg(not(windows))]
        {
            let _ = (s16, frames_fed, pts_us_of_first_frame);
            return Err(self.fail("MF_UNSUPPORTED_OS".into()));
        }

        // Anchor this block only after the MFT accepted its bytes — a
        // rejected block leaves no stampable timeline behind (fail-closed).
        self.book.record_block(self.total_input_frames, pts_us_of_first_frame);
        self.total_input_frames += frames_fed;

        let mut out = Vec::new();
        self.collect_pending_outputs(&mut out)?;
        Ok(out)
    }

    /// Pull completed packets until the MFT reports NEED_MORE_INPUT, stamping
    /// each by its absolute frame position against the anchor ring
    /// ([`PtsBook::next_packet_pts`]).
    fn collect_pending_outputs(&mut self, out: &mut Vec<AacOut>) -> Result<(), String> {
        loop {
            #[cfg(windows)]
            let chunk = {
                let session = match self.inner.as_ref() {
                    Some(s) => s,
                    None => return Err(self.fail("AAC_ENCODER_NOT_INITIALIZED".into())),
                };
                match session.process_output_once() {
                    Ok(c) => c,
                    Err(e) => {
                        let msg = self.fail(e);
                        return Err(msg);
                    }
                }
            };
            #[cfg(not(windows))]
            let chunk: Option<Vec<u8>> = None;

            let Some(data) = chunk else { break };
            out.push(AacOut {
                data,
                pts_us: self.book.next_packet_pts(),
                sample_count: AAC_FRAME_FRAMES,
            });
        }
        Ok(())
    }
}

impl AacEncoderPort for MfAacEncoder {
    fn encode_block(
        &mut self,
        block: &super::PcmBlock,
        pts_us_of_first_frame: u64,
    ) -> Result<Vec<AacOut>, String> {
        if let Some(err) = &self.failed {
            return Err(err.clone());
        }
        if block.channels != self.output_channels {
            return Err(format!(
                "AAC_CHANNEL_MISMATCH:track={} block={}",
                self.output_channels, block.channels
            ));
        }
        // RATE POLICY: everything enters the MFT at the contract's 48 kHz.
        let resampled;
        let samples: &[f32] = if block.sample_rate != AAC_OUTPUT_SAMPLE_RATE {
            resampled =
                linear_resample(&block.samples, block.channels as usize, block.sample_rate, AAC_OUTPUT_SAMPLE_RATE);
            &resampled
        } else {
            &block.samples
        };
        // §12 drift compensation: squeeze/stretch the 48 kHz stream so its
        // content duration matches the QPC span the device delivered it over.
        // Below DRIFT_COMPENSATION_MIN_PPM the passthrough avoids per-block
        // interpolation for inaudible gain.
        let compensated;
        let samples: &[f32] = if self.drift_ppm.abs() >= DRIFT_COMPENSATION_MIN_PPM {
            compensated = linear_resample_scaled(
                samples,
                block.channels as usize,
                1_000_000.0 / (1_000_000.0 + self.drift_ppm),
            );
            &compensated
        } else {
            samples
        };
        let frames_fed = (samples.len() / block.channels.max(1) as usize) as u64;
        if frames_fed == 0 {
            return Ok(Vec::new()); // empty block: nothing consumed, nothing owed
        }
        let s16 = f32_to_s16_bytes(samples);
        self.encode_converted(&s16, frames_fed, pts_us_of_first_frame)
    }

    fn drain(&mut self) -> Result<Vec<AacOut>, String> {
        if let Some(err) = &self.failed {
            return Err(err.clone());
        }
        // No flush message exists for sync MFTs: pull whatever complete
        // frames are buffered; a trailing <1024-frame remainder stays
        // unpadded by design (≤21.3 ms of tail audio, module docs).
        let mut out = Vec::new();
        self.collect_pending_outputs(&mut out)?;
        Ok(out)
    }

    fn output_sample_rate(&self) -> u32 {
        AAC_OUTPUT_SAMPLE_RATE
    }

    fn set_drift_ppm(&mut self, ppm: f64) {
        // NaN/inf guards — a poisoned estimate must never wedge the resampler.
        if ppm.is_finite() && ppm.abs() < 5_000.0 {
            self.drift_ppm = ppm;
        }
    }

    fn output_channels(&self) -> u32 {
        self.output_channels
    }
}

// ─── Windows Media Foundation implementation ───────────────────────────────

#[cfg(windows)]
mod mf {
    //! Raw MF plumbing: ref-counted `MFStartup` guard, `MFTEnumEx`
    //! activation, media-type configuration and sample marshalling.

    use std::mem::ManuallyDrop;
    use std::sync::atomic::{AtomicUsize, Ordering};

    use windows::Win32::Media::MediaFoundation::{
        IMFActivate, IMFMediaType, IMFTransform, IMFSample, MFCreateMemoryBuffer,
        MFCreateMediaType, MFCreateSample, MFAudioFormat_AAC, MFAudioFormat_PCM,
        MFMediaType_Audio, MFSTARTUP_LITE, MFStartup, MFShutdown, MF_VERSION,
        MF_MT_AAC_PAYLOAD_TYPE, MF_MT_AUDIO_AVG_BYTES_PER_SECOND, MF_MT_AUDIO_BITS_PER_SAMPLE,
        MF_MT_AUDIO_BLOCK_ALIGNMENT, MF_MT_AUDIO_NUM_CHANNELS, MF_MT_AUDIO_SAMPLES_PER_SECOND,
        MF_MT_MAJOR_TYPE, MF_MT_SUBTYPE, MF_E_TRANSFORM_NEED_MORE_INPUT,
        MFT_CATEGORY_AUDIO_ENCODER, MFT_ENUM_FLAG_SYNCMFT, MFT_REGISTER_TYPE_INFO,
        MFT_OUTPUT_DATA_BUFFER, MFT_OUTPUT_DATA_BUFFER_FORMAT_CHANGE,
        MFT_OUTPUT_STREAM_CAN_PROVIDE_SAMPLES, MFT_OUTPUT_STREAM_INFO,
        MFT_OUTPUT_STREAM_PROVIDES_SAMPLES, MFTEnumEx,
    };
    use windows::Win32::System::Com::CoTaskMemFree;

    use super::AAC_OUTPUT_SAMPLE_RATE;

    /// Ref-counted `MFStartup`/`MFShutdown` pair — safe across concurrent
    /// encoders and probes (MF startup is itself ref-counted by the OS).
    static MF_REFCOUNT: AtomicUsize = AtomicUsize::new(0);

    pub(crate) struct MfGuard;

    impl MfGuard {
        pub(crate) fn acquire() -> Result<Self, String> {
            if MF_REFCOUNT.fetch_add(1, Ordering::SeqCst) == 0 {
                if let Err(e) = unsafe { MFStartup(MF_VERSION, MFSTARTUP_LITE) } {
                    MF_REFCOUNT.fetch_sub(1, Ordering::SeqCst);
                    return Err(format!("MF_STARTUP_FAILED:{e}"));
                }
            }
            Ok(Self)
        }
    }

    impl Drop for MfGuard {
        fn drop(&mut self) {
            if MF_REFCOUNT.fetch_sub(1, Ordering::SeqCst) == 1 {
                unsafe {
                    let _ = MFShutdown();
                }
            }
        }
    }

    /// One live sync-MFT AAC session.
    pub(crate) struct MfSession {
        transform: IMFTransform,
        /// Keeps `MFStartup` balanced while the transform lives.
        _guard: MfGuard,
        /// Minimum output allocation reported by `GetOutputStreamInfo`.
        out_buffer_bytes: u32,
    }

    // # Send — required by `AacEncoderPort: Send`. MF sync MFTs are agile COM
    // objects (no apartment affinity); the encoder is used from exactly one
    // pipeline thread at a time, so cross-thread moves are safe.
    unsafe impl Send for MfSession {}

    fn mf<T>(r: windows::core::Result<T>, code: &str) -> Result<T, String> {
        r.map_err(|e| format!("{code}:{e}"))
    }

    unsafe fn build_input_type(channels: u32) -> Result<IMFMediaType, String> {
        let t = mf(unsafe { MFCreateMediaType() }, "MF_CREATE_TYPE_FAILED")?;
        unsafe {
            mf(t.SetGUID(&MF_MT_MAJOR_TYPE, &MFMediaType_Audio), "MF_SET_GUID_FAILED")?;
            mf(t.SetGUID(&MF_MT_SUBTYPE, &MFAudioFormat_PCM), "MF_SET_GUID_FAILED")?;
            mf(t.SetUINT32(&MF_MT_AUDIO_SAMPLES_PER_SECOND, AAC_OUTPUT_SAMPLE_RATE), "MF_SET_U32_FAILED")?;
            mf(t.SetUINT32(&MF_MT_AUDIO_NUM_CHANNELS, channels), "MF_SET_U32_FAILED")?;
            mf(t.SetUINT32(&MF_MT_AUDIO_BITS_PER_SAMPLE, 16), "MF_SET_U32_FAILED")?;
            mf(t.SetUINT32(&MF_MT_AUDIO_BLOCK_ALIGNMENT, channels * 2), "MF_SET_U32_FAILED")?;
            mf(
                t.SetUINT32(&MF_MT_AUDIO_AVG_BYTES_PER_SECOND, AAC_OUTPUT_SAMPLE_RATE * channels * 2),
                "MF_SET_U32_FAILED",
            )?;
        }
        Ok(t)
    }

    unsafe fn build_output_type(channels: u32, bitrate_bps: u32) -> Result<IMFMediaType, String> {
        let t = mf(unsafe { MFCreateMediaType() }, "MF_CREATE_TYPE_FAILED")?;
        unsafe {
            mf(t.SetGUID(&MF_MT_MAJOR_TYPE, &MFMediaType_Audio), "MF_SET_GUID_FAILED")?;
            mf(t.SetGUID(&MF_MT_SUBTYPE, &MFAudioFormat_AAC), "MF_SET_GUID_FAILED")?;
            mf(t.SetUINT32(&MF_MT_AUDIO_SAMPLES_PER_SECOND, AAC_OUTPUT_SAMPLE_RATE), "MF_SET_U32_FAILED")?;
            mf(t.SetUINT32(&MF_MT_AUDIO_NUM_CHANNELS, channels), "MF_SET_U32_FAILED")?;
            // Required by the MS AAC encoder's output validation (missing it
            // fails with MF_E_ATTRIBUTENOTFOUND): decoded AAC-LC is s16.
            mf(t.SetUINT32(&MF_MT_AUDIO_BITS_PER_SAMPLE, 16), "MF_SET_U32_FAILED")?;
            // Payload type 0 = raw AAC frames (no ADTS) — what MKV expects.
            mf(t.SetUINT32(&MF_MT_AAC_PAYLOAD_TYPE, 0), "MF_SET_U32_FAILED")?;
            mf(
                t.SetUINT32(&MF_MT_AUDIO_AVG_BYTES_PER_SECOND, bitrate_bps / 8),
                "MF_SET_U32_FAILED",
            )?;
        }
        Ok(t)
    }

    /// Enumerate sync PCM→AAC encoder MFTs; caller frees the returned array.
    unsafe fn enum_sync_encoders() -> Result<(*mut Option<IMFActivate>, u32), String> {
        let in_type = MFT_REGISTER_TYPE_INFO {
            guidMajorType: MFMediaType_Audio,
            guidSubtype: MFAudioFormat_PCM,
        };
        let out_type = MFT_REGISTER_TYPE_INFO {
            guidMajorType: MFMediaType_Audio,
            guidSubtype: MFAudioFormat_AAC,
        };
        let mut activates: *mut Option<IMFActivate> = std::ptr::null_mut();
        let mut count: u32 = 0;
        unsafe {
            mf(
                MFTEnumEx(
                    MFT_CATEGORY_AUDIO_ENCODER,
                    MFT_ENUM_FLAG_SYNCMFT,
                    Some(&in_type),
                    Some(&out_type),
                    &mut activates,
                    &mut count,
                ),
                "MF_AAC_ENUM_FAILED",
            )?;
        }
        Ok((activates, count))
    }

    /// # Safety
    /// Frees an array previously filled by [`enum_sync_encoders`], releasing
    /// every remaining activation object.
    unsafe fn free_activates(activates: *mut Option<IMFActivate>, count: u32) {
        if activates.is_null() {
            return;
        }
        unsafe {
            let slice = std::slice::from_raw_parts_mut(activates, count as usize);
            for slot in slice.iter_mut() {
                drop(slot.take()); // release each COM reference exactly once
            }
            CoTaskMemFree(Some(activates.cast()));
        }
    }

    impl MfSession {
        /// Activate the first synchronous PCM→AAC MFT and lock both media
        /// types. Absent encoders surface as `AAC_ENCODER_UNAVAILABLE`.
        pub(crate) fn activate(channels: u32, bitrate_bps: u32) -> Result<Self, String> {
            let guard = MfGuard::acquire()?;
            let (activates, count) = unsafe { enum_sync_encoders() }?;
            if count == 0 {
                unsafe { free_activates(activates, count) };
                return Err("AAC_ENCODER_UNAVAILABLE".into());
            }
            // SAFETY: count ≥ 1 and the array is live; take element 0 and
            // release the rest.
            let first = unsafe {
                let head = std::slice::from_raw_parts_mut(activates, count as usize)[0].take();
                free_activates(activates, count);
                head
            };
            let Some(activate) = first else {
                return Err("AAC_ENCODER_UNAVAILABLE".into());
            };

            let transform: IMFTransform = mf(
                unsafe { activate.ActivateObject::<IMFTransform>() },
                "MF_AAC_ACTIVATE_FAILED",
            )?;
            drop(activate); // transform owns its own reference now

            unsafe {
                let in_type = build_input_type(channels)?;
                mf(transform.SetInputType(0, &in_type, 0), "MF_AAC_SET_INPUT_TYPE_FAILED")?;
                let out_type = build_output_type(channels, bitrate_bps)?;
                mf(transform.SetOutputType(0, &out_type, 0), "MF_AAC_SET_OUTPUT_TYPE_FAILED")?;
            }
            let info: MFT_OUTPUT_STREAM_INFO = mf(
                unsafe { transform.GetOutputStreamInfo(0) },
                "MF_AAC_STREAM_INFO_FAILED",
            )?;
            Ok(Self {
                transform,
                _guard: guard,
                out_buffer_bytes: info.cbSize.max(4096),
            })
        }

        /// Wrap one s16 block in a memory-buffer sample and submit it.
        pub(crate) fn process_input(
            &self,
            s16: &[u8],
            frames: u64,
            pts_us_of_first_frame: u64,
        ) -> Result<(), String> {
            unsafe {
                let sample: IMFSample = mf(MFCreateSample(), "MF_CREATE_SAMPLE_FAILED")?;
                let buffer = mf(
                    MFCreateMemoryBuffer(s16.len().max(1) as u32),
                    "MF_CREATE_BUFFER_FAILED",
                )?;
                {
                    let mut data: *mut u8 = std::ptr::null_mut();
                    mf(buffer.Lock(&mut data, None, None), "MF_BUFFER_LOCK_FAILED")?;
                    std::ptr::copy_nonoverlapping(s16.as_ptr(), data, s16.len());
                    mf(buffer.Unlock(), "MF_BUFFER_UNLOCK_FAILED")?;
                }
                mf(buffer.SetCurrentLength(s16.len() as u32), "MF_SET_LENGTH_FAILED")?;
                mf(sample.AddBuffer(&buffer), "MF_ADD_BUFFER_FAILED")?;
                // 100 ns units for MF bookkeeping; authoritative PTS stays ours.
                let _ = sample.SetSampleTime((pts_us_of_first_frame.min(i64::MAX as u64 / 10) * 10) as i64);
                let _ = sample.SetSampleDuration(
                    (frames * 10_000_000 / AAC_OUTPUT_SAMPLE_RATE as u64) as i64,
                );
                mf(self.transform.ProcessInput(0, &sample, 0), "MF_AAC_INPUT_REJECTED")
            }
        }

        /// One `ProcessOutput` round. `Ok(None)` = need more input.
        pub(crate) fn process_output_once(&self) -> Result<Option<Vec<u8>>, String> {
            unsafe {
                let info: MFT_OUTPUT_STREAM_INFO = mf(
                    self.transform.GetOutputStreamInfo(0),
                    "MF_AAC_STREAM_INFO_FAILED",
                )?;
                let provides = (info.dwFlags & MFT_OUTPUT_STREAM_PROVIDES_SAMPLES.0 as u32) != 0
                    || (info.dwFlags & MFT_OUTPUT_STREAM_CAN_PROVIDE_SAMPLES.0 as u32) != 0;

                let mut buffers = [MFT_OUTPUT_DATA_BUFFER::default()];
                buffers[0].dwStreamID = 0;
                if !provides {
                    // Standard sync MFT: caller allocates the output sample.
                    let sample: IMFSample = mf(MFCreateSample(), "MF_CREATE_SAMPLE_FAILED")?;
                    let mem = mf(
                        MFCreateMemoryBuffer(self.out_buffer_bytes),
                        "MF_CREATE_BUFFER_FAILED",
                    )?;
                    mf(sample.AddBuffer(&mem), "MF_ADD_BUFFER_FAILED")?;
                    buffers[0].pSample = ManuallyDrop::new(Some(sample));
                }

                let mut status = 0u32;
                match self.transform.ProcessOutput(0, &mut buffers, &mut status) {
                    Ok(()) => {
                        // Take ownership back out of the ManuallyDrop slots so
                        // COM references release exactly once.
                        let produced: Option<IMFSample> =
                            ManuallyDrop::take(&mut buffers[0].pSample);
                        let events = ManuallyDrop::take(&mut buffers[0].pEvents);
                        drop(events);
                        // Per-buffer dwStatus carries MFT_OUTPUT_DATA_BUFFER_*
                        // flags (`status` only ever reports new streams).
                        if buffers[0].dwStatus & MFT_OUTPUT_DATA_BUFFER_FORMAT_CHANGE.0 as u32 != 0
                        {
                            return Err("MF_AAC_FORMAT_CHANGE_UNHANDLED".into());
                        }
                        match produced {
                            Some(sample) => Ok(Some(read_sample_bytes(&sample)?)),
                            None => Ok(None), // S_OK without a sample: nothing ready yet
                        }
                    }
                    Err(e) if e.code() == MF_E_TRANSFORM_NEED_MORE_INPUT => Ok(None),
                    Err(e) => Err(format!("MF_AAC_OUTPUT_FAILED:{e}")),
                }
            }
        }
    }

    /// Copy one filled sample's bytes out (contiguous view → Lock/copy/Unlock).
    unsafe fn read_sample_bytes(sample: &IMFSample) -> Result<Vec<u8>, String> {
        unsafe {
            let contiguous = mf(sample.ConvertToContiguousBuffer(), "MF_CONTIGUOUS_FAILED")?;
            let mut data: *mut u8 = std::ptr::null_mut();
            let mut max_len: u32 = 0;
            let mut cur_len: u32 = 0;
            mf(
                contiguous.Lock(&mut data, Some(&mut max_len), Some(&mut cur_len)),
                "MF_BUFFER_LOCK_FAILED",
            )?;
            let bytes = if data.is_null() || cur_len == 0 {
                Vec::new()
            } else {
                std::slice::from_raw_parts(data, cur_len as usize).to_vec()
            };
            mf(contiguous.Unlock(), "MF_BUFFER_UNLOCK_FAILED")?;
            Ok(bytes)
        }
    }

    /// Probe-only enumeration used by [`super::mf_aac_encoder_present`].
    pub(crate) fn probe_count() -> Result<u32, String> {
        let _guard = MfGuard::acquire()?;
        let (activates, count) = unsafe { enum_sync_encoders() }?;
        unsafe { free_activates(activates, count) };
        Ok(count)
    }
}

#[cfg(windows)]
fn probe_mf_aac() -> bool {
    mf::probe_count().map(|c| c > 0).unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn s16_conversion_clamps_symmetrically() {
        assert_eq!(f32_to_s16_clamped(0.0), 0);
        assert_eq!(f32_to_s16_clamped(1.0), 32_767);
        assert_eq!(f32_to_s16_clamped(-1.0), -32_767);
        assert_eq!(f32_to_s16_clamped(1.5), 32_767, "+overflow clamps");
        assert_eq!(f32_to_s16_clamped(-1.5), -32_767, "-overflow clamps");
        assert_eq!(f32_to_s16_clamped(0.5), 16_384);
        // NaN maps to silence rather than an edge value or a wrap.
        assert_eq!(f32_to_s16_clamped(f32::NAN), 0);
    }

    #[test]
    fn byte_pack_is_little_endian_interleaved() {
        let bytes = f32_to_s16_bytes(&[1.0, -1.0]);
        assert_eq!(bytes.len(), 4);
        assert_eq!([bytes[0], bytes[1]], 32_767i16.to_le_bytes());
        assert_eq!([bytes[2], bytes[3]], (-32_767i16).to_le_bytes());
    }

    #[test]
    fn resample_identity_preserves_length_and_content() {
        let src: Vec<f32> = (0..960).map(|n| (n as f32 * 0.01).sin()).collect();
        let got = linear_resample(&src, 2, 48_000, 48_000);
        assert_eq!(got.len(), src.len());
        assert_eq!(got.to_vec(), src.to_vec());
    }

    #[test]
    fn resample_44100_to_48000_scales_length_within_one_frame() {
        let src = vec![0.25f32; 44_100]; // 1 s mono
        let got = linear_resample(&src, 1, 44_100, 48_000);
        let want_exact = 44_100f64 * 48_000.0 / 44_100.0;
        assert!(
            (got.len() as f64 - want_exact).abs() <= 1.0,
            "len={} want≈{}",
            got.len(),
            want_exact
        );
        // Constant signal survives interpolation exactly.
        assert!(got.iter().all(|&v| (v - 0.25).abs() < 1e-6));
    }

    #[test]
    fn resample_keeps_channel_interleaving() {
        let src = vec![1.0f32, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]; // 4 stereo frames
        let got = linear_resample(&src, 2, 96_000, 48_000);
        assert_eq!(got.len(), 4); // 2 output stereo frames
        assert_eq!(got[0], 1.0); // L
        assert_eq!(got[1], 0.0); // R — channels never smear into each other
    }

    // ── §12 drift compensation ─────────────────────────────────────────────

    #[test]
    fn compensated_frame_count_squeezes_fast_and_stretches_slow_devices() {
        // +10000 ppm (device fast): 48_480 delivered → ≈48_000 nominal.
        assert_eq!(compensated_frame_count(48_480, 10_000.0), 48_000);
        // −10000 ppm (device slow): 47_520 delivered → ≈48_000.
        assert_eq!(compensated_frame_count(47_520, -10_000.0), 48_000);
        // Zero drift is an exact identity.
        assert_eq!(compensated_frame_count(1024, 0.0), 1024);
    }

    #[test]
    fn scaled_resampler_is_exact_identity_at_scale_one() {
        let src: Vec<f32> = (0..2048).map(|n| (n as f32 * 0.031).sin()).collect();
        let got = linear_resample_scaled(&src, 2, 1.0);
        assert_eq!(got, src);
    }

    #[test]
    fn scaled_resampler_matches_drift_ratio_within_one_frame_per_second() {
        // One second of a fast (+10000 ppm) device compresses to nominal.
        let src: Vec<f32> = (0..48_480).map(|n| (n as f32 * 0.007).sin()).collect();
        let got = linear_resample_scaled(&src, 1, 1_000_000.0 / 1_010_000.0);
        let want = compensated_frame_count(48_480, 10_000.0) as usize;
        assert!((got.len() as i64 - want as i64).abs() <= 1, "len={} want={}", got.len(), want);
        // Stereo interleaving survives the squeeze too.
        let st: Vec<f32> = vec![0.5f32; 48_480 * 2];
        let got_st = linear_resample_scaled(&st, 2, 1_000_000.0 / 1_010_000.0);
        assert_eq!(got_st.len(), want * 2);
    }


    #[test]
    fn pts_progression_crosses_1024_frame_boundaries_monotonically() {
        // Continuous 3-block stream: 2048 + 1024 + 1024 frames @ 48 kHz,
        // every completed packet collected after each block (production flow).
        let mut book = PtsBook::default();
        let mut stamped = Vec::new();
        let mut absolute_frame = 0u64;
        let mut block_clock_us = 0u64;
        for frames in [2_048u64, 1_024, 1_024] {
            book.record_block(absolute_frame, block_clock_us);
            absolute_frame += frames;
            block_clock_us += frames * 1_000_000 / AAC_OUTPUT_SAMPLE_RATE as u64;
            let completed_packets = absolute_frame / AAC_FRAME_FRAMES;
            while (stamped.len() as u64) < completed_packets {
                stamped.push(book.next_packet_pts());
            }
        }
        assert_eq!(stamped.len(), 4);
        let expected_step = 1_000_000.0 * AAC_FRAME_FRAMES as f64 / 48_000.0; // ≈21333 µs
        for w in stamped.windows(2) {
            let delta = (w[1] - w[0]) as f64;
            assert!(
                (delta - expected_step).abs() <= 1.0,
                "delta={delta} want≈{expected_step}"
            );
        }
        assert_eq!(stamped[0], 0);
        assert_eq!(stamped[3], 63_999, "3×21333 rounded");
    }

    #[test]
    fn pts_stays_strictly_monotonic_when_emission_lags_a_full_block() {
        // Regression for the real-hardware failure: the MS AAC MFT surfaced
        // packets several blocks late, so boundary-straddling packets all
        // clamped to the newest block's PTS ([…, 100000, 100000, 100000, …]).
        // 4800-frame blocks on a 100 ms cadence make packet boundaries land
        // mid-block every time — the worst case.
        let mut book = PtsBook::default();
        let mut stamped = Vec::new();
        let mut absolute_frame = 0u64;
        let mut clock_us = 0u64;
        for _ in 0..6 {
            book.record_block(absolute_frame, clock_us);
            absolute_frame += 4_800;
            clock_us += 100_000;
            let complete = absolute_frame / AAC_FRAME_FRAMES;
            while (stamped.len() as u64) < complete {
                stamped.push(book.next_packet_pts());
            }
        }
        assert!(stamped.len() >= 20, "28 800 frames ⇒ ≥28 packets, got {}", stamped.len());
        // Continuous stream ⇒ frame-step spacing throughout. Integer PTS
        // quantization makes each step land on ⌊21333.33⌋ or ⌈⌉ (±1 µs).
        let step = AAC_FRAME_FRAMES as f64 * 1_000_000.0 / AAC_OUTPUT_SAMPLE_RATE as f64;
        for w in stamped.windows(2) {
            assert!(
                w[1] > w[0],
                "PTS must be strictly monotonic: {} then {}",
                w[0],
                w[1]
            );
            assert!(
                (w[1] - w[0]) as f64 - step <= 1.0,
                "boundary-straddling packets keep the grid: {}→{}",
                w[0],
                w[1]
            );
        }
    }

    #[test]
    fn loopback_silence_gap_restarts_timeline_at_resuming_anchor() {
        // Two blocks, a long silent span (no blocks delivered), then audio
        // resumes with a jumped QPC. The packet straddling the boundary keeps
        // its pre-gap sample-time (its first sample is pre-gap); the first
        // fully post-gap packet stamps at the resuming block's true wall
        // clock — never backwards, never extrapolated across the gap.
        let mut book = PtsBook::default();
        book.record_block(0, 0);
        book.record_block(4_800, 100_000);
        for _ in 0..9 {
            let _ = book.next_packet_pts(); // packets start frames 0…8192
        }
        // Silence: nothing recorded. Resume at +500 ms wall clock.
        book.record_block(9_600, 600_000);
        let straddler = book.next_packet_pts(); // start frame 9216 → pre-gap block
        assert_eq!(
            straddler,
            100_000 + (9_216 - 4_800) * 1_000_000 / 48_000,
            "pre-gap continuation stays on the old timeline"
        );
        let post_gap = book.next_packet_pts(); // start frame 10240 ≥ 9600
        assert_eq!(
            post_gap,
            600_000 + 640 * 1_000_000 / 48_000,
            "post-gap stream restarts at the resuming anchor"
        );
        assert!(post_gap > straddler);
    }

    #[test]
    fn anchor_ring_prunes_unreachable_entries() {
        // Production drains every completed packet after each block, so the
        // un-stamped window is bounded by the encoder's emission lag — the
        // ring must stay tiny over hours of feeding instead of growing.
        let mut book = PtsBook::default();
        let mut stamped = 0u64;
        for b in 0..10_000u64 {
            book.record_block(b * 4_800, b * 100_000);
            let complete = (b + 1) * 4_800 / AAC_FRAME_FRAMES;
            while stamped < complete {
                let _ = book.next_packet_pts();
                stamped += 1;
            }
        }
        assert!(
            book.anchors.len() <= 4,
            "ring must stay tiny, got {}",
            book.anchors.len()
        );
        // And stamping remains correct afterwards.
        let pts = book.next_packet_pts();
        assert!(pts > 0);
    }

    #[test]
    fn pre_stream_offsets_fall_back_to_first_anchor() {
        // Defensive paths: stamping before any block was recorded yields 0,
        // and a packet starting before the earliest retained anchor stamps at
        // that anchor rather than wrapping or panicking.
        let mut book = PtsBook::default();
        assert_eq!(book.next_packet_pts(), 0, "no anchors yet");

        let mut late_anchor = PtsBook::default();
        late_anchor.record_block(500, 1_000_000);
        assert_eq!(
            late_anchor.next_packet_pts(),
            1_000_000,
            "packet start frame 0 predates the first anchor"
        );
        // Next packet starts at 1024 ≥ 500 and interpolates inside it.
        assert_eq!(
            late_anchor.next_packet_pts(),
            1_000_000 + (1_024 - 500) * 1_000_000 / AAC_OUTPUT_SAMPLE_RATE as u64
        );
    }

    #[test]
    fn asc_matches_muxer_contract_for_allowed_channel_counts() {
        // Ties §10 ("mono stays mono") to the muxer's ASC builder: every
        // channel count this encoder accepts must produce a valid ASC record.
        for ch in [1u32, 2] {
            assert!(
                crate::muxer::tracks::build_aac_asc(AAC_OUTPUT_SAMPLE_RATE, ch).is_some(),
                "chanCfg={ch} must map to a valid ASC"
            );
        }
        // …and nothing outside [1,2] is accepted by MfAacEncoder::new anyway.
        assert!(crate::muxer::tracks::build_aac_asc(AAC_OUTPUT_SAMPLE_RATE, 6).is_some());
    }

    #[test]
    fn new_validates_purely_before_touching_the_os() {
        let info = |ch: u32, rate: u32| AudioDeviceInfo {
            available: true,
            endpoint_name: "probe".into(),
            device_id: "probe".into(),
            channels: ch,
            sample_rate: rate,
            is_float: true,
        };
        assert!(MfAacEncoder::new(&info(0, 48_000), 128_000)
            .unwrap_err()
            .contains("AAC_UNSUPPORTED_CHANNEL_COUNT"));
        assert!(MfAacEncoder::new(&info(6, 48_000), 128_000)
            .unwrap_err()
            .contains("AAC_UNSUPPORTED_CHANNEL_COUNT"));
        assert!(MfAacEncoder::new(&info(2, 0), 128_000)
            .unwrap_err()
            .contains("AAC_INVALID_INPUT_RATE"));
        assert!(MfAacEncoder::new(&info(2, 48_000), 8_000)
            .unwrap_err()
            .contains("AAC_BITRATE_OUT_OF_RANGE"));
        assert!(MfAacEncoder::new(&info(2, 48_000), 600_000)
            .unwrap_err()
            .contains("AAC_BITRATE_OUT_OF_RANGE"));
    }

    #[test]
    fn present_degrades_gracefully() {
        // Hardware-dependent smoke — never panics; off-Windows is false.
        let _ = mf_aac_encoder_present();
        #[cfg(not(windows))]
        assert!(!mf_aac_encoder_present());
    }

    #[cfg(not(windows))]
    #[test]
    fn encoder_fails_closed_off_windows() {
        let mut enc = MfAacEncoder::new(
            &AudioDeviceInfo {
                available: true,
                endpoint_name: String::new(),
                device_id: String::new(),
                channels: 2,
                sample_rate: 48_000,
                is_float: true,
            },
            128_000,
        );
        assert_eq!(enc.unwrap_err(), "MF_UNSUPPORTED_OS");
    }

    #[cfg(windows)]
    #[test]
    fn real_encode_round_trip_when_mft_present() {
        if !mf_aac_encoder_present() {
            eprintln!("skipping: no Media Foundation AAC MFT on this host");
            return;
        }
        let mut enc = MfAacEncoder::new(
            &AudioDeviceInfo {
                available: true,
                endpoint_name: "probe".into(),
                device_id: "probe".into(),
                channels: 1, // §10: mono stays mono end-to-end
                sample_rate: 48_000,
                is_float: true,
            },
            96_000,
        )
        .expect("present MFT must activate");
        assert_eq!(enc.output_sample_rate(), 48_000);
        assert_eq!(enc.output_channels(), 1);

        let mut all_packets = Vec::new();
        for b in 0..6u64 {
            let block = super::super::PcmBlock {
                samples: (0..4_800).map(|n| ((b * 4_800 + n) % 240) as f32 / 240.0 - 0.5).collect(),
                channels: 1,
                sample_rate: 48_000,
                qpc: crate::clock::qpc_now(),
            };
            let packets = enc.encode_block(&block, b * 100_000).expect("encode");
            for p in &packets {
                assert_eq!(p.sample_count, AAC_FRAME_FRAMES);
                assert!(!p.data.is_empty(), "raw AAC frames carry payload");
            }
            all_packets.extend(packets);
        }
        assert!(!all_packets.is_empty(), "28 800 frames ⇒ ≥28 packets");
        let pts_seq: Vec<u64> = all_packets.iter().map(|p| p.pts_us).collect();
        eprintln!("PTS sequence ({}): {:?}", pts_seq.len(), pts_seq);
        let sizes: Vec<usize> = all_packets.iter().map(|p| p.data.len()).collect();
        eprintln!("packet byte sizes: {:?}", sizes);
        for w in all_packets.windows(2) {
            assert!(
                w[1].pts_us > w[0].pts_us,
                "PTS strictly monotonic: {} then {} (sample_counts {}→{})",
                w[0].pts_us,
                w[1].pts_us,
                w[0].sample_count,
                w[1].sample_count
            );
        }
        let drained = enc.drain().expect("drain");
        if let (Some(last), Some(first_drained)) = (all_packets.last(), drained.first()) {
            assert!(first_drained.pts_us > last.pts_us, "drain continues the PTS line");
        }
        // Sticky-fault culture: a healthy session never sets one.
        assert!(matches!(enc.encode_block(
            &super::super::PcmBlock {
                samples: vec![0.0; 480],
                channels: 1,
                sample_rate: 48_000,
                qpc: crate::clock::qpc_now()
            },
            999_999
        ), Ok(_)));
    }
}
