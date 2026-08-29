//! Segmented MKV writer on top of the runtime-loaded libavformat
//! (ban_ke_hoach_v1.md §9).
//!
//! ```text
//! open_segment ──► alloc ctx("matroska") + AVStream per track + avio(.tmp)
//!      │            (codecpar filled EXCEPT extradata; header NOT written)
//!      ▼
//! set_video_extradata(avcC|hvcC) / set_audio_extradata(track, ASC)
//!      ▼
//! write_packet ×N ──► first call flushes the header (lazy), then
//!      │              av_new_packet → memcpy → rescale → interleaved write
//!      ▼
//! close_segment ──► trailer → avio close → fsync → atomic rename → report
//! ```
//!
//! ## Lazy-header handshake (extradata is staged before the first packet)
//!
//! NVENC emits Annex-B, so the avcC/hvcC record a Matroska track needs must
//! be built from the codec parameter sets. They come from
//! `NvEncGetSequenceParams`, fetched once at session init (`nvenc_session`)
//! — NOT scraped from the first keyframe, because under lookahead an AAC
//! packet can arrive before NVENC emits any video packet. The mux driver:
//!
//! 1. calls [`MuxerPort::open_segment`] — streams and codec params are laid
//!    out but `avformat_write_header` is deferred;
//! 2. immediately stages avcC/hvcC (built once per session from the sequence
//!    header via [`crate::muxer::tracks::split_annex_b`] plus
//!    `build_avcc`/`build_hvcc`) and one `build_aac_asc` per audio track via
//!    [`MuxerPort::stage_video_extradata`] / [`MuxerPort::stage_audio_extradata`];
//! 3. the first [`MuxerPort::write_packet`] — of whichever track arrives
//!    first — flushes the staged extradata into `codecpar` and writes the
//!    header exactly once.
//!
//! Fail-closed: a video track without `set_video_extradata` before the first
//! packet errors `MKV_EXTRADATA_MISSING` — a header-less MKV stream is never
//! produced silently.
//!
//! ## Ownership / memory rules
//!
//! - Packets: payload bytes are copied into an `av_new_packet` refcounted
//!   buffer; `av_interleaved_write_frame` consumes the reference and the
//!   packet is unref'd after every attempt.
//! - Extradata: copied into `av_mallocz` buffers because
//!   `avformat_free_context` releases `par->extradata` with `av_free` —
//!   Rust-owned memory here would free across allocator boundaries.
//! - Files: each segment writes to `{dir}/segment_NNNN.mkv.tmp`, is finished
//!   (trailer + fsync) and atomically renamed, so any file without `.tmp`
//!   is committed by construction (crash-recovery contract §15).
//!
//! Threading: libav touches no COM, so unlike the capture/WASAPI modules no
//! `CoInitializeEx` is needed; the engine confines one muxer to the pipeline's
//! dedicated mux thread (`pipeline.rs` §3).

use super::timestamps::{pts_from_micros, TIMEBASE_DEN};
use super::{MuxedSegment, MuxerPort, TrackId, TrackParams};
use crate::encoder::EncodedPacket;
#[cfg(not(windows))]
use crate::muxer::LIBAV_UNAVAILABLE;

/// Per-track stream bookkeeping for the open segment.
#[derive(Debug, Clone, Copy)]
struct Slot {
    id: TrackId,
    /// `AVStream->index` handed to `AVPacket.stream_index`.
    index: i32,
}

/// State of the currently open segment file. Lives only between successful
/// `open_segment` and `close_segment`; [`SegmentState::drop`] is a leak guard
/// for error paths that abandon native handles mid-open.
struct SegmentState {
    index: u32,
    tmp_path: String,
    final_path: String,
    slots: Vec<Slot>,
    /// Set once `avformat_write_header` succeeded.
    header_written: bool,
    /// avcC/hvcC bytes staged by `set_video_extradata`, flushed at first packet.
    video_extradata: Option<Vec<u8>>,
    /// ASC bytes per audio track, same lazy flush.
    audio_extradata: Vec<(TrackId, Vec<u8>)>,
    first_pts_us: Option<u64>,
    last_pts_us: Option<i64>,
    /// Per-slot last PTS (presentation time, 1/TIMEBASE_DEN ticks) — one entry per slot.
    /// Zero is valid and preserved. With B-frames, PTS in decode (written) order
    /// is NOT monotonic — a B-frame's PTS can be earlier than the preceding P's
    /// PTS (e.g., decode order I0/P3/B1/B2 has PTS 0, 100k, 33k, 66k). Therefore
    /// PTS monotonic is presentation-order: the muxer does not enforce PTS
    /// monotonic in written order when DTS != PTS; it preserves PTS verbatim
    /// and relies on DTS monotonic to keep decode order valid. Gross PTS
    /// regressions where DTS > PTS are still rejected. See validate_packet_contract.
    last_pts_by_slot: Vec<Option<i64>>,
    /// Per-slot last DTS (decode time, 1/TIMEBASE_DEN ticks) for monotonic enforcement
    /// in written (decode) order — the exact order packets are interleaved into
    /// Matroska. DTS must be nondecreasing per slot; regression is fail-closed.
    /// Zero is valid; DTS <= PTS (decode before presentation) is enforced.
    last_dts_by_slot: Vec<Option<i64>>,
    bytes_written: u64,
    #[cfg(windows)]
    ctx: *mut crate::muxer::libav_loader::AVFormatContext,
    #[cfg(windows)]
    pkt: *mut crate::muxer::libav_loader::AVPacket,
    /// One `*mut AVStream` per slot, in slot order (the post-header time_base
    /// is read through these when stamping packets).
    #[cfg(windows)]
    streams: Vec<*mut crate::muxer::libav_loader::AVStream>,
}

impl Drop for SegmentState {
    fn drop(&mut self) {
        // Safety net only — normal teardown happens explicitly in
        // `close_native`, which nulls both handles first. Without this guard
        // an error return between alloc and trailer would leak native memory.
        #[cfg(windows)]
        {
            if self.ctx.is_null() && self.pkt.is_null() {
                return;
            }
            let Ok(rt) = crate::muxer::libav_loader::LibavRuntime::load() else { return };
            if !self.ctx.is_null() {
                // SAFETY: ctx is non-null and owned exclusively by this state.
                unsafe {
                    let prefix =
                        self.ctx as *mut crate::muxer::libav_loader::AVFormatContextPrefix;
                    let pb = core::ptr::addr_of_mut!((*prefix).pb);
                    if !(*pb).is_null() {
                        let _ = rt.io_close(pb);
                    }
                    rt.free_context(self.ctx);
                }
                self.ctx = core::ptr::null_mut();
            }
            if !self.pkt.is_null() {
                rt.packet_free(core::ptr::addr_of_mut!(self.pkt));
                self.pkt = core::ptr::null_mut();
            }
        }
    }
}

/// Native MKV muxer backed by runtime-resolved libavformat (§9). Constructed
/// by the pipeline; [`crate::muxer::LIBAV_UNAVAILABLE`] surfaces from
/// [`MuxerPort::prepare`] when the shared libraries are absent.
pub struct LibavMuxer {
    output_dir: Option<String>,
    seg: Option<SegmentState>,
    /// Highest segment index accepted so far — reopen/regressions are
    /// rejected fail-closed (`MKV_SEGMENT_INDEX_REGRESSION`).
    last_open_index: Option<u32>,
}

impl LibavMuxer {
    pub fn new() -> Self {
        Self { output_dir: None, seg: None, last_open_index: None }
    }

    /// Stage avcC/hvcC extradata for the video track. MUST be called after
    /// [`MuxerPort::open_segment`] and before the first
    /// [`MuxerPort::write_packet`] — see the module docs for the handshake.
    pub fn set_video_extradata(&mut self, avcc_or_hvcc: Vec<u8>) -> Result<(), String> {
        if avcc_or_hvcc.is_empty() {
            return Err("MKV_EXTRADATA_EMPTY: avcC/hvcC must not be empty".into());
        }
        let seg = self.seg.as_mut().ok_or(
            "MKV_SEGMENT_NOT_OPEN: set_video_extradata requires an open segment",
        )?;
        if seg.header_written {
            return Err("MKV_HEADER_ALREADY_WRITTEN: too late to stage video extradata".into());
        }
        seg.video_extradata = Some(avcc_or_hvcc);
        Ok(())
    }

