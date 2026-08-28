//! Hand-written FFI surface for `nvEncodeAPI64.dll` (ban_ke_hoach_v1.md §8).
//!
//! ```text
//! LoadLibraryW(nvEncodeAPI64.dll)
//!     └─ GetProcAddress("NvEncodeAPICreateInstance")
//!          └─ fills NV_ENCODE_API_FUNCTION_LIST (positional — ORDER IS ABI)
//! ```
//!
//! Every struct below is transcribed **verbatim** from the NVIDIA Video Codec
//! SDK header `nvEncodeAPI.h`, SDK **13.1** (`NVENCAPI_MAJOR_VERSION 13`,
//! `NVENCAPI_MINOR_VERSION 1`; copyright 2010-2026 NVIDIA Corporation), taken
//! from the byte-exact mirror maintained at `FFmpeg/nv-codec-headers`. Field
//! names, types and — critically — **order** are preserved because the
//! function list and the parameter structs are positional contracts: a single
//! swapped field silently corrupts the encode stream. Never edit a struct
//! without re-diffing against the upstream header.
//!
//! Version discipline (§3-C fail-closed):
//! * Per-struct `.version` fields are built with [`nvenapi_struct_version`]
//!   exactly like the header's `NVENCAPI_STRUCT_VERSION` macro.
//! * At load time [`load`] walks a small API-version ladder (13.1 → 12.0).
//!   The function table is append-only across SDK releases, so an older
//!   driver correctly fills the prefix of our newer-shaped table; every entry
//!   this engine calls predates the ladder floor.
//! * A driver older than the ladder answers `NV_ENC_ERR_INVALID_VERSION`,
//!   which surfaces as the explicit blocker `NVENC_DRIVER_TOO_OLD` — recording
//!   is blocked, never silently degraded (Principle C).
//!
//! All unsafe FFI is wrapped in small checked methods on [`NvencApi`]; none of
//! them panics on a driver error — each maps the status code to a named
//! blocker string via [`status_name`].

/// Major version of the SDK header this module was transcribed against.
pub const NVENCAPI_MAJOR_VERSION: u32 = 13;
/// Minor version of the SDK header this module was transcribed against.
pub const NVENCAPI_MINOR_VERSION: u32 = 1;

/// SDK identity in the same bit layout as the wire `apiVersion` field:
/// `(major | minor << 24)` — mirrors `NVENCAPI_VERSION`.
pub const TRANSCRIBED_SDK_VERSION: u32 = nvenapi_version(NVENCAPI_MAJOR_VERSION, NVENCAPI_MINOR_VERSION);

/// `NVENCAPI_VERSION (MAJOR | (MINOR << 24))`.
pub const fn nvenapi_version(major: u32, minor: u32) -> u32 {
    major | (minor << 24)
}

/// `NVENCAPI_STRUCT_VERSION(ver) ((uint32_t)NVENCAPI_VERSION | ((ver)<<16) | (0x7 << 28))`.
pub const fn nvenapi_struct_version(api_version: u32, counter: u32) -> u32 {
    api_version | (counter << 16) | (0x7 << 28)
}

/// Variant of [`nvenapi_struct_version`] with the `1u << 31` flag the header
/// OR-s onto structs that embed the large codec-config/reserved tails
/// (`| (1u<<31)` in `NV_ENC_CONFIG_VER`, `NV_ENC_INITIALIZE_PARAMS_VER`, …).
pub const fn nvenapi_struct_version_ext(api_version: u32, counter: u32) -> u32 {
    nvenapi_struct_version(api_version, counter) | (1u32 << 31)
}

/// Negotiated API version used to stamp every struct `.version` field.
///
/// [`load()`] picks the highest version the installed driver accepts from the
/// compatibility ladder; session code derives all struct versions from this so
/// client and driver always agree on the wire format.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ApiVersion {
    pub major: u32,
    pub minor: u32,
}

impl ApiVersion {
    /// Version transcribed verbatim in this module.
    pub const TRANSCRIBED: Self = Self { major: NVENCAPI_MAJOR_VERSION, minor: NVENCAPI_MINOR_VERSION };

    /// Lowest version accepted by the load ladder (see [`load`]).
    pub const LADDER_FLOOR: Self = Self { major: 12, minor: 0 };

    /// `(major | minor << 24)` — the `NVENCAPI_VERSION` wire form.
    pub const fn raw(self) -> u32 {
        nvenapi_version(self.major, self.minor)
    }

    /// Struct-version field without the `1<<31` flag.
    pub const fn struct_ver(self, counter: u32) -> u32 {
        nvenapi_struct_version(self.raw(), counter)
    }

    /// Struct-version field including the `1<<31` flag.
    pub const fn struct_ver_ext(self, counter: u32) -> u32 {
        nvenapi_struct_version_ext(self.raw(), counter)
    }
}

// ─── GUID ────────────────────────────────────────────────────────────────────

/// Byte-exact stand-in for the Windows `GUID` layout (16 bytes, align 4).
///
/// Declared locally instead of pulling `windows::core::GUID` so the pure ABI
/// layer (structs, builders, unit tests) compiles on every host; the binary
/// layout is identical, which is all the FFI cares about.
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct NvGuid {
    pub data1: u32,
    pub data2: u16,
    pub data3: u16,
    pub data4: [u8; 8],
}

impl NvGuid {
    pub const fn from_u128(v: u128) -> Self {
        Self {
            data1: (v >> 96) as u32,
            data2: (v >> 80) as u16,
            data3: (v >> 64) as u16,
            data4: [
                (v >> 56) as u8,
                (v >> 48) as u8,
                (v >> 40) as u8,
                (v >> 32) as u8,
                (v >> 24) as u8,
                (v >> 16) as u8,
                (v >> 8) as u8,
                v as u8,
            ],
        }
    }

    pub const fn as_u128(self) -> u128 {
        (self.data1 as u128) << 96
            | (self.data2 as u128) << 80
            | (self.data3 as u128) << 64
            | (self.data4[0] as u128) << 56
            | (self.data4[1] as u128) << 48
            | (self.data4[2] as u128) << 40
            | (self.data4[3] as u128) << 32
            | (self.data4[4] as u128) << 24
            | (self.data4[5] as u128) << 16
            | (self.data4[6] as u128) << 8
            | (self.data4[7] as u128)
    }
}

// ─── Codec / profile / preset GUIDs (header defines, verbatim) ──────────────

/// `{6BC82762-4E63-4ca4-AA85-1E50F321F6BF}` — NV_ENC_CODEC_H264_GUID
pub const NV_ENC_CODEC_H264_GUID: NvGuid =
    NvGuid::from_u128(0x6bc82762_4e63_4ca4_aa85_1e50f321f6bf);
/// `{790CDC88-4522-4d7b-9425-BDA9975F7603}` — NV_ENC_CODEC_HEVC_GUID
pub const NV_ENC_CODEC_HEVC_GUID: NvGuid =
    NvGuid::from_u128(0x790cdc88_4522_4d7b_9425_bda9975f7603);
/// `{BFD6F8E7-233C-4341-8B3E-4818523803F4}` — NV_ENC_CODEC_PROFILE_AUTOSELECT_GUID
pub const NV_ENC_CODEC_PROFILE_AUTOSELECT_GUID: NvGuid =
    NvGuid::from_u128(0xbfd6f8e7_233c_4341_8b3e_4818523803f4);
/// `{E7CBC309-4F7A-4b89-AF2A-D537C92BE310}` — NV_ENC_H264_PROFILE_HIGH_GUID
pub const NV_ENC_H264_PROFILE_HIGH_GUID: NvGuid =
    NvGuid::from_u128(0xe7cbc309_4f7a_4b89_af2a_d537c92be310);
/// `{B514C39A-B55B-40fa-878F-F1253B4DFDEC}` — NV_ENC_HEVC_PROFILE_MAIN_GUID
pub const NV_ENC_HEVC_PROFILE_MAIN_GUID: NvGuid =
    NvGuid::from_u128(0xb514c39a_b55b_40fa_878f_f1253b4dfdec);

/// `{FC0A8D3E-45F8-4CF8-80C7-298871590EBF}` — NV_ENC_PRESET_P1_GUID
pub const NV_ENC_PRESET_P1_GUID: NvGuid =
    NvGuid::from_u128(0xfc0a8d3e_45f8_4cf8_80c7_298871590ebf);
/// `{F581CFB8-88D6-4381-93F0-DF13F9C27DAB}` — NV_ENC_PRESET_P2_GUID
pub const NV_ENC_PRESET_P2_GUID: NvGuid =
    NvGuid::from_u128(0xf581cfb8_88d6_4381_93f0_df13f9c27dab);
/// `{36850110-3A07-441F-94D5-3670631F91F6}` — NV_ENC_PRESET_P3_GUID
pub const NV_ENC_PRESET_P3_GUID: NvGuid =
    NvGuid::from_u128(0x36850110_3a07_441f_94d5_3670631f91f6);
/// `{90A7B826-DF06-4862-B9D2-CD6D73A08681}` — NV_ENC_PRESET_P4_GUID
pub const NV_ENC_PRESET_P4_GUID: NvGuid =
    NvGuid::from_u128(0x90a7b826_df06_4862_b9d2_cd6d73a08681);
/// `{21C6E6B4-297A-4CBA-998F-B6CBDE72ADE3}` — NV_ENC_PRESET_P5_GUID
pub const NV_ENC_PRESET_P5_GUID: NvGuid =
    NvGuid::from_u128(0x21c6e6b4_297a_4cba_998f_b6cbde72ade3);
/// `{8E75C279-6299-4AB6-8302-0B215A335CF5}` — NV_ENC_PRESET_P6_GUID
pub const NV_ENC_PRESET_P6_GUID: NvGuid =
    NvGuid::from_u128(0x8e75c279_6299_4ab6_8302_0b215a335cf5);
/// `{84848C12-6F71-4C13-931B-53E283F57974}` — NV_ENC_PRESET_P7_GUID
pub const NV_ENC_PRESET_P7_GUID: NvGuid =
    NvGuid::from_u128(0x84848c12_6f71_4c13_931b_53e283f57974);

// ─── Enumerations (values verbatim from the header) ─────────────────────────

/// `_NV_ENC_PARAMS_RC_MODE`.
pub const NV_ENC_PARAMS_RC_CONSTQP: u32 = 0x0;
/// `_NV_ENC_PARAMS_RC_MODE`.
pub const NV_ENC_PARAMS_RC_VBR: u32 = 0x1;
/// `_NV_ENC_PARAMS_FRAME_FIELD_MODE` — progressive frames (no UNDEFINED
/// member exists; zero would be rejected as an invalid mode).
pub const NV_ENC_PARAMS_FRAME_FIELD_MODE_FRAME: u32 = 0x01;
/// `_NV_ENC_PARAMS_RC_MODE`.
pub const NV_ENC_PARAMS_RC_CBR: u32 = 0x2;

/// `_NV_ENC_MULTI_PASS` — Single Pass.
pub const NV_ENC_MULTI_PASS_DISABLED: u32 = 0x0;
/// `_NV_ENC_MULTI_PASS` — first pass quarter resolution.
pub const NV_ENC_TWO_PASS_QUARTER_RESOLUTION: u32 = 0x1;
/// `_NV_ENC_MULTI_PASS` — first pass full resolution.
pub const NV_ENC_TWO_PASS_FULL_RESOLUTION: u32 = 0x2;

/// `NV_ENC_TUNING_INFO_UNDEFINED` — invalid for encoding.
pub const NV_ENC_TUNING_INFO_UNDEFINED: u32 = 0;
/// `NV_ENC_TUNING_INFO_HIGH_QUALITY` — quality-first screen recording (§8).
pub const NV_ENC_TUNING_INFO_HIGH_QUALITY: u32 = 1;
/// `NV_ENC_TUNING_INFO_LOW_LATENCY`.
pub const NV_ENC_TUNING_INFO_LOW_LATENCY: u32 = 2;
/// `NV_ENC_TUNING_INFO_ULTRA_LOW_LATENCY`.
pub const NV_ENC_TUNING_INFO_ULTRA_LOW_LATENCY: u32 = 3;
/// `NV_ENC_TUNING_INFO_LOSSLESS`.
pub const NV_ENC_TUNING_INFO_LOSSLESS: u32 = 4;
/// `NV_ENC_TUNING_INFO_ULTRA_HIGH_QUALITY`.
pub const NV_ENC_TUNING_INFO_ULTRA_HIGH_QUALITY: u32 = 5;

/// `NV_ENC_PIC_STRUCT_FRAME` — progressive.
pub const NV_ENC_PIC_STRUCT_FRAME: u32 = 0x01;

/// `NV_ENC_PIC_TYPE_P` — values per nvEncodeAPI.h `NVENCSTATUS`-free enum
/// (P=0x0, B=0x1, EMPTY=0x2, IDR=0x3, IFRAME=0x4, SKIPPED=0x5).
pub const NV_ENC_PIC_TYPE_P: u32 = 0x0;
/// `NV_ENC_PIC_TYPE_B`.
pub const NV_ENC_PIC_TYPE_B: u32 = 0x01;
/// `NV_ENC_PIC_TYPE_EMPTY` — no picture encoded this call.
pub const NV_ENC_PIC_TYPE_EMPTY: u32 = 0x02;
/// `NV_ENC_PIC_TYPE_IDR` — instantaneous decoding refresh (H.264/HEVC IDR).
pub const NV_ENC_PIC_TYPE_IDR: u32 = 0x03;
/// `NV_ENC_PIC_TYPE_I` — intra frame that is *not* an IDR.
///
/// An earlier transcription placed this at 0x02, which is
/// [`NV_ENC_PIC_TYPE_EMPTY`]; the real header lists IFRAME after IDR.
pub const NV_ENC_PIC_TYPE_I: u32 = 0x04;
/// `NV_ENC_PIC_TYPE_SKIPPED`.
pub const NV_ENC_PIC_TYPE_SKIPPED: u32 = 0x05;
/// `NV_ENC_PIC_TYPE_UNKNOWN` (used with `enablePTD=1`).
pub const NV_ENC_PIC_TYPE_UNKNOWN: u32 = 0xFF;

/// `NV_ENC_BUFFER_FORMAT_ARGB` — 8-bit packed A8R8G8B8.
///
/// This is the NVENC name for `DXGI_FORMAT_B8G8R8A8_UNORM` (byte order
/// B,G,R,A little-endian) — the WGC composition format (§7).
pub const NV_ENC_BUFFER_FORMAT_ARGB: u32 = 0x01000000;

