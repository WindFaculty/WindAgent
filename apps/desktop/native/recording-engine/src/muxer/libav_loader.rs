//! Runtime loader for the libav shared libraries (ban_ke_hoach_v1.md §9-A).
//!
//! The engine never links avformat/avcodec/avutil import libraries: every
//! entry point is resolved with `LoadLibraryW` + `GetProcAddress` at recording
//! start, so a host without the FFmpeg shared build degrades to a fail-closed
//! [`crate::muxer::LIBAV_UNAVAILABLE`] error instead of failing process start.
//!
//! Search order (first complete hit wins):
//! 1. `WINDAGENT_LIBAV_DIR` environment variable — explicit deployment dir.
//! 2. executable directory — DLLs bundled next to `windagent-recorder.exe`.
//! 3. bare DLL names through the standard loader search (PATH).
//!
//! §26 packaging note: a bundled install always resolves at step 1–2 and
//! never depends on PATH; step 3 exists only for dev machines that
//! provision the DLLs out-of-band. If the bundled DLLs are missing the
//! engine fails closed with [`crate::muxer::LIBAV_UNAVAILABLE`] naming every
//! probe — it never silently substitutes a user-installed ffmpeg.
//!
//! Within each location the release families are probed newest-first:
//! FFmpeg 8.x (`avformat-62` / `avcodec-62` / `avutil-60`), 7.x (`-61` /
//! `-61` / `-59`), 6.x (`-60` / `-60` / `-58`). avutil loads FIRST (it is a
//! dependency of both siblings), then avcodec (owns the `av_packet_*` API),
//! then avformat. The actual major versions are read back through
//! `av*_version()` and reported; only the FFmpeg 8.x family is ABI-supported
//! because the struct transcriptions below were taken verbatim from the
//! n8.1.2 headers — older majors still load (better diagnostics than a bare
//! miss) but [`LibavRuntime::abi_supported`] returns `false` and the muxer
//! rejects them fail-closed before any struct write.
//!
//! Struct/constant transcription source (VERBATIM against FFmpeg tag
//! `n8.1.2`, https://github.com/FFmpeg/FFmpeg/tree/n8.1.2; local cache
//! `%TEMP%\windagent_libav\include`):
//! - `libavformat/avformat.h` — `AVFormatContext` prefix through
//!   `streams/nb_streams`; `AVStream` prefix through `codecpar` (in 8.1
//!   `codecpar` sits at offset 16, BEFORE the inline `AVPacket attached_pic`,
//!   so no AVPacket-by-value transcription is needed for stream access).
//! - `libavformat/avio.h` — `avio_open`, `avio_closep`, `AVIO_FLAG_WRITE`.
//! - `libavcodec/codec_par.h` — `AVCodecParameters` complete.
//! - `libavcodec/packet.h` — `AVPacket` field prefix (we mutate
//!   pts/dts/data/size/stream_index/flags/duration/pos through a partial
//!   mirror), `AV_PKT_FLAG_KEY`.
//! - `libavcodec/codec_id.h` — enum positions counted by hand:
//!   `AV_CODEC_ID_H264`=27, `AV_CODEC_ID_HEVC`=173,
//!   `AV_CODEC_ID_AAC`=0x15002 (=86018: MP2 anchors 0x15000, MP3 +1).
//! - `libavutil/channel_layout.h` — `AVChannelLayout` (union collapsed to its
//!   `uint64_t mask` member — we only ever express mono/stereo masks).
//! - `libavutil/rational.h` — `AVRational`; `pixfmt.h` — YUV420P=0 (first
//!   entry after NONE=-1); `error.h` — `av_strerror`, string buffer 64;
//!   `dict.h` — `av_dict_set`; `avutil.h` — `AVMEDIA_TYPE_VIDEO/AUDIO`.
//!
//! Threading: the loader runs on whichever thread calls [`LibavRuntime::load`]
//! and touches no COM objects, so no `CoInitializeEx` is required here
//! (contrast the capture/WGC and WASAPI modules).

use core::ffi::{c_char, c_int, c_uint, c_void};

// ─── Verified constants (see transcription sources above) ───────────────────

/// `AVIO_FLAG_WRITE` (libavformat/avio.h).
pub const AVIO_FLAG_WRITE: c_int = 2;
/// `AVMEDIA_TYPE_VIDEO` (libavutil/avutil.h, first enum AVMediaType entry).
pub const AVMEDIA_TYPE_VIDEO: c_int = 0;
/// `AVMEDIA_TYPE_AUDIO` (second entry).
pub const AVMEDIA_TYPE_AUDIO: c_int = 1;
/// `AV_CODEC_ID_H264` (libavcodec/codec_id.h — 27th enum position).
pub const AV_CODEC_ID_H264: c_int = 27;
/// `AV_CODEC_ID_HEVC` (173rd position; assumes the default
/// `FF_API_V408_CODECID=1` build, as shipped in official shared builds).
pub const AV_CODEC_ID_HEVC: c_int = 173;
/// `AV_CODEC_ID_AAC` = 0x15002 (MP2=0x15000, MP3=+1, AAC=+2) = 86018.
/// Note: NOT 86016 — that anchor belongs to MP2.
pub const AV_CODEC_ID_AAC: c_int = 0x15002;
/// `AV_PIX_FMT_YUV420P` (pixfmt.h — 0, immediately after NONE=-1).
pub const AV_PIX_FMT_YUV420P: c_int = 0;
/// `AV_PKT_FLAG_KEY` (packet.h 0x0001).
pub const AV_PKT_FLAG_KEY: c_int = 0x0001;
/// `AV_CHANNEL_ORDER_NATIVE` (channel_layout.h — UNSPEC=0, NATIVE=1).
pub const AV_CHANNEL_ORDER_NATIVE: c_int = 1;
/// `AV_ERROR_MAX_STRING_SIZE` (error.h) — stack buffer size for av_strerror.
pub const AV_ERROR_MAX_STRING_SIZE: usize = 64;
/// `AV_NOPTS_VALUE` ((int64_t)UINT64_C(0x8000000000000000) == i64::MIN).
pub const AV_NOPTS_VALUE_I64: i64 = i64::MIN;
/// avformat major the transcriptions are proven against (FFmpeg 8.x).
pub const LIBAVFORMAT_MAJOR_SUPPORTED: u32 = 62;
/// avcodec major matching the above.
pub const AVCODEC_MAJOR_SUPPORTED: u32 = 62;
/// avutil major matching the above.
pub const AVUTIL_MAJOR_SUPPORTED: u32 = 60;