    /// Stage AAC AudioSpecificConfig bytes for one audio track. Same timing
    /// contract as [`LibavMuxer::set_video_extradata`].
    pub fn set_audio_extradata(&mut self, track: TrackId, asc: Vec<u8>) -> Result<(), String> {
        if asc.len() < 2 {
            return Err(format!(
                "MKV_EXTRADATA_EMPTY: ASC for {} must be ≥2 bytes, got {}",
                track.as_str(),
                asc.len()
            ));
        }
        let seg = self.seg.as_mut().ok_or(
            "MKV_SEGMENT_NOT_OPEN: set_audio_extradata requires an open segment",
        )?;
        if seg.header_written {
            return Err("MKV_HEADER_ALREADY_WRITTEN: too late to stage audio extradata".into());
        }
        if !seg.slots.iter().any(|s| s.id == track) {
            return Err(format!(
                "MKV_UNKNOWN_TRACK: {} has no stream in this segment",
                track.as_str()
            ));
        }
        seg.audio_extradata.retain(|(t, _)| *t != track);
        seg.audio_extradata.push((track, asc));
        Ok(())
    }

    // ── Pure helpers (unit-tested below, platform-independent) ──

    fn tmp_path(dir: &str, index: u32) -> String {
        format!("{}/segment_{index:04}.mkv.tmp", dir.trim_end_matches(['/', '\\']))
    }

    fn final_path(dir: &str, index: u32) -> String {
        format!("{}/segment_{index:04}.mkv", dir.trim_end_matches(['/', '\\']))
    }

    /// Tokenized delivery ref `take_xxx/segment_NNNN.mkv` — the take folder
    /// name comes from the output dir's last component; a bare root falls
    /// back to `segment_NNNN.mkv`. Never a raw absolute path.
    fn delivery_token(dir: &str, index: u32) -> String {
        match std::path::Path::new(dir).file_name().and_then(std::ffi::OsStr::to_str) {
            Some(folder) if !folder.is_empty() => format!("{folder}/segment_{index:04}.mkv"),
            _ => format!("segment_{index:04}.mkv"),
        }
    }

    /// Monotonic open-sequence guard: indexes may only increase within a take.
    fn assert_index_sequence(prev: Option<u32>, next: u32) -> Result<(), String> {
        match prev {
            Some(last) if next <= last => Err(format!(
                "MKV_SEGMENT_INDEX_REGRESSION: cannot open segment {next} after {last}"
            )),
            _ => Ok(()),
        }
    }

    /// V2 records mic/system as mono or stereo only — anything else is a
    /// contract violation, not something to downmix silently.
    fn channel_mask(channels: u32) -> Result<u64, String> {
        match channels {
            1 => Ok(0b1),
            2 => Ok(0b11),
            n => Err(format!(
                "MKV_CHANNEL_LAYOUT_UNSUPPORTED: {n} channels (V2 allows mono|stereo)"
            )),
        }
    }

    fn validate_layout(tracks: &[(TrackId, TrackParams)]) -> Result<(), String> {
        if tracks.is_empty() {
            return Err("MKV_TRACK_LAYOUT_EMPTY: open_segment needs at least one track".into());
        }
        if let Some(pos) = tracks.iter().position(|(id, _)| matches!(id, TrackId::Video)) {
            if pos != 0 {
                return Err(
                    "MKV_TRACK_ORDER_INVALID: video must be tracks[0] when present".into()
                );
            }
            if !matches!(
                tracks[0].1,
                TrackParams::VideoH264 { .. } | TrackParams::VideoHevc { .. }
            ) {
                return Err(
                    "MKV_TRACK_ORDER_INVALID: TrackId::Video paired with non-video params".into()
                );
            }
        }
        for (n, (id, params)) in tracks.iter().enumerate() {
            if tracks[n + 1..].iter().any(|(other, _)| other == id) {
                return Err(format!("MKV_TRACK_DUPLICATED: {} appears twice", id.as_str()));
            }
            if let TrackParams::Aac { sample_rate, channels } = params {
                if *sample_rate != 48_000 {
                    return Err(format!(
                        "MKV_SAMPLE_RATE_UNSUPPORTED: {sample_rate} Hz (V2 contract locks 48000)"
                    ));
                }
                if Self::channel_mask(*channels).is_err() {
                    return Err(Self::channel_mask(*channels).unwrap_err());
                }
            }
        }
        Ok(())
    }

    /// Pure packet contract validation extracted for testability (no libav needed).
    /// Validates B-frame-capable timestamps without fabricating them:
    /// - non-empty, codec matches slot
    /// - zero PTS is valid and preserved
    /// - PTS is presentation time; DTS is decode time. Both are carried in
    ///   1/TIMEBASE_DEN ticks (pts_from_micros / dts_us). DTS must be >=0 and
    ///   <= PTS (decode before or at presentation); DTS monotonic is enforced
    ///   in written (decode) order per slot. PTS monotonic in presentation
    ///   order is not enforced in written order when B-frames reorder
    ///   (e.g., decode I0/P3/B1/B2 has PTS 0,100k,33k,66k) — the muxer preserves
    ///   both fields verbatim via AVPacket pts/dts + av_packet_rescale_ts.
    /// Returns slot index + PTS ticks on success.
    #[cfg(any(windows, test))]
    fn validate_packet_contract(
        seg: &SegmentState,
        track: TrackId,
        packet: &EncodedPacket,
    ) -> Result<(usize, i64), String> {
        let slot_idx = seg.slots.iter().position(|s| s.id == track).ok_or_else(|| {
            format!("MKV_UNKNOWN_TRACK: {} has no stream in this segment", track.as_str())
        })?;
        if packet.data.is_empty() {
            return Err("MKV_PACKET_EMPTY: video/audio packet data must not be empty".into());
        }
        let codec_ok = match seg.slots[slot_idx].id {
            TrackId::Video => packet.codec == "H264" || packet.codec == "HEVC",
            TrackId::Mic | TrackId::System => packet.codec == "AAC",
        };
        if !codec_ok {
            return Err(format!(
                "MKV_CODEC_MISMATCH: track {} expects {} but packet carries {}",
                track.as_str(),
                match seg.slots[slot_idx].id {
                    TrackId::Video => "H264|HEVC",
                    _ => "AAC",
                },
                packet.codec
            ));
        }
        let this_pts = pts_from_micros(packet.pts_us);
        let this_dts = packet.dts_us;
        if this_pts < 0 {
            return Err(format!(
                "TIMESTAMP_INVALID: {} track pts {} <0 (pts_us {})",
                track.as_str(),
                this_pts,
                packet.pts_us
            ));
        }
        if this_dts < 0 {
            return Err(format!(
                "TIMESTAMP_INVALID: {} track dts {} <0 (pts_us {})",
                track.as_str(),
                this_dts,
                packet.pts_us
            ));
        }
        if this_dts > this_pts {
            return Err(format!(
                "TIMESTAMP_INVALID: {} track dts {} > pts {} (decode after presentation) pts_us {}",
                track.as_str(),
                this_dts,
                this_pts,
                packet.pts_us
            ));
        }
        // DTS monotonic in written (decode) order per slot — B-frames are
        // emitted in decode order, so DTS must be nondecreasing.
        if let Some(prev_dts) = seg.last_dts_by_slot.get(slot_idx).and_then(|o| *o) {
            if this_dts < prev_dts {
                return Err(format!(
                    "TIMESTAMP_REGRESSION: {} track dts {} < prev {} (pts_us {} < {})",
                    track.as_str(),
                    this_dts,
                    prev_dts,
                    packet.pts_us,
                    seg.first_pts_us.unwrap_or(0)
                ));
            }
        }
        // PTS is preserved verbatim; when DTS==PTS (no B-frames) the DTS
        // monotonic check already enforces PTS monotonic in written order.
        // When DTS != PTS, PTS in written order may legitimately go backward
        // (e.g., 0, 100k, 33k) so we do not enforce PTS monotonic here. The
        // encoder's VideoConfig.b_frames and NvencSession has_b_frames DTS logic
        // already produce valid DTS<=PTS pairs; the muxer validates and
        // preserves them via AVPacket + av_packet_rescale_ts without rewriting.
        Ok((slot_idx, this_pts))
    }

    // ── Native bodies (Windows only; each takes the runtime explicitly so
    //    no path ever calls load() twice mid-operation) ──

