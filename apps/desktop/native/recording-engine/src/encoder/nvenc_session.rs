//! One NVENC encoding session bound to a D3D11 device (ban_ke_hoach_v1.md §8).
//!
//! Lifecycle: open(config, device) → register/map textures (zero-copy DX
//! resource path) → encode_picture → lock bitstream → packets. Destroyed in
//! strict reverse order on Drop.
//!
//! Sync mode (`enable_encode_async=0`) with a single bitstream buffer keeps
//! the pipeline simplest-correct: each `encode_picture` completes on the
//! calling (encode) thread before we map/unmap the next frame. B-frame
//! reordering still applies — frames whose packets aren't ready answer
//! `NV_ENC_ERR_NEED_MORE_INPUT` and surface later via [`Self::flush`].
//!
//! All driver calls go through [`crate::encoder::nvenc_api::NvencApi`]; none
//! of them panics — every status maps to a named blocker string (Principle C).

use std::collections::VecDeque;
#[cfg(windows)]
use std::os::raw::c_void;
#[cfg(windows)]
use windows::core::Interface;

use crate::encoder::{EncodedPacket, NvencConfig};
#[cfg(windows)]
use crate::encoder::nvenc_api as nv;

/// Encoder capability report from a live session-less probe.
#[derive(Debug, Clone, Default)]
pub struct NvencProbe {
    pub api_version: u32,
    pub h264_supported: bool,
    pub hevc_supported: bool,
    pub max_width: u32,
    pub max_height: u32,
    pub max_sessions: u32,
    pub bframes_supported: bool,
    pub lookahead_supported: bool,
    pub aq_supported: bool,
}

/// Session-less capability probe against the real driver stack.
///
/// Opens a throwaway NVENC session on a fresh D3D11 device (the same
/// NVIDIA-preferred walk capture uses), queries codec GUIDs + caps, then
/// destroys everything. Err = explicit blocker string, never a panic.
pub fn probe() -> Result<NvencProbe, String> {
    #[cfg(windows)]
    {
        let device_bundle = crate::capture::d3d11_device::create_preferred_device()
            .map_err(|e| format!("NVENC_D3D11_UNAVAILABLE:{e}"))?;
        let api = nv::load()?;
        // SAFETY: bundle outlives every call in this scope; the COM pointer is
        // passed as the opaque IUnknown* NVENC expects for DirectX devices.
        let dev_ptr = device_bundle.device.as_raw() as *mut c_void;

        let encoder = api.open_encode_session_ex(dev_ptr)?;
        let mut probe = NvencProbe { api_version: api.api_version.raw(), ..Default::default() };
        let query = (|| -> Result<(), String> {
            let guids = api.get_encode_guids(encoder)?;
            probe.h264_supported = guids.contains(&nv::NV_ENC_CODEC_H264_GUID);
            probe.hevc_supported = guids.contains(&nv::NV_ENC_CODEC_HEVC_GUID);
            if probe.h264_supported {
                let guid = nv::NV_ENC_CODEC_H264_GUID;
                probe.max_width = api.get_encode_caps(encoder, guid, nv::caps::WIDTH_MAX)?.max(0) as u32;
                probe.max_height =
                    api.get_encode_caps(encoder, guid, nv::caps::HEIGHT_MAX)?.max(0) as u32;
                probe.bframes_supported =
                    api.get_encode_caps(encoder, guid, nv::caps::NUM_MAX_BFRAMES)? > 0;
                probe.lookahead_supported =
                    api.get_encode_caps(encoder, guid, nv::caps::SUPPORT_LOOKAHEAD)? != 0;
                probe.aq_supported =
                    api.get_encode_caps(encoder, guid, nv::caps::SUPPORT_TEMPORAL_AQ)? != 0;
                probe.max_sessions =
                    api.get_encode_caps(encoder, guid, nv::caps::NUM_ENCODER_ENGINES)?.max(0)
                        as u32;
            }
            Ok(())
        })();
        api.destroy_encoder(encoder);
        query?;
        Ok(probe)
    }
    #[cfg(not(windows))]
    {
        Err("NVENC_UNSUPPORTED_OS".into())
    }
}

/// One live NVENC session owning registered input resources.
///
/// Texture registration cache: WGC hands out textures from a small frame-pool
/// that cycles, so registrations are memoized by raw pointer (bounded ring)
/// instead of re-registering every frame; all are unregistered on Drop.
///
/// Each entry carries at most ONE live input mapping. The driver requires
/// map/unmap calls to balance per resource: stacking `NvEncMapInputResource`
/// on the same registered resource without unmapping corrupts session state,
/// and the next `NvEncLockBitstream` faults hard (observed 0xc0000005 after
/// 29 stacked maps under lookahead). Re-using the one live mapping while the
/// encoder buffers pictures mirrors the reference clients, which feed every
/// queued picture from the same mapped surface.
#[cfg(windows)]
type RegisteredEntry = (usize /* tex raw */, *mut c_void /* registered */, Option<*mut c_void> /* mapped */);

pub struct NvencSession {
    #[cfg(windows)]
    #[allow(dead_code)] // kept alive so the DLL cannot unload under us
    api: &'static nv::NvencApi,
    #[cfg(windows)]
    encoder: *mut c_void,
    #[cfg(windows)]
    bitstream: *mut c_void,
    #[cfg(windows)]
    hevc: bool,
    /// Mirrors `config.b_frames > 0`: when false there is no decode/presentation
    /// divergence, so DTS ≡ PTS (see [`Self::lock_packets`]).
    #[cfg(windows)]
    has_b_frames: bool,
    #[cfg(windows)]
    width: u32,
    #[cfg(windows)]
    height: u32,
    /// (texture raw ptr, registered handle) pairs, most-recently-used first.
    #[cfg(windows)]
    registered_cache: Vec<RegisteredEntry>,
    #[cfg(windows)]
    eos_sent: bool,
    /// Pictures accepted by the encoder but not yet locked out of the
    /// bitstream buffer (lookahead/B-chain buffering). With the default
    /// lookahead=0 sync-mode session this is always 0 at flush time —
    /// which is exactly how `flush` knows it may skip EOS entirely.
    #[cfg(windows)]
    pending_outputs: usize,
    /// Annex-B parameter sets (SPS/PPS, +VPS for HEVC) captured at session
    /// init via `NvEncGetSequenceParams` — the avcC/hvcC source for the MKV
    /// extradata handshake (`muxer/libav.rs`).
    #[cfg(windows)]
    sequence_header: Vec<u8>,
    /// Encode-call latency samples (ms), bounded — p50/p95 read on demand.
    latency_samples: VecDeque<f64>,
}

// The session lives entirely on the encode thread (see service.rs); the raw
// pointers are only ever dereferenced by NVENC itself.
unsafe impl Send for NvencSession {}

const LATENCY_SAMPLES_MAX: usize = 512;
const REGISTERED_CACHE_MAX: usize = 16;
/// Upper bound for the EOS drain loop in [`Self::flush`] — mirrors the
/// profile validation cap on `video.lookahead` plus B-frame slack.
const FLUSH_DRAIN_MAX: usize = 64;
/// SPS/PPS/VPS are a few hundred bytes even at 8K; 256 KiB leaves orders of
/// magnitude of headroom for any future in-band prefix the driver appends.
#[cfg(windows)]
const SEQUENCE_PARAMS_BUF_BYTES: usize = 256 * 1024;