// ─── Minimal #[repr(C)] mirrors (transcribed field-by-field) ────────────────

/// `AVRational` (libavutil/rational.h): `{ int num; int den; }`.
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AVRational {
    pub num: c_int,
    pub den: c_int,
}

/// Opaque `AVFormatContext` — accessed through [`AVFormatContextPrefix`].
#[repr(C)]
pub struct AVFormatContext {
    _private: [u8; 0],
}

/// Opaque `AVIOContext` — only ever passed by pointer.
#[repr(C)]
pub struct AVIOContext {
    _private: [u8; 0],
}

/// Opaque `AVOutputFormat` — only ever passed by pointer.
#[repr(C)]
pub struct AVOutputFormat {
    _private: [u8; 0],
}

/// Opaque `AVStream` — accessed through [`AVStreamPrefix`].
#[repr(C)]
pub struct AVStream {
    _private: [u8; 0],
}

/// Opaque `AVDictionary` — created/destroyed by libavutil only.
#[repr(C)]
pub struct AVDictionary {
    _private: [u8; 0],
}

/// Opaque `AVPacket` allocated by `av_packet_alloc` — mutated through
/// [`AVPacketPartial`].
#[repr(C)]
pub struct AVPacket {
    _private: [u8; 0],
}

/// `AVFormatContext` prefix (avformat.h lines 1265-…): fields up to and
/// including `streams`. Everything past `streams` is untouched opaque memory.
///
/// Verified order: `av_class, iformat, oformat, priv_data, pb, ctx_flags,
/// nb_streams, streams`.
#[repr(C)]
pub struct AVFormatContextPrefix {
    pub av_class: *const c_void,
    pub iformat: *const c_void,
    pub oformat: *const c_void,
    pub priv_data: *mut c_void,
    pub pb: *mut AVIOContext,
    pub ctx_flags: c_int,
    pub nb_streams: c_uint,
    pub streams: *mut *mut AVStream,
}

/// `AVStream` prefix (avformat.h lines 746-769): `av_class, index, id,
/// codecpar`. In FFmpeg 8.1 `codecpar` precedes `priv_data`/`time_base`/…
/// and crucially precedes the inline `AVPacket attached_pic`, so this four-
/// field mirror is all the muxer needs for codec-parameter access.
#[repr(C)]
pub struct AVStreamPrefix {
    pub av_class: *const c_void,
    pub index: c_int,
    pub id: c_int,
    pub codecpar: *mut AVCodecParameters,
}

/// Wider `AVStream` prefix reaching the timing hints the muxer sets or reads:
/// verified declaration order (avformat.h 746-857): `av_class, index, id,
/// codecpar, priv_data, time_base, start_time, duration, nb_frames,
/// disposition, discard, sample_aspect_ratio, metadata, avg_frame_rate`.
/// Used to set `time_base`/`avg_frame_rate` before the header and to read
/// back the muxer-adjusted `time_base` when stamping packets.
#[repr(C)]
pub struct AVStreamTimingPrefix {
    pub av_class: *const c_void,
    pub index: c_int,
    pub id: c_int,
    pub codecpar: *mut AVCodecParameters,
    pub priv_data: *mut c_void,
    pub time_base: AVRational,
    pub start_time: i64,
    pub duration: i64,
    pub nb_frames: i64,
    pub disposition: c_int,
    /// `enum AVDiscard`.
    pub discard: c_int,
    pub sample_aspect_ratio: AVRational,
    /// `AVDictionary *` — opaque.
    pub metadata: *mut c_void,
    pub avg_frame_rate: AVRational,
}

/// Complete `AVCodecParameters` (libavcodec/codec_par.h, FFmpeg ≥7 layout:
/// includes `coded_side_data`/`nb_coded_side_data`, `trailing_padding` and
/// `alpha_mode`). Field-for-field transcription — see the module header.
#[repr(C)]
pub struct AVCodecParameters {
    pub codec_type: c_int,
    pub codec_id: c_int,
    pub codec_tag: u32,
    pub extradata: *mut u8,
    pub extradata_size: c_int,
    /// `AVPacketSideData *` — opaque here, we never touch side data.
    pub coded_side_data: *mut c_void,
    pub nb_coded_side_data: c_int,
    pub format: c_int,
    pub bit_rate: i64,
    pub bits_per_coded_sample: c_int,
    pub bits_per_raw_sample: c_int,
    pub profile: c_int,
    pub level: c_int,
    pub width: c_int,
    pub height: c_int,
    pub sample_aspect_ratio: AVRational,
    pub framerate: AVRational,
    pub field_order: c_int,
    pub color_range: c_int,
    pub color_primaries: c_int,
    pub color_trc: c_int,
    pub color_space: c_int,
    pub chroma_location: c_int,
    pub video_delay: c_int,
    pub ch_layout: AVChannelLayout,
    pub sample_rate: c_int,
    pub block_align: c_int,
    pub frame_size: c_int,
    pub initial_padding: c_int,
    pub trailing_padding: c_int,
    pub seek_preroll: c_int,
    pub alpha_mode: c_int,
}