    #[cfg(windows)]
    fn open_native(
        rt: &'static crate::muxer::libav_loader::LibavRuntime,
        dir: &str,
        index: u32,
        tracks: &[(TrackId, TrackParams)],
    ) -> Result<SegmentState, String> {
        use crate::muxer::libav_loader::{
            AV_CHANNEL_ORDER_NATIVE, AVMEDIA_TYPE_AUDIO, AVMEDIA_TYPE_VIDEO, AV_CODEC_ID_AAC,
            AV_CODEC_ID_H264, AV_CODEC_ID_HEVC, AV_PIX_FMT_YUV420P, AVChannelLayout,
            AVCodecParameters, AVStreamPrefix, AVStreamTimingPrefix, AVRational,
        };

        // The matroska muxer must exist in the loaded DLL — a stripped build
        // would otherwise fail much later, mid-recording.
        if rt.guess_format("matroska").is_none() {
            return Err("MKV_FORMAT_MISSING: av_guess_format(\"matroska\") returned NULL".into());
        }
        let ctx = rt
            .alloc_output_context("matroska")
            .map_err(|e| format!("MKV_ALLOC_FAILED:{e}"))?;

        let mut state = SegmentState {
            index,
            tmp_path: Self::tmp_path(dir, index),
            final_path: Self::final_path(dir, index),
            slots: Vec::with_capacity(tracks.len()),
            header_written: false,
            video_extradata: None,
            audio_extradata: Vec::new(),
            first_pts_us: None,
            last_pts_us: None,
            last_pts_by_slot: vec![None; tracks.len()],
            last_dts_by_slot: vec![None; tracks.len()],
            bytes_written: 0,
            ctx,
            pkt: core::ptr::null_mut(),
            streams: Vec::with_capacity(tracks.len()),
        };

        for (slot_no, (id, params)) in tracks.iter().enumerate() {
            // Compute everything fallible BEFORE allocating the stream so an
            // error cannot strand half-built native state in this iteration.
            let (codec_id, mask, sample_rate) = match params {
                TrackParams::VideoH264 { .. } => (AV_CODEC_ID_H264, 0u64, 0u32),
                TrackParams::VideoHevc { .. } => (AV_CODEC_ID_HEVC, 0u64, 0u32),
                TrackParams::Aac { sample_rate, channels } => {
                    let mask = match Self::channel_mask(*channels) {
                        Ok(m) => m,
                        Err(e) => {
                            rt.free_context(ctx);
                            return Err(e);
                        }
                    };
                    (AV_CODEC_ID_AAC, mask, *sample_rate)
                }
            };

            let st = match rt.new_stream(ctx) {
                Ok(st) => st,
                Err(e) => {
                    rt.free_context(ctx);
                    return Err(format!("MKV_ALLOC_FAILED:{e}"));
                }
            };
            let par = unsafe { (*(st as *const AVStreamPrefix)).codecpar };
            if par.is_null() {
                rt.free_context(ctx);
                return Err("MKV_CODECPAR_NULL: new stream carries no codec parameters".into());
            }

            unsafe {
                (*par.cast::<AVCodecParameters>()).codec_type = match params {
                    TrackParams::Aac { .. } => AVMEDIA_TYPE_AUDIO,
                    _ => AVMEDIA_TYPE_VIDEO,
                };
                (*par.cast::<AVCodecParameters>()).codec_id = codec_id;
                // Matroska derives its track entries from codec_id alone;
                // tag stays 0 so the muxer picks its own fourcc.
                (*par.cast::<AVCodecParameters>()).codec_tag = 0;
                match params {
                    TrackParams::VideoH264 { width, height, fps }
                    | TrackParams::VideoHevc { width, height, fps } => {
                        (*par.cast::<AVCodecParameters>()).width = *width as i32;
                        (*par.cast::<AVCodecParameters>()).height = *height as i32;
                        (*par.cast::<AVCodecParameters>()).format = AV_PIX_FMT_YUV420P;
                        (*par.cast::<AVCodecParameters>()).sample_aspect_ratio =
                            AVRational { num: 1, den: 1 }; // square pixels
                        (*par.cast::<AVCodecParameters>()).framerate =
                            AVRational { num: *fps as i32, den: 1 };
                    }
                    TrackParams::Aac { channels, .. } => {
                        (*par.cast::<AVCodecParameters>()).sample_rate = sample_rate as i32;
                        (*par.cast::<AVCodecParameters>()).ch_layout = AVChannelLayout {
                            order: AV_CHANNEL_ORDER_NATIVE,
                            nb_channels: *channels as i32,
                            mask,
                            opaque: core::ptr::null_mut(),
                        };
                    }
                }

                // Stream-level timing hints through the verified prefix mirror:
                // time_base = microseconds (§9/§12); avg_frame_rate for video.
                let stp = st.cast::<AVStreamTimingPrefix>();
                (*stp).time_base = AVRational { num: 1, den: TIMEBASE_DEN as i32 };
                if let TrackParams::VideoH264 { fps, .. } | TrackParams::VideoHevc { fps, .. } =
                    params
                {
                    (*stp).avg_frame_rate = AVRational { num: *fps as i32, den: 1 };
                }
            }

            state.slots.push(Slot { id: *id, index: slot_no as i32 });
            state.streams.push(st);
        }

        match rt.packet_alloc() {
            Ok(pkt) => state.pkt = pkt,
            Err(e) => {
                rt.free_context(ctx);
                return Err(format!("MKV_ALLOC_FAILED:{e}"));
            }
        }

        let url = nul_terminated(&state.tmp_path)?;
        // SAFETY: ctx was just allocated by libav and is exclusively ours.
        let pb = unsafe {
            let prefix = ctx as *mut crate::muxer::libav_loader::AVFormatContextPrefix;
            core::ptr::addr_of_mut!((*prefix).pb)
        };
        if let Err(e) = rt.io_open(pb, url.to_string_lossy().as_ref()) {
            rt.packet_free(core::ptr::addr_of_mut!(state.pkt));
            rt.free_context(ctx);
            return Err(format!("MKV_OPEN_FAILED:{e}"));
        }
        Ok(state)
    }

    /// Apply staged extradata into codecpar and write the header exactly once.
    #[cfg(windows)]
    fn flush_header(
        rt: &'static crate::muxer::libav_loader::LibavRuntime,
        seg: &mut SegmentState,
    ) -> Result<(), String> {
        use crate::muxer::libav_loader::AVStreamPrefix;

        if seg.header_written {
            return Ok(());
        }
        // Video must carry avcC/hvcC before any packet is written.
        if let Some(vpos) = seg.slots.iter().position(|s| matches!(s.id, TrackId::Video)) {
            match &seg.video_extradata {
                Some(extradata) => {
                    let par =
                        unsafe { (*(seg.streams[vpos] as *const AVStreamPrefix)).codecpar };
                    apply_extradata(rt, par, extradata)?;
                }
                None => {
                    return Err(
                        "MKV_EXTRADATA_MISSING: set_video_extradata(avcc|hvcC) must be called before the first packet (see muxer/libav.rs handshake)".into()
                    );
                }
            }
        }
        for (track, asc) in seg.audio_extradata.iter() {
            let pos = seg.slots.iter().position(|s| &s.id == track).ok_or_else(|| {
                format!("MKV_UNKNOWN_TRACK: {} missing at header time", track.as_str())
            })?;
            let par = unsafe { (*(seg.streams[pos] as *const AVStreamPrefix)).codecpar };
            apply_extradata(rt, par, asc)?;
        }
        rt.write_header(seg.ctx).map_err(|e| format!("MKV_HEADER_FAILED:{e}"))?;
        seg.header_written = true;
        Ok(())
    }