impl NvencSession {
    /// Open a session bound to `device` with the given quality config.
    ///
    /// Err carries a named blocker (`NVENC_*`); nothing falls back to software.
    pub fn open(
        config: &NvencConfig,
        device: &windows::Win32::Graphics::Direct3D11::ID3D11Device,
    ) -> Result<Self, String> {
        #[cfg(windows)]
        {
            let api = nv::load()?;
            // SAFETY: the caller's D3D11 device outlives this session; NVENC
            // holds no reference past destroy_encoder.
            let dev_ptr = device.as_raw() as *mut c_void;
            let encoder = api.open_encode_session_ex(dev_ptr)?;

            let build = (|| -> Result<(bool /*hevc*/, *mut c_void /*bitstream*/, Vec<u8> /*sequence header*/), String> {
                let codec_guid = match config.codec {
                    crate::encoder::Codec::H264 => nv::NV_ENC_CODEC_H264_GUID,
                    crate::encoder::Codec::Hevc => nv::NV_ENC_CODEC_HEVC_GUID,
                };
                let profile_guid = match config.codec {
                    crate::encoder::Codec::H264 => nv::NV_ENC_H264_PROFILE_HIGH_GUID,
                    crate::encoder::Codec::Hevc => nv::NV_ENC_HEVC_PROFILE_MAIN_GUID,
                };
                let preset_guid = match config.preset {
                    crate::encoder::Preset::P5 => nv::NV_ENC_PRESET_P5_GUID,
                    crate::encoder::Preset::P6 => nv::NV_ENC_PRESET_P6_GUID,
                    crate::encoder::Preset::P7 => nv::NV_ENC_PRESET_P7_GUID,
                };

                // Quality-first V2 tuning. ULTRA_HIGH_QUALITY is HEVC/AV1-only
                // per nvEncodeAPI.h ("Only supported for HEVC and AV1 on
                // Turing+ architectures"); H264 uses HIGH_QUALITY.
                let tuning_info = match config.codec {
                    crate::encoder::Codec::H264 => nv::NV_ENC_TUNING_INFO_HIGH_QUALITY,
                    crate::encoder::Codec::Hevc => nv::NV_ENC_TUNING_INFO_ULTRA_HIGH_QUALITY,
                };

                // Config built directly instead of copied from a
                // NvEncGetEncodePresetConfigEx query: recent drivers reject
                // that query outright (NV_ENC_ERR_INVALID_VERSION for every
                // codec×preset×tuning combo, verified by the
                // `preset_config_combo_matrix` diagnostic), and both FFmpeg
                // and OBS initialize this way instead. nvEncodeAPI.h
                // documents the merge semantics: init.presetGuid "will not
                // override the custom config structure but will be used to
                // determine other Encoder HW specific parameters".
                let mut enc_config = nv::NV_ENC_CONFIG::zeroed();
                enc_config.version = api.api_version.struct_ver_ext(9);
                enc_config.profile_guid = profile_guid;
                // No UNDEFINED member exists in this enum (FRAME=1, FIELD=2):
                // zero would be an invalid mode, so pin progressive frames.
                enc_config.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
                enc_config.gop_length = config.gop_frames.max(1);
                // frameIntervalP = B-frames + 1 (1 ⇒ IPP, no B-frames).
                enc_config.frame_interval_p = config.b_frames.min(31) as i32 + 1;

                // Rate control: CQP at the profile's quantization parameter.
                enc_config.rc_params.version = api.api_version.struct_ver(1);
                enc_config.rc_params.rate_control_mode = nv::NV_ENC_PARAMS_RC_CONSTQP;
                let qp = config.cq.clamp(0, 51) as u32;
                enc_config.rc_params.const_qp.qp_inter_p = qp;
                enc_config.rc_params.const_qp.qp_inter_b = qp;
                enc_config.rc_params.const_qp.qp_intra = qp;
                enc_config.rc_params.multi_pass = match config.multipass {
                    crate::encoder::Multipass::Disabled => nv::NV_ENC_MULTI_PASS_DISABLED,
                    crate::encoder::Multipass::HalfRes => nv::NV_ENC_TWO_PASS_QUARTER_RESOLUTION,
                    crate::encoder::Multipass::FullRes => nv::NV_ENC_TWO_PASS_FULL_RESOLUTION,
                };
                // Optional knobs honour driver support; a missing knob degrades
                // that feature only — never the session itself (§18 ladder).
                if config.lookahead > 0
                    && api.get_encode_caps(encoder, codec_guid, nv::caps::SUPPORT_LOOKAHEAD)? != 0
                {
                    enc_config.rc_params.set_enable_lookahead(true);
                    enc_config.rc_params.lookahead_depth = config.lookahead.min(32) as u16;
                }
                if config.spatial_aq
                    && api.get_encode_caps(encoder, codec_guid, nv::caps::SUPPORT_TEMPORAL_AQ)? != 0
                {
                    enc_config.rc_params.set_enable_aq(true);
                    enc_config.rc_params.set_aq_strength(8);
                }
                if config.temporal_aq
                    && api.get_encode_caps(encoder, codec_guid, nv::caps::SUPPORT_TEMPORAL_AQ)? != 0
                {
                    enc_config.rc_params.set_enable_temporal_aq(true);
                }

                // Crash-safe segments: SPS/PPS repeat at every IDR (§15).
                // The preset path fills chromaFormatIDC from the preset
                // table; a direct custom config must declare the bitstream's
                // own color format or InitializeEncoder rejects the whole
                // session ("Unsupported color format.", INVALID_PARAM).
                // 1 = 4:2:0 — what RGB→YUV conversion produces for ARGB
                // input (verified by the initialize_params_matrix diag).
                unsafe {
                    match config.codec {
                        crate::encoder::Codec::H264 => {
                            enc_config.encode_codec_config.h264_config.chroma_format_idc = 1;
                            enc_config.encode_codec_config.h264_config.set_repeat_spspps(true);
                        }
                        crate::encoder::Codec::Hevc => {
                            enc_config
                                .encode_codec_config
                                .hevc_config
                                .set_chroma_format_idc(1);
                            enc_config.encode_codec_config.hevc_config.set_repeat_spspps(true);
                        }
                    }
                }

                let mut init = nv::NV_ENC_INITIALIZE_PARAMS::zeroed();
                init.version = api.api_version.struct_ver_ext(7);
                init.encode_guid = codec_guid;
                init.preset_guid = preset_guid;
                init.encode_width = config.width;
                init.encode_height = config.height;
                init.dar_width = config.width;
                init.dar_height = config.height;
                init.frame_rate_num = config.fps.max(1);
                init.frame_rate_den = 1;
                init.enable_encode_async = 0; // sync mode (§8)
                init.enable_ptd = 1; // NVENC decides I/P/B placement
                init.tuning_info = tuning_info;
                init.buffer_format = nv::NV_ENC_BUFFER_FORMAT_ARGB;
                init.max_encode_width = config.width;
                init.max_encode_height = config.height;
                init.encode_config = &mut enc_config;
                api.initialize_encoder(encoder, &mut init)?;

                let bitstream = api.create_bitstream_buffer(encoder)?;

                // Capture the codec parameter sets while the session is fresh
                // (§9): avcC/hvcC must exist before the first MKV packet, and
                // waiting for the first keyframe would race AAC packets that
                // arrive earlier under lookahead. Fail-closed: no sequence
                // params → unusable session.
                let mut seq_buf = vec![0u8; SEQUENCE_PARAMS_BUF_BYTES];
                let seq_len = api.get_sequence_params(encoder, &mut seq_buf)?;
                seq_buf.truncate(seq_len);

                Ok((
                    matches!(config.codec, crate::encoder::Codec::Hevc),
                    bitstream,
                    seq_buf,
                ))
            })();

            match build {
                Ok((hevc, bitstream, sequence_header)) => Ok(Self {
                    api,
                    encoder,
                    bitstream,
                    hevc,
                    has_b_frames: config.b_frames > 0,
                    width: config.width,
                    height: config.height,
                    registered_cache: Vec::new(),
                    eos_sent: false,
                    pending_outputs: 0,
                    sequence_header,
                    latency_samples: VecDeque::with_capacity(64),
                }),
                Err(e) => {
                    api.destroy_encoder(encoder);
                    Err(e)
                }
            }
        }
        #[cfg(not(windows))]
        {
            let _ = (config, device);
            Err(crate::encoder::NVENC_UNAVAILABLE.into())
        }
    }