/// `AVChannelLayout` (libavutil/channel_layout.h) with the anonymous union
/// collapsed to its `uint64_t mask` member: the union also holds a pointer
/// (`AVChannelCustom *map`) but both members are 8 bytes on x64, so masking
/// the union down to `u64` preserves size (24) and alignment (8).
#[repr(C)]
pub struct AVChannelLayout {
    /// `enum AVChannelOrder` — use [`AV_CHANNEL_ORDER_NATIVE`].
    pub order: c_int,
    pub nb_channels: c_int,
    /// Union member `mask` (bit i set ⇒ AVChannel i present; stereo = 0b11).
    pub mask: u64,
    /// Union sibling `opaque` — kept NULL.
    pub opaque: *mut c_void,
}

/// `AVPacket` field prefix (libavcodec/packet.h lines 565-633) covering every
/// field the muxer writes. The tail (`opaque`, `opaque_ref`, `time_base`)
/// is left to libav. Verified order: `buf, pts, dts, data, size, stream_index,
/// flags, side_data, side_data_elems, duration, pos, …`.
#[repr(C)]
pub struct AVPacketPartial {
    /// `AVBufferRef *` — owned by libav after av_new_packet; never touched.
    pub buf: *mut c_void,
    pub pts: i64,
    pub dts: i64,
    pub data: *mut u8,
    pub size: c_int,
    pub stream_index: c_int,
    pub flags: c_int,
    /// `AVPacketSideData *` — opaque.
    pub side_data: *mut c_void,
    pub side_data_elems: c_int,
    pub duration: i64,
    pub pos: i64,
}

// ─── Raw entry-point signatures (all stable across the probed families) ─────

pub type AvformatVersionFn = unsafe extern "system" fn() -> c_uint;
pub type AvformatAllocOutputContext2Fn = unsafe extern "system" fn(
    ctx: *mut *mut AVFormatContext,
    oformat: *const AVOutputFormat,
    format_name: *const c_char,
    filename: *const c_char,
) -> c_int;
pub type AvformatNewStreamFn =
    unsafe extern "system" fn(s: *mut AVFormatContext, c: *const c_void) -> *mut AVStream;
pub type AvioOpenFn = unsafe extern "system" fn(
    s: *mut *mut AVIOContext,
    url: *const c_char,
    flags: c_int,
) -> c_int;
pub type AvioClosepFn = unsafe extern "system" fn(s: *mut *mut AVIOContext) -> c_int;
pub type AvformatWriteHeaderFn =
    unsafe extern "system" fn(s: *mut AVFormatContext, options: *mut *mut AVDictionary) -> c_int;
pub type AvInterleavedWriteFrameFn =
    unsafe extern "system" fn(s: *mut AVFormatContext, pkt: *mut AVPacket) -> c_int;
pub type AvWriteTrailerFn = unsafe extern "system" fn(s: *mut AVFormatContext) -> c_int;
pub type AvformatFreeContextFn = unsafe extern "system" fn(s: *mut AVFormatContext);
pub type AvGuessFormatFn = unsafe extern "system" fn(
    short_name: *const c_char,
    filename: *const c_char,
    mime_type: *const c_char,
) -> *const AVOutputFormat;
pub type AvcodecVersionFn = unsafe extern "system" fn() -> c_uint;
pub type AvPacketAllocFn = unsafe extern "system" fn() -> *mut AVPacket;
pub type AvPacketFreeFn = unsafe extern "system" fn(pkt: *mut *mut AVPacket);
pub type AvNewPacketFn = unsafe extern "system" fn(pkt: *mut AVPacket, size: c_int) -> c_int;
pub type AvPacketUnrefFn = unsafe extern "system" fn(pkt: *mut AVPacket);
pub type AvPacketRescaleTsFn = unsafe extern "system" fn(
    pkt: *mut AVPacket,
    tb_src: AVRational,
    tb_dst: AVRational,
);
pub type AvutilVersionFn = unsafe extern "system" fn() -> c_uint;
pub type AvStrerrorFn =
    unsafe extern "system" fn(errnum: c_int, errbuf: *mut c_char, errbuf_size: usize) -> c_int;
pub type AvDictSetFn = unsafe extern "system" fn(
    pm: *mut *mut AVDictionary,
    key: *const c_char,
    value: *const c_char,
    flags: c_int,
) -> c_int;
/// `void *av_mallocz(size_t size)` (libavutil/mem.c) — used for extradata
/// buffers because `avformat_free_context` releases `par->extradata` with
/// `av_free`; Rust-owned memory would be freed across allocator boundaries.
pub type AvMalloczFn = unsafe extern "system" fn(size: usize) -> *mut c_void;

// ─── Runtime handle ─────────────────────────────────────────────────────────