    #[cfg(windows)]
    fn write_native(
        rt: &'static crate::muxer::libav_loader::LibavRuntime,
        seg: &mut SegmentState,
        track: TrackId,
        packet: &EncodedPacket,
    ) -> Result<(), String> {
        use crate::muxer::libav_loader::{
            AVPacketPartial, AVStreamTimingPrefix, AV_PKT_FLAG_KEY, AVRational,
        };

        Self::flush_header(rt, seg)?;
        // Pure contract checks (slot lookup, empty, codec, per-track DTS monotonic with zero valid, PTS/DTS B-frame semantics preserved).
        let (slot_idx, _this_pts) = Self::validate_packet_contract(seg, track, packet)?;
        let len = packet.data.len();
        if len > i32::MAX as usize {
            return Err(format!("MKV_PACKET_TOO_LARGE: {len} bytes exceeds AVPacket capacity"));
        }

        let pkt = seg.pkt;
        rt.new_packet(pkt, len as i32).map_err(|e| format!("MKV_ALLOC_FAILED:{e}"))?;

        let p = pkt as *mut AVPacketPartial;
        unsafe {
            if len > 0 {
                core::ptr::copy_nonoverlapping(packet.data.as_ptr(), (*p).data, len);
            }
            (*p).size = len as i32;
            (*p).pts = pts_from_micros(packet.pts_us);
            (*p).dts = packet.dts_us;
            (*p).duration = 0;
            (*p).pos = -1;
            (*p).flags = if packet.is_keyframe { AV_PKT_FLAG_KEY } else { 0 };
            (*p).stream_index = seg.slots[slot_idx].index;

            // Rescale µs → the stream's post-header time_base. Same basis ⇒
            // identity today, but keep the call so a muxer-side time_base
            // change can never corrupt timestamps silently (§12).
            let st = seg.streams[slot_idx];
            let dst_tb = core::ptr::read_unaligned(
                core::ptr::addr_of!((*(st as *const AVStreamTimingPrefix)).time_base),
            );
            rt.rescale_ts(pkt, AVRational { num: 1, den: TIMEBASE_DEN as i32 }, dst_tb);
        }
        if let Err(e) = rt.interleaved_write_frame(seg.ctx, pkt) {
            rt.packet_unref(pkt);
            return Err(format!("MKV_WRITE_FAILED:{e}"));
        }
        rt.packet_unref(pkt);

        seg.bytes_written += len as u64;
        seg.first_pts_us.get_or_insert(packet.pts_us);
        // Monotonic bookkeeping: store exactly, never silently max() — DTS regression is fail-closed above.
        // Preserve both PTS and DTS verbatim; DTS monotonic (written order) is the decode-order invariant.
        seg.last_pts_us = Some(pts_from_micros(packet.pts_us));
        if slot_idx < seg.last_pts_by_slot.len() {
            seg.last_pts_by_slot[slot_idx] = Some(pts_from_micros(packet.pts_us));
        }
        if slot_idx < seg.last_dts_by_slot.len() {
            seg.last_dts_by_slot[slot_idx] = Some(packet.dts_us);
        }
        Ok(())
    }

    #[cfg(windows)]
    fn close_native(
        rt: &'static crate::muxer::libav_loader::LibavRuntime,
        out_dir: &str,
        mut seg: SegmentState,
    ) -> Result<MuxedSegment, String> {
        use crate::muxer::libav_loader::AVFormatContextPrefix;

        if !seg.header_written {
            return Err(
                "MKV_SEGMENT_EMPTY: closed before any packet — refusing to emit an unplayable file"
                    .into(),
            );
        }
        if let Err(e) = rt.write_trailer(seg.ctx) {
            return Err(format!("MKV_TRAILER_FAILED:{e}")); // Drop guard cleans up
        }
        // SAFETY: seg.ctx is a live libav allocation owned by this segment.
        let pb = unsafe {
            let prefix = seg.ctx as *mut AVFormatContextPrefix;
            core::ptr::addr_of_mut!((*prefix).pb)
        };
        rt.io_close(pb).map_err(|e| format!("MKV_CLOSE_FAILED:{e}"))?;
        rt.packet_free(core::ptr::addr_of_mut!(seg.pkt));
        rt.free_context(seg.ctx);
        seg.pkt = core::ptr::null_mut();
        seg.ctx = core::ptr::null_mut();

        // Commit: fsync then atomic rename (§15 crash-safety). The write
        // handle is gone with the AVIO context, so reopen for WRITE —
        // FlushFileBuffers requires GENERIC_WRITE; a read-only handle fails
        // with Access denied on Windows.
        let file = std::fs::OpenOptions::new()
            .write(true)
            .open(&seg.tmp_path)
            .map_err(|e| format!("MKV_FSYNC_FAILED:{} ({e})", seg.tmp_path))?;
        file.sync_all()
            .map_err(|e| format!("MKV_FSYNC_FAILED:{} ({e})", seg.tmp_path))?;
        drop(file);
        std::fs::rename(&seg.tmp_path, &seg.final_path).map_err(|e| {
            format!("MKV_RENAME_FAILED:{} → {} ({e})", seg.tmp_path, seg.final_path)
        })?;

        let duration_sec = match (seg.first_pts_us, seg.last_pts_us) {
            (Some(first), Some(last)) => ((last - first as i64).max(0)) as f64 / 1_000_000.0,
            _ => 0.0,
        };
        let byte_len = std::fs::metadata(&seg.final_path)
            .map(|m| m.len())
            .map_err(|e| format!("MKV_STAT_FAILED:{} ({e})", seg.final_path))?;
        Ok(MuxedSegment {
            index: seg.index,
            file_token: Self::delivery_token(out_dir, seg.index),
            duration_sec,
            byte_len,
            // Reached only after trailer + fsync + rename all succeeded.
            is_playable: true,
        })
    }
}

impl Default for LibavMuxer {
    fn default() -> Self {
        Self::new()
    }
}

/// Copy `bytes` into an `av_mallocz` buffer owned by libav and attach it as
/// `codecpar` extradata (avcC/hvcC/ASC). libavformat frees it via `av_free`
/// during `avformat_free_context` — hence the libav-side allocation.
#[cfg(windows)]
fn apply_extradata(
    rt: &'static crate::muxer::libav_loader::LibavRuntime,
    par: *mut crate::muxer::libav_loader::AVCodecParameters,
    bytes: &[u8],
) -> Result<(), String> {
    if par.is_null() {
        return Err("MKV_CODECPAR_NULL: cannot attach extradata".into());
    }
    let buf = rt.mallocz(bytes.len()).map_err(|e| format!("MKV_ALLOC_FAILED:{e}"))?;
    unsafe {
        core::ptr::copy_nonoverlapping(bytes.as_ptr(), buf, bytes.len());
        (*par).extradata = buf;
        (*par).extradata_size = bytes.len() as i32;
    }
    Ok(())
}

#[cfg(any(windows, test))]
fn nul_terminated(s: &str) -> Result<std::ffi::CString, String> {
    std::ffi::CString::new(s).map_err(|_| format!("MKV_PATH_INVALID: embedded NUL in {s:?}"))
}

// SAFETY: the engine pins one LibavMuxer to the pipeline's dedicated mux
// thread (pipeline.rs §3); the raw libav pointers inside are never accessed
// concurrently from another thread.
#[cfg(windows)]
unsafe impl Send for LibavMuxer {}

impl MuxerPort for LibavMuxer {
    fn stage_video_extradata(&mut self, avcc_or_hvcc: &[u8]) -> Result<(), String> {
        self.set_video_extradata(avcc_or_hvcc.to_vec())
    }

    fn stage_audio_extradata(&mut self, track: TrackId, asc: &[u8]) -> Result<(), String> {
        self.set_audio_extradata(track, asc.to_vec())
    }

    fn prepare(&mut self, output_dir: &str) -> Result<(), String> {
        std::fs::create_dir_all(output_dir)
            .map_err(|e| format!("MKV_DIR_FAILED:{output_dir} ({e})"))?;
        #[cfg(windows)]
        {
            let rt = crate::muxer::libav_loader::LibavRuntime::load()?;
            if !rt.abi_supported() {
                let (f, c, u) = rt.versions();
                return Err(format!(
                    "LIBAV_ABI_MISMATCH: loaded avformat-{f}/avcodec-{c}/avutil-{u} but struct layouts are transcribed against FFmpeg 8.x (62/62/60) — install the matching shared build"
                ));
            }
            self.output_dir = Some(output_dir.to_string());
            Ok(())
        }
        #[cfg(not(windows))]
        {
            let _ = output_dir;
            Err(format!("{LIBAV_UNAVAILABLE}: libav muxer is Windows-only"))
        }
    }