    /// Zero-copy encode of one captured texture → Annex-B packets stamped
    /// with `pts_us`.
    ///
    /// Returns an empty Vec when the encoder buffers the picture internally
    /// (`NEED_MORE_INPUT`, B-frame lookahead) — the packet surfaces on a later
    /// call or in [`Self::flush`].
    #[cfg(windows)]
    pub fn encode_texture(
        &mut self,
        tex: &windows::Win32::Graphics::Direct3D11::ID3D11Texture2D,
        pts_us: u64,
        force_idr: bool,
    ) -> Result<Vec<EncodedPacket>, String> {
        if self.eos_sent {
            return Err("NVENC_API_FAILED:encode_texture:EOS_ALREADY_SENT".into());
        }
        let started = std::time::Instant::now();
        let (_registered, mapped) = self.input_mapping(tex)?;

        let mut params = nv::NV_ENC_PIC_PARAMS::zeroed();
        params.version = self.api.api_version.struct_ver_ext(7);
        params.input_width = self.width;
        params.input_height = self.height;
        params.input_time_stamp = pts_us; // QPC-derived µs since take start
        params.input_buffer = mapped;
        params.output_bitstream = self.bitstream;
        params.buffer_fmt = nv::NV_ENC_BUFFER_FORMAT_ARGB;
        params.picture_struct = nv::NV_ENC_PIC_STRUCT_FRAME;
        params.encode_pic_flags =
            if force_idr { nv::NV_ENC_PIC_FLAG_FORCEIDR } else { 0 };

        let encode_result = self.api.encode_picture(self.encoder, &mut params);
        self.record_latency(started.elapsed().as_secs_f64() * 1000.0);

        let mut packets = Vec::new();
        match encode_result {
            // The picture was encoded into our buffer this call: lock the
            // bitstream FIRST, release input mappings LAST. Lock failure must
            // still release mappings to avoid leaking a mapped resource.
            Ok(status) if status == nv::NV_ENC_SUCCESS => {
                let lock_res = self.lock_packets(pts_us, false);
                // Ensure every live mapping is released even when lock fails;
                // otherwise the authoritative mapping would leak across an error
                // boundary (invariant: encode errors cannot retain a mapping).
                let packets_res = match lock_res {
                    Ok(pkts) => pkts,
                    Err(e) => {
                        self.release_input_mappings();
                        return Err(e);
                    }
                };
                packets = packets_res;
                self.release_input_mappings();
            }
            // Buffered internally (lookahead/B-chain): the mapping stays
            // alive (see [`RegisteredEntry`]) until the next drain.
            Ok(_) => {
                self.pending_outputs += 1;
            }
            Err(e) => {
                // Encode rejected the picture — the driver did not consume the
                // input surface, so unmap only this texture's mapping instead
                // of discarding every buffered lookahead surface.
                let raw = tex.as_raw() as usize;
                if let Some(pos) = self.registered_cache.iter().position(|(k, _, _)| *k == raw) {
                    if let Some(m) = self.registered_cache[pos].2.take() {
                        self.api.unmap_input_resource(self.encoder, m);
                    }
                }
                return Err(e);
            }
        }
        Ok(packets)
    }

    /// Unmap every live input mapping. Called only after a successful drain
    /// (packets locked out) or on teardown — never while the encoder may
    /// still hold the surfaces internally.
    #[cfg(windows)]
    fn release_input_mappings(&mut self) {
        for (_, _, mapped) in self.registered_cache.iter_mut() {
            if let Some(m) = mapped.take() {
                self.api.unmap_input_resource(self.encoder, m);
            }
        }
    }

    /// Drain buffered (lookahead/B-frame) packets at end of take by sending
    /// EOS and locking until the pipeline runs dry.
    pub fn flush(&mut self) -> Result<Vec<EncodedPacket>, String> {
        #[cfg(windows)]
        {
            // Default profile (lookahead=0, no B-frames) drains every picture
            // synchronously in `encode_texture` — nothing is ever pending, so
            // EOS + bitstream locks can be skipped entirely. On this driver a
            // lock with no pending output blocks even with doNotWait set.
            if self.pending_outputs == 0 {
                self.release_input_mappings();
                return Ok(vec![]);
            }
            if !self.eos_sent {
                let mut eos = nv::NV_ENC_PIC_PARAMS::zeroed();
                eos.version = self.api.api_version.struct_ver_ext(7);
                eos.encode_pic_flags = nv::NV_ENC_PIC_FLAG_EOS;
                // The EOS completion lands in our bitstream buffer like any
                // picture — leaving it NULL stalls the pipeline.
                eos.output_bitstream = self.bitstream;
                let _ = self.api.encode_picture(self.encoder, &mut eos);
                self.eos_sent = true;
            }
            // EOS pushes every buffered picture through the single output
            // buffer serially. `pending_outputs` bounds the loop to exactly
            // the packets that exist, so each blocking lock below is
            // guaranteed data and cannot wait forever.
            let mut drained = Vec::new();
            while self.pending_outputs > 0 && drained.len() < FLUSH_DRAIN_MAX {
                match self.lock_packets(0, false) {
                    Ok(mut pkts) if !pkts.is_empty() => drained.append(&mut pkts),
                    Ok(_) => break,
                    Err(e) => {
                        if !e.contains("NEED_MORE_INPUT") {
                            eprintln!("windagent-recorder: flush ended early: {e}");
                        }
                        break;
                    }
                }
            }
            // Every buffered picture is consumed now — all live input
            // mappings can be released.
            self.release_input_mappings();
            Ok(drained)
        }
        #[cfg(not(windows))]
        {
            Ok(vec![])
        }
    }

    /// (p50, p95) encode latency in milliseconds measured around encode calls.
    pub fn latency_stats(&self) -> (Option<f64>, Option<f64>) {
        if self.latency_samples.is_empty() {
            return (None, None);
        }
        let mut sorted: Vec<f64> = self.latency_samples.iter().copied().collect();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let pick = |pct: f64| -> f64 {
            let idx = ((sorted.len() as f64 - 1.0) * pct).round() as usize;
            sorted[idx.min(sorted.len() - 1)]
        };
        (Some(pick(0.50)), Some(pick(0.95)))
    }

    /// Annex-B parameter-set blob captured at session init — never empty for
    /// a successfully opened session (`open` fails closed without it).
    #[cfg(windows)]
    pub fn sequence_header(&self) -> &[u8] {
        &self.sequence_header
    }

    // ── internals ────────────────────────────────────────────────────────────

    /// Registration + input mapping for `tex`, memoized per texture: at most
    /// one live map per resource at any time. A cache hit with no live
    /// mapping re-maps; a hit with a live mapping reuses it (the encoder may
    /// still be buffering pictures from that surface).
    #[cfg(windows)]
    fn input_mapping(
        &mut self,
        tex: &windows::Win32::Graphics::Direct3D11::ID3D11Texture2D,
    ) -> Result<(*mut c_void, *mut c_void), String> {
        let raw = tex.as_raw() as usize;
        if let Some(pos) = self.registered_cache.iter().position(|(k, _, _)| *k == raw) {
            // MRU bump — WGC frame pools cycle a small set of buffers.
            let entry = self.registered_cache.remove(pos);
            self.registered_cache.insert(0, entry);
        }
        if !self
            .registered_cache
            .iter()
            .any(|(k, _, _)| *k == raw)
        {
            let mut reg = nv::NV_ENC_REGISTER_RESOURCE::zeroed();
            reg.version = self.api.api_version.struct_ver(5);
            reg.resource_type = nv::NV_ENC_INPUT_RESOURCE_TYPE_DIRECTX;
            reg.width = self.width;
            reg.height = self.height;
            reg.resource_to_register = tex.as_raw() as *mut c_void;
            reg.buffer_format = nv::NV_ENC_BUFFER_FORMAT_ARGB;
            let registered = self.api.register_resource(self.encoder, &mut reg)?;

            self.registered_cache.insert(0, (raw, registered, None));
            if self.registered_cache.len() > REGISTERED_CACHE_MAX {
                if let Some((_, stale_registered, stale_mapped)) = self.registered_cache.pop() {
                    // Never unregister while a mapping is live — pulling the
                    // registration out from under a buffered picture is
                    // another route to corrupted session state.
                    if let Some(m) = stale_mapped {
                        self.api.unmap_input_resource(self.encoder, m);
                    }
                    self.api.unregister_resource(self.encoder, stale_registered);
                }
            }
        }

        let pos = self
            .registered_cache
            .iter()
            .position(|(k, _, _)| *k == raw)
            .expect("entry inserted above");
        let (_, registered, mapped) = &mut self.registered_cache[pos];
        if mapped.is_none() {
            let (m, _) = self.api.map_input_resource(self.encoder, *registered)?;
            *mapped = Some(m);
        }
        Ok((*registered, mapped.expect("just filled")))
    }