/// `NV_ENC_BUFFER_FORMAT_NV12` — semi-planar 8-bit YUV 4:2:0.
pub const NV_ENC_BUFFER_FORMAT_NV12: u32 = 0x00000001;

/// `NV_ENC_INPUT_RESOURCE_TYPE_DIRECTX`.
pub const NV_ENC_INPUT_RESOURCE_TYPE_DIRECTX: u32 = 0x0;

/// `NV_ENC_DEVICE_TYPE_DIRECTX`.
pub const NV_ENC_DEVICE_TYPE_DIRECTX: u32 = 0x0;

/// `_NV_ENC_PIC_FLAGS` — encode as Intra.
pub const NV_ENC_PIC_FLAG_FORCEINTRA: u32 = 0x1;
/// `_NV_ENC_PIC_FLAGS` — encode as IDR.
pub const NV_ENC_PIC_FLAG_FORCEIDR: u32 = 0x2;
/// `_NV_ENC_PIC_FLAGS` — write SPS/PPS into this picture's bitstream.
pub const NV_ENC_PIC_FLAG_OUTPUT_SPSPPS: u32 = 0x4;
/// `_NV_ENC_PIC_FLAGS` — end of input stream (flush marker).
pub const NV_ENC_PIC_FLAG_EOS: u32 = 0x8;

/// `NV_ENC_BUFFER_USAGE` — registered surface is an input image.
pub const NV_ENC_INPUT_IMAGE: u32 = 0x0;

/// `NV_ENC_MEMORY_HEAP_AUTOSELECT`.
pub const NV_ENC_MEMORY_HEAP_AUTOSELECT: u32 = 0;

/// `NV_ENC_H264_ENTROPY_CODING_MODE_AUTOSELECT`.
pub const NV_ENC_H264_ENTROPY_CODING_MODE_AUTOSELECT: u32 = 0x0;
/// `NV_ENC_H264_BDIRECT_MODE_AUTOSELECT`.
pub const NV_ENC_H264_BDIRECT_MODE_AUTOSELECT: u32 = 0x0;
/// `NV_ENC_H264_FMO_AUTOSELECT`.
pub const NV_ENC_H264_FMO_AUTOSELECT: u32 = 0x0;
/// `NV_ENC_H264_ADAPTIVE_TRANSFORM_AUTOSELECT`.
pub const NV_ENC_H264_ADAPTIVE_TRANSFORM_AUTOSELECT: u32 = 0x0;
/// `NV_ENC_STEREO_PACKING_MODE_NONE`.
pub const NV_ENC_STEREO_PACKING_MODE_NONE: u32 = 0x0;
/// `NV_ENC_BFRAME_REF_MODE_DISABLED`.
pub const NV_ENC_BFRAME_REF_MODE_DISABLED: u32 = 0x0;
/// `NV_ENC_NUM_REF_FRAMES_AUTOSELECT`.
pub const NV_ENC_NUM_REF_FRAMES_AUTOSELECT: u32 = 0x0;
/// `NV_ENC_HEVC_CUSIZE_AUTOSELECT`.
pub const NV_ENC_HEVC_CUSIZE_AUTOSELECT: u32 = 0;
/// `NV_ENC_LOOKAHEAD_LEVEL_AUTOSELECT`.
pub const NV_ENC_LOOKAHEAD_LEVEL_AUTOSELECT: u32 = 15;
/// `NV_ENC_LEVEL_AUTOSELECT`.
pub const NV_ENC_LEVEL_AUTOSELECT: u32 = 0;
/// `NV_ENC_BIT_DEPTH_8`.
pub const NV_ENC_BIT_DEPTH_8: u32 = 8;
/// `NVENC_INFINITE_GOPLENGTH`.
pub const NVENC_INFINITE_GOPLENGTH: u32 = 0xffff_ffff;

/// `NV_ENC_QP_MAP_DISABLED`.
pub const NV_ENC_QP_MAP_DISABLED: u32 = 0x0;

/// `_NV_ENC_CAPS` — ordinal positions are ABI (enum starts at 0).
///
/// Transcribed in declaration order from the SDK 13.1 header; the values the
/// engine queries are `NUM_MAX_BFRAMES`, `WIDTH_MAX`, `HEIGHT_MAX`,
/// `SUPPORT_LOOKAHEAD`, `SUPPORT_TEMPORAL_AQ` and
/// `DYNAMIC_QUERY_ENCODER_CAPACITY`.
pub mod caps {
    pub const NUM_MAX_BFRAMES: i32 = 0;
    pub const SUPPORTED_RATECONTROL_MODES: i32 = 1;
    pub const SUPPORT_FIELD_ENCODING: i32 = 2;
    pub const SUPPORT_MONOCHROME: i32 = 3;
    pub const SUPPORT_FMO: i32 = 4;
    pub const SUPPORT_QPELMV: i32 = 5;
    pub const SUPPORT_BDIRECT_MODE: i32 = 6;
    pub const SUPPORT_CABAC: i32 = 7;
    pub const SUPPORT_ADAPTIVE_TRANSFORM: i32 = 8;
    pub const SUPPORT_STEREO_MVC: i32 = 9;
    pub const NUM_MAX_TEMPORAL_LAYERS: i32 = 10;
    pub const SUPPORT_HIERARCHICAL_PFRAMES: i32 = 11;
    pub const SUPPORT_HIERARCHICAL_BFRAMES: i32 = 12;
    pub const LEVEL_MAX: i32 = 13;
    pub const LEVEL_MIN: i32 = 14;
    pub const SEPARATE_COLOUR_PLANE: i32 = 15;
    pub const WIDTH_MAX: i32 = 16;
    pub const HEIGHT_MAX: i32 = 17;
    pub const SUPPORT_TEMPORAL_SVC: i32 = 18;
    pub const SUPPORT_DYN_RES_CHANGE: i32 = 19;
    pub const SUPPORT_DYN_BITRATE_CHANGE: i32 = 20;
    pub const SUPPORT_DYN_FORCE_CONSTQP: i32 = 21;
    pub const SUPPORT_DYN_RCMODE_CHANGE: i32 = 22;
    pub const SUPPORT_SUBFRAME_READBACK: i32 = 23;
    pub const SUPPORT_CONSTRAINED_ENCODING: i32 = 24;
    pub const SUPPORT_INTRA_REFRESH: i32 = 25;
    pub const SUPPORT_CUSTOM_VBV_BUF_SIZE: i32 = 26;
    pub const SUPPORT_DYNAMIC_SLICE_MODE: i32 = 27;
    pub const SUPPORT_REF_PIC_INVALIDATION: i32 = 28;
    pub const PREPROC_SUPPORT: i32 = 29;
    pub const ASYNC_ENCODE_SUPPORT: i32 = 30;
    pub const MB_NUM_MAX: i32 = 31;
    pub const MB_PER_SEC_MAX: i32 = 32;
    pub const SUPPORT_YUV444_ENCODE: i32 = 33;
    pub const SUPPORT_LOSSLESS_ENCODE: i32 = 34;
    pub const SUPPORT_SAO: i32 = 35;
    pub const SUPPORT_MEONLY_MODE: i32 = 36;
    pub const SUPPORT_LOOKAHEAD: i32 = 37;
    pub const SUPPORT_TEMPORAL_AQ: i32 = 38;
    pub const SUPPORT_10BIT_ENCODE: i32 = 39;
    pub const NUM_MAX_LTR_FRAMES: i32 = 40;
    pub const SUPPORT_WEIGHTED_PREDICTION: i32 = 41;
    pub const DYNAMIC_QUERY_ENCODER_CAPACITY: i32 = 42;
    pub const SUPPORT_BFRAME_REF_MODE: i32 = 43;
    pub const SUPPORT_EMPHASIS_LEVEL_MAP: i32 = 44;
    pub const WIDTH_MIN: i32 = 45;
    pub const HEIGHT_MIN: i32 = 46;
    pub const SUPPORT_MULTIPLE_REF_FRAMES: i32 = 47;
    pub const SUPPORT_ALPHA_LAYER_ENCODING: i32 = 48;
    pub const NUM_ENCODER_ENGINES: i32 = 49;
    pub const SINGLE_SLICE_INTRA_REFRESH: i32 = 50;
    pub const DISABLE_ENC_STATE_ADVANCE: i32 = 51;
    pub const OUTPUT_RECON_SURFACE: i32 = 52;
    pub const OUTPUT_BLOCK_STATS: i32 = 53;
    pub const OUTPUT_ROW_STATS: i32 = 54;
    pub const SUPPORT_TEMPORAL_FILTER: i32 = 55;
    pub const SUPPORT_LOOKAHEAD_LEVEL: i32 = 56;
    pub const SUPPORT_UNIDIRECTIONAL_B: i32 = 57;
    pub const SUPPORT_MVHEVC_ENCODE: i32 = 58;
    pub const SUPPORT_YUV422_ENCODE: i32 = 59;
    pub const EXPOSED_COUNT: i32 = 60;
}

// ─── Status codes (_NVENCSTATUS ordinals) ────────────────────────────────────

pub const NV_ENC_SUCCESS: u32 = 0;
pub const NV_ENC_ERR_NO_ENCODE_DEVICE: u32 = 1;
pub const NV_ENC_ERR_UNSUPPORTED_DEVICE: u32 = 2;
pub const NV_ENC_ERR_INVALID_ENCODERDEVICE: u32 = 3;
pub const NV_ENC_ERR_INVALID_DEVICE: u32 = 4;
pub const NV_ENC_ERR_DEVICE_NOT_EXIST: u32 = 5;
pub const NV_ENC_ERR_INVALID_PTR: u32 = 6;
pub const NV_ENC_ERR_INVALID_EVENT: u32 = 7;
pub const NV_ENC_ERR_INVALID_PARAM: u32 = 8;
pub const NV_ENC_ERR_INVALID_CALL: u32 = 9;
pub const NV_ENC_ERR_OUT_OF_MEMORY: u32 = 10;
pub const NV_ENC_ERR_ENCODER_NOT_INITIALIZED: u32 = 11;
pub const NV_ENC_ERR_UNSUPPORTED_PARAM: u32 = 12;
pub const NV_ENC_ERR_LOCK_BUSY: u32 = 13;
pub const NV_ENC_ERR_NOT_ENOUGH_BUFFER: u32 = 14;
pub const NV_ENC_ERR_INVALID_VERSION: u32 = 15;
pub const NV_ENC_ERR_MAP_FAILED: u32 = 16;
pub const NV_ENC_ERR_NEED_MORE_INPUT: u32 = 17;
pub const NV_ENC_ERR_ENCODER_BUSY: u32 = 18;
pub const NV_ENC_ERR_EVENT_NOT_REGISTERD: u32 = 19;
pub const NV_ENC_ERR_GENERIC: u32 = 20;
pub const NV_ENC_ERR_INCOMPATIBLE_CLIENT_KEY: u32 = 21;
pub const NV_ENC_ERR_UNIMPLEMENTED: u32 = 22;
pub const NV_ENC_ERR_RESOURCE_REGISTER_FAILED: u32 = 23;
pub const NV_ENC_ERR_RESOURCE_NOT_REGISTERED: u32 = 24;
pub const NV_ENC_ERR_RESOURCE_NOT_MAPPED: u32 = 25;
pub const NV_ENC_ERR_NEED_MORE_OUTPUT: u32 = 26;

/// Map a `_NVENCSTATUS` code to its header name (diagnostics in blockers).
pub fn status_name(status: u32) -> &'static str {
    match status {
        NV_ENC_SUCCESS => "NV_ENC_SUCCESS",
        NV_ENC_ERR_NO_ENCODE_DEVICE => "NV_ENC_ERR_NO_ENCODE_DEVICE",
        NV_ENC_ERR_UNSUPPORTED_DEVICE => "NV_ENC_ERR_UNSUPPORTED_DEVICE",
        NV_ENC_ERR_INVALID_ENCODERDEVICE => "NV_ENC_ERR_INVALID_ENCODERDEVICE",
        NV_ENC_ERR_INVALID_DEVICE => "NV_ENC_ERR_INVALID_DEVICE",
        NV_ENC_ERR_DEVICE_NOT_EXIST => "NV_ENC_ERR_DEVICE_NOT_EXIST",
        NV_ENC_ERR_INVALID_PTR => "NV_ENC_ERR_INVALID_PTR",
        NV_ENC_ERR_INVALID_EVENT => "NV_ENC_ERR_INVALID_EVENT",
        NV_ENC_ERR_INVALID_PARAM => "NV_ENC_ERR_INVALID_PARAM",
        NV_ENC_ERR_INVALID_CALL => "NV_ENC_ERR_INVALID_CALL",
        NV_ENC_ERR_OUT_OF_MEMORY => "NV_ENC_ERR_OUT_OF_MEMORY",
        NV_ENC_ERR_ENCODER_NOT_INITIALIZED => "NV_ENC_ERR_ENCODER_NOT_INITIALIZED",
        NV_ENC_ERR_UNSUPPORTED_PARAM => "NV_ENC_ERR_UNSUPPORTED_PARAM",
        NV_ENC_ERR_LOCK_BUSY => "NV_ENC_ERR_LOCK_BUSY",
        NV_ENC_ERR_NOT_ENOUGH_BUFFER => "NV_ENC_ERR_NOT_ENOUGH_BUFFER",
        NV_ENC_ERR_INVALID_VERSION => "NV_ENC_ERR_INVALID_VERSION",
        NV_ENC_ERR_MAP_FAILED => "NV_ENC_ERR_MAP_FAILED",
        NV_ENC_ERR_NEED_MORE_INPUT => "NV_ENC_ERR_NEED_MORE_INPUT",
        NV_ENC_ERR_ENCODER_BUSY => "NV_ENC_ERR_ENCODER_BUSY",
        NV_ENC_ERR_EVENT_NOT_REGISTERD => "NV_ENC_ERR_EVENT_NOT_REGISTERD",
        NV_ENC_ERR_GENERIC => "NV_ENC_ERR_GENERIC",
        NV_ENC_ERR_INCOMPATIBLE_CLIENT_KEY => "NV_ENC_ERR_INCOMPATIBLE_CLIENT_KEY",
        NV_ENC_ERR_UNIMPLEMENTED => "NV_ENC_ERR_UNIMPLEMENTED",
        NV_ENC_ERR_RESOURCE_REGISTER_FAILED => "NV_ENC_ERR_RESOURCE_REGISTER_FAILED",
        NV_ENC_ERR_RESOURCE_NOT_REGISTERED => "NV_ENC_ERR_RESOURCE_NOT_REGISTERED",
        NV_ENC_ERR_RESOURCE_NOT_MAPPED => "NV_ENC_ERR_RESOURCE_NOT_MAPPED",
        NV_ENC_ERR_NEED_MORE_OUTPUT => "NV_ENC_ERR_NEED_MORE_OUTPUT",
        _ => "NV_ENC_ERR_UNKNOWN",
    }
}