    fn open_segment(&mut self, index: u32, tracks: &[(TrackId, TrackParams)]) -> Result<(), String> {
        // Order matters: every check below runs BEFORE the runtime is touched,
        // so the state-machine tests behave identically with and without DLLs.
        Self::assert_index_sequence(self.last_open_index, index)?;
        Self::validate_layout(tracks)?;
        let dir = self
            .output_dir
            .clone()
            .ok_or("MKV_NOT_PREPARED: prepare() must run before open_segment")?;
        if self.seg.is_some() {
            return Err(format!(
                "MKV_SEGMENT_ALREADY_OPEN: close segment {:04} before opening {index:04}",
                self.seg.as_ref().unwrap().index
            ));
        }
        #[cfg(windows)]
        {
            let rt = crate::muxer::libav_loader::LibavRuntime::load()?;
            self.seg = Some(Self::open_native(rt, &dir, index, tracks)?);
            // Burn the index only once the open actually succeeded so a
            // failed open can be retried with the same number.
            self.last_open_index = Some(index);
            Ok(())
        }
        #[cfg(not(windows))]
        {
            let _ = (dir, index, tracks);
            Err(format!("{LIBAV_UNAVAILABLE}: libav muxer is Windows-only"))
        }
    }

    fn write_packet(&mut self, track: TrackId, packet: &EncodedPacket) -> Result<(), String> {
        #[cfg(windows)]
        {
            let rt = crate::muxer::libav_loader::LibavRuntime::load()?;
            let seg = self
                .seg
                .as_mut()
                .ok_or("MKV_SEGMENT_NOT_OPEN: write_packet requires an open segment")?;
            Self::write_native(rt, seg, track, packet)
        }
        #[cfg(not(windows))]
        {
            let _ = (track, packet);
            Err(format!("{LIBAV_UNAVAILABLE}: libav muxer is Windows-only"))
        }
    }

    fn close_segment(&mut self) -> Result<MuxedSegment, String> {
        let seg = self
            .seg
            .take()
            .ok_or("MKV_SEGMENT_NOT_OPEN: close_segment requires an open segment")?;
        #[cfg(windows)]
        {
            let rt = crate::muxer::libav_loader::LibavRuntime::load()?;
            let dir = self.output_dir.clone().unwrap_or_default();
            Self::close_native(rt, &dir, seg)
        }
        #[cfg(not(windows))]
        {
            let _ = seg;
            Err(format!("{LIBAV_UNAVAILABLE}: libav muxer is Windows-only"))
        }
    }

    fn finalize_take(&mut self) -> Result<(), String> {
        // Each segment was already closed by its own `close_segment`; a still-
        // open segment here means the driver skipped its teardown — fail
        // closed rather than abandoning an unfinished `.tmp` file.
        if let Some(seg) = &self.seg {
            return Err(format!(
                "MKV_SEGMENT_STILL_OPEN: finalize_take with segment {:04} unclosed",
                seg.index
            ));
        }
        // Full state reset so the same muxer instance can serve the next
        // take: numbering restarts at segment_0000 (each take owns its own
        // output dir), so the monotonic guard must re-arm from scratch.
        self.output_dir = None;
        self.last_open_index = None;
        Ok(())
    }

    /// Bytes written into the currently open segment (telemetry §16).
    fn bytes_written(&self) -> u64 {
        self.seg.as_ref().map_or(0, |s| s.bytes_written)
    }
}