    /// Resolve PTS from NVENC output timestamp, preserving zero.
    ///
    /// NVENC echoes `NV_ENC_PIC_PARAMS.input_time_stamp` exactly in
    /// `NV_ENC_LOCK_BITSTREAM.output_time_stamp`, including `0` which is a
    /// valid PTS for the first frame. The API defines no sentinel value for
    /// "unavailable" output timestamp — zero must not be treated as absent.
    /// Fallback is retained only for the non-Windows stub where no driver
    /// exists; on Windows the driver timestamp is always authoritative.
    #[cfg(windows)]
    #[inline]
    pub(crate) fn resolve_output_pts(output_time_stamp: u64, _fallback_pts_us: u64) -> u64 {
        // Explicitly preserve zero; never conflate it with unavailable.
        output_time_stamp
    }

    /// Lock the output bitstream and copy out every pending packet.
    ///
    /// `do_not_wait=false` (live encode path) blocks until the driver has
    /// the picture ready — the preceding `encode_picture` returned SUCCESS,
    /// so data is guaranteed. The EOS drain passes `true`: once every
    /// buffered picture is out, a blocking lock would wait forever.
    #[cfg(windows)]
    fn lock_packets(&mut self, fallback_pts_us: u64, do_not_wait: bool) -> Result<Vec<EncodedPacket>, String> {
        let mut lock = nv::NV_ENC_LOCK_BITSTREAM::zeroed();
        lock.version = self.api.api_version.struct_ver_ext(2);
        lock.output_bitstream = self.bitstream;
        self.api.lock_bitstream(self.encoder, &mut lock, do_not_wait)?;

        let size = lock.bitstream_size_in_bytes as usize;
        // Allocate FIRST, then copy: `Vec::new()` has capacity 0, and
        // `set_len` past capacity is UB — `as_mut_ptr()` would hand back a
        // dangling pointer and the copy below faults (this was a real
        // 0xc0000005, hit on the first non-empty lock after the lookahead
        // warm-up).
        let mut data: Vec<u8> = vec![0u8; size];
        if size > 0 && !lock.bitstream_buffer_ptr.is_null() {
            // SAFETY: NVENC guarantees [ptr, ptr+size) is valid while locked.
            unsafe {
                std::ptr::copy_nonoverlapping(
                    lock.bitstream_buffer_ptr as *const u8,
                    data.as_mut_ptr(),
                    size,
                );
            }
        }
        let pts_us = Self::resolve_output_pts(lock.output_time_stamp, fallback_pts_us);
        // B-frame reordering: output_duration is how far DTS lags PTS. With
        // no B-chain there is nothing to reorder — and the driver reports an
        // irregular output_duration anyway, so subtracting it produces a
        // non-monotonic DTS that the Matroska muxer rejects packet-by-packet.
        // DTS ≡ PTS keeps the stream valid.
        let dts_us = if self.has_b_frames {
            pts_us as i64 - lock.output_duration as i64
        } else {
            pts_us as i64
        };
        let is_keyframe =
            lock.picture_type == nv::NV_ENC_PIC_TYPE_IDR || lock.picture_type == nv::NV_ENC_PIC_TYPE_I;
        let codec = if self.hevc { "HEVC" } else { "H264" }.to_string();
        self.api.unlock_bitstream(self.encoder, self.bitstream);

        if data.is_empty() {
            return Ok(vec![]);
        }
        self.pending_outputs = self.pending_outputs.saturating_sub(1);
        // NVENC emits Annex-B start-coded bytes; the Matroska track declares
        // avcC/hvcC with 4-byte length-prefixed NAL units. Muxing raw Annex-B
        // into an avcC track garbles every demuxer's NAL boundaries and drops
        // packet flags — convert at the encoder boundary so every downstream
        // consumer (MKV master, MP4 export) sees one canonical form.
        let data = crate::muxer::tracks::annex_b_to_length_prefixed(&data);
        Ok(vec![EncodedPacket { pts_us, dts_us, is_keyframe, data, codec }])
    }

    #[cfg(not(windows))]
    fn lock_packets(&mut self, _fallback_pts_us: u64, _do_not_wait: bool) -> Result<Vec<EncodedPacket>, String> {
        Ok(vec![])
    }

    fn record_latency(&mut self, ms: f64) {
        if self.latency_samples.len() >= LATENCY_SAMPLES_MAX {
            self.latency_samples.pop_front();
        }
        self.latency_samples.push_back(ms);
    }
}

impl Drop for NvencSession {
    fn drop(&mut self) {
        // Strict reverse order: unmap live mappings → unregister →
        // bitstream → encoder.
        #[cfg(windows)]
        {
            if !self.encoder.is_null() {
                for (_, _, mapped) in self.registered_cache.iter_mut() {
                    if let Some(m) = mapped.take() {
                        self.api.unmap_input_resource(self.encoder, m);
                    }
                }
            }
            for (_, registered, _) in self.registered_cache.drain(..) {
                self.api.unregister_resource(self.encoder, registered);
            }
            if !self.bitstream.is_null() {
                self.api.destroy_bitstream_buffer(self.encoder, self.bitstream);
                self.bitstream = std::ptr::null_mut();
            }
            if !self.encoder.is_null() {
                self.api.destroy_encoder(self.encoder);
                self.encoder = std::ptr::null_mut();
            }
        }
    }
}

/// Diagnostic matrix (run manually): which (codec × preset × tuning) combos
/// the installed driver accepts for NvEncGetEncodePresetConfigEx. Not part of
/// CI expectations — prints a status table via --nocapture.
#[test]
#[ignore = "manual driver diagnostics"]
fn preset_config_combo_matrix() {
    use crate::encoder::nvenc_api as nv;
    let bundle = match crate::capture::d3d11_device::create_preferred_device() {
        Ok(b) => b,
        Err(e) => {
            println!("no d3d11 device: {e}");
            return;
        }
    };
    let api = match nv::load() {
        Ok(a) => a,
        Err(e) => {
            println!("nvenc load failed: {e}");
            return;
        }
    };
    let dev_ptr = bundle.device.as_raw() as *mut core::ffi::c_void;
    let encoder = match api.open_encode_session_ex(dev_ptr) {
        Ok(e) => e,
        Err(e) => {
            println!("open session failed: {e}");
            return;
        }
    };
    let codecs: [(&str, nv::NvGuid); 2] = [
        ("h264", nv::NV_ENC_CODEC_H264_GUID),
        ("hevc", nv::NV_ENC_CODEC_HEVC_GUID),
    ];
    let presets: [(&str, nv::NvGuid); 3] = [
        ("P5", nv::NV_ENC_PRESET_P5_GUID),
        ("P6", nv::NV_ENC_PRESET_P6_GUID),
        ("P7", nv::NV_ENC_PRESET_P7_GUID),
    ];
    let tunings: [(&str, u32); 2] = [
        ("HQ", nv::NV_ENC_TUNING_INFO_HIGH_QUALITY),
        ("UHQ", nv::NV_ENC_TUNING_INFO_ULTRA_HIGH_QUALITY),
    ];
    for (cn, cg) in codecs {
        for (pn, pg) in presets {
            for (tn, tv) in tunings {
                match api.get_encode_preset_config_ex(encoder, cg, pg, tv) {
                    Ok(_) => println!("{cn}/{pn}/{tn}: OK"),
                    Err(e) => println!("{cn}/{pn}/{tn}: ERR {e}"),
                }
            }
        }
    }

    // Legacy variant (no tuning info).
    let (cn, cg) = codecs[0];
    match api.get_encode_preset_config(encoder, cg, nv::NV_ENC_PRESET_P7_GUID) {
        Ok(_) => println!("{cn}/P7/legacy: OK"),
        Err(e) => println!("{cn}/P7/legacy: ERR {e}"),
    }

    // Presets the driver itself advertises for H264.
    match api.get_encode_preset_guids(encoder, codecs[0].1) {
        Ok(list) => {
            println!("driver preset count: {}", list.len());
            for g in &list {
                println!("  driver preset guid: {:08x}-{:04x}-{:04x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
                    g.data1, g.data2, g.data3,
                    g.data4[0], g.data4[1], g.data4[2], g.data4[3],
                    g.data4[4], g.data4[5], g.data4[6], g.data4[7]);
                match api.get_encode_preset_config_ex(encoder, codecs[0].1, *g,
                    nv::NV_ENC_TUNING_INFO_HIGH_QUALITY)
                {
                    Ok(_) => println!("    config-ex(HQ): OK"),
                    Err(e) => println!("    config-ex(HQ): ERR {e}"),
                }
            }
        }
        Err(e) => println!("preset guids failed: {e}"),
    }
}