// ─── Structs (transcribed verbatim — DO NOT reorder fields) ─────────────────

use std::os::raw::{c_char, c_void};

/// Zeroed constructor for the POD ABI structs (all-zero is a valid state:
/// every pointer slot is `Option<fn>` / `*mut c_void`, every numeric slot is
/// documented as "must be 0").
macro_rules! abi_zeroed {
    ($($t:ty),* $(,)?) => {$(
        impl $t {
            /// All-zero instance — the required baseline before filling fields.
            pub fn zeroed() -> Self {
                // SAFETY: these are plain-data #[repr(C)] structs; the all-bits-
                // zero pattern is valid for every field (null pointers, zeros).
                unsafe { std::mem::zeroed() }
            }
        }
    )*};
}

/// QP value for frames (`_NV_ENC_QP`). Size 12.
#[repr(C)]
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct NV_ENC_QP {
    pub qp_inter_p: u32,
    pub qp_inter_b: u32,
    pub qp_intra: u32,
}

/// Input struct for querying capabilities (`_NV_ENC_CAPS_PARAM`).
/// `NV_ENC_CAPS_PARAM_VER = NVENCAPI_STRUCT_VERSION(1)`. Size 256.
#[repr(C)]
pub struct NV_ENC_CAPS_PARAM {
    pub version: u32,
    pub caps_to_query: i32,
    pub reserved: [u32; 62],
}
abi_zeroed!(NV_ENC_CAPS_PARAM);

/// Encoder Session Creation parameters (`_NV_ENC_OPEN_ENCODE_SESSIONEX_PARAMS`).
/// `…_VER = NVENCAPI_STRUCT_VERSION(1)`. Size 1552 (MSVC x64).
#[repr(C)]
pub struct NV_ENC_OPEN_ENCODE_SESSION_EX_PARAMS {
    pub version: u32,
    pub device_type: u32,
    pub device: *mut c_void,
    pub reserved: *mut c_void,
    pub api_version: u32,
    pub reserved1: [u32; 253],
    pub reserved2: [*mut c_void; 64],
}
abi_zeroed!(NV_ENC_OPEN_ENCODE_SESSION_EX_PARAMS);

/// H264/HEVC shared VUI parameters (`_NV_ENC_CONFIG_H264_VUI_PARAMETERS`,
/// typedef'd as `NV_ENC_CONFIG_HEVC_VUI_PARAMETERS` in the header). Size 112.
#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct NV_ENC_CONFIG_VUI_PARAMETERS {
    pub overscan_info_present_flag: u32,
    pub overscan_info: u32,
    pub video_signal_type_present_flag: u32,
    pub video_format: u32,
    pub video_full_range_flag: u32,
    pub colour_description_present_flag: u32,
    pub colour_primaries: u32,
    pub transfer_characteristics: u32,
    pub colour_matrix: u32,
    pub chroma_sample_location_flag: u32,
    pub chroma_sample_location_top: u32,
    pub chroma_sample_location_bot: u32,
    pub bitstream_restriction_flag: u32,
    pub timing_info_present_flag: u32,
    pub num_unit_in_ticks: u32,
    pub time_scale: u32,
    pub reserved: [u32; 12],
}
abi_zeroed!(NV_ENC_CONFIG_VUI_PARAMETERS);

/// External motion-vector hint counts per block type
/// (`_NVENC_EXTERNAL_ME_HINT_COUNTS_PER_BLOCKTYPE`).
///
/// The six C bitfields (`4+4+4+4+8+8`) are packed LSB-first into one u32 —
/// MSVC allocates bit fields from the least significant bit of the storage
/// unit, and Rust reproduces the same layout by hand here. Size 16.
#[repr(C)]
#[derive(Debug, Clone, Copy, Default)]
pub struct NVENC_EXTERNAL_ME_HINT_COUNTS_PER_BLOCKTYPE {
    packed_counts: u32,
    pub reserved1: [u32; 3],
}

/// Rate Control Configuration Parameters (`_NV_ENC_RC_PARAMS`).
/// `NV_ENC_RC_PARAMS_VER = NVENCAPI_STRUCT_VERSION(1)`. Size 128.
///
/// The 18 single-bit/4-bit C bitfields are hand-packed LSB-first into
/// [`Self::bit_fields`] (see the accessor helpers).
#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct NV_ENC_RC_PARAMS {
    pub version: u32,
    pub rate_control_mode: u32,
    pub const_qp: NV_ENC_QP,
    pub average_bit_rate: u32,
    pub max_bit_rate: u32,
    pub vbv_buffer_size: u32,
    pub vbv_initial_delay: u32,
    /// enableMinQP:1 enableMaxQP:1 enableInitialRCQP:1 enableAQ:1
    /// reservedBitField1:1 enableLookahead:1 disableIadapt:1 disableBadapt:1
    /// enableTemporalAQ:1 zeroReorderDelay:1 enableNonRefP:1 strictGOPTarget:1
    /// aqStrength:4 enableExtLookahead:1 reservedBitFields:15
    pub bit_fields: u32,
    pub min_qp: NV_ENC_QP,
    pub max_qp: NV_ENC_QP,
    pub initial_rcqp: NV_ENC_QP,
    pub temporallayer_idx_mask: u32,
    pub temporal_layer_qp: [u8; 8],
    pub target_quality: u8,
    pub target_quality_lsb: u8,
    pub lookahead_depth: u16,
    pub low_delay_key_frame_scale: i8,
    pub y_dc_qp_index_offset: i8,
    pub u_dc_qp_index_offset: i8,
    pub v_dc_qp_index_offset: i8,
    pub qp_map_mode: u32,
    pub multi_pass: u32,
    pub alpha_layer_bitrate_ratio: u32,
    pub cb_qp_index_offset: i8,
    pub cr_qp_index_offset: i8,
    pub reserved2: u16,
    pub lookahead_level: u32,
    pub view_bitrate_ratios: [u8; 7],
    pub reserved3: u8,
    pub reserved1: u32,
}
abi_zeroed!(NV_ENC_RC_PARAMS);

impl NV_ENC_RC_PARAMS {
    // Bit offsets mirror the header's declaration order, LSB-first.
    const BF_ENABLE_MIN_QP: u32 = 0;
    const BF_ENABLE_MAX_QP: u32 = 1;
    const BF_ENABLE_INITIAL_RCQP: u32 = 2;
    const BF_ENABLE_AQ: u32 = 3;
    // Transcription completeness: bit 4 is reserved in nvEncodeAPI.h; kept so
    // the bit layout reads 1:1 against the header.
    #[allow(dead_code)]
    const BF_RESERVED_BIT_FIELD1: u32 = 4;
    const BF_ENABLE_LOOKAHEAD: u32 = 5;
    const BF_DISABLE_IADAPT: u32 = 6;
    const BF_DISABLE_BADAPT: u32 = 7;
    const BF_ENABLE_TEMPORAL_AQ: u32 = 8;
    const BF_ZERO_REORDER_DELAY: u32 = 9;
    const BF_ENABLE_NONREF_P: u32 = 10;
    const BF_STRICT_GOP_TARGET: u32 = 11;
    const BF_AQ_STRENGTH: u32 = 12; // :4 → bits 12..15
    const BF_ENABLE_EXT_LOOKAHEAD: u32 = 16;

    fn get(bit: u32) -> u32 {
        1 << bit
    }

    pub fn enable_min_qp(&self) -> bool {
        self.bit_fields & Self::get(Self::BF_ENABLE_MIN_QP) != 0
    }
    pub fn set_enable_min_qp(&mut self, v: bool) {
        self.bit_fields.set_bit(Self::BF_ENABLE_MIN_QP, v);
    }
    pub fn enable_max_qp(&self) -> bool {
        self.bit_fields & Self::get(Self::BF_ENABLE_MAX_QP) != 0
    }
    pub fn set_enable_max_qp(&mut self, v: bool) {
        self.bit_fields.set_bit(Self::BF_ENABLE_MAX_QP, v);
    }
    pub fn enable_initial_rcqp(&self) -> bool {
        self.bit_fields & Self::get(Self::BF_ENABLE_INITIAL_RCQP) != 0
    }
    pub fn set_enable_initial_rcqp(&mut self, v: bool) {
        self.bit_fields.set_bit(Self::BF_ENABLE_INITIAL_RCQP, v);
    }
    /// Spatial adaptive quantization (profile `spatial_aq`, §8).
    pub fn enable_aq(&self) -> bool {
        self.bit_fields & Self::get(Self::BF_ENABLE_AQ) != 0
    }
    pub fn set_enable_aq(&mut self, v: bool) {
        self.bit_fields.set_bit(Self::BF_ENABLE_AQ, v);
    }
    pub fn enable_lookahead(&self) -> bool {
        self.bit_fields & Self::get(Self::BF_ENABLE_LOOKAHEAD) != 0
    }
    pub fn set_enable_lookahead(&mut self, v: bool) {
        self.bit_fields.set_bit(Self::BF_ENABLE_LOOKAHEAD, v);
    }
    pub fn disable_iadapt(&self) -> bool {
        self.bit_fields & Self::get(Self::BF_DISABLE_IADAPT) != 0
    }
    pub fn set_disable_iadapt(&mut self, v: bool) {
        self.bit_fields.set_bit(Self::BF_DISABLE_IADAPT, v);
    }
    pub fn disable_badapt(&self) -> bool {
        self.bit_fields & Self::get(Self::BF_DISABLE_BADAPT) != 0
    }
    pub fn set_disable_badapt(&mut self, v: bool) {
        self.bit_fields.set_bit(Self::BF_DISABLE_BADAPT, v);
    }
    /// Temporal adaptive quantization (profile `temporal_aq`, §8).
    pub fn enable_temporal_aq(&self) -> bool {
        self.bit_fields & Self::get(Self::BF_ENABLE_TEMPORAL_AQ) != 0
    }
    pub fn set_enable_temporal_aq(&mut self, v: bool) {
        self.bit_fields.set_bit(Self::BF_ENABLE_TEMPORAL_AQ, v);
    }
    pub fn zero_reorder_delay(&self) -> bool {
        self.bit_fields & Self::get(Self::BF_ZERO_REORDER_DELAY) != 0
    }
    pub fn set_zero_reorder_delay(&mut self, v: bool) {
        self.bit_fields.set_bit(Self::BF_ZERO_REORDER_DELAY, v);
    }
    pub fn enable_non_ref_p(&self) -> bool {
        self.bit_fields & Self::get(Self::BF_ENABLE_NONREF_P) != 0
    }
    pub fn set_enable_non_ref_p(&mut self, v: bool) {
        self.bit_fields.set_bit(Self::BF_ENABLE_NONREF_P, v);
    }
    pub fn strict_gop_target(&self) -> bool {
        self.bit_fields & Self::get(Self::BF_STRICT_GOP_TARGET) != 0
    }
    pub fn set_strict_gop_target(&mut self, v: bool) {
        self.bit_fields.set_bit(Self::BF_STRICT_GOP_TARGET, v);
    }
    /// AQ strength 1 (low) … 15 (aggressive); 0 = driver default.
    pub fn aq_strength(&self) -> u32 {
        (self.bit_fields >> Self::BF_AQ_STRENGTH) & 0xF
    }
    pub fn set_aq_strength(&mut self, strength: u32) {
        self.bit_fields &= !(0xF << Self::BF_AQ_STRENGTH);
        self.bit_fields |= (strength & 0xF) << Self::BF_AQ_STRENGTH;
    }
    pub fn enable_ext_lookahead(&self) -> bool {
        self.bit_fields & Self::get(Self::BF_ENABLE_EXT_LOOKAHEAD) != 0
    }
    pub fn set_enable_ext_lookahead(&mut self, v: bool) {
        self.bit_fields.set_bit(Self::BF_ENABLE_EXT_LOOKAHEAD, v);
    }
}

trait SetBit {
    fn set_bit(&mut self, bit: u32, v: bool);
}
impl SetBit for u32 {
    fn set_bit(&mut self, bit: u32, v: bool) {
        if v {
            *self |= 1 << bit;
        } else {
            *self &= !(1 << bit);
        }
    }
}

/// H264 encoder configuration parameters (`_NV_ENC_CONFIG_H264`).
/// Embedded in `NV_ENC_CODEC_CONFIG`; the engine keeps every knob at its
/// header default except `repeatSPSPPS` (crash-safe segments, §15) and the
/// bit-depth/profile defaults. Size 1792 (MSVC x64).
#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct NV_ENC_CONFIG_H264 {
    /// enableTemporalSVC:1 … reservedBitFields:10 (22 single bits total,
    /// packed LSB-first — see `nvenc_api.h` declaration order).
    pub bit_fields: u32,
    pub level: u32,
    pub idr_period: u32,
    pub separate_colour_plane_flag: u32,
    pub disable_deblocking_filter_idc: u32,
    pub num_temporal_layers: u32,
    pub sps_id: u32,
    pub pps_id: u32,
    pub adaptive_transform_mode: u32,
    pub fmo_mode: u32,
    pub bdirect_mode: u32,
    pub entropy_coding_mode: u32,
    pub stereo_mode: u32,
    pub intra_refresh_period: u32,
    pub intra_refresh_cnt: u32,
    pub max_num_ref_frames: u32,
    pub slice_mode: u32,
    pub slice_mode_data: u32,
    pub h264_vui_parameters: NV_ENC_CONFIG_VUI_PARAMETERS,
    pub ltr_num_frames: u32,
    pub ltr_trust_mode: u32,
    pub chroma_format_idc: u32,
    pub max_temporal_layers: u32,
    pub use_bframes_as_ref: u32,
    pub num_ref_l0: u32,
    pub num_ref_l1: u32,
    pub output_bit_depth: u32,
    pub input_bit_depth: u32,
    pub tf_level: u32,
    pub reserved1: [u32; 264],
    pub reserved2: [*mut c_void; 64],
}
abi_zeroed!(NV_ENC_CONFIG_H264);