/// Resolved libav entry points, cached process-wide by [`LibavRuntime::load`].
///
/// SAFETY for the Send/Sync impls below: every field is a function pointer,
/// module handle or `&'static str` — plain machine words, immutable after
/// load; FFmpeg's libavformat/libavcodec/libavutil entry points are
/// documented thread-safe.
#[cfg(windows)]
pub struct LibavRuntime {
    // Module handles — intentionally pinned for the process lifetime; the
    // OnceLock cache means the probe (and any partial-load leak) runs once.
    // Never read back: keeping the fields documents exclusive ownership and
    // blocks any future "tidy" FreeLibrary call while function pointers from
    // these modules are still reachable through this struct.
    #[allow(dead_code)]
    h_avutil: windows::Win32::Foundation::HMODULE,
    #[allow(dead_code)]
    h_avcodec: windows::Win32::Foundation::HMODULE,
    #[allow(dead_code)]
    h_avformat: windows::Win32::Foundation::HMODULE,

    /// Which DLL files actually satisfied this load (diagnostics/report).
    pub dll_avutil: &'static str,
    pub dll_avcodec: &'static str,
    pub dll_avformat: &'static str,

    // avutil
    pub avutil_version: AvutilVersionFn,
    pub av_strerror: AvStrerrorFn,
    pub av_dict_set: AvDictSetFn,
    pub av_mallocz: AvMalloczFn,

    // avcodec
    pub avcodec_version: AvcodecVersionFn,
    pub av_packet_alloc: AvPacketAllocFn,
    pub av_packet_free: AvPacketFreeFn,
    pub av_new_packet: AvNewPacketFn,
    pub av_packet_unref: AvPacketUnrefFn,
    pub av_packet_rescale_ts: AvPacketRescaleTsFn,

    // avformat
    pub avformat_version: AvformatVersionFn,
    pub avformat_alloc_output_context2: AvformatAllocOutputContext2Fn,
    pub avformat_new_stream: AvformatNewStreamFn,
    pub avio_open: AvioOpenFn,
    pub avio_closep: AvioClosepFn,
    pub avformat_write_header: AvformatWriteHeaderFn,
    pub av_interleaved_write_frame: AvInterleavedWriteFrameFn,
    pub av_write_trailer: AvWriteTrailerFn,
    pub avformat_free_context: AvformatFreeContextFn,
    pub av_guess_format: AvGuessFormatFn,
}

// SAFETY: see the struct-level doc comment — plain machine words, immutable
// after load; libav entry points are thread-safe.
#[cfg(windows)]
unsafe impl Send for LibavRuntime {}
#[cfg(windows)]
unsafe impl Sync for LibavRuntime {}

#[cfg(not(windows))]
pub struct LibavRuntime {
    _private: (),
}