/// Diagnostic (run manually): which InitializeEncoder parameter shapes the
/// driver accepts. Each variant gets a FRESH encode session — a failed
/// Initialize can poison the session, so sharing one across variants makes
/// results order-dependent. Variants form an isolation ladder: each adds one
/// knob group on top of the last, so the first failing run names the culprit.
#[test]
#[ignore = "manual driver diagnostics"]
fn initialize_params_matrix() {
    use crate::encoder::nvenc_api as nv;
    let Ok(bundle) = crate::capture::d3d11_device::create_preferred_device() else {
        println!("no d3d11 device");
        return;
    };
    println!(
        "device: {} vendor=0x{:04X} vram={}MB fl=0x{:X}",
        bundle.info.description, bundle.info.vendor_id, bundle.info.vram_mb, bundle.info.feature_level
    );
    let Ok(api) = nv::load() else {
        println!("nvenc load failed");
        return;
    };
    let dev_ptr = bundle.device.as_raw() as *mut core::ffi::c_void;

    let codec_guid = nv::NV_ENC_CODEC_H264_GUID;
    let profile_guid = nv::NV_ENC_H264_PROFILE_HIGH_GUID;

    /// Runs `build` against its own fresh encode session.
    fn variant(
        name: &str,
        api: &nv::NvencApi,
        dev_ptr: *mut core::ffi::c_void,
        build: impl FnOnce(&mut nv::NV_ENC_INITIALIZE_PARAMS),
    ) {
        let Ok(encoder) = api.open_encode_session_ex(dev_ptr) else {
            println!("{name}: open-session FAILED");
            return;
        };
        let mut init = nv::NV_ENC_INITIALIZE_PARAMS::zeroed();
        init.version = api.api_version.struct_ver_ext(7);
        init.encode_guid = nv::NV_ENC_CODEC_H264_GUID;
        init.preset_guid = nv::NV_ENC_PRESET_P7_GUID;
        init.encode_width = 1920;
        init.encode_height = 1080;
        init.dar_width = 1920;
        init.dar_height = 1080;
        init.frame_rate_num = 60;
        init.frame_rate_den = 1;
        init.tuning_info = nv::NV_ENC_TUNING_INFO_HIGH_QUALITY;
        init.buffer_format = nv::NV_ENC_BUFFER_FORMAT_ARGB;
        build(&mut init);
        match api.initialize_encoder(encoder, &mut init) {
            Ok(()) => println!("{name}: OK"),
            Err(e) => println!("{name}: ERR {e}"),
        }
        api.destroy_encoder(encoder);
    }

    // (a) pure preset — no custom config at all (baseline).
    variant("a pure-preset", &api, dev_ptr, |_| {});

    // (b) bare NV_ENC_CONFIG: version+profile+gop+frameIntervalP+
    //     frameFieldMode only — rc_params left zeroed.
    variant("b config-bare", &api, dev_ptr, |init| {
        let mut cfg = Box::leak(Box::new(nv::NV_ENC_CONFIG::zeroed()));
        cfg.version = api.api_version.struct_ver_ext(9);
        cfg.profile_guid = profile_guid;
        cfg.gop_length = 120;
        cfg.frame_interval_p = 1;
        cfg.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
        init.encode_config = cfg;
    });

    // (c) bare config + stamped rc_params CQP16, multiPass left DISABLED(0).
    variant("c +rc-cqp-nomultipass", &api, dev_ptr, |init| {
        let mut cfg = Box::leak(Box::new(nv::NV_ENC_CONFIG::zeroed()));
        cfg.version = api.api_version.struct_ver_ext(9);
        cfg.profile_guid = profile_guid;
        cfg.gop_length = 120;
        cfg.frame_interval_p = 1;
        cfg.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
        cfg.rc_params.version = api.api_version.struct_ver(1);
        cfg.rc_params.rate_control_mode = nv::NV_ENC_PARAMS_RC_CONSTQP;
        cfg.rc_params.const_qp.qp_inter_p = 16;
        cfg.rc_params.const_qp.qp_inter_b = 16;
        cfg.rc_params.const_qp.qp_intra = 16;
        init.encode_config = cfg;
    });

    // (d) production shape: c + multiPass FULL_RESOLUTION.
    variant("d +multipass-fullres", &api, dev_ptr, |init| {
        let mut cfg = Box::leak(Box::new(nv::NV_ENC_CONFIG::zeroed()));
        cfg.version = api.api_version.struct_ver_ext(9);
        cfg.profile_guid = profile_guid;
        cfg.gop_length = 120;
        cfg.frame_interval_p = 1;
        cfg.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
        cfg.rc_params.version = api.api_version.struct_ver(1);
        cfg.rc_params.rate_control_mode = nv::NV_ENC_PARAMS_RC_CONSTQP;
        cfg.rc_params.const_qp.qp_inter_p = 16;
        cfg.rc_params.const_qp.qp_inter_b = 16;
        cfg.rc_params.const_qp.qp_intra = 16;
        cfg.rc_params.multi_pass = nv::NV_ENC_TWO_PASS_FULL_RESOLUTION;
        init.encode_config = cfg;
    });

    // (e) production shape but NV12 buffer format instead of ARGB.
    variant("e nv12-buffer", &api, dev_ptr, |init| {
        init.buffer_format = nv::NV_ENC_BUFFER_FORMAT_NV12;
        let mut cfg = Box::leak(Box::new(nv::NV_ENC_CONFIG::zeroed()));
        cfg.version = api.api_version.struct_ver_ext(9);
        cfg.profile_guid = profile_guid;
        cfg.gop_length = 120;
        cfg.frame_interval_p = 1;
        cfg.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
        cfg.rc_params.version = api.api_version.struct_ver(1);
        cfg.rc_params.rate_control_mode = nv::NV_ENC_PARAMS_RC_CONSTQP;
        cfg.rc_params.const_qp.qp_inter_p = 16;
        cfg.rc_params.const_qp.qp_inter_b = 16;
        cfg.rc_params.const_qp.qp_intra = 16;
        cfg.rc_params.multi_pass = nv::NV_ENC_TWO_PASS_FULL_RESOLUTION;
        init.encode_config = cfg;
    });

    // (f) production shape but tuning UNDEFINED(0).
    variant("f no-tuning", &api, dev_ptr, |init| {
        init.tuning_info = 0; // NV_ENC_TUNING_INFO_UNDEFINED
        let mut cfg = Box::leak(Box::new(nv::NV_ENC_CONFIG::zeroed()));
        cfg.version = api.api_version.struct_ver_ext(9);
        cfg.profile_guid = profile_guid;
        cfg.gop_length = 120;
        cfg.frame_interval_p = 1;
        cfg.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
        cfg.rc_params.version = api.api_version.struct_ver(1);
        cfg.rc_params.rate_control_mode = nv::NV_ENC_PARAMS_RC_CONSTQP;
        cfg.rc_params.const_qp.qp_inter_p = 16;
        cfg.rc_params.const_qp.qp_inter_b = 16;
        cfg.rc_params.const_qp.qp_intra = 16;
        cfg.rc_params.multi_pass = nv::NV_ENC_TWO_PASS_FULL_RESOLUTION;
        init.encode_config = cfg;
    });

    // Single-field probes against (b): each differs from the bare config by
    // exactly one knob, so the first OK names the invalid zero-default.
    // g: numTemporalLayers=0 is outside the documented [1, max] range.
    variant("g numtemporal=1", &api, dev_ptr, |init| {
        let mut cfg = Box::leak(Box::new(nv::NV_ENC_CONFIG::zeroed()));
        cfg.version = api.api_version.struct_ver_ext(9);
        cfg.profile_guid = profile_guid;
        cfg.gop_length = 120;
        cfg.frame_interval_p = 1;
        cfg.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
        unsafe { cfg.encode_codec_config.h264_config.num_temporal_layers = 1 };
        init.encode_config = cfg;
    });

    // h: idrPeriod mirrors gopLength the way every reference client does it.
    variant("h idrperiod", &api, dev_ptr, |init| {
        let mut cfg = Box::leak(Box::new(nv::NV_ENC_CONFIG::zeroed()));
        cfg.version = api.api_version.struct_ver_ext(9);
        cfg.profile_guid = profile_guid;
        cfg.gop_length = 120;
        cfg.frame_interval_p = 1;
        cfg.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
        unsafe { cfg.encode_codec_config.h264_config.idr_period = 120 };
        init.encode_config = cfg;
    });

    // i: explicit CABAC instead of AUTOSELECT(0).
    variant("i cabac", &api, dev_ptr, |init| {
        let mut cfg = Box::leak(Box::new(nv::NV_ENC_CONFIG::zeroed()));
        cfg.version = api.api_version.struct_ver_ext(9);
        cfg.profile_guid = profile_guid;
        cfg.gop_length = 120;
        cfg.frame_interval_p = 1;
        cfg.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
        unsafe { cfg.encode_codec_config.h264_config.entropy_coding_mode = 1 }; // CABAC
        init.encode_config = cfg;
    });

    // j: profile autodetect in the config instead of HIGH.
    variant("j profile-auto", &api, dev_ptr, |init| {
        let mut cfg = Box::leak(Box::new(nv::NV_ENC_CONFIG::zeroed()));
        cfg.version = api.api_version.struct_ver_ext(9);
        cfg.profile_guid = nv::NV_ENC_CODEC_PROFILE_AUTOSELECT_GUID;
        cfg.gop_length = 120;
        cfg.frame_interval_p = 1;
        cfg.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
        init.encode_config = cfg;
    });

    // k: I-only GOP (frameIntervalP=0).
    variant("k i-only", &api, dev_ptr, |init| {
        let mut cfg = Box::leak(Box::new(nv::NV_ENC_CONFIG::zeroed()));
        cfg.version = api.api_version.struct_ver_ext(9);
        cfg.profile_guid = profile_guid;
        cfg.gop_length = 120;
        cfg.frame_interval_p = 0;
        cfg.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
        init.encode_config = cfg;
    });

    // Color-format probes against (b): if the custom-config path validates
    // init.bufferFormat while the preset path ignores it, exactly one of
    // these should flip to OK and name the accepted format.
    let bare_cfg = |api: &nv::NvencApi| {
        let mut cfg = Box::leak(Box::new(nv::NV_ENC_CONFIG::zeroed()));
        cfg.version = api.api_version.struct_ver_ext(9);
        cfg.profile_guid = profile_guid;
        cfg.gop_length = 120;
        cfg.frame_interval_p = 1;
        cfg.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
        cfg
    };
    variant("l buf-undefined", &api, dev_ptr, |init| {
        init.buffer_format = 0; // NV_ENC_BUFFER_FORMAT_UNDEFINED
        init.encode_config = bare_cfg(&api);
    });
    variant("m buf-abgr", &api, dev_ptr, |init| {
        init.buffer_format = 0x10000000; // NV_ENC_BUFFER_FORMAT_ABGR
        init.encode_config = bare_cfg(&api);
    });
    variant("n buf-yuv444", &api, dev_ptr, |init| {
        init.buffer_format = 0x00001000; // NV_ENC_BUFFER_FORMAT_YUV444
        init.encode_config = bare_cfg(&api);
    });

    // o: chromaFormatIDC=1 (4:2:0) — the bitstream's own color format.
    // Zero is not a valid chroma format and the failure text ("Unsupported
    // color format.") reads like exactly this field's validation.
    variant("o chroma420", &api, dev_ptr, |init| {
        let cfg = bare_cfg(&api);
        unsafe { cfg.encode_codec_config.h264_config.chroma_format_idc = 1 };
        init.encode_config = cfg;
    });
}