impl NV_ENC_CONFIG_H264 {
    const BF_REPEAT_SPSPPS: u32 = 12; // 13th declared single-bit field

    /// Write SPS/PPS at every IDR — each MKV segment starts independently
    /// playable even after a crash mid-take (§9 segmentation + §15 recovery).
    pub fn repeat_spspps(&self) -> bool {
        self.bit_fields & (1 << Self::BF_REPEAT_SPSPPS) != 0
    }
    pub fn set_repeat_spspps(&mut self, v: bool) {
        <u32 as SetBit>::set_bit(&mut self.bit_fields, Self::BF_REPEAT_SPSPPS, v);
    }
}

/// HEVC encoder configuration parameters (`_NV_ENC_CONFIG_HEVC`).
/// Size 1560 (MSVC x64).
///
/// Bit-field word (LSB-first, SDK 13.1 header order): bits 0-8 are
/// useConstrainedIntraPred, disableDeblockAcrossSliceBoundary,
/// outputBufferingPeriodSEI, outputPictureTimingSEI, outputAUD, enableLTR,
/// disableSPSPPS, repeatSPSPPS, enableIntraRefresh; bits 9-10 hold
/// chromaFormatIDC (:2); then reserved3:3 and thirteen more single-bit
/// flags through enableRefPicListModification; reserved:5 tops the word.
#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct NV_ENC_CONFIG_HEVC {
    pub level: u32,
    pub tier: u32,
    pub min_cu_size: u32,
    pub max_cu_size: u32,
    /// useConstrainedIntraPred:1 … reserved:5 (chromaFormatIDC:2 at 9..10).
    pub bit_fields: u32,
    pub idr_period: u32,
    pub intra_refresh_period: u32,
    pub intra_refresh_cnt: u32,
    pub max_num_ref_frames_in_dpb: u32,
    pub ltr_num_frames: u32,
    pub vps_id: u32,
    pub sps_id: u32,
    pub pps_id: u32,
    pub slice_mode: u32,
    pub slice_mode_data: u32,
    pub max_temporal_layers_minus1: u32,
    pub hevc_vui_parameters: NV_ENC_CONFIG_VUI_PARAMETERS,
    pub ltr_trust_mode: u32,
    pub use_bframes_as_ref: u32,
    pub num_ref_l0: u32,
    pub num_ref_l1: u32,
    pub tf_level: u32,
    pub disable_deblocking_filter_idc: u32,
    pub output_bit_depth: u32,
    pub input_bit_depth: u32,
    pub num_temporal_layers: u32,
    pub num_views: u32,
    pub reserved1: [u32; 208],
    pub reserved2: [*mut c_void; 64],
}
abi_zeroed!(NV_ENC_CONFIG_HEVC);

impl NV_ENC_CONFIG_HEVC {
    /// 8th declared single-bit field (bits 0-7: useConstrainedIntraPred,
    /// disableDeblockAcrossSliceBoundary, outputBufferingPeriodSEI,
    /// outputPictureTimingSEI, outputAUD, enableLTR, disableSPSPPS,
    /// repeatSPSPPS). An earlier transcription skipped
    /// disableDeblockAcrossSliceBoundary and wrote this flag into bit 8 —
    /// `enableIntraRefresh` — silently turning on intra refresh instead.
    const BF_REPEAT_SPSPPS: u32 = 7;
    /// chromaFormatIDC is a :2 field at bits 9-10 in the SAME word (unlike
    /// H264 where chromaFormatIDC is a standalone u32).
    const BF_CHROMA_FORMAT_IDC: u32 = 9;

    /// See [`NV_ENC_CONFIG_H264::repeat_spspps`].
    pub fn repeat_spspps(&self) -> bool {
        self.bit_fields & (1 << Self::BF_REPEAT_SPSPPS) != 0
    }
    pub fn set_repeat_spspps(&mut self, v: bool) {
        <u32 as SetBit>::set_bit(&mut self.bit_fields, Self::BF_REPEAT_SPSPPS, v);
    }

    /// Bitstream chroma format (1 = 4:2:0). The custom-config path must
    /// declare it or InitializeEncoder fails with "Unsupported color format."
    pub fn chroma_format_idc(&self) -> u32 {
        (self.bit_fields >> Self::BF_CHROMA_FORMAT_IDC) & 0x3
    }
    pub fn set_chroma_format_idc(&mut self, v: u32) {
        self.bit_fields &= !(0x3 << Self::BF_CHROMA_FORMAT_IDC);
        self.bit_fields |= (v & 0x3) << Self::BF_CHROMA_FORMAT_IDC;
    }
}

/// `NV_ENC_CODEC_CONFIG` union — codec-specific config inside
/// `_NV_ENC_CONFIG`. Union size = max(member, reserved[320]) = 1792.
#[repr(C)]
#[derive(Clone, Copy)]
pub union NV_ENC_CODEC_CONFIG {
    pub h264_config: NV_ENC_CONFIG_H264,
    pub hevc_config: NV_ENC_CONFIG_HEVC,
    pub reserved: [u32; 320],
}

/// Encoder configuration parameters (`_NV_ENC_CONFIG`).
/// `NV_ENC_CONFIG_VER = NVENCAPI_STRUCT_VERSION(9) | (1u<<31)`. Size 3584.
#[repr(C)]
pub struct NV_ENC_CONFIG {
    pub version: u32,
    pub profile_guid: NvGuid,
    pub gop_length: u32,
    /// GOP pattern: 0=I, 1=IPP, 2=IBP, 3=IBBP … (`b_frames + 1`, §8).
    pub frame_interval_p: i32,
    pub monochrome_encoding: u32,
    pub frame_field_mode: u32,
    pub mv_precision: u32,
    pub rc_params: NV_ENC_RC_PARAMS,
    pub encode_codec_config: NV_ENC_CODEC_CONFIG,
    pub reserved: [u32; 278],
    pub reserved2: [*mut c_void; 64],
}
abi_zeroed!(NV_ENC_CONFIG);

/// `NVENC_EXTERNAL_ME_HINT_COUNTS_PER_BLOCKTYPE` — all fields packed into one
/// bitfield word plus three reserved words (16 bytes). We never pass external
/// ME hints, so zeroed is always correct here; the array exists purely to
/// keep the surrounding layout honest.

/// Encode Session Initialization parameters (`_NV_ENC_INITIALIZE_PARAMS`).
/// `…_VER = NVENCAPI_STRUCT_VERSION(7) | (1u<<31)`. Size 1800 (MSVC x64).
///
/// Layout lesson from this exact file's history: dropping
/// `maxMEHintCountsPerBlock` (it exists in BOTH this struct and
/// `NV_ENC_PIC_PARAMS`) keeps the total size plausible but shifts every later
/// field down 32 bytes — the driver then reads garbage for `tuningInfo`
/// (`Unsupported color format.` / INVALID_PARAM on healthy hardware). The
/// `offset_of!` regression test below pins each field against the SDK header,
/// not against whatever the struct happens to be today.
#[repr(C)]
pub struct NV_ENC_INITIALIZE_PARAMS {
    pub version: u32,
    pub encode_guid: NvGuid,
    pub preset_guid: NvGuid,
    pub encode_width: u32,
    pub encode_height: u32,
    pub dar_width: u32,
    pub dar_height: u32,
    pub frame_rate_num: u32,
    pub frame_rate_den: u32,
    /// Sync mode (`async=0`, §8) — simplest correct pipeline.
    pub enable_encode_async: u32,
    /// Picture Type Decision delegated to NVENC (`enablePTD=1`, §8).
    pub enable_ptd: u32,
    /// reportSliceOffsets:1 enableSubFrameWrite:1 enableExternalMEHints:1
    /// enableMEOnlyMode:1 enableWeightedPrediction:1 splitEncodeMode:4
    /// enableOutputInVidmem:1 enableReconFrameOutput:1 enableOutputStats:1
    /// enableUniDirectionalB:1 reservedBitFields:19
    pub bit_fields: u32,
    pub priv_data_size: u32,
    pub reserved: u32,
    pub priv_data: *mut c_void,
    pub encode_config: *mut NV_ENC_CONFIG,
    pub max_encode_width: u32,
    pub max_encode_height: u32,
    pub max_me_hint_counts_per_block: [NVENC_EXTERNAL_ME_HINT_COUNTS_PER_BLOCKTYPE; 2],
    pub tuning_info: u32,
    pub buffer_format: u32,
    pub num_state_buffers: u32,
    pub output_stats_level: u32,
    pub reserved1: [u32; 284],
    pub reserved2: [*mut c_void; 64],
}
abi_zeroed!(NV_ENC_INITIALIZE_PARAMS);

/// Encode Session Reconfigure parameters (`_NV_ENC_RECONFIGURE_PARAMS`).
/// `…_VER = NVENCAPI_STRUCT_VERSION(2) | (1u<<31)`. Declared for completeness;
/// V2 takes never reconfigures mid-take (§4 forbids auto profile changes).
#[repr(C)]
pub struct NV_ENC_RECONFIGURE_PARAMS {
    pub version: u32,
    pub reserved: u32,
    pub re_init_encode_params: NV_ENC_INITIALIZE_PARAMS,
    /// resetEncoder:1 forceIDR:1 reserved1:30
    pub bit_fields: u32,
    pub reserved2: u32,
}
abi_zeroed!(NV_ENC_RECONFIGURE_PARAMS);

/// Encoder preset config (`_NV_ENC_PRESET_CONFIG`).
/// `…_VER = NVENCAPI_STRUCT_VERSION(5) | (1u<<31)`.
#[repr(C)]
pub struct NV_ENC_PRESET_CONFIG {
    pub version: u32,
    pub reserved: u32,
    pub preset_cfg: NV_ENC_CONFIG,
    pub reserved1: [u32; 256],
    pub reserved2: [*mut c_void; 64],
}
abi_zeroed!(NV_ENC_PRESET_CONFIG);

/// Register a resource (`_NV_ENC_REGISTER_RESOURCE`).
/// `…_VER = NVENCAPI_STRUCT_VERSION(5)`. Size 1536 (MSVC x64).
#[repr(C)]
pub struct NV_ENC_REGISTER_RESOURCE {
    pub version: u32,
    pub resource_type: u32,
    pub width: u32,
    pub height: u32,
    /// 0 for `NV_ENC_INPUT_RESOURCE_TYPE_DIRECTX` resources (per header).
    pub pitch: u32,
    pub sub_resource_index: u32,
    pub resource_to_register: *mut c_void,
    pub registered_resource: *mut c_void,
    pub buffer_format: u32,
    pub buffer_usage: u32,
    pub p_input_fence_point: *mut c_void,
    pub chroma_offset: [u32; 2],
    pub chroma_offset_in: [u32; 2],
    pub reserved1: [u32; 244],
    pub reserved2: [*mut c_void; 61],
}
abi_zeroed!(NV_ENC_REGISTER_RESOURCE);

/// Map a registered resource (`_NV_ENC_MAP_INPUT_RESOURCE`).
/// `…_VER = NVENCAPI_STRUCT_VERSION(4)`. Size 1544 (MSVC x64).
#[repr(C)]
pub struct NV_ENC_MAP_INPUT_RESOURCE {
    pub version: u32,
    pub sub_resource_index: u32,
    pub input_resource: *mut c_void,
    pub registered_resource: *mut c_void,
    pub mapped_resource: *mut c_void,
    pub mapped_buffer_fmt: u32,
    pub reserved1: [u32; 251],
    pub reserved2: [*mut c_void; 63],
}
abi_zeroed!(NV_ENC_MAP_INPUT_RESOURCE);

/// Per-frame encoding parameters (`_NV_ENC_PIC_PARAMS`).
/// `NV_ENC_PIC_PARAMS_VER = NVENCAPI_STRUCT_VERSION(7) | (1u<<31)`.
/// Size 2840 (MSVC x64).
///
/// `codec_pic_params` is carried as `[u32; 256]` — the exact size of the C
/// `NV_ENC_CODEC_PIC_PARAMS` union. This engine drives per-picture behaviour
/// exclusively through `enablePTD=1` and the picture flags, so the union
/// payload stays all-zero; typing it deeper would add transcription risk
/// with zero behavioural gain.
#[repr(C)]
pub struct NV_ENC_PIC_PARAMS {
    pub version: u32,
    pub input_width: u32,
    pub input_height: u32,
    pub input_pitch: u32,
    pub encode_pic_flags: u32,
    pub frame_idx: u32,
    pub input_time_stamp: u64,
    pub input_duration: u64,
    pub input_buffer: *mut c_void,
    pub output_bitstream: *mut c_void,
    pub completion_event: *mut c_void,
    pub buffer_fmt: u32,
    pub picture_struct: u32,
    pub picture_type: u32,
    pub codec_pic_params: [u32; 256],
    pub me_hint_counts_per_block: [NVENC_EXTERNAL_ME_HINT_COUNTS_PER_BLOCKTYPE; 2],
    pub me_external_hints: *mut c_void,
    pub reserved2: [u32; 7],
    pub reserved5: [*mut c_void; 2],
    pub qp_delta_map: *mut i8,
    pub qp_delta_map_size: u32,
    pub reserved_bit_fields: u32,
    pub me_hint_ref_pic_dist: [u16; 2],
    pub diff_pic_num_hint: i32,
    pub alpha_buffer: *mut c_void,
    pub me_external_sb_hints: *mut c_void,
    pub me_sb_hints_count: u32,
    pub state_buffer_idx: u32,
    pub output_recon_buffer: *mut c_void,
    pub reserved3: [u32; 284],
    pub reserved6: [*mut c_void; 57],
}
abi_zeroed!(NV_ENC_PIC_PARAMS);