impl LibavRuntime {
    /// Resolve and cache the libav runtime. Total: returns `Ok` on hosts with
    /// the DLLs reachable via the documented search order, `Err` prefixed
    /// [`crate::muxer::LIBAV_UNAVAILABLE`] otherwise; never panics.
    #[cfg(windows)]
    pub fn load() -> Result<&'static Self, String> {
        static RUNTIME: std::sync::OnceLock<Result<LibavRuntime, String>> =
            std::sync::OnceLock::new();
        // get_or_init hands back a &'static Result; destructuring keeps the
        // 'static borrow on the inner value — no unsafe needed.
        match RUNTIME.get_or_init(Self::load_uncached) {
            Ok(rt) => Ok(rt),
            Err(e) => Err(e.clone()),
        }
    }

    /// Non-Windows builds have no libav runtime — fail closed.
    #[cfg(not(windows))]
    pub fn load() -> Result<&'static Self, String> {
        Err(format!(
            "{}: libav_loader has no implementation outside Windows",
            crate::muxer::LIBAV_UNAVAILABLE
        ))
    }

    /// True when the loaded family matches the ABI the struct transcriptions
    /// were proven against (FFmpeg 8.x: avformat 62 / avcodec 62 / avutil 60).
    /// Older families load for diagnostics but MUST be rejected before any
    /// `AVCodecParameters` write — pre-8.x layouts lack `coded_side_data`,
    /// `trailing_padding` and `alpha_mode`, so blind field writes would
    /// corrupt the smaller allocation made by the foreign libavformat.
    #[cfg(windows)]
    pub fn abi_supported(&self) -> bool {
        self.avformat_major() == LIBAVFORMAT_MAJOR_SUPPORTED
            && self.avcodec_major() == AVCODEC_MAJOR_SUPPORTED
            && self.avutil_major() == AVUTIL_MAJOR_SUPPORTED
    }

    /// Loaded `(avformat, avcodec, avutil)` major versions.
    #[cfg(windows)]
    pub fn versions(&self) -> (u32, u32, u32) {
        (self.avformat_major(), self.avcodec_major(), self.avutil_major())
    }

    #[cfg(windows)]
    fn avformat_major(&self) -> u32 {
        av_version_major(unsafe { (self.avformat_version)() })
    }

    #[cfg(windows)]
    fn avcodec_major(&self) -> u32 {
        av_version_major(unsafe { (self.avcodec_version)() })
    }

    #[cfg(windows)]
    fn avutil_major(&self) -> u32 {
        av_version_major(unsafe { (self.avutil_version)() })
    }

    /// Names of the DLLs that satisfied the load (report/diagnostics).
    #[cfg(windows)]
    pub fn dll_names(&self) -> [&'static str; 3] {
        [self.dll_avformat, self.dll_avcodec, self.dll_avutil]
    }

    // ── Safe checked wrappers ──
    //
    // Negative libav return codes surface as Err("<av_strerror text>") — the
    // MKV_* tagging happens one layer up in `muxer/libav.rs`.

    /// `avformat_alloc_output_context2` with a forced muxer short name.
    #[cfg(windows)]
    pub fn alloc_output_context(
        &self,
        format_name: &str,
    ) -> Result<*mut AVFormatContext, String> {
        let name = nul_terminated(format_name)?;
        let mut ctx: *mut AVFormatContext = core::ptr::null_mut();
        let ret =
            unsafe { (self.avformat_alloc_output_context2)(&mut ctx, core::ptr::null(), name.as_ptr(), core::ptr::null()) };
        if ret < 0 {
            return Err(self.err_str(ret));
        }
        if ctx.is_null() {
            return Err("avformat_alloc_output_context2 returned NULL without error".into());
        }
        Ok(ctx)
    }

    /// `avformat_new_stream` (the codec argument is unused in current libav).
    #[cfg(windows)]
    pub fn new_stream(&self, ctx: *mut AVFormatContext) -> Result<*mut AVStream, String> {
        let st = unsafe { (self.avformat_new_stream)(ctx, core::ptr::null()) };
        if st.is_null() {
            return Err("avformat_new_stream returned NULL".into());
        }
        Ok(st)
    }

    /// `avio_open` into the context's `pb` slot.
    #[cfg(windows)]
    pub fn io_open(&self, pb: *mut *mut AVIOContext, url: &str) -> Result<(), String> {
        let url = nul_terminated(url)?;
        let ret = unsafe { (self.avio_open)(pb, url.as_ptr(), AVIO_FLAG_WRITE) };
        if ret < 0 {
            return Err(self.err_str(ret));
        }
        Ok(())
    }

    /// `avio_closep` — flushes and closes the IO context behind `pb`.
    #[cfg(windows)]
    pub fn io_close(&self, pb: *mut *mut AVIOContext) -> Result<(), String> {
        let ret = unsafe { (self.avio_closep)(pb) };
        if ret < 0 {
            return Err(self.err_str(ret));
        }
        Ok(())
    }

    /// `avformat_write_header` with no option dictionary.
    #[cfg(windows)]
    pub fn write_header(&self, ctx: *mut AVFormatContext) -> Result<(), String> {
        let ret = unsafe { (self.avformat_write_header)(ctx, core::ptr::null_mut()) };
        if ret < 0 {
            return Err(self.err_str(ret));
        }
        Ok(())
    }

    /// `av_interleaved_write_frame` (takes the packet's buffer reference).
    #[cfg(windows)]
    pub fn interleaved_write_frame(
        &self,
        ctx: *mut AVFormatContext,
        pkt: *mut AVPacket,
    ) -> Result<(), String> {
        let ret = unsafe { (self.av_interleaved_write_frame)(ctx, pkt) };
        if ret < 0 {
            return Err(self.err_str(ret));
        }
        Ok(())
    }

    /// `av_write_trailer`.
    #[cfg(windows)]
    pub fn write_trailer(&self, ctx: *mut AVFormatContext) -> Result<(), String> {
        let ret = unsafe { (self.av_write_trailer)(ctx) };
        if ret < 0 {
            return Err(self.err_str(ret));
        }
        Ok(())
    }

    /// `avformat_free_context` (NULL-tolerant).
    #[cfg(windows)]
    pub fn free_context(&self, ctx: *mut AVFormatContext) {
        if !ctx.is_null() {
            unsafe { (self.avformat_free_context)(ctx) };
        }
    }

    /// `av_packet_alloc` (NULL-checked).
    #[cfg(windows)]
    pub fn packet_alloc(&self) -> Result<*mut AVPacket, String> {
        let pkt = unsafe { (self.av_packet_alloc)() };
        if pkt.is_null() {
            return Err("av_packet_alloc returned NULL".into());
        }
        Ok(pkt)
    }

    /// `av_packet_free` (NULL-tolerant double-pointer).
    #[cfg(windows)]
    pub fn packet_free(&self, pkt: *mut *mut AVPacket) {
        unsafe { (self.av_packet_free)(pkt) };
    }

    /// `av_new_packet` — payload-sized refcounted buffer.
    #[cfg(windows)]
    pub fn new_packet(&self, pkt: *mut AVPacket, size: c_int) -> Result<(), String> {
        let ret = unsafe { (self.av_new_packet)(pkt, size) };
        if ret < 0 {
            return Err(self.err_str(ret));
        }
        Ok(())
    }

    /// `av_packet_unref`.
    #[cfg(windows)]
    pub fn packet_unref(&self, pkt: *mut AVPacket) {
        unsafe { (self.av_packet_unref)(pkt) };
    }

    /// `av_packet_rescale_ts`.
    #[cfg(windows)]
    pub fn rescale_ts(&self, pkt: *mut AVPacket, src: AVRational, dst: AVRational) {
        unsafe { (self.av_packet_rescale_ts)(pkt, src, dst) };
    }

    /// `av_dict_set` on a dictionary owned by the caller.
    #[cfg(windows)]
    pub fn dict_set(
        &self,
        dict: &mut *mut AVDictionary,
        key: &str,
        value: &str,
        flags: c_int,
    ) -> Result<(), String> {
        let key = nul_terminated(key)?;
        let value = nul_terminated(value)?;
        let ret = unsafe { (self.av_dict_set)(dict, key.as_ptr(), value.as_ptr(), flags) };
        if ret < 0 {
            return Err(self.err_str(ret));
        }
        Ok(())
    }

    /// `av_guess_format` — `None` when no muxer matches (stripped build).
    #[cfg(windows)]
    pub fn guess_format(&self, short_name: &str) -> Option<*const AVOutputFormat> {
        let name = nul_terminated(short_name).ok()?;
        let fmt = unsafe { (self.av_guess_format)(name.as_ptr(), core::ptr::null(), core::ptr::null()) };
        if fmt.is_null() {
            None
        } else {
            Some(fmt)
        }
    }

    /// `av_mallocz` — zero-initialised libav-heap allocation. Required for
    /// anything libav will later `av_free` (extradata).
    #[cfg(windows)]
    pub fn mallocz(&self, size: usize) -> Result<*mut u8, String> {
        let ptr = unsafe { (self.av_mallocz)(size) };
        if ptr.is_null() {
            return Err(format!("av_mallocz({size}) returned NULL"));
        }
        Ok(ptr.cast::<u8>())
    }

    /// `av_strerror` into a stack buffer ([`AV_ERROR_MAX_STRING_SIZE`]).
    #[cfg(windows)]
    pub fn err_str(&self, code: c_int) -> String {
        let mut buf = [0u8; AV_ERROR_MAX_STRING_SIZE];
        unsafe {
            (self.av_strerror)(code, buf.as_mut_ptr().cast::<c_char>(), buf.len());
        }
        let end = buf.iter().position(|&b| b == 0).unwrap_or(buf.len());
        String::from_utf8_lossy(&buf[..end]).into_owned()
    }
}