/// Diagnostic (run manually): full session lifecycle, one println per step —
/// the last line printed before an access violation names the crashing call.
#[test]
#[ignore = "manual driver diagnostics"]
fn session_lifecycle_probe() {
    use crate::encoder::nvenc_api as nv;
    let Ok(bundle) = crate::capture::d3d11_device::create_preferred_device() else {
        println!("no d3d11 device");
        return;
    };
    let Ok(api) = nv::load() else {
        println!("no nvenc api");
        return;
    };
    let dev_ptr = bundle.device.as_raw() as *mut core::ffi::c_void;
    let encoder = match api.open_encode_session_ex(dev_ptr) {
        Ok(e) => e,
        Err(e) => {
            println!("open-session: ERR {e}");
            return;
        }
    };

    // Production-shape custom config with the chroma declaration.
    let build = (|| -> Result<nv::NV_ENC_CONFIG, String> {
        let mut cfg = nv::NV_ENC_CONFIG::zeroed();
        cfg.version = api.api_version.struct_ver_ext(9);
        cfg.profile_guid = nv::NV_ENC_H264_PROFILE_HIGH_GUID;
        cfg.gop_length = 120;
        cfg.frame_interval_p = 1;
        cfg.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
        cfg.rc_params.version = api.api_version.struct_ver(1);
        cfg.rc_params.rate_control_mode = nv::NV_ENC_PARAMS_RC_CONSTQP;
        cfg.rc_params.const_qp.qp_inter_p = 16;
        cfg.rc_params.const_qp.qp_inter_b = 16;
        cfg.rc_params.const_qp.qp_intra = 16;
        unsafe {
            cfg.encode_codec_config.h264_config.chroma_format_idc = 1;
            cfg.encode_codec_config.h264_config.set_repeat_spspps(true);
        }
        Ok(cfg)
    })();

    let mut enc_config = match build {
        Ok(c) => c,
        Err(e) => {
            println!("config: ERR {e}");
            return;
        }
    };
    let mut init = nv::NV_ENC_INITIALIZE_PARAMS::zeroed();
    init.version = api.api_version.struct_ver_ext(7);
    init.encode_guid = nv::NV_ENC_CODEC_H264_GUID;
    init.preset_guid = nv::NV_ENC_PRESET_P7_GUID;
    init.encode_width = 1920;
    init.encode_height = 1080;
    init.dar_width = 1920;
    init.dar_height = 1080;
    init.frame_rate_num = 60;
    init.frame_rate_den = 1;
    init.enable_encode_async = 0;
    init.enable_ptd = 1;
    init.tuning_info = nv::NV_ENC_TUNING_INFO_HIGH_QUALITY;
    init.buffer_format = nv::NV_ENC_BUFFER_FORMAT_ARGB;
    init.encode_config = &mut enc_config;
    if let Err(e) = api.initialize_encoder(encoder, &mut init) {
        println!("initialize: ERR {e}");
        return;
    }
    println!("initialize: OK");

    let bitstream = match api.create_bitstream_buffer(encoder) {
        Ok(b) => b,
        Err(e) => {
            println!("bitstream-buffer: ERR {e}");
            return;
        }
    };
    println!("bitstream-buffer: OK");

    let mut seq_buf = vec![0u8; 256 * 1024];
    match api.get_sequence_params(encoder, &mut seq_buf) {
        Ok(n) => println!("sequence-params: OK {n} bytes ({:?}…)", &seq_buf[..n.min(8)]),
        Err(e) => {
            println!("sequence-params: ERR {e}");
            return;
        }
    }

    // A real BGRA texture on the same device.
    use windows::Win32::Graphics::Direct3D11::{
        D3D11_BIND_RENDER_TARGET, D3D11_TEXTURE2D_DESC, D3D11_USAGE_DEFAULT, ID3D11Texture2D,
    };
    use windows::Win32::Graphics::Dxgi::Common::{DXGI_FORMAT_B8G8R8A8_UNORM};
    let desc = D3D11_TEXTURE2D_DESC {
        Width: 1920,
        Height: 1080,
        MipLevels: 1,
        ArraySize: 1,
        Format: DXGI_FORMAT_B8G8R8A8_UNORM,
        SampleDesc: windows::Win32::Graphics::Dxgi::Common::DXGI_SAMPLE_DESC { Count: 1, Quality: 0 },
        Usage: D3D11_USAGE_DEFAULT,
        BindFlags: (D3D11_BIND_RENDER_TARGET.0) as u32,
        CPUAccessFlags: 0,
        MiscFlags: 0,
    };
    let tex: Option<ID3D11Texture2D> = None;
    let mut tex = tex;
    unsafe {
        bundle.device.CreateTexture2D(&desc, None, Some(&mut tex));
    }
    let Some(tex) = tex else {
        println!("texture-create: FAILED");
        return;
    };
    println!("texture-create: OK");

    let mut reg = nv::NV_ENC_REGISTER_RESOURCE::zeroed();
    reg.version = api.api_version.struct_ver(5);
    reg.resource_type = nv::NV_ENC_INPUT_RESOURCE_TYPE_DIRECTX;
    reg.width = 1920;
    reg.height = 1080;
    reg.resource_to_register = tex.as_raw() as *mut core::ffi::c_void;
    reg.buffer_format = nv::NV_ENC_BUFFER_FORMAT_ARGB;
    let registered = match api.register_resource(encoder, &mut reg) {
        Ok(r) => r,
        Err(e) => {
            println!("register-resource: ERR {e}");
            return;
        }
    };
    println!("register-resource: OK");

    let mapped = match api.map_input_resource(encoder, registered) {
        Ok((m, _)) => m,
        Err(e) => {
            println!("map-input: ERR {e}");
            return;
        }
    };
    println!("map-input: OK");

    let mut params = nv::NV_ENC_PIC_PARAMS::zeroed();
    params.version = api.api_version.struct_ver_ext(7);
    params.input_width = 1920;
    params.input_height = 1080;
    params.input_time_stamp = 0;
    params.input_buffer = mapped;
    params.output_bitstream = bitstream;
    params.buffer_fmt = nv::NV_ENC_BUFFER_FORMAT_ARGB;
    params.picture_struct = nv::NV_ENC_PIC_STRUCT_FRAME;
    params.encode_pic_flags = nv::NV_ENC_PIC_FLAG_FORCEIDR;
    match api.encode_picture(encoder, &mut params) {
        Ok(s) => println!("encode-picture: status={s}"),
        Err(e) => {
            println!("encode-picture: ERR {e}");
            return;
        }
    }

    let mut lock = nv::NV_ENC_LOCK_BITSTREAM::zeroed();
    lock.version = api.api_version.struct_ver_ext(2);
    lock.output_bitstream = bitstream;
    match api.lock_bitstream(encoder, &mut lock, false) {
        Ok(()) => println!(
            "lock-bitstream: OK {} bytes, picType={} frameIdx={}",
            lock.bitstream_size_in_bytes, lock.picture_type, lock.frame_idx
        ),
        Err(e) => println!("lock-bitstream: ERR {e}"),
    }
}