/// Bitstream lock parameters (`_NV_ENC_LOCK_BITSTREAM`).
/// `NV_ENC_LOCK_BITSTREAM_VER = NVENCAPI_STRUCT_VERSION(2) | (1u<<31)`.
/// Size 1544 (MSVC x64).
#[repr(C)]
pub struct NV_ENC_LOCK_BITSTREAM {
    pub version: u32,
    /// doNotWait:1 ltrFrame:1 getRCStats:1 reservedBitFields:29
    pub bit_fields: u32,
    pub output_bitstream: *mut c_void,
    pub slice_offsets: *mut u32,
    pub frame_idx: u32,
    pub hw_encode_status: u32,
    pub num_slices: u32,
    pub bitstream_size_in_bytes: u32,
    pub output_time_stamp: u64,
    pub output_duration: u64,
    pub bitstream_buffer_ptr: *mut c_void,
    pub picture_type: u32,
    pub picture_struct: u32,
    pub frame_avg_qp: u32,
    pub frame_satd: u32,
    pub ltr_frame_idx: u32,
    pub ltr_frame_bitmap: u32,
    pub temporal_id: u32,
    pub intra_mb_count: u32,
    pub inter_mb_count: u32,
    pub average_mvx: i32,
    pub average_mvy: i32,
    pub alpha_layer_size_in_bytes: u32,
    pub output_stats_ptr_size: u32,
    pub reserved: u32,
    pub output_stats_ptr: *mut c_void,
    pub frame_idx_display: u32,
    pub reserved1: [u32; 219],
    pub reserved2: [*mut c_void; 63],
    pub reserved_internal: [u32; 8],
}
abi_zeroed!(NV_ENC_LOCK_BITSTREAM);

impl NV_ENC_LOCK_BITSTREAM {
    const BF_DO_NOT_WAIT: u32 = 0;

    /// Non-blocking lock: returns immediately, check [`Self::hw_encode_status`].
    pub fn set_do_not_wait(&mut self, v: bool) {
        <u32 as SetBit>::set_bit(&mut self.bit_fields, Self::BF_DO_NOT_WAIT, v);
    }
}

/// Output bitstream buffer creation (`_NV_ENC_CREATE_BITSTREAM_BUFFER`).
/// `…_VER = NVENCAPI_STRUCT_VERSION(1)`. Size 776 (MSVC x64).
#[repr(C)]
pub struct NV_ENC_CREATE_BITSTREAM_BUFFER {
    pub version: u32,
    pub size: u32,
    pub memory_heap: u32,
    pub reserved: u32,
    pub bitstream_buffer: *mut c_void,
    pub bitstream_buffer_ptr: *mut c_void,
    pub reserved1: [u32; 58],
    pub reserved2: [*mut c_void; 64],
}
abi_zeroed!(NV_ENC_CREATE_BITSTREAM_BUFFER);

/// Creation parameters for input buffer (`_NV_ENC_CREATE_INPUT_BUFFER`).
/// Declared for function-table fidelity; unused by the zero-copy DX path.
#[repr(C)]
pub struct NV_ENC_CREATE_INPUT_BUFFER {
    pub version: u32,
    pub width: u32,
    pub height: u32,
    pub memory_heap: u32,
    pub buffer_fmt: u32,
    pub reserved: u32,
    pub input_buffer: *mut c_void,
    pub p_sys_mem_buffer: *mut c_void,
    pub reserved1: [u32; 58],
    pub reserved2: [*mut c_void; 63],
}
abi_zeroed!(NV_ENC_CREATE_INPUT_BUFFER);

/// Encode stats (`_NV_ENC_STAT`).
#[repr(C)]
pub struct NV_ENC_STAT {
    pub version: u32,
    pub reserved: u32,
    pub output_bit_stream: *mut c_void,
    pub bit_stream_size: u32,
    pub pic_type: u32,
    pub last_valid_byte_offset: u32,
    pub slice_offsets: [u32; 16],
    pub pic_idx: u32,
    pub frame_avg_qp: u32,
    /// ltrFrame:1 reservedBitFields:31
    pub bit_fields: u32,
    pub ltr_frame_idx: u32,
    pub intra_mb_count: u32,
    pub inter_mb_count: u32,
    pub average_mvx: i32,
    pub average_mvy: i32,
    pub reserved1: [u32; 227],
    pub reserved2: [*mut c_void; 64],
}
abi_zeroed!(NV_ENC_STAT);

/// Sequence/picture-header payload (`_NV_ENC_SEQUENCE_PARAM_PAYLOAD`).
#[repr(C)]
pub struct NV_ENC_SEQUENCE_PARAM_PAYLOAD {
    pub version: u32,
    pub in_buffer_size: u32,
    pub sps_id: u32,
    pub pps_id: u32,
    pub spspps_buffer: *mut c_void,
    pub out_spspps_payload_size: *mut u32,
    pub reserved: [u32; 250],
    pub reserved2: [*mut c_void; 64],
}
abi_zeroed!(NV_ENC_SEQUENCE_PARAM_PAYLOAD);

/// Event registration parameters (`_NV_ENC_EVENT_PARAMS`) — async mode only;
/// this engine runs sync mode (§8).
#[repr(C)]
pub struct NV_ENC_EVENT_PARAMS {
    pub version: u32,
    pub reserved: u32,
    pub completion_event: *mut c_void,
    pub reserved1: [u32; 254],
    pub reserved2: [*mut c_void; 64],
}
abi_zeroed!(NV_ENC_EVENT_PARAMS);

/// Uncompressed input-buffer lock (`_NV_ENC_LOCK_INPUT_BUFFER`) — sysmem path,
/// unused by the zero-copy pipeline.
#[repr(C)]
pub struct NV_ENC_LOCK_INPUT_BUFFER {
    pub version: u32,
    /// doNotWait:1 reservedBitFields:31
    pub bit_fields: u32,
    pub input_buffer: *mut c_void,
    pub buffer_data_ptr: *mut c_void,
    pub pitch: u32,
    pub reserved1: [u32; 251],
    pub reserved2: [*mut c_void; 64],
}
abi_zeroed!(NV_ENC_LOCK_INPUT_BUFFER);

/// ME-only MV buffer creation (`_NV_ENC_CREATE_MV_BUFFER`).
#[repr(C)]
pub struct NV_ENC_CREATE_MV_BUFFER {
    pub version: u32,
    pub reserved: u32,
    pub mv_buffer: *mut c_void,
    pub reserved1: [u32; 254],
    pub reserved2: [*mut c_void; 63],
}
abi_zeroed!(NV_ENC_CREATE_MV_BUFFER);

/// Lookahead picture parameters (`_NV_ENC_LOOKAHEAD_PIC_PARAMS`).
#[repr(C)]
pub struct NV_ENC_LOOKAHEAD_PIC_PARAMS {
    pub version: u32,
    pub reserved: u32,
    pub input_buffer: *mut c_void,
    pub picture_type: u32,
    pub buffer_fmt: u32,
    pub encode_pic_flags: u32,
    pub reserved1: [u32; 61],
    pub reserved2: [*mut c_void; 64],
}
abi_zeroed!(NV_ENC_LOOKAHEAD_PIC_PARAMS);

/// Encoder-state restore (`_NV_ENC_RESTORE_ENCODER_STATE_PARAMS`).
#[repr(C)]
pub struct NV_ENC_RESTORE_ENCODER_STATE_PARAMS {
    pub version: u32,
    pub buffer_idx: u32,
    pub state: u32,
    pub reserved: u32,
    pub output_bitstream: *mut c_void,
    pub completion_event: *mut c_void,
    pub reserved1: [u32; 64],
    pub reserved2: [*mut c_void; 64],
}
abi_zeroed!(NV_ENC_RESTORE_ENCODER_STATE_PARAMS);

/// ME-only parameters (`_NV_ENC_MEONLY_PARAMS`).
#[repr(C)]
pub struct NV_ENC_MEONLY_PARAMS {
    pub version: u32,
    pub input_width: u32,
    pub input_height: u32,
    pub reserved: u32,
    pub input_buffer: *mut c_void,
    pub reference_frame: *mut c_void,
    pub mv_buffer: *mut c_void,
    pub reserved2: u32,
    pub buffer_fmt: u32,
    pub completion_event: *mut c_void,
    pub view_id: u32,
    pub me_hint_counts_per_block: [NVENC_EXTERNAL_ME_HINT_COUNTS_PER_BLOCKTYPE; 2],
    pub me_external_hints: *mut c_void,
    pub reserved1: [u32; 241],
    pub reserved3: [*mut c_void; 59],
}
abi_zeroed!(NV_ENC_MEONLY_PARAMS);

// ─── Function-pointer typedefs (verbatim signatures) ────────────────────────

pub type FnOpenEncodeSession =
    unsafe extern "system" fn(device: *mut c_void, device_type: u32, encoder: *mut *mut c_void) -> u32;
pub type FnGetEncodeGuidCount = unsafe extern "system" fn(encoder: *mut c_void, count: *mut u32) -> u32;
pub type FnGetEncodeProfileGuidCount =
    unsafe extern "system" fn(encoder: *mut c_void, encode_guid: NvGuid, count: *mut u32) -> u32;
pub type FnGetEncodeProfileGuids = unsafe extern "system" fn(
    encoder: *mut c_void,
    encode_guid: NvGuid,
    guids: *mut NvGuid,
    guid_array_size: u32,
    guid_count: *mut u32,
) -> u32;
pub type FnGetEncodeGuids =
    unsafe extern "system" fn(encoder: *mut c_void, guids: *mut NvGuid, guid_array_size: u32, guid_count: *mut u32) -> u32;
pub type FnGetInputFormatCount =
    unsafe extern "system" fn(encoder: *mut c_void, encode_guid: NvGuid, count: *mut u32) -> u32;
pub type FnGetInputFormats = unsafe extern "system" fn(
    encoder: *mut c_void,
    encode_guid: NvGuid,
    fmts: *mut u32,
    fmt_array_size: u32,
    fmt_count: *mut u32,
) -> u32;
pub type FnGetEncodeCaps = unsafe extern "system" fn(
    encoder: *mut c_void,
    encode_guid: NvGuid,
    caps_param: *mut NV_ENC_CAPS_PARAM,
    caps_val: *mut i32,
) -> u32;
pub type FnGetEncodePresetCount =
    unsafe extern "system" fn(encoder: *mut c_void, encode_guid: NvGuid, count: *mut u32) -> u32;
pub type FnGetEncodePresetGuids = unsafe extern "system" fn(
    encoder: *mut c_void,
    encode_guid: NvGuid,
    guids: *mut NvGuid,
    guid_array_size: u32,
    preset_guid_count: *mut u32,
) -> u32;
pub type FnGetEncodePresetConfig = unsafe extern "system" fn(
    encoder: *mut c_void,
    encode_guid: NvGuid,
    preset_guid: NvGuid,
    preset_config: *mut NV_ENC_PRESET_CONFIG,
) -> u32;
pub type FnInitializeEncoder =
    unsafe extern "system" fn(encoder: *mut c_void, create_encode_params: *mut NV_ENC_INITIALIZE_PARAMS) -> u32;
pub type FnCreateInputBuffer =
    unsafe extern "system" fn(encoder: *mut c_void, create_input_buffer_params: *mut NV_ENC_CREATE_INPUT_BUFFER) -> u32;
pub type FnDestroyInputBuffer = unsafe extern "system" fn(encoder: *mut c_void, input_buffer: *mut c_void) -> u32;
pub type FnCreateBitstreamBuffer =
    unsafe extern "system" fn(encoder: *mut c_void, params: *mut NV_ENC_CREATE_BITSTREAM_BUFFER) -> u32;
pub type FnDestroyBitstreamBuffer = unsafe extern "system" fn(encoder: *mut c_void, bitstream_buffer: *mut c_void) -> u32;
pub type FnEncodePicture = unsafe extern "system" fn(encoder: *mut c_void, encode_pic_params: *mut NV_ENC_PIC_PARAMS) -> u32;
pub type FnLockBitstream =
    unsafe extern "system" fn(encoder: *mut c_void, lock_bitstream_params: *mut NV_ENC_LOCK_BITSTREAM) -> u32;
pub type FnUnlockBitstream = unsafe extern "system" fn(encoder: *mut c_void, bitstream_buffer: *mut c_void) -> u32;
pub type FnLockInputBuffer =
    unsafe extern "system" fn(encoder: *mut c_void, lock_input_buffer_params: *mut NV_ENC_LOCK_INPUT_BUFFER) -> u32;
pub type FnUnlockInputBuffer = unsafe extern "system" fn(encoder: *mut c_void, input_buffer: *mut c_void) -> u32;
pub type FnGetEncodeStats = unsafe extern "system" fn(encoder: *mut c_void, encode_stats: *mut NV_ENC_STAT) -> u32;
pub type FnGetSequenceParams =
    unsafe extern "system" fn(encoder: *mut c_void, sequence_param_payload: *mut NV_ENC_SEQUENCE_PARAM_PAYLOAD) -> u32;
pub type FnRegisterAsyncEvent = unsafe extern "system" fn(encoder: *mut c_void, event_params: *mut NV_ENC_EVENT_PARAMS) -> u32;
pub type FnUnregisterAsyncEvent = unsafe extern "system" fn(encoder: *mut c_void, event_params: *mut NV_ENC_EVENT_PARAMS) -> u32;
pub type FnMapInputResource =
    unsafe extern "system" fn(encoder: *mut c_void, map_input_res_params: *mut NV_ENC_MAP_INPUT_RESOURCE) -> u32;
pub type FnUnmapInputResource = unsafe extern "system" fn(encoder: *mut c_void, mapped_input_buffer: *mut c_void) -> u32;
pub type FnDestroyEncoder = unsafe extern "system" fn(encoder: *mut c_void) -> u32;
pub type FnInvalidateRefFrames =
    unsafe extern "system" fn(encoder: *mut c_void, invalid_ref_frame_timestamp: u64) -> u32;
pub type FnOpenEncodeSessionEx =
    unsafe extern "system" fn(open_session_ex_params: *mut NV_ENC_OPEN_ENCODE_SESSION_EX_PARAMS, encoder: *mut *mut c_void) -> u32;
pub type FnRegisterResource =
    unsafe extern "system" fn(encoder: *mut c_void, register_res_params: *mut NV_ENC_REGISTER_RESOURCE) -> u32;
pub type FnUnregisterResource = unsafe extern "system" fn(encoder: *mut c_void, registered_res: *mut c_void) -> u32;
pub type FnReconfigureEncoder =
    unsafe extern "system" fn(encoder: *mut c_void, re_init_encode_params: *mut NV_ENC_RECONFIGURE_PARAMS) -> u32;