/// NUL-terminate a Rust string for a C API, rejecting embedded NULs
/// fail-closed (a silent truncation would write to the wrong file).
fn nul_terminated(s: &str) -> Result<std::ffi::CString, String> {
    std::ffi::CString::new(s).map_err(|_| format!("MKV_PATH_INVALID: embedded NUL in {s:?}"))
}

// ─── Windows loading machinery ──────────────────────────────────────────────

/// `AV_VERSION_MAJOR(a)` (libavutil/version.h): the packed version int is
/// `major<<16 | minor<<8 | micro`, so the major sits in the top 16 bits.
fn av_version_major(v: u32) -> u32 {
    v >> 16
}

#[cfg(windows)]
mod imp {
    use super::*;
    use std::os::windows::ffi::OsStrExt;
    use std::path::{Path, PathBuf};
    use windows::core::{PCSTR, PCWSTR};
    use windows::Win32::Foundation::HMODULE;
    use windows::Win32::System::LibraryLoader::{GetProcAddress, LoadLibraryW};

    // Note on module lifetimes: modules loaded during a FAILED probe are
    // intentionally never freed (FreeLibrary is not part of this crate's
    // windows-crate feature set, and the probe runs at most once per process
    // behind the OnceLock cache) — a bounded handful of pinned HMODULEs is
    // preferable to unloading DLLs whose threads may still hold TLS.

    /// One supported FFmpeg release family: DLL base names plus the major
    /// versions they are expected to report back through av*_version().
    struct Family {
        avformat: &'static str,
        avcodec: &'static str,
        avutil: &'static str,
    }

    const FAMILIES: [Family; 3] = [
        Family { avformat: "avformat-62.dll", avcodec: "avcodec-62.dll", avutil: "avutil-60.dll" },
        Family { avformat: "avformat-61.dll", avcodec: "avcodec-61.dll", avutil: "avutil-59.dll" },
        Family { avformat: "avformat-60.dll", avcodec: "avcodec-60.dll", avutil: "avutil-58.dll" },
    ];

    fn wide(path: &Path) -> Vec<u16> {
        path.as_os_str().encode_wide().chain(std::iter::once(0)).collect()
    }

    fn wide_bare(name: &str) -> Vec<u16> {
        name.encode_utf16().chain(std::iter::once(0)).collect()
    }

    /// Resolve one symbol or abort the family attempt with a named error.
    macro_rules! require_sym {
        ($handle:expr, $name:literal, $ty:ty) => {{
            let proc = unsafe { GetProcAddress($handle, PCSTR(concat!($name, "\0").as_ptr())) };
            match proc {
                // SAFETY: GetProcAddress handed back a real exported function
                // whose signature we transcribed; transmuting to that exact
                // type is the standard windows-crate pattern.
                Some(f) => unsafe {
                    std::mem::transmute::<unsafe extern "system" fn() -> isize, $ty>(f)
                },
                None => return Err(format!("symbol {} not exported by loaded DLL", $name)),
            }
        }};
    }

    /// Attempt one (location, family) pair: avutil first, then avcodec, then
    /// avformat; any failure frees what was loaded and reports the reason.
    fn try_family(dir: Option<&Path>, family: &Family) -> Result<LibavRuntime, String> {
        let load_dll = |dll: &'static str| -> Result<HMODULE, String> {
            match dir {
                Some(d) => {
                    let full = d.join(dll);
                    let w = wide(&full);
                    unsafe { LoadLibraryW(PCWSTR::from_raw(w.as_ptr())) }
                        .map_err(|e| format!("LoadLibraryW({}) → {e}", full.display()))
                }
                None => {
                    let w = wide_bare(dll);
                    unsafe { LoadLibraryW(PCWSTR::from_raw(w.as_ptr())) }
                        .map_err(|e| format!("LoadLibraryW({dll} via PATH) → {e}"))
                }
            }
        };

        // Dependency order: avutil → avcodec → avformat. Loaded modules are
        // pinned for the process lifetime even on failure (see note above).
        let h_util = load_dll(family.avutil)?;
        let h_codec = load_dll(family.avcodec).map_err(|e| format!("{e} [after {util} ok]", util = family.avutil))?;
        let h_fmt = load_dll(family.avformat)
            .map_err(|e| format!("{e} [after {u}/{c} ok]", u = family.avutil, c = family.avcodec))?;