/// Decisive diagnostic (run manually): drives the PRODUCTION code path —
/// `NvencSession::open` + `encode_texture` (mapping cache, lock, release) —
/// for 70 frames off one self-created texture. Isolates encode-path bugs
/// from WGC texture provenance / preview / multithreading.
#[test]
#[ignore = "manual driver diagnostics"]
fn production_encode_texture_probe() {
    let Ok(bundle) = crate::capture::d3d11_device::create_preferred_device() else {
        println!("no d3d11 device");
        return;
    };
    let config = crate::encoder::NvencConfig {
        codec: crate::encoder::Codec::H264,
        width: 1920,
        height: 1080,
        fps: 60,
        cq: 16,
        preset: crate::encoder::Preset::P7,
        multipass: crate::encoder::Multipass::FullRes,
        lookahead: 32,
        spatial_aq: std::env::var("PROBE_SPATIAL_AQ").map(|v| v == "1").unwrap_or(false),
        temporal_aq: std::env::var("PROBE_TEMPORAL_AQ").map(|v| v == "1").unwrap_or(false),
        b_frames: 0,
        gop_frames: 240,
    };
    let mut session = match NvencSession::open(&config, &bundle.device) {
        Ok(s) => s,
        Err(e) => {
            println!("open: ERR {e}");
            return;
        }
    };
    println!(
        "open: OK (spatial_aq={} temporal_aq={})",
        config.spatial_aq, config.temporal_aq
    );

    use windows::Win32::Graphics::Direct3D11::{
        D3D11_BIND_RENDER_TARGET, D3D11_TEXTURE2D_DESC, D3D11_USAGE_DEFAULT, ID3D11Texture2D,
    };
    use windows::Win32::Graphics::Dxgi::Common::DXGI_FORMAT_B8G8R8A8_UNORM;
    let desc = D3D11_TEXTURE2D_DESC {
        Width: 1920,
        Height: 1080,
        MipLevels: 1,
        ArraySize: 1,
        Format: DXGI_FORMAT_B8G8R8A8_UNORM,
        SampleDesc: windows::Win32::Graphics::Dxgi::Common::DXGI_SAMPLE_DESC { Count: 1, Quality: 0 },
        Usage: D3D11_USAGE_DEFAULT,
        BindFlags: (D3D11_BIND_RENDER_TARGET.0) as u32,
        CPUAccessFlags: 0,
        MiscFlags: 0,
    };
    let mut tex: Option<ID3D11Texture2D> = None;
    unsafe {
        bundle.device.CreateTexture2D(&desc, None, Some(&mut tex));
    }
    let Some(tex) = tex else {
        println!("texture-create: FAILED");
        return;
    };

    let mut success_frames = 0u32;
    let mut emitted_pts: Vec<u64> = Vec::new();
    for frame in 0..70u64 {
        match session.encode_texture(&tex, frame * 16666, frame == 0) {
            Ok(pkts) => {
                if !pkts.is_empty() {
                    success_frames += pkts.len() as u32;
                    emitted_pts.push(pkts[0].pts_us);
                    println!(
                        "frame {frame}: {} pkt(s) {} bytes keyframe={} picPts={}",
                        pkts.len(),
                        pkts[0].data.len(),
                        pkts[0].is_keyframe,
                        pkts[0].pts_us
                    );
                }
            }
            Err(e) => {
                println!("frame {frame}: encode ERR {e}");
                return;
            }
        }
    }
    let flushed = session.flush().unwrap_or_default();
    for p in &flushed {
        emitted_pts.push(p.pts_us);
    }
    println!("COMPLETED: drained={success_frames} flushed={} pkt(s) pts={:?}", flushed.len(), emitted_pts);
    // Repair Pass 1 regression: zero PTS must be preserved and sequence must be nondecreasing.
    // NVENC echoes input_time_stamp exactly, including 0 for the first frame.
    assert!(
        emitted_pts.contains(&0),
        "PTS must include 0 (first frame), got {:?}",
        emitted_pts
    );
    for w in emitted_pts.windows(2) {
        assert!(
            w[0] <= w[1],
            "PTS must be nondecreasing, violated at {} -> {} in {:?}",
            w[0],
            w[1],
            emitted_pts
        );
    }
}