pub type FnCreateMvBuffer = unsafe extern "system" fn(encoder: *mut c_void, create_mv_buffer_params: *mut NV_ENC_CREATE_MV_BUFFER) -> u32;
pub type FnDestroyMvBuffer = unsafe extern "system" fn(encoder: *mut c_void, mv_buffer: *mut c_void) -> u32;
pub type FnRunMotionEstimationOnly =
    unsafe extern "system" fn(encoder: *mut c_void, me_only_params: *mut NV_ENC_MEONLY_PARAMS) -> u32;
pub type FnGetLastErrorString = unsafe extern "system" fn(encoder: *mut c_void) -> *const c_char;
pub type FnSetIoCudaStreams =
    unsafe extern "system" fn(encoder: *mut c_void, input_stream: *mut c_void, output_stream: *mut c_void) -> u32;
pub type FnGetEncodePresetConfigEx = unsafe extern "system" fn(
    encoder: *mut c_void,
    encode_guid: NvGuid,
    preset_guid: NvGuid,
    tuning_info: u32,
    preset_config: *mut NV_ENC_PRESET_CONFIG,
) -> u32;
pub type FnGetSequenceParamEx = unsafe extern "system" fn(
    encoder: *mut c_void,
    enc_init_params: *mut NV_ENC_INITIALIZE_PARAMS,
    sequence_param_payload: *mut NV_ENC_SEQUENCE_PARAM_PAYLOAD,
) -> u32;
pub type FnRestoreEncoderState =
    unsafe extern "system" fn(encoder: *mut c_void, restore_state: *mut NV_ENC_RESTORE_ENCODER_STATE_PARAMS) -> u32;
pub type FnLookaheadPicture =
    unsafe extern "system" fn(encoder: *mut c_void, lookahead_params: *mut NV_ENC_LOOKAHEAD_PIC_PARAMS) -> u32;

/// `_NV_ENCODE_API_FUNCTION_LIST` — POSITIONAL ABI.
///
/// Field order is transcribed verbatim from the SDK 13.1 header (version →
/// `nvEncOpenEncodeSession` → … → `nvEncLookaheadPicture` → `reserved2`). The
/// driver indexes this table positionally: adding, removing or reordering a
/// slot shifts every subsequent entry and crashes the process. New SDK
/// releases only ever append slots before `reserved2`.
#[repr(C)]
pub struct NV_ENCODE_API_FUNCTION_LIST {
    pub version: u32,
    pub reserved: u32,
    pub nv_enc_open_encode_session: Option<FnOpenEncodeSession>,
    pub nv_enc_get_encode_guid_count: Option<FnGetEncodeGuidCount>,
    pub nv_enc_get_encode_profile_guid_count: Option<FnGetEncodeProfileGuidCount>,
    pub nv_enc_get_encode_profile_guids: Option<FnGetEncodeProfileGuids>,
    pub nv_enc_get_encode_guids: Option<FnGetEncodeGuids>,
    pub nv_enc_get_input_format_count: Option<FnGetInputFormatCount>,
    pub nv_enc_get_input_formats: Option<FnGetInputFormats>,
    pub nv_enc_get_encode_caps: Option<FnGetEncodeCaps>,
    pub nv_enc_get_encode_preset_count: Option<FnGetEncodePresetCount>,
    pub nv_enc_get_encode_preset_guids: Option<FnGetEncodePresetGuids>,
    pub nv_enc_get_encode_preset_config: Option<FnGetEncodePresetConfig>,
    pub nv_enc_initialize_encoder: Option<FnInitializeEncoder>,
    pub nv_enc_create_input_buffer: Option<FnCreateInputBuffer>,
    pub nv_enc_destroy_input_buffer: Option<FnDestroyInputBuffer>,
    pub nv_enc_create_bitstream_buffer: Option<FnCreateBitstreamBuffer>,
    pub nv_enc_destroy_bitstream_buffer: Option<FnDestroyBitstreamBuffer>,
    pub nv_enc_encode_picture: Option<FnEncodePicture>,
    pub nv_enc_lock_bitstream: Option<FnLockBitstream>,
    pub nv_enc_unlock_bitstream: Option<FnUnlockBitstream>,
    pub nv_enc_lock_input_buffer: Option<FnLockInputBuffer>,
    pub nv_enc_unlock_input_buffer: Option<FnUnlockInputBuffer>,
    pub nv_enc_get_encode_stats: Option<FnGetEncodeStats>,
    pub nv_enc_get_sequence_params: Option<FnGetSequenceParams>,
    pub nv_enc_register_async_event: Option<FnRegisterAsyncEvent>,
    pub nv_enc_unregister_async_event: Option<FnUnregisterAsyncEvent>,
    pub nv_enc_map_input_resource: Option<FnMapInputResource>,
    pub nv_enc_unmap_input_resource: Option<FnUnmapInputResource>,
    pub nv_enc_destroy_encoder: Option<FnDestroyEncoder>,
    pub nv_enc_invalidate_ref_frames: Option<FnInvalidateRefFrames>,
    pub nv_enc_open_encode_session_ex: Option<FnOpenEncodeSessionEx>,
    pub nv_enc_register_resource: Option<FnRegisterResource>,
    pub nv_enc_unregister_resource: Option<FnUnregisterResource>,
    pub nv_enc_reconfigure_encoder: Option<FnReconfigureEncoder>,
    pub reserved1: *mut c_void,
    pub nv_enc_create_mv_buffer: Option<FnCreateMvBuffer>,
    pub nv_enc_destroy_mv_buffer: Option<FnDestroyMvBuffer>,
    pub nv_enc_run_motion_estimation_only: Option<FnRunMotionEstimationOnly>,
    pub nv_enc_get_last_error_string: Option<FnGetLastErrorString>,
    pub nv_enc_set_io_cuda_streams: Option<FnSetIoCudaStreams>,
    pub nv_enc_get_encode_preset_config_ex: Option<FnGetEncodePresetConfigEx>,
    pub nv_enc_get_sequence_param_ex: Option<FnGetSequenceParamEx>,
    pub nv_enc_restore_encoder_state: Option<FnRestoreEncoderState>,
    pub nv_enc_lookahead_picture: Option<FnLookaheadPicture>,
    pub reserved2: [*mut c_void; 275],
}
abi_zeroed!(NV_ENCODE_API_FUNCTION_LIST);

// ─── Loader ──────────────────────────────────────────────────────────────────

/// Resolved NVENC client function table, pinned for the process lifetime.
pub struct NvencApi {
    /// Highest API version the driver accepted from the ladder.
    pub api_version: ApiVersion,
    fn_table: Box<NV_ENCODE_API_FUNCTION_LIST>,
    /// Kept alive forever: the driver DLL must outlive every session.
    #[cfg(windows)]
    _dll: windows::Win32::Foundation::HMODULE,
}

/// Load-ladder: highest first. The function table is append-only across these
/// releases, so any driver ≥ the floor can fill the slots we call.
const VERSION_LADDER: [ApiVersion; 5] = [
    ApiVersion::TRANSCRIBED,               // 13.1
    ApiVersion { major: 13, minor: 0 },    // 13.0
    ApiVersion { major: 12, minor: 2 },    // 12.2
    ApiVersion { major: 12, minor: 1 },    // 12.1
    ApiVersion::LADDER_FLOOR,              // 12.0
];

type CreateInstanceFn = unsafe extern "system" fn(function_list: *mut NV_ENCODE_API_FUNCTION_LIST) -> u32;

/// Load `nvEncodeAPI64.dll` and resolve the client function table.
///
/// Search order (§8): System32 (driver-store install), then the exe directory
/// (bundled fallback for locked-down deployments), then the OS default search
/// path. The result is cached — first call wins; later callers receive the
/// same `&'static` (or the same blocker).
///
/// Blockers: `NVENC_DLL_NOT_FOUND`, `NVENC_ENTRY_POINT_NOT_FOUND`,
/// `NVENC_API_INIT_FAILED:<status>`, `NVENC_DRIVER_TOO_OLD:<detail>`,
/// `NVENC_FUNCTION_TABLE_INCOMPLETE:<slot>`.
#[cfg(windows)]
pub fn load() -> Result<&'static NvencApi, String> {
    static CELL: std::sync::OnceLock<Result<NvencApi, String>> = std::sync::OnceLock::new();
    match CELL.get_or_init(create_api) {
        Ok(api) => Ok(api),
        Err(e) => Err(e.clone()),
    }
}

/// Non-Windows fallback — fail-closed stub (Principle C: no soft success).
#[cfg(not(windows))]
pub fn load() -> Result<&'static NvencApi, String> {
    Err("NVENC_DLL_NOT_FOUND".into())
}

#[cfg(windows)]
fn create_api() -> Result<NvencApi, String> {
    use windows::core::{PCSTR, PCWSTR};
    use windows::Win32::Foundation::HMODULE;
    use windows::Win32::System::LibraryLoader::{GetProcAddress, LoadLibraryW};

    const DLL_NAME: &[u8] = b"NvEncodeAPICreateInstance\0";

    let mut candidates: Vec<Vec<u16>> = Vec::new();
    // 1. System32 (the driver installs nvEncodeAPI64.dll there).
    let mut sys_dir = [0u16; 260];
    let n = unsafe {
        windows::Win32::System::SystemInformation::GetSystemDirectoryW(Some(&mut sys_dir[..]))
    };
    if n > 0 {
        let mut p = sys_dir[..n as usize].to_vec();
        p.extend("\\nvEncodeAPI64.dll\0".encode_utf16());
        candidates.push(p);
    }
    // 2. Bundled next to the exe (packaging fallback, §20).
    let mut exe_path = [0u16; 1024];
    let n = unsafe { windows::Win32::System::LibraryLoader::GetModuleFileNameW(None, &mut exe_path) };
    if n > 0 {
        if let Some(dir_end) = exe_path[..n as usize].iter().rposition(|&c| c == b'\\' as u16) {
            let mut p = exe_path[..dir_end + 1].to_vec();
            p.extend("nvEncodeAPI64.dll\0".encode_utf16());
            candidates.push(p);
        }
    }
    // 3. Default DLL search order.
    candidates.push("nvEncodeAPI64.dll\0".encode_utf16().collect());

    let mut dll: Option<HMODULE> = None;
    for path in &candidates {
        // windows-rs maps a NULL module handle to Err already.
        if let Ok(h) = unsafe { LoadLibraryW(PCWSTR(path.as_ptr())) } {
            dll = Some(h);
            break;
        }
    }
    let dll = dll.ok_or_else(|| "NVENC_DLL_NOT_FOUND".to_string())?;

    let proc = unsafe { GetProcAddress(dll, PCSTR(DLL_NAME.as_ptr())) };
    let create_instance: CreateInstanceFn = match proc {
        Some(f) => unsafe { std::mem::transmute::<usize, CreateInstanceFn>(f as usize) },
        None => return Err("NVENC_ENTRY_POINT_NOT_FOUND".into()),
    };

    // Walk the version ladder until the driver accepts the function-table
    // request. INVALID_VERSION on the final rung ⇒ explicit blocker.
    let mut last_status = 0u32;
    for api in VERSION_LADDER {
        let mut table: Box<NV_ENCODE_API_FUNCTION_LIST> =
            Box::new(NV_ENCODE_API_FUNCTION_LIST::zeroed());
        table.version = nvenapi_struct_version(api.raw(), 2); // NV_ENCODE_API_FUNCTION_LIST_VER
        let status = unsafe { create_instance(&mut *table) };
        if status == NV_ENC_SUCCESS {
            verify_table(&table)?;
            return Ok(NvencApi { api_version: api, fn_table: table, _dll: dll });
        }
        last_status = status;
        if status != NV_ENC_ERR_INVALID_VERSION {
            return Err(format!("NVENC_API_INIT_FAILED:{}:{}", status_name(status), status));
        }
    }
    Err(format!(
        "NVENC_DRIVER_TOO_OLD:nvEncodeAPICreateInstance rejected every supported API version (last={}:{})",
        status_name(last_status),
        last_status
    ))
}