        macro_rules! bail_keep_modules {
            ($err:expr) => {{
                return Err($err);
            }};
        }

        // Symbol resolution — all-or-nothing so a half-matched install cannot
        // produce a runtime that crashes mid-recording.
        let rt = LibavRuntime {
            h_avutil: h_util,
            h_avcodec: h_codec,
            h_avformat: h_fmt,
            dll_avutil: family.avutil,
            dll_avcodec: family.avcodec,
            dll_avformat: family.avformat,
            avutil_version: require_sym!(h_util, "avutil_version", AvutilVersionFn),
            av_strerror: require_sym!(h_util, "av_strerror", AvStrerrorFn),
            av_dict_set: require_sym!(h_util, "av_dict_set", AvDictSetFn),
            av_mallocz: require_sym!(h_util, "av_mallocz", AvMalloczFn),
            avcodec_version: require_sym!(h_codec, "avcodec_version", AvcodecVersionFn),
            av_packet_alloc: require_sym!(h_codec, "av_packet_alloc", AvPacketAllocFn),
            av_packet_free: require_sym!(h_codec, "av_packet_free", AvPacketFreeFn),
            av_new_packet: require_sym!(h_codec, "av_new_packet", AvNewPacketFn),
            av_packet_unref: require_sym!(h_codec, "av_packet_unref", AvPacketUnrefFn),
            av_packet_rescale_ts: require_sym!(
                h_codec,
                "av_packet_rescale_ts",
                AvPacketRescaleTsFn
            ),
            avformat_version: require_sym!(h_fmt, "avformat_version", AvformatVersionFn),
            avformat_alloc_output_context2: require_sym!(
                h_fmt,
                "avformat_alloc_output_context2",
                AvformatAllocOutputContext2Fn
            ),
            avformat_new_stream: require_sym!(h_fmt, "avformat_new_stream", AvformatNewStreamFn),
            avio_open: require_sym!(h_fmt, "avio_open", AvioOpenFn),
            avio_closep: require_sym!(h_fmt, "avio_closep", AvioClosepFn),
            avformat_write_header: require_sym!(
                h_fmt,
                "avformat_write_header",
                AvformatWriteHeaderFn
            ),
            av_interleaved_write_frame: require_sym!(
                h_fmt,
                "av_interleaved_write_frame",
                AvInterleavedWriteFrameFn
            ),
            av_write_trailer: require_sym!(h_fmt, "av_write_trailer", AvWriteTrailerFn),
            avformat_free_context: require_sym!(
                h_fmt,
                "avformat_free_context",
                AvformatFreeContextFn
            ),
            av_guess_format: require_sym!(h_fmt, "av_guess_format", AvGuessFormatFn),
        };

        // Read back what actually loaded — a renamed DLL cannot lie here.
        let (fmt_maj, cod_maj, uti_maj) = rt.versions();
        if fmt_maj != expected_major(family.avformat)
            || cod_maj != expected_major(family.avcodec)
            || uti_maj != expected_major(family.avutil)
        {
            bail_keep_modules!(format!(
                "version mismatch: DLL names imply avformat-{}/avcodec-{}/avutil-{} but exports report {}/{}/{}",
                expected_major(family.avformat),
                expected_major(family.avcodec),
                expected_major(family.avutil),
                fmt_maj,
                cod_maj,
                uti_maj,
            ));
        }
        Ok(rt)
    }

    fn expected_major(dll: &str) -> u32 {
        // "avformat-62.dll" → 62
        dll.rsplit_once('-')
            .and_then(|(_, rest)| rest.split('.').next())
            .and_then(|n| n.parse().ok())
            .unwrap_or(0)
    }

    fn exe_dir() -> Option<PathBuf> {
        std::env::current_exe().ok()?.parent().map(Path::to_path_buf)
    }

    impl LibavRuntime {
        /// Uncached probe across every (location × family) pair.
        pub(super) fn load_uncached() -> Result<LibavRuntime, String> {
            let mut locations: Vec<(String, Option<PathBuf>)> = Vec::new();
            match std::env::var("WINDAGENT_LIBAV_DIR") {
                Ok(dir) if !dir.is_empty() => {
                    locations.push((format!("WINDAGENT_LIBAV_DIR={dir}"), Some(PathBuf::from(dir))));
                }
                Ok(_) => {}
                Err(std::env::VarError::NotPresent) => {}
                Err(e) => {
                    return Err(format!(
                        "{}: WINDAGENT_LIBAV_DIR unreadable ({e})",
                        crate::muxer::LIBAV_UNAVAILABLE
                    ));
                }
            }
            if let Some(dir) = exe_dir() {
                locations.push((format!("exe dir {}", dir.display()), Some(dir)));
            }
            locations.push(("standard search path (PATH)".to_string(), None));

            let mut attempts: Vec<String> = Vec::new();
            for (_, dir) in &locations {
                for family in FAMILIES.iter() {
                    match try_family(dir.as_deref(), family) {
                        Ok(rt) => return Ok(rt),
                        Err(e) => attempts.push(e),
                    }
                }
            }
            // Every failure is reported — the first attempt (newest family,
            // bundled dir) is the one that matters for a vendored install; a
            // last-only summary would hide its cause behind the PATH misses.
            Err(format!(
                "{}: probed {} location(s) × {} release family(ies), no usable avformat/avcodec/avutil. Failures: {}",
                crate::muxer::LIBAV_UNAVAILABLE,
                locations.len(),
                FAMILIES.len(),
                if attempts.is_empty() {
                    "(none)".to_string()
                } else {
                    attempts.join(" | ")
                },
            ))
        }
    }
}