/// Diagnostic (run manually): production-shape session (P7/HQ/CQP16/lookahead
/// 32/AQ/multipass full-res) driven for 60 frames off one reused texture —
/// reproduces the encode-thread crash without WGC in the picture.
#[test]
#[ignore = "manual driver diagnostics"]
fn production_shape_sustained_probe() {
    use crate::encoder::nvenc_api as nv;
    let Ok(bundle) = crate::capture::d3d11_device::create_preferred_device() else {
        println!("no d3d11 device");
        return;
    };
    let Ok(api) = nv::load() else {
        println!("no nvenc api");
        return;
    };
    let dev_ptr = bundle.device.as_raw() as *mut core::ffi::c_void;
    let encoder = match api.open_encode_session_ex(dev_ptr) {
        Ok(e) => e,
        Err(e) => {
            println!("open-session: ERR {e}");
            return;
        }
    };

    // Exactly what open() builds for a PROFILE_V2 take.
    let mut cfg = nv::NV_ENC_CONFIG::zeroed();
    cfg.version = api.api_version.struct_ver_ext(9);
    cfg.profile_guid = nv::NV_ENC_H264_PROFILE_HIGH_GUID;
    cfg.gop_length = 240;
    cfg.frame_interval_p = 1;
    cfg.frame_field_mode = nv::NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME;
    cfg.rc_params.version = api.api_version.struct_ver(1);
    cfg.rc_params.rate_control_mode = nv::NV_ENC_PARAMS_RC_CONSTQP;
    cfg.rc_params.const_qp.qp_inter_p = 16;
    cfg.rc_params.const_qp.qp_inter_b = 16;
    cfg.rc_params.const_qp.qp_intra = 16;
    cfg.rc_params.multi_pass = nv::NV_ENC_TWO_PASS_FULL_RESOLUTION;
    if api.get_encode_caps(encoder, nv::NV_ENC_CODEC_H264_GUID, nv::caps::SUPPORT_LOOKAHEAD).unwrap_or(0) != 0 {
        cfg.rc_params.set_enable_lookahead(true);
        cfg.rc_params.lookahead_depth = 32;
    }
    if api.get_encode_caps(encoder, nv::NV_ENC_CODEC_H264_GUID, nv::caps::SUPPORT_TEMPORAL_AQ).unwrap_or(0) != 0 {
        cfg.rc_params.set_enable_aq(true);
        cfg.rc_params.set_aq_strength(8);
        cfg.rc_params.set_enable_temporal_aq(true);
    }
    unsafe {
        cfg.encode_codec_config.h264_config.chroma_format_idc = 1;
        cfg.encode_codec_config.h264_config.set_repeat_spspps(true);
    }

    let mut init = nv::NV_ENC_INITIALIZE_PARAMS::zeroed();
    init.version = api.api_version.struct_ver_ext(7);
    init.encode_guid = nv::NV_ENC_CODEC_H264_GUID;
    init.preset_guid = nv::NV_ENC_PRESET_P7_GUID;
    init.encode_width = 1920;
    init.encode_height = 1080;
    init.dar_width = 1920;
    init.dar_height = 1080;
    init.frame_rate_num = 60;
    init.frame_rate_den = 1;
    init.enable_encode_async = 0;
    init.enable_ptd = 1;
    init.tuning_info = nv::NV_ENC_TUNING_INFO_HIGH_QUALITY;
    init.buffer_format = nv::NV_ENC_BUFFER_FORMAT_ARGB;
    init.max_encode_width = 1920;
    init.max_encode_height = 1080;
    init.encode_config = &mut cfg;
    if let Err(e) = api.initialize_encoder(encoder, &mut init) {
        println!("initialize: ERR {e}");
        return;
    }
    println!("initialize: OK");

    let bitstream = match api.create_bitstream_buffer(encoder) {
        Ok(b) => b,
        Err(e) => {
            println!("bitstream-buffer: ERR {e}");
            return;
        }
    };

    use windows::Win32::Graphics::Direct3D11::{
        D3D11_BIND_RENDER_TARGET, D3D11_TEXTURE2D_DESC, D3D11_USAGE_DEFAULT, ID3D11Texture2D,
    };
    use windows::Win32::Graphics::Dxgi::Common::DXGI_FORMAT_B8G8R8A8_UNORM;
    let desc = D3D11_TEXTURE2D_DESC {
        Width: 1920,
        Height: 1080,
        MipLevels: 1,
        ArraySize: 1,
        Format: DXGI_FORMAT_B8G8R8A8_UNORM,
        SampleDesc: windows::Win32::Graphics::Dxgi::Common::DXGI_SAMPLE_DESC { Count: 1, Quality: 0 },
        Usage: D3D11_USAGE_DEFAULT,
        BindFlags: (D3D11_BIND_RENDER_TARGET.0) as u32,
        CPUAccessFlags: 0,
        MiscFlags: 0,
    };
    let mut tex: Option<ID3D11Texture2D> = None;
    unsafe {
        bundle.device.CreateTexture2D(&desc, None, Some(&mut tex));
    }
    let Some(tex) = tex else {
        println!("texture-create: FAILED");
        return;
    };

    let mut reg = nv::NV_ENC_REGISTER_RESOURCE::zeroed();
    reg.version = api.api_version.struct_ver(5);
    reg.resource_type = nv::NV_ENC_INPUT_RESOURCE_TYPE_DIRECTX;
    reg.width = 1920;
    reg.height = 1080;
    reg.resource_to_register = tex.as_raw() as *mut core::ffi::c_void;
    reg.buffer_format = nv::NV_ENC_BUFFER_FORMAT_ARGB;
    let registered = match api.register_resource(encoder, &mut reg) {
        Ok(r) => r,
        Err(e) => {
            println!("register-resource: ERR {e}");
            return;
        }
    };
    println!("register-resource: OK");

    for frame in 0..60u64 {
        let (mapped, _) = match api.map_input_resource(encoder, registered) {
            Ok(m) => m,
            Err(e) => {
                println!("frame {frame}: map ERR {e}");
                return;
            }
        };
        let mut params = nv::NV_ENC_PIC_PARAMS::zeroed();
        params.version = api.api_version.struct_ver_ext(7);
        params.input_width = 1920;
        params.input_height = 1080;
        params.input_time_stamp = frame * 16666;
        params.input_buffer = mapped;
        params.output_bitstream = bitstream;
        params.buffer_fmt = nv::NV_ENC_BUFFER_FORMAT_ARGB;
        params.picture_struct = nv::NV_ENC_PIC_STRUCT_FRAME;
        params.encode_pic_flags = if frame == 0 { nv::NV_ENC_PIC_FLAG_FORCEIDR } else { 0 };
        match api.encode_picture(encoder, &mut params) {
            Ok(s) if s == nv::NV_ENC_SUCCESS => {
                eprintln!("frame {frame}: SUCCESS → lock");
                let mut lock = nv::NV_ENC_LOCK_BITSTREAM::zeroed();
                lock.version = api.api_version.struct_ver_ext(2);
                lock.output_bitstream = bitstream;
                match api.lock_bitstream(encoder, &mut lock, false) {
                    Ok(()) => eprintln!(
                        "frame {frame}: lock {} bytes picType={}",
                        lock.bitstream_size_in_bytes, lock.picture_type
                    ),
                    Err(e) => {
                        println!("frame {frame}: lock ERR {e}");
                        return;
                    }
                }
            }
            Ok(s) => eprintln!("frame {frame}: status={s}"),
            Err(e) => {
                println!("frame {frame}: encode ERR {e}");
                return;
            }
        }
        api.unmap_input_resource(encoder, mapped);
    }
    println!("sustained probe: COMPLETED 60 frames");
}