/// Fail closed if the driver left any slot this engine depends on NULL.
#[cfg(windows)]
fn verify_table(table: &NV_ENCODE_API_FUNCTION_LIST) -> Result<(), String> {
    let required: [(&'static str, Option<*const c_void>); 14] = [
        ("openEncodeSessionEx", table.nv_enc_open_encode_session_ex.map(|f| f as *const c_void)),
        ("getEncodeGUIDCount", table.nv_enc_get_encode_guid_count.map(|f| f as *const c_void)),
        ("getEncodeGUIDs", table.nv_enc_get_encode_guids.map(|f| f as *const c_void)),
        ("getEncodeCaps", table.nv_enc_get_encode_caps.map(|f| f as *const c_void)),
        (
            "getEncodePresetConfigEx",
            table.nv_enc_get_encode_preset_config_ex.map(|f| f as *const c_void),
        ),
        ("initializeEncoder", table.nv_enc_initialize_encoder.map(|f| f as *const c_void)),
        ("getSequenceParams", table.nv_enc_get_sequence_params.map(|f| f as *const c_void)),
        (
            "createBitstreamBuffer",
            table.nv_enc_create_bitstream_buffer.map(|f| f as *const c_void),
        ),
        (
            "destroyBitstreamBuffer",
            table.nv_enc_destroy_bitstream_buffer.map(|f| f as *const c_void),
        ),
        ("encodePicture", table.nv_enc_encode_picture.map(|f| f as *const c_void)),
        ("lockBitstream", table.nv_enc_lock_bitstream.map(|f| f as *const c_void)),
        ("unmapInputResource", table.nv_enc_unmap_input_resource.map(|f| f as *const c_void)),
        ("destroyEncoder", table.nv_enc_destroy_encoder.map(|f| f as *const c_void)),
        ("registerResource", table.nv_enc_register_resource.map(|f| f as *const c_void)),
    ];
    for (name, slot) in required {
        if slot.is_none() {
            return Err(format!("NVENC_FUNCTION_TABLE_INCOMPLETE:{name}"));
        }
    }
    Ok(())
}

impl NvencApi {
    /// `nvEncOpenEncodeSessionEx` — binds the encoder to a client device.
    #[cfg(windows)]
    pub(crate) fn open_encode_session_ex(&self, device: *mut c_void) -> Result<*mut c_void, String> {
        let mut params = NV_ENC_OPEN_ENCODE_SESSION_EX_PARAMS::zeroed();
        params.version = self.api_version.struct_ver(1); // …_SESSION_EX_PARAMS_VER
        params.device_type = NV_ENC_DEVICE_TYPE_DIRECTX;
        params.device = device;
        params.api_version = self.api_version.raw();
        let mut encoder: *mut c_void = std::ptr::null_mut();
        let status = unsafe {
            (self.fn_table.nv_enc_open_encode_session_ex.expect("checked by verify_table"))(&mut params, &mut encoder)
        };
        self.check(status, "NvEncOpenEncodeSessionEx")?;
        if encoder.is_null() {
            return Err("NVENC_NO_SESSION:null encoder handle".into());
        }
        Ok(encoder)
    }

    /// `nvEncGetEncodeGUIDCount` + `nvEncGetEncodeGUIDs` — codecs present.
    #[cfg(windows)]
    pub(crate) fn get_encode_guids(&self, encoder: *mut c_void) -> Result<Vec<NvGuid>, String> {
        let get_count = self.fn_table.nv_enc_get_encode_guid_count.expect("checked by verify_table");
        let get_guids = self.fn_table.nv_enc_get_encode_guids.expect("checked by verify_table");
        let mut count = 0u32;
        let status = unsafe { get_count(encoder, &mut count) };
        self.check(status, "NvEncGetEncodeGUIDCount")?;
        if count == 0 {
            return Ok(Vec::new());
        }
        let mut guids = vec![NvGuid::from_u128(0); count as usize];
        let mut written = 0u32;
        let status = unsafe { get_guids(encoder, guids.as_mut_ptr(), count, &mut written) };
        self.check(status, "NvEncGetEncodeGUIDs")?;
        guids.truncate(written.min(count) as usize);
        Ok(guids)
    }

    /// `nvEncGetEncodeCaps` — one capability value for one codec.
    #[cfg(windows)]
    pub(crate) fn get_encode_caps(
        &self,
        encoder: *mut c_void,
        encode_guid: NvGuid,
        caps_to_query: i32,
    ) -> Result<i32, String> {
        let get_caps = self.fn_table.nv_enc_get_encode_caps.expect("checked by verify_table");
        let mut param = NV_ENC_CAPS_PARAM::zeroed();
        param.version = self.api_version.struct_ver(1); // NV_ENC_CAPS_PARAM_VER
        param.caps_to_query = caps_to_query;
        let mut value = 0i32;
        let status = unsafe { get_caps(encoder, encode_guid, &mut param, &mut value) };
        self.check(status, "NvEncGetEncodeCaps")?;
        Ok(value)
    }

    /// `nvEncGetEncodePresetCount`.
    // Production initializes from a direct custom config (recent drivers
    // reject the preset query outright); these wrappers stay for the
    // `preset_config_combo_matrix` driver diagnostic.
    #[cfg(windows)]
    #[allow(dead_code)]
    pub(crate) fn get_encode_preset_count(
        &self,
        encoder: *mut c_void,
        encode_guid: NvGuid,
    ) -> Result<u32, String> {
        let f = self.fn_table.nv_enc_get_encode_preset_count.expect("checked by verify_table");
        let mut count = 0u32;
        let status = unsafe { f(encoder, encode_guid, &mut count) };
        self.check(status, "NvEncGetEncodePresetCount")?;
        Ok(count)
    }

    /// `nvEncGetEncodePresetGuids` — the presets the driver itself advertises.
    #[cfg(windows)]
    #[allow(dead_code)] // preset_config_combo_matrix driver diagnostic
    pub(crate) fn get_encode_preset_guids(
        &self,
        encoder: *mut c_void,
        encode_guid: NvGuid,
    ) -> Result<Vec<NvGuid>, String> {
        let f = self.fn_table.nv_enc_get_encode_preset_guids.expect("checked by verify_table");
        let count = self.get_encode_preset_count(encoder, encode_guid)?;
        let mut guids = vec![NvGuid::from_u128(0); count as usize];
        let mut written = 0u32;
        let status = unsafe { f(encoder, encode_guid, guids.as_mut_ptr(), count, &mut written) };
        self.check(status, "NvEncGetEncodePresetGuids")?;
        guids.truncate(written.min(count) as usize);
        Ok(guids)
    }

    /// `nvEncGetEncodePresetConfig` — legacy (no tuning-info) variant; kept
    /// for driver diagnostics when the Ex variant is rejected.
    #[cfg(windows)]
    #[allow(dead_code)] // preset_config_combo_matrix driver diagnostic
    pub(crate) fn get_encode_preset_config(
        &self,
        encoder: *mut c_void,
        encode_guid: NvGuid,
        preset_guid: NvGuid,
    ) -> Result<NV_ENC_PRESET_CONFIG, String> {
        let get_cfg = self.fn_table.nv_enc_get_encode_preset_config.expect("checked by verify_table");
        let mut cfg = NV_ENC_PRESET_CONFIG::zeroed();
        cfg.version = self.api_version.struct_ver_ext(5); // NV_ENC_PRESET_CONFIG_VER
        let status = unsafe { get_cfg(encoder, encode_guid, preset_guid, &mut cfg) };
        self.check(status, "NvEncGetEncodePresetConfig")?;
        Ok(cfg)
    }

    /// `nvEncGetEncodePresetConfigEx` — driver-authored config for one preset
    /// under one tuning info; the recommended initialization base.
    #[cfg(windows)]
    #[allow(dead_code)] // preset_config_combo_matrix driver diagnostic
    pub(crate) fn get_encode_preset_config_ex(
        &self,
        encoder: *mut c_void,
        encode_guid: NvGuid,
        preset_guid: NvGuid,
        tuning_info: u32,
    ) -> Result<NV_ENC_PRESET_CONFIG, String> {
        let get_cfg = self
            .fn_table
            .nv_enc_get_encode_preset_config_ex
            .expect("checked by verify_table");
        let mut cfg = NV_ENC_PRESET_CONFIG::zeroed();
        cfg.version = self.api_version.struct_ver_ext(5); // NV_ENC_PRESET_CONFIG_VER
        let status = unsafe { get_cfg(encoder, encode_guid, preset_guid, tuning_info, &mut cfg) };
        self.check(status, "NvEncGetEncodePresetConfigEx")?;
        Ok(cfg)
    }

    /// `nvEncInitializeEncoder`.
    #[cfg(windows)]
    pub(crate) fn initialize_encoder(
        &self,
        encoder: *mut c_void,
        params: &mut NV_ENC_INITIALIZE_PARAMS,
    ) -> Result<(), String> {
        let init = self.fn_table.nv_enc_initialize_encoder.expect("checked by verify_table");
        let status = unsafe { init(encoder, params) };
        if status != NV_ENC_SUCCESS {
            // Surface the driver's own diagnostic text when it offers one —
            // e.g. "Unsupported color format." pointed straight at an
            // undeclared chromaFormatIDC during the custom-config bring-up.
            let base = self.fail(status, "NvEncInitializeEncoder");
            match self.last_error_text(encoder) {
                Some(text) if !text.is_empty() => return Err(format!("{base} [driver: {text}]")),
                _ => return Err(base),
            }
        }
        Ok(())
    }

    /// `nvEncGetSequenceParams` — codec parameter sets (SPS/PPS, plus VPS for
    /// HEVC) in Annex-B form, valid right after `NvEncInitializeEncoder`.
    /// This is the extradata source for the MKV lazy-header handshake
    /// (`muxer/libav.rs`): avcC/hvcC are built from these bytes once per
    /// session instead of scraping the first keyframe mid-take.
    ///
    /// `out_buf` must be generously sized (SPS/PPS/VPS are a few hundred
    /// bytes even at 8K); returns how many bytes the driver wrote.
    #[cfg(windows)]
    pub(crate) fn get_sequence_params(
        &self,
        encoder: *mut c_void,
        out_buf: &mut [u8],
    ) -> Result<usize, String> {
        if out_buf.is_empty() {
            return Err("NVENC_NO_SEQUENCE_PARAMS:zero-length output buffer".into());
        }
        let f = self.fn_table.nv_enc_get_sequence_params.expect("checked by verify_table");
        let mut written: u32 = 0;
        let mut payload = NV_ENC_SEQUENCE_PARAM_PAYLOAD::zeroed();
        payload.version = self.api_version.struct_ver(1); // NV_ENC_SEQUENCE_PARAM_PAYLOAD_VER
        payload.in_buffer_size = out_buf.len() as u32;
        payload.spspps_buffer = out_buf.as_mut_ptr() as *mut c_void;
        payload.out_spspps_payload_size = &mut written;
        let status = unsafe { f(encoder, &mut payload) };
        self.check(status, "NvEncGetSequenceParams")?;
        if written == 0 || written as usize > out_buf.len() {
            return Err(format!(
                "NVENC_NO_SEQUENCE_PARAMS: driver reported {written} sequence-param bytes"
            ));
        }
        Ok(written as usize)
    }

    /// `nvEncCreateBitstreamBuffer` → output buffer handle.
    #[cfg(windows)]
    pub(crate) fn create_bitstream_buffer(&self, encoder: *mut c_void) -> Result<*mut c_void, String> {
        let create = self.fn_table.nv_enc_create_bitstream_buffer.expect("checked by verify_table");
        let mut params = NV_ENC_CREATE_BITSTREAM_BUFFER::zeroed();
        params.version = self.api_version.struct_ver(1); // NV_ENC_CREATE_BITSTREAM_BUFFER_VER
        let status = unsafe { create(encoder, &mut params) };
        self.check(status, "NvEncCreateBitstreamBuffer")?;
        if params.bitstream_buffer.is_null() {
            return Err("NVENC_NO_BITSTREAM_BUFFER:null handle".into());
        }
        Ok(params.bitstream_buffer)
    }

    /// `nvEncDestroyBitstreamBuffer`.
    #[cfg(windows)]
    pub(crate) fn destroy_bitstream_buffer(&self, encoder: *mut c_void, buffer: *mut c_void) {
        if let Some(f) = self.fn_table.nv_enc_destroy_bitstream_buffer {
            unsafe { f(encoder, buffer) };
        }
    }

    /// `nvEncRegisterResource` → registered-resource handle.
    #[cfg(windows)]
    pub(crate) fn register_resource(
        &self,
        encoder: *mut c_void,
        params: &mut NV_ENC_REGISTER_RESOURCE,
    ) -> Result<*mut c_void, String> {
        let register = self.fn_table.nv_enc_register_resource.expect("checked by verify_table");
        params.registered_resource = std::ptr::null_mut();
        let status = unsafe { register(encoder, params) };
        self.check(status, "NvEncRegisterResource")?;
        if params.registered_resource.is_null() {
            return Err("NVENC_REGISTER_FAILED:null registered handle".into());
        }
        Ok(params.registered_resource)
    }

    /// `nvEncUnregisterResource`.
    #[cfg(windows)]
    pub(crate) fn unregister_resource(&self, encoder: *mut c_void, registered: *mut c_void) {
        if let Some(f) = self.fn_table.nv_enc_unregister_resource {
            unsafe { f(encoder, registered) };
        }
    }

    /// `nvEncMapInputResource` → (mapped input ptr, mapped buffer format).
    #[cfg(windows)]
    pub(crate) fn map_input_resource(
        &self,
        encoder: *mut c_void,
        registered: *mut c_void,
    ) -> Result<(*mut c_void, u32), String> {
        let map = self.fn_table.nv_enc_map_input_resource.expect("checked by verify_table");
        let mut params = NV_ENC_MAP_INPUT_RESOURCE::zeroed();
        params.version = self.api_version.struct_ver(4); // NV_ENC_MAP_INPUT_RESOURCE_VER
        params.registered_resource = registered;
        let status = unsafe { map(encoder, &mut params) };
        self.check(status, "NvEncMapInputResource")?;
        if params.mapped_resource.is_null() {
            return Err("NVENC_MAP_FAILED:null mapped handle".into());
        }
        Ok((params.mapped_resource, params.mapped_buffer_fmt))
    }

    /// `nvEncUnmapInputResource`.
    #[cfg(windows)]
    pub(crate) fn unmap_input_resource(&self, encoder: *mut c_void, mapped: *mut c_void) {
        if let Some(f) = self.fn_table.nv_enc_unmap_input_resource {
            unsafe { f(encoder, mapped) };
        }
    }

    /// `nvEncEncodePicture`. Returns the raw status so the caller can apply
    /// the documented `NEED_MORE_INPUT` (B-frame buffering) semantics:
    /// `Ok(NV_ENC_SUCCESS | NV_ENC_ERR_NEED_MORE_INPUT)`, else `Err`.
    #[cfg(windows)]
    pub(crate) fn encode_picture(
        &self,
        encoder: *mut c_void,
        params: &mut NV_ENC_PIC_PARAMS,
    ) -> Result<u32, String> {
        let encode = self.fn_table.nv_enc_encode_picture.expect("checked by verify_table");
        let status = unsafe { encode(encoder, params) };
        match status {
            NV_ENC_SUCCESS | NV_ENC_ERR_NEED_MORE_INPUT => Ok(status),
            _ => Err(self.fail(status, "NvEncEncodePicture")),
        }
    }

    /// `nvEncLockBitstream` — `do_not_wait` selects blocking/non-blocking.
    #[cfg(windows)]
    pub(crate) fn lock_bitstream(
        &self,
        encoder: *mut c_void,
        params: &mut NV_ENC_LOCK_BITSTREAM,
        do_not_wait: bool,
    ) -> Result<(), String> {
        let lock = self.fn_table.nv_enc_lock_bitstream.expect("checked by verify_table");
        params.set_do_not_wait(do_not_wait);
        let status = unsafe { lock(encoder, params) };
        self.check(status, "NvEncLockBitstream")
    }

    /// `nvEncUnlockBitstream`.
    #[cfg(windows)]
    pub(crate) fn unlock_bitstream(&self, encoder: *mut c_void, buffer: *mut c_void) {
        if let Some(f) = self.fn_table.nv_enc_unlock_bitstream {
            unsafe { f(encoder, buffer) };
        }
    }

    /// `nvEncDestroyEncoder` — also ends the session opened on the handle.
    #[cfg(windows)]
    pub(crate) fn destroy_encoder(&self, encoder: *mut c_void) {
        if let Some(f) = self.fn_table.nv_enc_destroy_encoder {
            unsafe { f(encoder) };
        }
    }

    /// Best-effort `nvEncGetLastErrorString` (driver-local error text).
    #[cfg(windows)]
    pub(crate) fn last_error_text(&self, encoder: *mut c_void) -> Option<String> {
        let f = self.fn_table.nv_enc_get_last_error_string?;
        let ptr = unsafe { f(encoder) };
        if ptr.is_null() {
            return None;
        }
        // SAFETY: driver returns a NUL-terminated ASCII/UTF-8 diagnostic that
        // stays valid until the next NVENC call on this thread.
        let len = unsafe { std::ffi::CStr::from_ptr(ptr) };
        Some(len.to_string_lossy().into_owned())
    }

    /// Status → Err translation with context and driver detail text.
    #[cfg(windows)]
    fn check(&self, status: u32, api: &str) -> Result<(), String> {
        if status == NV_ENC_SUCCESS {
            Ok(())
        } else {
            Err(self.fail(status, api))
        }
    }

    #[cfg(windows)]
    fn fail(&self, status: u32, api: &str) -> String {
        format!("NVENC_API_FAILED:{api}:{}:{}", status_name(status), status)
    }
}

// SAFETY: NvencApi is immutable after construction (function pointers + the
// pinned DLL handle). NVENC documents the resolved table as thread-safe for
// concurrent calls on distinct sessions; sessions themselves stay on their
// owning encode thread (see nvenc_session.rs).
unsafe impl Send for NvencApi {}
unsafe impl Sync for NvencApi {}

// ─── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::mem::size_of;

    #[test]
    fn sdk_version_identity_is_transcribed() {
        assert_eq!(NVENCAPI_MAJOR_VERSION, 13);
        assert_eq!(NVENCAPI_MINOR_VERSION, 1);
        assert_eq!(TRANSCRIBED_SDK_VERSION, 13 | (1 << 24));
        assert_eq!(ApiVersion::TRANSCRIBED.raw(), TRANSCRIBED_SDK_VERSION);
    }

    #[test]
    fn struct_version_macro_matches_header_semantics() {
        // NVENCAPI_STRUCT_VERSION(1) with API 13.1:
        // 13 | (1<<24) | (1<<16) | (0x7<<28)
        let v = nvenapi_struct_version(TRANSCRIBED_SDK_VERSION, 1);
        assert_eq!(v, 13 | (1 << 24) | (1 << 16) | (0x7 << 28));
        assert_eq!(nvenapi_struct_version_ext(TRANSCRIBED_SDK_VERSION, 9) >> 31, 1);
        // Counter rides bits 16..23, magic occupies 28..31.
        assert_eq!((nvenapi_struct_version(TRANSCRIBED_SDK_VERSION, 9) >> 16) & 0xFF, 9);
    }

    #[test]
    fn guid_roundtrip_matches_header_defines() {
        // {6BC82762-4E63-4ca4-AA85-1E50F321F6BF} — Data4 tail from the header.
        let h264 = NV_ENC_CODEC_H264_GUID;
        assert_eq!(h264.data1, 0x6bc82762);
        assert_eq!(h264.data2, 0x4e63);
        assert_eq!(h264.data3, 0x4ca4);
        assert_eq!(h264.data4, [0xaa, 0x85, 0x1e, 0x50, 0xf3, 0x21, 0xf6, 0xbf]);
        assert_eq!(h264.as_u128(), 0x6bc82762_4e63_4ca4_aa85_1e50f321f6bf);
        assert_eq!(NvGuid::from_u128(h264.as_u128()), h264);
        // Presets P5/P6/P7 differ pairwise (guards against copy-paste typos).
        assert_ne!(NV_ENC_PRESET_P5_GUID, NV_ENC_PRESET_P6_GUID);
        assert_ne!(NV_ENC_PRESET_P6_GUID, NV_ENC_PRESET_P7_GUID);
        assert_ne!(NV_ENC_CODEC_H264_GUID, NV_ENC_CODEC_HEVC_GUID);
    }

    #[test]
    fn caps_ordinals_match_header_declaration_order() {
        // Spot-check the queried ordinals against the SDK 13.1 enum walk.
        assert_eq!(caps::NUM_MAX_BFRAMES, 0);
        assert_eq!(caps::WIDTH_MAX, 16);
        assert_eq!(caps::HEIGHT_MAX, 17);
        assert_eq!(caps::MB_PER_SEC_MAX, 32);
        assert_eq!(caps::SUPPORT_LOOKAHEAD, 37);
        assert_eq!(caps::SUPPORT_TEMPORAL_AQ, 38);
        assert_eq!(caps::SUPPORT_10BIT_ENCODE, 39);
        assert_eq!(caps::DYNAMIC_QUERY_ENCODER_CAPACITY, 42);
        assert_eq!(caps::EXPOSED_COUNT, 60);
    }

    #[test]
    fn status_names_cover_every_documented_code() {
        assert_eq!(status_name(0), "NV_ENC_SUCCESS");
        assert_eq!(status_name(NV_ENC_ERR_NEED_MORE_INPUT), "NV_ENC_ERR_NEED_MORE_INPUT");
        assert_eq!(status_name(NV_ENC_ERR_INVALID_VERSION), "NV_ENC_ERR_INVALID_VERSION");
        assert_eq!(status_name(9999), "NV_ENC_ERR_UNKNOWN");
    }

    #[cfg(windows)]
    #[test]
    fn load_returns_static_or_blocker_never_panics() {
        match load() {
            Ok(api) => {
                assert!(VERSION_LADDER.contains(&api.api_version));
                assert!(api.api_version.raw() >= ApiVersion::LADDER_FLOOR.raw());
            }
            Err(e) => {
                assert!(
                    e.starts_with("NVENC_DLL_NOT_FOUND")
                        || e.starts_with("NVENC_ENTRY_POINT_NOT_FOUND")
                        || e.starts_with("NVENC_API_INIT_FAILED")
                        || e.starts_with("NVENC_DRIVER_TOO_OLD")
                        || e.starts_with("NVENC_FUNCTION_TABLE_INCOMPLETE"),
                    "{e}"
                );
            }
        }
    }

    /// Layout audit against hand-computed MSVC x64 offsets from the header
    /// (see module doc). A mismatch means a field moved — STOP and re-diff.
    #[test]
    fn struct_sizes_match_transcribed_layouts() {
        assert_eq!(size_of::<NvGuid>(), 16);
        assert_eq!(size_of::<NV_ENC_QP>(), 12, "NV_ENC_QP");
        assert_eq!(size_of::<NV_ENC_RC_PARAMS>(), 128, "NV_ENC_RC_PARAMS");
        assert_eq!(size_of::<NV_ENC_CAPS_PARAM>(), 256, "NV_ENC_CAPS_PARAM");
        assert_eq!(
            size_of::<NV_ENC_OPEN_ENCODE_SESSION_EX_PARAMS>(),
            1552,
            "OPEN_ENCODE_SESSION_EX"
        );
        assert_eq!(size_of::<NV_ENC_CONFIG_VUI_PARAMETERS>(), 112, "VUI");
        assert_eq!(size_of::<NV_ENC_CONFIG_H264>(), 1792, "NV_ENC_CONFIG_H264");
        assert_eq!(size_of::<NV_ENC_CONFIG_HEVC>(), 1560, "NV_ENC_CONFIG_HEVC");
        assert_eq!(size_of::<NV_ENC_CODEC_CONFIG>(), 1792, "CODEC_CONFIG union");
        assert_eq!(size_of::<NV_ENC_CONFIG>(), 3584, "NV_ENC_CONFIG");
        // MSVC x64 from the SDK 13.1 header. GUIDs are align-4, so
        // encodeGUID sits at @4 and no padding precedes the pointers at @80.
        // Offset locks — the driver reads these positionally; a single moved
        // field corrupts everything after it. Values below are computed from
        // the SDK 13.1 header layout (MSVC x64: GUID aligns to 4), NOT from
        // whatever the transcription currently says — that circularity is
        // exactly how the missing maxMEHintCountsPerBlock survived review:
        // the struct was 1768 instead of 1800 and every field after
        // maxEncodeHeight was read by the driver at a −32 byte offset.
        assert_eq!(size_of::<NV_ENC_INITIALIZE_PARAMS>(), 1800, "INITIALIZE_PARAMS");
        assert_eq!(std::mem::offset_of!(NV_ENC_INITIALIZE_PARAMS, preset_guid), 20, "preset_guid");
        assert_eq!(std::mem::offset_of!(NV_ENC_INITIALIZE_PARAMS, enable_ptd), 64, "enable_ptd");
        assert_eq!(std::mem::offset_of!(NV_ENC_INITIALIZE_PARAMS, priv_data), 80, "priv_data");
        assert_eq!(
            std::mem::offset_of!(NV_ENC_INITIALIZE_PARAMS, encode_config),
            88,
            "encode_config"
        );
        assert_eq!(
            std::mem::offset_of!(NV_ENC_INITIALIZE_PARAMS, max_encode_width),
            96,
            "max_encode_width"
        );
        assert_eq!(
            std::mem::offset_of!(NV_ENC_INITIALIZE_PARAMS, max_me_hint_counts_per_block),
            104,
            "max_me_hint_counts_per_block"
        );
        assert_eq!(
            size_of::<NVENC_EXTERNAL_ME_HINT_COUNTS_PER_BLOCKTYPE>(),
            16,
            "ME_HINT_COUNTS_PER_BLOCKTYPE"
        );
        assert_eq!(std::mem::offset_of!(NV_ENC_INITIALIZE_PARAMS, tuning_info), 136, "tuning_info");
        assert_eq!(
            std::mem::offset_of!(NV_ENC_INITIALIZE_PARAMS, buffer_format),
            140,
            "buffer_format"
        );
        assert_eq!(std::mem::offset_of!(NV_ENC_INITIALIZE_PARAMS, num_state_buffers), 144);
        assert_eq!(std::mem::offset_of!(NV_ENC_INITIALIZE_PARAMS, reserved1), 152, "reserved1");
        assert_eq!(size_of::<NV_ENC_REGISTER_RESOURCE>(), 1536, "REGISTER_RESOURCE");
        assert_eq!(size_of::<NV_ENC_MAP_INPUT_RESOURCE>(), 1544, "MAP_INPUT_RESOURCE");
        assert_eq!(size_of::<NV_ENC_PIC_PARAMS>(), 2840, "PIC_PARAMS");
        assert_eq!(size_of::<NV_ENC_LOCK_BITSTREAM>(), 1544, "LOCK_BITSTREAM");
        assert_eq!(size_of::<NV_ENC_CREATE_BITSTREAM_BUFFER>(), 776, "CREATE_BITSTREAM_BUFFER");
        assert_eq!(
            size_of::<NV_ENCODE_API_FUNCTION_LIST>(),
            2552,
            "FUNCTION_LIST (8 hdr + 33*8 legacy + 8 reserved1 + 9*8 modern + 275*8)"
        );
    }

    #[test]
    fn rc_params_bitfield_helpers_pack_lsb_first() {
        let mut rc = NV_ENC_RC_PARAMS::zeroed();
        rc.set_enable_lookahead(true);
        rc.set_enable_temporal_aq(true);
        rc.set_enable_aq(true);
        rc.set_aq_strength(8);
        assert!(rc.enable_lookahead());
        assert!(rc.enable_temporal_aq());
        assert!(rc.enable_aq());
        assert_eq!(rc.aq_strength(), 8);
        // Bit 5 = enableLookahead, bit 3 = enableAQ, bit 8 = enableTemporalAQ,
        // bits 12..15 = strength.
        assert_eq!(rc.bit_fields, (1 << 5) | (1 << 3) | (1 << 8) | (8 << 12));
        rc.set_enable_aq(false);
        assert_eq!(rc.bit_fields, (1 << 5) | (1 << 8) | (8 << 12));
        rc.set_aq_strength(15);
        assert_eq!(rc.bit_fields, (1 << 5) | (1 << 8) | (15 << 12));
    }

    /// Bit positions pinned against the SDK 13.1 header, not against the
    /// helpers — the HEVC repeatSPSPPS bit drifted once when a transcription
    /// skipped disableDeblockAcrossSliceBoundary and the helper kept
    /// "working" while flipping enableIntraRefresh instead.
    #[test]
    fn hevc_bitfield_positions_match_sdk_header() {
        // repeatSPSPPS = bit 7 (after disableSPSPPS at 6).
        let mut hevc = NV_ENC_CONFIG_HEVC::zeroed();
        hevc.set_repeat_spspps(true);
        assert_eq!(hevc.bit_fields, 1 << 7, "repeatSPSPPS must land on bit 7");
        assert!(hevc.repeat_spspps());

        // chromaFormatIDC:2 = bits 9-10; writing it must not disturb bit 7.
        hevc.set_chroma_format_idc(1);
        assert_eq!(hevc.bit_fields, (1 << 7) | (1 << 9), "chroma=1 → bits 7|9");
        assert_eq!(hevc.chroma_format_idc(), 1);
        hevc.set_chroma_format_idc(3);
        assert_eq!(hevc.bit_fields, (1 << 7) | (0b11 << 9));
        assert_eq!(hevc.chroma_format_idc(), 3);
        hevc.set_chroma_format_idc(1);
        assert!(hevc.repeat_spspps(), "chroma write clobbered repeatSPSPPS");

        // H264 counterpart: repeatSPSPPS = bit 12 (22 declared single-bit
        // flags precede the :10 reserved tail); chromaFormatIDC is a
        // standalone u32 there, NOT part of the word.
        let mut h264 = NV_ENC_CONFIG_H264::zeroed();
        h264.set_repeat_spspps(true);
        assert_eq!(h264.bit_fields, 1 << 12, "H264 repeatSPSPPS must be bit 12");
        assert_eq!(h264.chroma_format_idc, 0);
    }

    #[test]
    fn hevc_codec_config_sizes_unchanged() {
        assert_eq!(
            size_of::<NV_ENC_CONFIG_HEVC>(),
            1560,
            "HEVC size moved — re-derive offsets from the header"
        );
    }

    #[cfg(windows)]
    #[test]
    fn load_is_idempotent_and_stable() {
        let a = load();
        let b = load();
        match (a, b) {
            (Ok(x), Ok(y)) => {
                assert!(std::ptr::eq(x, y), "cached loader must return the same instance");
            }
            (Err(e1), Err(e2)) => assert_eq!(e1, e2),
            _ => panic!("loader flip-flopped between Ok and Err"),
        }
    }
}