// ─── Tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use core::mem::{align_of, size_of};

    /// Lock the transcription against accidental edits: each size was derived
    /// from the n8.1.2 headers (x64: int=4, pointers align to 8).
    #[test]
    fn transcribed_layouts_match_the_headers() {
        assert_eq!(size_of::<AVRational>(), 8);
        assert_eq!(align_of::<AVChannelLayout>(), 8);
        // 4+4 + (pad4) + 8(mask) + 8(opaque) — union is 8 bytes wide.
        assert_eq!(size_of::<AVChannelLayout>(), 24);

        // av_class(8) index(4) id(4) codecpar(8) — codecpar lands at offset 16.
        assert_eq!(size_of::<AVStreamPrefix>(), 24);

        // …priv_data(8) time_base(8) start_time(8) duration(8) nb_frames(8)
        // disposition(4) discard(4) sar(8) metadata(8) avg_frame_rate(8):
        // time_base at offset 32, avg_frame_rate at offset 88, total 96.
        assert_eq!(size_of::<AVStreamTimingPrefix>(), 96);

        // av_class..streams: 5×8 ptrs + int + uint + pad + ptr = 56.
        assert_eq!(size_of::<AVFormatContextPrefix>(), 56);

        // Full AVCodecParameters: 184 bytes on x64 (see derivation comment in
        // the struct definition; alpha_mode closes at offset 180 → padded 184).
        assert_eq!(size_of::<AVCodecParameters>(), 184);

        // AVPacket prefix through pos: buf8 pts8 dts8 data8 size4 si4 flags4
        // pad4 sd8 sde4 pad4 dur8 pos8 = 80.
        assert_eq!(size_of::<AVPacketPartial>(), 80);
    }

    /// Numeric values counted directly from the n8.1.2 enums — a wrong codec
    /// id here would make libavformat silently mislabel tracks.
    #[test]
    fn verified_constants_match_ffmpeg_n8_1_2() {
        assert_eq!(AVIO_FLAG_WRITE, 2);
        assert_eq!(AVMEDIA_TYPE_VIDEO, 0);
        assert_eq!(AVMEDIA_TYPE_AUDIO, 1);
        assert_eq!(AV_CODEC_ID_H264, 27);
        assert_eq!(AV_CODEC_ID_HEVC, 173);
        assert_eq!(AV_CODEC_ID_AAC, 0x15002);
        assert_eq!(AV_PIX_FMT_YUV420P, 0);
        assert_eq!(AV_PKT_FLAG_KEY, 0x0001);
        assert_eq!(AV_CHANNEL_ORDER_NATIVE, 1);
        assert_eq!(AV_NOPTS_VALUE_I64, i64::MIN);
        assert_eq!(AV_ERROR_MAX_STRING_SIZE, 64);
    }

    /// Embedded NULs must be rejected, never silently truncated.
    #[cfg(windows)]
    #[test]
    fn nul_terminated_rejects_embedded_nul() {
        assert!(nul_terminated("ok.mkv").is_ok());
        assert!(nul_terminated("bad\0path.mkv").is_err());
    }

    /// Regression lock: the packed version int is `major<<16 | minor<<8 |
    /// micro` (libavutil/version.h AV_VERSION_INT). A previous transcription
    /// shifted by 20, which turned the real 60/62/62 majors into 3 and made
    /// every family fail the readback gate on hosts with healthy DLLs. The
    /// literals below are the exact n8.1 header values (60.26.100 and
    /// representative 62.x.100 packs).
    #[test]
    fn version_major_decodes_ffmpeg_packed_int() {
        // LIBAVUTIL_VERSION_INT = 60<<16 | 26<<8 | 100 = 0x003C1A64.
        assert_eq!(av_version_major(0x003C_1A64), 60);
        // avcodec/avformat 62.x.100 → major 62.
        assert_eq!(av_version_major(62 << 16 | 11 << 8 | 100), 62);
        // Sanity: a wrong-shift decode would NOT equal these majors.
        assert_ne!((0x003C_1A64u32 >> 20), av_version_major(0x003C_1A64));
    }

    /// `load()` is total: Ok on hosts with the DLLs (this dev machine keeps
    /// them on PATH once provisioned), LIBAV_UNAVAILABLE-prefixed Err
    /// elsewhere. Either way it must never panic.
    #[test]
    fn loader_is_total_and_never_panics() {
        match LibavRuntime::load() {
            Ok(rt) => {
                let names = rt.dll_names();
                assert!(names.iter().all(|n| !n.is_empty()));
                // av_strerror(0) must produce non-empty text ("Success").
                assert!(!rt.err_str(0).is_empty());
                // Versions must be coherent with whatever family loaded.
                let (f, c, u) = rt.versions();
                assert!(f > 0 && c > 0 && u > 0);
                if !rt.abi_supported() {
                    // Older family: allowed to load, but flagged unsupported.
                    assert!(f != LIBAVFORMAT_MAJOR_SUPPORTED || c != AVCODEC_MAJOR_SUPPORTED || u != AVUTIL_MAJOR_SUPPORTED);
                }
            }
            Err(msg) => assert!(msg.starts_with("LIBAV_UNAVAILABLE"), "got: {msg}"),
        }
    }
}