// ─── Tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn h264(w: u32, h: u32) -> (TrackId, TrackParams) {
        (TrackId::Video, TrackParams::VideoH264 { width: w, height: h, fps: 60 })
    }

    fn mic() -> (TrackId, TrackParams) {
        (TrackId::Mic, TrackParams::Aac { sample_rate: 48_000, channels: 1 })
    }

    #[test]
    fn segment_paths_are_stable_and_tmp_suffixed() {
        let dir = "D:/rec/take_20260825";
        assert_eq!(LibavMuxer::tmp_path(dir, 3), "D:/rec/take_20260825/segment_0003.mkv.tmp");
        assert_eq!(LibavMuxer::final_path(dir, 12), "D:/rec/take_20260825/segment_0012.mkv");
        // Trailing separators must not double up.
        assert_eq!(LibavMuxer::final_path("D:/rec/", 1), "D:/rec/segment_0001.mkv");
    }

    #[test]
    fn delivery_token_uses_take_folder_never_raw_paths() {
        assert_eq!(LibavMuxer::delivery_token("D:/rec/take_x99", 7), "take_x99/segment_0007.mkv");
        // Root with no folder name degrades gracefully.
        assert_eq!(LibavMuxer::delivery_token("/", 0), "segment_0000.mkv");
    }

    #[test]
    fn index_sequence_is_monotonic_fail_closed() {
        assert!(LibavMuxer::assert_index_sequence(None, 0).is_ok());
        assert!(LibavMuxer::assert_index_sequence(Some(0), 1).is_ok());
        assert!(LibavMuxer::assert_index_sequence(Some(4), 5).is_ok());
        let err = LibavMuxer::assert_index_sequence(Some(4), 4).unwrap_err();
        assert!(err.starts_with("MKV_SEGMENT_INDEX_REGRESSION"), "{err}");
        let err = LibavMuxer::assert_index_sequence(Some(4), 2).unwrap_err();
        assert!(err.contains("REGRESSION"));
    }

    #[test]
    fn channel_masks_cover_mono_and_stereo_only() {
        assert_eq!(LibavMuxer::channel_mask(1), Ok(0b1));
        assert_eq!(LibavMuxer::channel_mask(2), Ok(0b11));
        assert!(LibavMuxer::channel_mask(6).is_err());
        assert!(LibavMuxer::channel_mask(0).is_err());
    }

    #[test]
    fn layout_validation_rejects_bad_orders_duplicates_and_rates() {
        assert!(LibavMuxer::validate_layout(&[]).is_err());
        // Video must be first when present.
        let bad_order = vec![mic(), h264(1920, 1080)];
        let err = LibavMuxer::validate_layout(&bad_order).unwrap_err();
        assert_eq!(err, "MKV_TRACK_ORDER_INVALID: video must be tracks[0] when present");
        // Duplicates rejected regardless of position.
        let err = LibavMuxer::validate_layout(&vec![mic(), mic()]).unwrap_err();
        assert!(err.starts_with("MKV_TRACK_DUPLICATED"), "{err}");
        // V2 locks 48 kHz — anything else fails closed.
        let bad_rate = vec![(
            TrackId::System,
            TrackParams::Aac { sample_rate: 44_100, channels: 2 },
        )];
        let err = LibavMuxer::validate_layout(&bad_rate).unwrap_err();
        assert!(err.starts_with("MKV_SAMPLE_RATE_UNSUPPORTED"), "{err}");
        // Sanity: the production layout passes.
        assert!(LibavMuxer::validate_layout(&[h264(1920, 1080), mic()]).is_ok());
    }

    /// The whole state machine must produce typed errors — never panic —
    /// whether or not the host has the libav DLLs installed.
    #[test]
    fn state_machine_fails_closed_without_runtime() {
        let mut m = LibavMuxer::new();
        let pkt = EncodedPacket {
            pts_us: 0,
            dts_us: 0,
            is_keyframe: true,
            data: vec![0u8; 4],
            codec: "H264".into(),
        };

        // Nothing open / nothing prepared yet — typed errors, never panic.
        // The runtime gate runs BEFORE the state gate, so a host without the
        // DLLs sees LIBAV_UNAVAILABLE here while one with them (or with an
        // already-loaded runtime) sees MKV_SEGMENT_NOT_OPEN. Both are
        // fail-closed; neither may panic.
        let is_typed_state_err = |err: &str| {
            err.starts_with("MKV_SEGMENT_NOT_OPEN") || err.starts_with("LIBAV_UNAVAILABLE")
        };
        let wp = m.write_packet(TrackId::Video, &pkt).unwrap_err();
        assert!(is_typed_state_err(&wp), "write_packet: {wp}");
        let cs = m.close_segment().unwrap_err();
        assert!(is_typed_state_err(&cs), "close_segment: {cs}");
        let sv = m.set_video_extradata(vec![1, 2]).unwrap_err();
        assert!(is_typed_state_err(&sv), "set_video_extradata: {sv}");
        let sa = m.set_audio_extradata(TrackId::Mic, vec![0x12, 0x10]).unwrap_err();
        assert!(is_typed_state_err(&sa), "set_audio_extradata: {sa}");
        assert_eq!(m.bytes_written(), 0);

        // Layout checks fire before the runtime is touched.
        let err = m.open_segment(0, &[]).unwrap_err();
        assert_eq!(err, "MKV_TRACK_LAYOUT_EMPTY: open_segment needs at least one track");

        // prepare() gates on the runtime: either it succeeds (DLLs present)
        // or it reports LIBAV_UNAVAILABLE / ABI mismatch — never panics.
        let scratch = std::env::temp_dir().join("windagent_mux_test_prepare");
        match m.prepare(scratch.to_string_lossy().as_ref()) {
            Ok(()) => {
                // With a real runtime available, valid layout opens cleanly…
                m.open_segment(0, &[h264(1280, 720), mic()])
                    .expect("runtime present: open_segment must succeed");
                // …and the extradata handshake is enforced pre-header.
                let err = m.write_packet(TrackId::Video, &pkt).unwrap_err();
                assert!(err.starts_with("MKV_EXTRADATA_MISSING"), "{err}");
                m.set_video_extradata(vec![0x01, 0x64, 0x00, 0x28, 0xFF]).expect("stage avcC");
                assert!(m.set_audio_extradata(TrackId::System, vec![0x12, 0x10]).is_err());
                // Teardown without ever writing a packet refuses to emit an
                // empty (unplayable) file.
                let err = m.close_segment().unwrap_err();
                assert!(err.starts_with("MKV_SEGMENT_EMPTY"), "{err}");
            }
            Err(e) => {
                assert!(
                    e.starts_with("LIBAV_UNAVAILABLE") || e.starts_with("LIBAV_ABI_MISMATCH"),
                    "unexpected prepare error: {e}"
                );
            }
        }
        std::fs::remove_dir_all(&scratch).ok();
    }

    #[test]
    fn finalize_rejects_open_segment_and_resets_when_clean() {
        let mut m = LibavMuxer::new();
        // Clean finalize (no segments ever opened) is a no-op success.
        m.finalize_take().expect("finalize without state is a no-op");
        // After finalize the muxer is unprepared again.
        assert!(
            m.open_segment(0, &[h264(1280, 720)])
                .unwrap_err()
                .starts_with("MKV_NOT_PREPARED")
        );
        // The monotonic-open guard re-arms too, so one muxer instance can
        // serve take #2 starting back at segment_0000.
        m.last_open_index = Some(3);
        m.finalize_take().unwrap();
        assert_eq!(m.last_open_index, None);
    }

    /// Integration sanity: the router's roll decisions, fed through the
    /// muxer's monotonic-open guard, yield strictly increasing segment
    /// indexes across a synthetic take with B-frame boundary holds.
    #[test]
    fn router_roll_sequence_drives_increasing_segment_indexes() {
        use crate::muxer::timestamps::{RouteAction, SegmentRouter};

        let mk = |pts: u64, key: bool| EncodedPacket {
            pts_us: pts,
            dts_us: pts as i64 - 16_000,
            is_keyframe: key,
            data: vec![0],
            codec: "H264".into(),
        };
        let mut router = SegmentRouter::new();
        router.request_roll(300_000_000);

        let mut opened: Vec<u32> = Vec::new();
        let feed = |router: &mut SegmentRouter, opened: &mut Vec<u32>, p: &EncodedPacket| {
            match router.route(p) {
                RouteAction::Current | RouteAction::HoldForNext => {}
                RouteAction::RollTo(i) => {
                    LibavMuxer::assert_index_sequence(opened.last().copied(), i)
                        .expect("roll sequence must be monotonic");
                    opened.push(i);
                }
            }
        };
        feed(&mut router, &mut opened, &mk(100_000_000, true));
        feed(&mut router, &mut opened, &mk(200_000_000, false));
        // Reordered B-frame past the boundary arrives first — held, no roll.
        feed(&mut router, &mut opened, &mk(300_016_000, false));
        // IDR at the boundary rolls exactly once.
        feed(&mut router, &mut opened, &mk(300_000_000, true));
        feed(&mut router, &mut opened, &mk(300_033_000, false));
        assert_eq!(opened, vec![1]);
    }

    /// Walk EBML top-down and count SimpleBlock keyflags. Ground truth of
    /// the FILE bytes — no ffprobe, no libav demuxer in between. Mirrors the
    /// proven Python walker line-for-line.
    fn count_simpleblock_keyflags(bytes: &[u8]) -> (usize, usize) {
        /// EBML vint data length from the marker bits of the leading octet.
        fn vlen(first: u8) -> usize {
            let mut n = 1usize;
            while n < 8 && first & (1 << (8 - n)) == 0 {
                n += 1;
            }
            n
        }
        fn rvint(b: &[u8], p: usize) -> Option<(u64, usize)> {
            let first = *b.get(p)?;
            let n = vlen(first);
            if p + n > b.len() {
                return None;
            }
            let mut val = 0u64;
            for k in 0..n {
                val = (val << 8) | u64::from(b[p + k]);
            }
            val &= (1u64 << (7 * n)) - 1; // strip the marker bits
            Some((val, n))
        }
        fn is_master(id: &[u8]) -> bool {
            matches!(
                id,
                [0x18, 0x53, 0x80, 0x67] // Segment
                    | [0x1F, 0x43, 0xB6, 0x75] // Cluster
                    | [0xA0] // BlockGroup
                    | [0x11, 0x4D, 0x9B, 0x74] // SeekHead
                    | [0x15, 0x49, 0xA9, 0x66] // Info
                    | [0x16, 0x54, 0xAE, 0x6B] // Tracks
                    | [0xAE] // TrackEntry
                    | [0xE0] // Video
                    | [0xE1] // Audio
                    | [0x4D, 0xBB] // Seek
                    | [0x1A, 0x45, 0xDF, 0xA3] // EBML header
                    | [0x19, 0x41, 0xA4, 0x70] // Tags
                    | [0x67]
            )
        }
        fn walk(b: &[u8], key: &mut usize, non_key: &mut usize) {
            let mut p = 0usize;
            while p < b.len() {
                let id_len = vlen(b[p]);
                let Some(id_end) = p.checked_add(id_len) else { return };
                let id = &b[p..id_end.min(b.len())];
                if id.len() != id_len {
                    return;
                }
                let Some((size, sn)) = rvint(b, id_end) else { return };
                let start = id_end + sn;
                let unknown = size == (1u64 << (7 * sn)) - 1;
                let sz = if unknown { b.len().saturating_sub(start) } else { size as usize };
                if start > b.len() || start + sz > b.len() {
                    return;
                }
                let payload = &b[start..start + sz];
                if is_master(id) {
                    walk(payload, key, non_key);
                } else if id == [0xA3] {
                    // SimpleBlock: track vint (MSB-terminated, ≤2 bytes here)
                    // + i16 timecode + flags byte whose bit 7 is the Keyflag.
                    let mut tl = 1usize;
                    while tl < payload.len() && payload[tl - 1] & 0x80 == 0 {
                        tl += 1;
                    }
                    let fi = tl + 2;
                    if fi < payload.len() {
                        if payload[fi] & 0x80 != 0 {
                            *key += 1;
                        } else {
                            *non_key += 1;
                        }
                    }
                }
                p = start + sz;
            }
        }
        let mut key = 0;
        let mut non_key = 0;
        walk(bytes, &mut key, &mut non_key);
        (key, non_key)
    }

    /// Contract: `is_keyframe=true` MUST land as a SimpleBlock Keyflag=1 in
    /// the produced MKV — seekability depends on it. Verified against the raw
    /// file bytes so no demuxer interpretation can mask a mux-side flag loss.
    #[test]
    fn keyframe_flag_reaches_mkv_simpleblock() {
        for with_audio in [false, true] {
            assert_keyflags_reach_mkv(with_audio);
        }
    }

    fn assert_keyflags_reach_mkv(with_audio: bool) {
        let Ok(rt) = crate::muxer::libav_loader::LibavRuntime::load() else {
            eprintln!("skipping: libav runtime unavailable on this host");
            return;
        };
        assert!(rt.abi_supported(), "runtime must be ABI-matched to run this");
        let mut m = LibavMuxer::new();
        let dir = std::env::temp_dir().join(format!(
            "windagent_kflag_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        m.prepare(dir.to_string_lossy().as_ref()).expect("prepare");
        if with_audio {
            m.open_segment(0, &[h264(1280, 720), mic()]).expect("open");
        } else {
            m.open_segment(0, &[h264(1280, 720)]).expect("open");
        }
        // A real avcC (captured from an NVENC session): High@L4.2, one SPS,
        // one PPS — the muxer validates the record at header time.
        m.set_video_extradata(vec![
            0x01, 0x64, 0x00, 0x2a, 0xff, 0xe1, 0x00, 0x17, 0x67, 0x64, 0x00, 0x2a, 0xac, 0x2c,
            0xa5, 0x01, 0xe0, 0x08, 0x9f, 0x97, 0x01, 0x10, 0x00, 0x00, 0x3e, 0x80, 0x00, 0x1d,
            0x4c, 0x08, 0x40, 0x01, 0x00, 0x04, 0x68, 0xeb, 0x8f, 0x2c,
        ])
        .expect("stage avcC");
        if with_audio {
            // Real-ish AAC AudioSpecificConfig (LC, 48 kHz mono).
            m.set_audio_extradata(TrackId::Mic, vec![0x12, 0x10])
                .expect("stage ASC");
        }

        let mk = |pts: u64, key: bool| EncodedPacket {
            pts_us: pts,
            dts_us: pts as i64,
            is_keyframe: key,
            data: vec![7u8; 96],
            codec: "H264".into(),
        };
        if with_audio {
            // Interleave audio blocks the way the mux thread does — every
            // audio packet rides in as KEY-flagged (AAC frames are all
            // random-access points), exactly like production.
            for i in 0..6u64 {
                m.write_packet(
                    TrackId::Mic,
                    &EncodedPacket {
                        pts_us: i * 21_333,
                        dts_us: (i * 21_333) as i64,
                        is_keyframe: true,
                        data: vec![9u8; 60],
                        codec: "AAC".into(),
                    },
                )
                .unwrap_or_else(|e| panic!("audio pkt {i}: {e}"));
                match i {
                    0 => m
                        .write_packet(TrackId::Video, &mk(0, true))
                        .expect("pkt 0"),
                    1 => m.write_packet(TrackId::Video, &mk(33_333, false)).expect("pkt 1"),
                    _ => {}
                }
            }
            m.write_packet(TrackId::Video, &mk(66_666, false)).expect("pkt 2");
        } else {
            m.write_packet(TrackId::Video, &mk(0, true)).expect("pkt 0");
            m.write_packet(TrackId::Video, &mk(33_333, false)).expect("pkt 1");
            m.write_packet(TrackId::Video, &mk(66_666, false)).expect("pkt 2");
        }
        m.close_segment().expect("close");

        let path = dir.join("segment_0000.mkv");
        let bytes = std::fs::read(&path).expect("segment file readable");
        let (key, non_key) = count_simpleblock_keyflags(&bytes);
        println!(
            "[with_audio={with_audio}] SimpleBlocks read back: key={key} nonkey={non_key}"
        );
        assert_eq!(key, if with_audio { 1 + 6 } else { 1 }, "video IDR (+audio) flagged");
        assert_eq!(non_key, 2, "both P packets unflagged");
        std::fs::remove_dir_all(&dir).ok();
    }

    // ── Phase 5 contract tests (no native handles required) ───────────────────

    fn synth_segment_state(slots: Vec<(TrackId, TrackParams)>) -> SegmentState {
        let mut seg_slots = Vec::new();
        for (idx, (id, _)) in slots.iter().enumerate() {
            seg_slots.push(Slot { id: *id, index: idx as i32 });
        }
        SegmentState {
            index: 0,
            tmp_path: "tmp".into(),
            final_path: "final".into(),
            slots: seg_slots,
            header_written: true,
            video_extradata: Some(vec![0x01, 0x02]),
            audio_extradata: Vec::new(),
            first_pts_us: None,
            last_pts_us: None,
            last_pts_by_slot: vec![None; slots.len()],
            last_dts_by_slot: vec![None; slots.len()],
            bytes_written: 0,
            #[cfg(windows)]
            ctx: core::ptr::null_mut(),
            #[cfg(windows)]
            pkt: core::ptr::null_mut(),
            #[cfg(windows)]
            streams: Vec::new(),
        }
    }

    fn mk_packet(pts_us: u64, codec: &str, key: bool) -> EncodedPacket {
        EncodedPacket { pts_us, dts_us: pts_us as i64, is_keyframe: key, data: vec![7u8; 32], codec: codec.into() }
    }

    fn mk_b_packet(pts_us: u64, dts_us: i64, codec: &str, key: bool) -> EncodedPacket {
        EncodedPacket { pts_us, dts_us, is_keyframe: key, data: vec![7u8; 32], codec: codec.into() }
    }

    #[test]
    fn timestamp_zero_is_valid_and_monotonic_per_track() {
        let mut seg = synth_segment_state(vec![h264(1280,720), mic()]);
        // Zero PTS/DTS is valid for first video packet.
        let pkt0 = mk_packet(0, "H264", true);
        LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &pkt0).expect("zero PTS must be valid");
        seg.last_pts_by_slot[0] = Some(0);
        seg.last_dts_by_slot[0] = Some(0);
        seg.first_pts_us = Some(0);
        // Next monotonic DTS packet passes.
        let pkt1 = mk_packet(33_333, "H264", false);
        LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &pkt1).expect("monotonic 33_333 after 0");
        seg.last_pts_by_slot[0] = Some(33_333);
        seg.last_dts_by_slot[0] = Some(33_333);
        // Same DTS allowed (duplicate, not regression) — per spec < is regression, <= is okay.
        let pkt_dup = mk_packet(33_333, "H264", false);
        LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &pkt_dup).expect("equal DTS not a regression");
        // Audio track independent: zero on audio track is also valid even though video already at 33_333.
        let apkt0 = mk_packet(0, "AAC", true);
        LibavMuxer::validate_packet_contract(&seg, TrackId::Mic, &apkt0).expect("audio zero independent");
        seg.last_pts_by_slot[1] = Some(0);
        seg.last_dts_by_slot[1] = Some(0);
        let apkt1 = mk_packet(21_333, "AAC", true);
        LibavMuxer::validate_packet_contract(&seg, TrackId::Mic, &apkt1).expect("audio monotonic");
    }

    #[test]
    fn valid_bframe_dts_pts_accepted() {
        let mut seg = synth_segment_state(vec![h264(1280,720)]);
        // B-frame: DTS must be <= PTS and both monotonic in DTS; zero valid.
        let b0 = mk_b_packet(0, 0, "H264", true);
        LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &b0).expect("IDR zero");
        seg.last_pts_by_slot[0] = Some(0);
        seg.last_dts_by_slot[0] = Some(0);
        seg.first_pts_us = Some(0);
        // Valid B-frame where DTS lags PTS (decode before presentation)
        let b1 = mk_b_packet(33_333, 16_000, "H264", false);
        LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &b1).expect("B-frame DTS!=PTS must be accepted");
        seg.last_pts_by_slot[0] = Some(33_333);
        seg.last_dts_by_slot[0] = Some(16_000);
        // Next P-frame with larger DTS still accepted
        let p = mk_b_packet(66_666, 33_333, "H264", false);
        LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &p).expect("P after B");
        // DTS==PTS (non B-frame) still passes
        let ok = mk_packet(100_000, "H264", false);
        LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &ok).expect("DTS==PTS");
    }

    #[test]
    fn bframe_reordered_pts_accepted_when_dts_monotonic() {
        let mut seg = synth_segment_state(vec![h264(1280,720)]);
        // Decode order I0/P3/B1/B2 has PTS 0,100k,33k,66k but DTS monotonic 0,33k,66k,100k is simplified here:
        // Real decode order from NvencSession: PTS/DTS pairs in decode order where DTS monotonic and PTS may go backward.
        // Example: I(pts 0 dts 0), P(pts 66_666 dts 33_333), B(pts 33_333 dts 16_000) would be DTS regression if B after P with dts 16k <33k,
        // so valid reorder must have DTS monotonic: I(0,0), P(66_666,33_333)? Actually Nvenc encodes in presentation order for first GOP; true reorder after warm-up is I0(0,0), P3(100_000,33_333), B1(33_333,16_000) is invalid DTS, so use monotonic DTS example:
        let i0 = mk_b_packet(0, 0, "H264", true);
        LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &i0).expect("I0");
        seg.last_pts_by_slot[0] = Some(0);
        seg.last_dts_by_slot[0] = Some(0);
        seg.first_pts_us = Some(0);
        let p3 = mk_b_packet(100_000, 33_333, "H264", false);
        LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &p3).expect("P3 DTS 33k");
        seg.last_pts_by_slot[0] = Some(100_000);
        seg.last_dts_by_slot[0] = Some(33_333);
        // B1 in decode order after P3 has PTS 33_333 which is < prev PTS 100_000 (presentation-order backward) but DTS 50_000 >33_333 monotonic — must be accepted.
        let _b1 = mk_b_packet(33_333, 50_000, "H264", false);
        // PTS 33k < 100k presentation backward is allowed in written order; only DTS monotonic matters.
        // But our DTS 50k >33k passes monotonic. However PTS 33k < DTS 50k violates DTS<=PTS, so this example invalid.
        // Use valid where DTS <= PTS: need DTS <= PTS, so B1 with pts 33_333 must have dts <=33_333.
        // To keep DTS monotonic after P3's dts 33_333, B1's dts must be >=33_333 and <=33_333 => only dts 33_333 qualifies, which equals.
        // So choose sequence where PTS reordering still respects DTS<=PTS:
        // I0(0,0) DTS0, B? Let's use I0(0,0), B1(33_333,10_000), P2(66_666,20_000) — PTS monotonic 0,33k,66k and DTS monotonic 0,10k,20k — not reordered.
        // Instead demonstrate reordering tolerance: PTS 66k then 33k with DTS 30k then 40k would have PTS backward but DTS forward and DTS<=PTS for second? 33k pts with dts 40k violates DTS<=PTS.
        // So valid reordered must have DTS <= PTS for each packet; therefore PTS backward in written order while DTS forward implies PTS of later packet < earlier PTS but DTS of later packet > earlier DTS. Can we have pts 60k dts 30k followed by pts 30k dts 40k? Second has dts 40k >30k monotonic but dts 40k > pts 30k invalid.
        // Hence any PTS backward in written order while DTS monotonic will inevitably make DTS > PTS for the backward packet if DTS keeps increasing. This shows why PTS presentation monotonic cannot be enforced in written order — the muxer must preserve both as-is. To demonstrate valid tolerance we use packets where PTS not monotonic but DTS monotonic and DTS<=PTS still holds: e.g., I(0,0), P(40_000,20_000), B(20_000,10_000) invalid as above. So we pick a case where PTS backward is still > DTS:
        // I(0,0) dts0, B(20_000,10_000) dts10k, P(60_000,20_000) pts60k dts20k — PTS monotonic forward, no backward.
        // For true backward, need pts 60k dts20k then pts 30k dts30k: second pts30k dts30k has dts30k==pts30k ok and dts30k>20k monotonic, pts30k<60k backward but accepted. This is the test.
        let b1_valid = mk_b_packet(30_000, 30_000, "H264", false);
        // This would be rejected only if we enforced PTS monotonic; after Repair it must be accepted.
        // Reset seg to have last PTS 60k and last DTS 20k from a preceding P
        let mut seg2 = synth_segment_state(vec![h264(1280,720)]);
        let p = mk_b_packet(60_000, 20_000, "H264", false);
        LibavMuxer::validate_packet_contract(&seg2, TrackId::Video, &p).expect("P 60k/20k");
        seg2.last_pts_by_slot[0] = Some(60_000);
        seg2.last_dts_by_slot[0] = Some(20_000);
        seg2.first_pts_us = Some(0);
        LibavMuxer::validate_packet_contract(&seg2, TrackId::Video, &b1_valid).expect("B-frame PTS backward in written order must be accepted when DTS monotonic and DTS<=PTS");
    }

    #[test]
    fn rejects_dts_regression_and_invalid_timestamps() {
        let mut seg = synth_segment_state(vec![h264(1920,1080)]);
        seg.last_pts_by_slot[0] = Some(50_000);
        seg.last_dts_by_slot[0] = Some(50_000);
        seg.first_pts_us = Some(0);
        // DTS regression: 40k < 50k must be rejected
        let pkt = mk_b_packet(60_000, 40_000, "H264", false);
        let err = LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &pkt).unwrap_err();
        assert!(err.starts_with("TIMESTAMP_REGRESSION"), "{err}");
        // Forward DTS still passes.
        let ok = mk_b_packet(60_000, 55_000, "H264", false);
        LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &ok).expect("forward DTS");
        // DTS > PTS invalid
        let bad = mk_b_packet(33_333, 40_000, "H264", false);
        let err2 = LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &bad).unwrap_err();
        assert!(err2.starts_with("TIMESTAMP_INVALID"), "{err2}");
        assert!(err2.contains("dts") || err2.contains("DTS"), "{err2}");
        // Negative DTS invalid
        let neg = EncodedPacket { pts_us: 10_000, dts_us: -5_000, is_keyframe: false, data: vec![7u8; 32], codec: "H264".into() };
        let err3 = LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &neg).unwrap_err();
        assert!(err3.starts_with("TIMESTAMP_INVALID"), "{err3}");
    }

    #[test]
    fn rejects_timestamp_regression_per_track() {
        // Legacy name preserved for compatibility: now validates DTS regression per track (written-order)
        let mut seg = synth_segment_state(vec![h264(1920,1080)]);
        seg.last_pts_by_slot[0] = Some(50_000);
        seg.last_dts_by_slot[0] = Some(50_000);
        seg.first_pts_us = Some(0);
        let pkt = mk_b_packet(40_000, 40_000, "H264", false);
        let err = LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &pkt).unwrap_err();
        assert!(err.starts_with("TIMESTAMP_REGRESSION"), "{err}");
        // Forward in time still passes.
        let ok = mk_packet(60_000, "H264", false);
        LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &ok).expect("forward");
    }

    #[test]
    fn rejects_codec_mismatch_per_track() {
        let seg = synth_segment_state(vec![h264(1280,720), mic()]);
        let v_aac = mk_packet(0, "AAC", true);
        let err = LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &v_aac).unwrap_err();
        assert!(err.starts_with("MKV_CODEC_MISMATCH"), "{err}");
        let a_h264 = mk_packet(0, "H264", true);
        let err2 = LibavMuxer::validate_packet_contract(&seg, TrackId::Mic, &a_h264).unwrap_err();
        assert!(err2.starts_with("MKV_CODEC_MISMATCH"), "{err2}");
        // Correct codecs pass.
        LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &mk_packet(0,"H264",true)).expect("video H264");
        LibavMuxer::validate_packet_contract(&seg, TrackId::Mic, &mk_packet(0,"AAC",true)).expect("audio AAC");
        // HEVC also valid for video.
        LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &mk_packet(0,"HEVC",true)).expect("video HEVC");
    }

    #[test]
    fn rejects_empty_packet_data() {
        let seg = synth_segment_state(vec![h264(1280,720)]);
        let pkt = EncodedPacket { pts_us: 0, dts_us: 0, is_keyframe: true, data: vec![], codec: "H264".into() };
        let err = LibavMuxer::validate_packet_contract(&seg, TrackId::Video, &pkt).unwrap_err();
        assert!(err.starts_with("MKV_PACKET_EMPTY"), "{err}");
    }

    #[test]
    fn rejects_unknown_track() {
        let seg = synth_segment_state(vec![h264(1280,720)]);
        let pkt = mk_packet(0, "AAC", true);
        let err = LibavMuxer::validate_packet_contract(&seg, TrackId::Mic, &pkt).unwrap_err();
        assert!(err.starts_with("MKV_UNKNOWN_TRACK"), "{err}");
    }

    #[test]
    fn segmentation_tmp_never_promoted_on_failure() {
        let mut m = LibavMuxer::new();
        let dir = std::env::temp_dir().join(format!(
            "windagent_seg_fail_{}",
            std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()
        ));
        // Prepare succeeds or reports LIBAV_UNAVAILABLE — either is fail-closed.
        let prep = m.prepare(dir.to_string_lossy().as_ref());
        if prep.is_err() {
            let e = prep.unwrap_err();
            assert!(e.starts_with("LIBAV_UNAVAILABLE") || e.starts_with("LIBAV_ABI_MISMATCH"), "{e}");
            return;
        }
        // When runtime is present, a failed close (empty segment) must not leave a .mkv.
        m.open_segment(0, &[h264(640,480)]).expect("open");
        m.set_video_extradata(vec![0x01,0x64,0x00,0x28,0xFF]).expect("stage");
        let err = m.close_segment().unwrap_err();
        assert!(err.starts_with("MKV_SEGMENT_EMPTY"), "{err}");
        assert!(!dir.join("segment_0000.mkv").exists(), "partial .mkv must never be published");
        assert!(!dir.join("segment_0000.mkv.tmp").exists() || std::fs::read(&dir.join("segment_0000.mkv.tmp")).is_ok(), ".tmp may exist but .mkv must not");
        std::fs::remove_dir_all(&dir).ok();
    }
}
