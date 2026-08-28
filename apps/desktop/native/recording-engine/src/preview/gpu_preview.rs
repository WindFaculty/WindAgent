//! GPU preview pipeline — downscale on the encode thread's D3D11 device,
//! one sanctioned CPU readback, JPEG encode, IPC-ready bytes
//! (ban_ke_hoach_v1.md §13, §3-A).
//!
//! ```text
//! CapturedFrame.texture (BGRA8 / FP16 HDR)
//!     │  ID3D11VideoProcessorBlt  (aspect-fit ≤ config.downscale)
//!     ▼
//! render-target BGRA8 texture ──CopyResource──► CPU_ACCESS_READ staging twin
//!                                                    │ Map(D3D11_MAP_READ)
//!                                                    ▼
//!                              Microsoft JPEG Encoder MFT (in-memory)
//!                                                    │
//!                                                    ▼
//!                                     PreviewJpeg { IPC-ready bytes }
//! ```
//!
//! Threading contract ([`crate::pipeline`]): all D3D11 immediate-context work
//! stays on the encode thread, so [`GpuPreviewPipeline`] lives there too —
//! it binds to the SAME device/context the NVENC session owns and never
//! creates threads of its own. Rate limiting (§18 priority ladder 2 → 1 →
//! 0.5 FPS → off) is the CALLER'S job via
//! [`crate::preview::PreviewSampler`]; [`GpuPreviewPipeline::process`] is
//! pure per-frame work and never touches recording-path state.
//!
//! COM threading: the owner thread must have called `CoInitializeEx`
//! (`COINIT_MULTITHREADED` recommended) before [`GpuPreviewPipeline::new`] —
//! Media Foundation activation needs an initialized apartment; a missing one
//! surfaces as an explicit `PREVIEW_INIT_FAILED:*` error, never silent
//! success.
//!
//! JPEG encoding note (documented deviation from the original WIC plan): the
//! pinned `windows = "=0.58.0"` dependency set does not enable
//! `Win32_System_Com_StructuredStorage`, which gates every WIC encoder entry
//! point (`IWICBitmapEncoder::CreateNewFrame`, `CreateStreamOnHGlobal`). The
//! equivalent in-memory path below drives the OS **Microsoft JPEG Encoder
//! MFT** discovered through `MFTEnum` — everything it needs sits inside
//! already-enabled features (`Win32_Media_MediaFoundation`,
//! `Win32_System_Com`). `config.jpeg_quality` [1..100] maps onto
//! `CODECAPI_AVEncCommonQuality`; encoders that reject the property keep
//! their default quality (best-effort hint by design, never a hard failure).
//!
//! HDR note: `SurfaceFormat::Rgba16Float` desktop capture arrives in PQ
//! (HDR10). The Video Processor is hinted with
//! `DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020` → sRGB output, which drivers
//! perform as best-effort tone mapping. Residual limitations (hard clip
//! instead of roll-off, no gamut compression) are accepted for v1 — full
//! tone-map polish is post-v1 work.
//!
//! Manual verification (no automated GPU test can run headless CI):
//! 1. On a machine with a display + NVIDIA adapter, run the recorder sidecar
//!    with preview enabled (`PreviewRate::TwoFps`).
//! 2. Confirm preview events arrive ≥500 ms apart, decode them, and check
//!    dimensions stay ≤1280×720 with the captured surface's aspect ratio.
//! 3. Repeat on an HDR display with FP16 capture and confirm the SDR preview
//!    is not washed out (tone-map smoke test).
//! 4. Stress TDR / unplug the adapter and confirm failures surface as
//!    `PREVIEW_PROCESS_FAILED:*` strings without panicking or disturbing the
//!    recording path.

// ─── Shared pure helpers (compiled everywhere, unit-tested) ─────────────────

/// Largest (w, h) that fits inside `(max_w, max_h)` while preserving the
/// `in_w : in_h` aspect ratio, rounded DOWN to an even size (safe for any
/// downstream consumer). Never upscales beyond the source; never returns 0 —
/// degenerate inputs clamp to 2×2.
pub fn fit_dims(in_w: u32, in_h: u32, max_w: u32, max_h: u32) -> (u32, u32) {
    let even_floor = |v: u32| v.max(2) & !1;
    let (in_w, in_h, max_w, max_h) =
        (in_w.max(1), in_h.max(1), max_w.max(1), max_h.max(1));
    // Width-limited candidate, capped so we never upscale the source.
    let w_fit = max_w.min(in_w);
    let h_from_w = (u64::from(w_fit) * u64::from(in_h) / u64::from(in_w)) as u32;
    if h_from_w <= max_h {
        (even_floor(w_fit), even_floor(h_from_w))
    } else {
        // Height-limited.
        let h_fit = max_h.min(in_h);
        let w_from_h = (u64::from(h_fit) * u64::from(in_w) / u64::from(in_h)) as u32;
        (even_floor(w_from_h), even_floor(h_fit))
    }
}

/// Clamp a configured JPEG quality into the range every backend accepts.
pub fn clamp_quality(q: u32) -> u32 {
    q.clamp(1, 100)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn api_surface_compiles() {
        // Compile-shaped guard demanded by the phase spec: the default preview
        // budget stays exactly ≤1280×720 so the readback twin remains "tiny",
        // and the helper agrees with that budget on a 1080p desktop.
        assert_eq!(crate::preview::PreviewConfig::default().downscale, (1280, 720));
        assert_eq!(fit_dims(1920, 1080, 1280, 720), (1280, 720));
    }

    #[test]
    fn fit_dims_preserves_aspect_and_never_upscales() {
        // 16:9 sources land exactly on the 16:9 budget.
        assert_eq!(fit_dims(3840, 2160, 1280, 720), (1280, 720));
        // Portrait phone window: height-limited, aspect kept.
        assert_eq!(fit_dims(720, 2560, 1280, 720), (202, 720));
        // Smaller than budget: untouched.
        assert_eq!(fit_dims(640, 480, 1280, 720), (640, 480));
        // Odd sizes floor to even numbers.
        assert_eq!(fit_dims(1000, 1000, 999, 999), (998, 998));
        // Near-16:9 source stays width-limited inside the budget.
        assert_eq!(fit_dims(1921, 1081, 1280, 720), (1280, 720));
        // Degenerate inputs clamp instead of dividing by zero.
        assert_eq!(fit_dims(0, 0, 1280, 720), (2, 2));
        assert_eq!(fit_dims(1920, 1080, 0, 0), (2, 2));
    }

    #[test]
    fn quality_clamps_into_backend_range() {
        assert_eq!(clamp_quality(0), 1);
        assert_eq!(clamp_quality(80), 80);
        assert_eq!(clamp_quality(101), 100);
    }
}

// ─── Windows implementation ────────────────────────────────────────────────

#[cfg(windows)]
pub mod imp {
    use std::mem::ManuallyDrop;

    use windows::core::{Interface, VARIANT};
    use windows::Win32::Foundation::{BOOL, RECT};
    use windows::Win32::Graphics::Direct3D11::{
        ID3D11Device, ID3D11DeviceContext, ID3D11Texture2D, ID3D11VideoContext,
        ID3D11VideoContext1, ID3D11VideoDevice, ID3D11VideoProcessor,
        ID3D11VideoProcessorEnumerator, ID3D11VideoProcessorInputView,
        ID3D11VideoProcessorOutputView, D3D11_BIND_RENDER_TARGET, D3D11_CPU_ACCESS_READ,
        D3D11_MAP_READ, D3D11_MAPPED_SUBRESOURCE, D3D11_TEX2D_VPIV, D3D11_TEX2D_VPOV,
        D3D11_TEXTURE2D_DESC, D3D11_USAGE_DEFAULT, D3D11_USAGE_STAGING,
        D3D11_VIDEO_FRAME_FORMAT_PROGRESSIVE, D3D11_VIDEO_PROCESSOR_COLOR_SPACE,
        D3D11_VIDEO_PROCESSOR_CONTENT_DESC, D3D11_VIDEO_PROCESSOR_INPUT_VIEW_DESC,
        D3D11_VIDEO_PROCESSOR_INPUT_VIEW_DESC_0, D3D11_VIDEO_PROCESSOR_OUTPUT_VIEW_DESC,
        D3D11_VIDEO_PROCESSOR_OUTPUT_VIEW_DESC_0, D3D11_VIDEO_PROCESSOR_STREAM,
        D3D11_VIDEO_USAGE_PLAYBACK_NORMAL, D3D11_VPIV_DIMENSION_TEXTURE2D,
        D3D11_VPOV_DIMENSION_TEXTURE2D,
    };
    use windows::Win32::Graphics::Dxgi::Common::{
        DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020, DXGI_COLOR_SPACE_RGB_FULL_G22_NONE_P709,
        DXGI_FORMAT_B8G8R8A8_UNORM, DXGI_RATIONAL, DXGI_SAMPLE_DESC,
    };
    use windows::Win32::Media::MediaFoundation::{
        CODECAPI_AVEncCommonQuality, ICodecAPI, IMFAttributes, IMFMediaType, IMFSample,
        IMFTransform, MF_E_TRANSFORM_NEED_MORE_INPUT, MFImageFormat_JPEG, MFMediaType_Video,
        MFSTARTUP_LITE, MFVideoFormat_RGB32, MF_MT_AVG_BITRATE, MF_MT_MAJOR_TYPE,
        MF_MT_SUBTYPE, MFT_CATEGORY_VIDEO_ENCODER, MFT_MESSAGE_NOTIFY_BEGIN_STREAMING,
        MFT_MESSAGE_NOTIFY_START_OF_STREAM, MFT_OUTPUT_DATA_BUFFER, MFT_OUTPUT_STREAM_INFO,
        MFT_OUTPUT_STREAM_PROVIDES_SAMPLES, MFT_REGISTER_TYPE_INFO, MFCreateMediaType,
        MFCreateMemoryBuffer, MFCreateSample, MFShutdown, MFStartup, MFTEnum,
    };
    use windows::Win32::System::Com::{CLSCTX_INPROC_SERVER, CoCreateInstance, CoTaskMemFree};

    use super::{clamp_quality, fit_dims};

    /// mfapi.h `MF_VERSION` (major 2, minor 0x70) — accepted by every
    /// supported Windows release for `MFStartup`.
    const MF_VERSION_2_70: u32 = 0x0002_0070;

    /// One preview producer bound to the encode thread's device/context.
    ///
    /// Expensive resources (Video Processor chain, staging textures, JPEG MFT)
    /// are created eagerly here / on first geometry change respectively;
    /// steady-state cost per preview frame is one Blt, one copy, one tiny map
    /// and one MFT pass — recording FPS is never affected (§13, §18).
    pub struct GpuPreviewPipeline {
        device: ID3D11Device,
        context: ID3D11DeviceContext,

        // ── D3D11 Video Processor chain (rebuilt when geometry changes) ──
        video_device: ID3D11VideoDevice,
        video_context: ID3D11VideoContext,
        /// `ID3D11VideoContext1` when the driver exposes it (colorspace hints).
        video_context1: Option<ID3D11VideoContext1>,
        enumerator: Option<ID3D11VideoProcessorEnumerator>,
        processor: Option<ID3D11VideoProcessor>,
        /// GPU-side downscaled BGRA8 render target.
        output_tex: Option<ID3D11Texture2D>,
        /// CPU-readable twin — the ONE sanctioned CPU readback (§3-A).
        staging_tex: Option<ID3D11Texture2D>,
        output_view: Option<ID3D11VideoProcessorOutputView>,
        /// (in_w, in_h, out_w, out_h) key the current chain was built for.
        chain_key: Option<(u32, u32, u32, u32)>,

        // ── JPEG encoder MFT (in-memory; see module header for why not WIC) ──
        /// Quality hint applied once at construction ([`Self::new`]); the
        /// configured MFT keeps it for its lifetime.
        jpeg_encoder: IMFTransform,
        mf_started: bool,

        // ── Frozen configuration ──
        downscale: (u32, u32),
    }

    impl GpuPreviewPipeline {
        /// Bind to the SAME device/context the encode thread owns (all D3D11
        /// immediate-context work stays on one thread — pipeline.rs contract).
        ///
        /// Fail-closed: every missing capability becomes an explicit
        /// `PREVIEW_INIT_FAILED:<ctx>` error — never silent degradation.
        pub fn new(
            device: &ID3D11Device,
            context: &ID3D11DeviceContext,
            config: &crate::preview::PreviewConfig,
        ) -> Result<Self, String> {
            let video_device: ID3D11VideoDevice = device
                .cast()
                .map_err(|e| format!("PREVIEW_INIT_FAILED:NO_VIDEO_DEVICE:{e}"))?;
            let video_context: ID3D11VideoContext = context
                .cast()
                .map_err(|e| format!("PREVIEW_INIT_FAILED:NO_VIDEO_CONTEXT:{e}"))?;
            // Colorspace1 hints are optional — legacy drivers fall back to the
            // bitfield color-space struct (see `set_colorspace`).
            let video_context1: Option<ID3D11VideoContext1> = context.cast().ok();

            // Media Foundation powers the in-memory JPEG MFT. Startup is
            // refcounted per process — safe alongside the AAC stack.
            //
            // SAFETY: flat mfplat.dll export; runs on the owner thread, which
            // the contract guarantees holds an initialized COM apartment.
            unsafe {
                if let Err(e) = MFStartup(MF_VERSION_2_70, MFSTARTUP_LITE) {
                    return Err(format!("PREVIEW_INIT_FAILED:MEDIA_FOUNDATION_START:{e}"));
                }
            }
            // Discover the OS still-JPEG encoder: uncompressed RGB32 in.
            let in_type = MFT_REGISTER_TYPE_INFO {
                guidMajorType: MFMediaType_Video,
                guidSubtype: MFVideoFormat_RGB32,
            };
            let no_attrs: Option<&IMFAttributes> = None;
            let mut clsids: *mut windows::core::GUID = std::ptr::null_mut();
            let mut count: u32 = 0;
            // SAFETY: out-pointers valid for the duration of the call; the
            // returned CLSID array is released via CoTaskMemFree below.
            let enumerated = unsafe {
                MFTEnum(
                    MFT_CATEGORY_VIDEO_ENCODER,
                    0, // sync MFTs only — driven inline, no async queues
                    Some(&in_type),
                    None,
                    no_attrs,
                    &mut clsids,
                    &mut count,
                )
            };
            if let Err(e) = enumerated {
                unsafe {
                    let _ = MFShutdown();
                }
                return Err(format!("PREVIEW_INIT_FAILED:JPEG_ENCODER_ENUMERATION:{e}"));
            }

            let mut encoder: Option<IMFTransform> = None;
            if !clsids.is_null() && count > 0 {
                let list = unsafe { std::slice::from_raw_parts(clsids, count as usize) };
                for clsid in list {
                    // SAFETY: CLSIDs come from the OS enumeration above.
                    let candidate: Result<IMFTransform, _> =
                        unsafe { CoCreateInstance(clsid, None, CLSCTX_INPROC_SERVER) };
                    let Ok(candidate) = candidate else { continue };
                    match Self::configure_jpeg_mft(&candidate, config.jpeg_quality) {
                        Ok(()) => {
                            encoder = Some(candidate);
                            break;
                        }
                        Err(_) => continue,
                    }
                }
            }
            // SAFETY: allocation handed to us by the successful MFTEnum above.
            unsafe {
                if !clsids.is_null() {
                    CoTaskMemFree(Some(clsids.cast()));
                }
            }

            let Some(jpeg_encoder) = encoder else {
                unsafe {
                    let _ = MFShutdown();
                }
                return Err(
                    "PREVIEW_INIT_FAILED:JPEG_ENCODER_UNAVAILABLE: no OS RGB32->JPEG MFT accepts \
                     the requested media types"
                        .into(),
                );
            };

            Ok(Self {
                device: device.clone(),
                context: context.clone(),
                video_device,
                video_context,
                video_context1,
                enumerator: None,
                processor: None,
                output_tex: None,
                staging_tex: None,
                output_view: None,
                chain_key: None,
                jpeg_encoder,
                mf_started: true,
                downscale: config.downscale,
            })
        }

        /// Set input/output media types (+ best-effort quality hint) on a
        /// freshly created JPEG encoder MFT.
        fn configure_jpeg_mft(mft: &IMFTransform, quality: u32) -> Result<(), String> {
            unsafe {
                let input_type: IMFMediaType = MFCreateMediaType()
                    .map_err(|e| format!("PREVIEW_INIT_FAILED:MEDIA_TYPE:{e}"))?;
                input_type
                    .SetGUID(&MF_MT_MAJOR_TYPE, &MFMediaType_Video)
                    .map_err(|e| format!("PREVIEW_INIT_FAILED:MEDIA_TYPE_GUID:{e}"))?;
                input_type
                    .SetGUID(&MF_MT_SUBTYPE, &MFVideoFormat_RGB32)
                    .map_err(|e| format!("PREVIEW_INIT_FAILED:MEDIA_TYPE_GUID:{e}"))?;
                mft.SetInputType(0, &input_type, 0)
                    .map_err(|e| format!("PREVIEW_INIT_FAILED:MFT_INPUT_TYPE:{e}"))?;

                let output_type: IMFMediaType = MFCreateMediaType()
                    .map_err(|e| format!("PREVIEW_INIT_FAILED:MEDIA_TYPE:{e}"))?;
                output_type
                    .SetGUID(&MF_MT_MAJOR_TYPE, &MFMediaType_Video)
                    .map_err(|e| format!("PREVIEW_INIT_FAILED:MEDIA_TYPE_GUID:{e}"))?;
                output_type
                    .SetGUID(&MF_MT_SUBTYPE, &MFImageFormat_JPEG)
                    .map_err(|e| format!("PREVIEW_INIT_FAILED:MEDIA_TYPE_GUID:{e}"))?;
                // Ceiling keeps worst-case preview bitstream bounded; still
                // encoders treat this as advisory.
                output_type
                    .SetUINT32(&MF_MT_AVG_BITRATE, 24_000_000)
                    .map_err(|e| format!("PREVIEW_INIT_FAILED:MEDIA_TYPE_BITRATE:{e}"))?;
                mft.SetOutputType(0, &output_type, 0)
                    .map_err(|e| format!("PREVIEW_INIT_FAILED:MFT_OUTPUT_TYPE:{e}"))?;

                // Best-effort quality (VT_UI4, 1..100). Encoders without the
                // property keep their default — documented, never fatal.
                let codec: Option<ICodecAPI> = mft.cast().ok();
                if let Some(c) = &codec {
                    let variant = VARIANT::from(clamp_quality(quality));
                    let _ = c.SetValue(&CODECAPI_AVEncCommonQuality, &variant);
                }
                let _ = mft.ProcessMessage(MFT_MESSAGE_NOTIFY_BEGIN_STREAMING, 0);
                let _ = mft.ProcessMessage(MFT_MESSAGE_NOTIFY_START_OF_STREAM, 0);
                Ok(())
            }
        }

        /// Downscale one captured texture (BGRA8 or HDR FP16) to ≤1280×720
        /// BGRA, read back the tiny staging surface (sanctioned CPU exception,
        /// §3-A), JPEG-encode, return bytes. Rate limiting is the CALLER'S job
        /// ([`crate::preview::PreviewSampler`]) — this fn is pure per-frame work.
        pub fn process(
            &mut self,
            frame: &crate::capture::CapturedFrame,
        ) -> Result<crate::preview::PreviewJpeg, String> {
            let texture = frame
                .texture
                .as_ref()
                .ok_or("PREVIEW_PROCESS_FAILED:NO_TEXTURE")?;

            // 1. Ensure the VP chain matches this frame's geometry.
            self.ensure_chain(frame.width, frame.height)?;
            let (_, _, out_w, out_h) = self
                .chain_key
                .ok_or_else(|| "PREVIEW_PROCESS_FAILED:CHAIN_KEY_MISSING".to_string())?;

            // SAFETY: all D3D11 calls run on the owning (encode) thread; every
            // handle was created from `self.device` or arrived from the capture
            // frame pool for this single pipeline stage.
            unsafe {
                let input_view = self.create_input_view(texture)?;
                self.set_colorspace(frame.format);
                let processor = self
                    .processor
                    .as_ref()
                    .ok_or_else(|| "PREVIEW_PROCESS_FAILED:PROCESSOR_MISSING".to_string())?;

                // Full-source → full-destination progressive Blt.
                self.video_context.VideoProcessorSetStreamFrameFormat(
                    processor,
                    0,
                    D3D11_VIDEO_FRAME_FORMAT_PROGRESSIVE,
                );
                let src = RECT {
                    left: 0,
                    top: 0,
                    right: frame.width as i32,
                    bottom: frame.height as i32,
                };
                let dst = RECT {
                    left: 0,
                    top: 0,
                    right: out_w as i32,
                    bottom: out_h as i32,
                };
                self.video_context.VideoProcessorSetStreamSourceRect(processor, 0, true, Some(&src));
                self.video_context.VideoProcessorSetStreamDestRect(processor, 0, true, Some(&dst));

                // Resolve the output view BEFORE the stream descriptor embeds
                // its input ref — a `?` past that point would leak it.
                let output_view = self
                    .output_view
                    .as_ref()
                    .ok_or_else(|| "PREVIEW_PROCESS_FAILED:OUTPUT_VIEW_MISSING".to_string())?;
                let mut streams = [D3D11_VIDEO_PROCESSOR_STREAM {
                    Enable: BOOL(1),
                    OutputIndex: 0,
                    InputFrameOrField: 0,
                    PastFrames: 0,
                    FutureFrames: 0,
                    ppPastSurfaces: std::ptr::null_mut(),
                    pInputSurface: ManuallyDrop::new(Some(input_view)),
                    ppFutureSurfaces: std::ptr::null_mut(),
                    ppPastSurfacesRight: std::ptr::null_mut(),
                    pInputSurfaceRight: ManuallyDrop::new(None),
                    ppFutureSurfacesRight: std::ptr::null_mut(),
                }];
                let blt = self
                    .video_context
                    .VideoProcessorBlt(processor, output_view, 0, &streams);
                // Release the view refs the descriptor embeds on EVERY path —
                // pool textures must never leak past one pipeline stage.
                ManuallyDrop::drop(&mut streams[0].pInputSurface);
                ManuallyDrop::drop(&mut streams[0].pInputSurfaceRight);
                blt.map_err(|e| format!("PREVIEW_PROCESS_FAILED:VIDEO_PROCESSOR_BLT:{e}"))?;

                // 2. Sanctioned CPU exception (§3-A): copy the tiny result to
                //    the staging twin and pull it off the GPU immediately.
                let staging = self
                    .staging_tex
                    .as_ref()
                    .ok_or_else(|| "PREVIEW_PROCESS_FAILED:STAGING_MISSING".to_string())?;
                let output = self
                    .output_tex
                    .as_ref()
                    .ok_or_else(|| "PREVIEW_PROCESS_FAILED:OUTPUT_TEXTURE_MISSING".to_string())?;
                self.context.CopyResource(staging, output);

                let mut mapped = D3D11_MAPPED_SUBRESOURCE::default();
                self.context
                    .Map(staging, 0, D3D11_MAP_READ, 0, Some(&mut mapped))
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:STAGING_MAP:{e}"))?;
                let pitch = mapped.RowPitch as usize;
                let row_bytes = out_w as usize * 4;
                let mut bgra = vec![0u8; row_bytes * out_h as usize];
                for row in 0..out_h as usize {
                    debug_assert!(pitch >= row_bytes);
                    std::ptr::copy_nonoverlapping(
                        mapped.pData.add(row * pitch).cast::<u8>(),
                        bgra.as_mut_ptr().add(row * row_bytes),
                        row_bytes,
                    );
                }
                self.context.Unmap(staging, 0);

                // 3. JPEG-encode entirely in memory via the OS MFT.
                let jpeg = self.encode_bgra_to_jpeg(&bgra)?;

                Ok(crate::preview::PreviewJpeg {
                    jpeg,
                    width: out_w,
                    height: out_h,
                    qpc: frame.qpc,
                })
            }
        }

        /// (Re)create enumerator/processor/textures/views for this geometry.
        /// The chain key is cleared FIRST so a mid-rebuild failure cannot
        /// leave a matching-but-dead key behind (the next frame retries the
        /// rebuild instead of trusting half-built state).
        fn ensure_chain(&mut self, in_w: u32, in_h: u32) -> Result<(), String> {
            if let Some((iw, ih, _, _)) = self.chain_key {
                if iw == in_w && ih == in_h {
                    return Ok(());
                }
            }
            let (out_w, out_h) = fit_dims(in_w, in_h, self.downscale.0, self.downscale.1);
            self.chain_key = None;

            self.processor = None;
            self.enumerator = None;
            self.output_view = None;
            self.output_tex = None;
            self.staging_tex = None;

            unsafe {
                let desc = D3D11_VIDEO_PROCESSOR_CONTENT_DESC {
                    InputFrameFormat: D3D11_VIDEO_FRAME_FORMAT_PROGRESSIVE,
                    InputFrameRate: DXGI_RATIONAL { Numerator: 30, Denominator: 1 },
                    InputWidth: in_w,
                    InputHeight: in_h,
                    OutputFrameRate: DXGI_RATIONAL { Numerator: 30, Denominator: 1 },
                    OutputWidth: out_w,
                    OutputHeight: out_h,
                    Usage: D3D11_VIDEO_USAGE_PLAYBACK_NORMAL,
                };
                let enumerator = self
                    .video_device
                    .CreateVideoProcessorEnumerator(&desc)
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:VP_ENUMERATOR:{e}"))?;
                let processor = self
                    .video_device
                    .CreateVideoProcessor(&enumerator, 0)
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:VP_CREATE:{e}"))?;

                // VP output target: render-target-bound BGRA8, misc 0.
                let tex_desc = D3D11_TEXTURE2D_DESC {
                    Width: out_w,
                    Height: out_h,
                    MipLevels: 1,
                    ArraySize: 1,
                    Format: DXGI_FORMAT_B8G8R8A8_UNORM,
                    SampleDesc: DXGI_SAMPLE_DESC { Count: 1, Quality: 0 },
                    Usage: D3D11_USAGE_DEFAULT,
                    BindFlags: D3D11_BIND_RENDER_TARGET.0 as u32,
                    CPUAccessFlags: 0,
                    MiscFlags: 0,
                };
                let mut output_tex: Option<ID3D11Texture2D> = None;
                self.device
                    .CreateTexture2D(&tex_desc, None, Some(&mut output_tex))
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:OUTPUT_TEXTURE:{e}"))?;
                let output_tex = output_tex.expect("CreateTexture2D wrote its handle");

                // Staging twin: CPU READ-only, no GPU binding.
                let stage_desc = D3D11_TEXTURE2D_DESC {
                    Usage: D3D11_USAGE_STAGING,
                    BindFlags: 0,
                    CPUAccessFlags: D3D11_CPU_ACCESS_READ.0 as u32,
                    MiscFlags: 0,
                    ..tex_desc
                };
                let mut staging_tex: Option<ID3D11Texture2D> = None;
                self.device
                    .CreateTexture2D(&stage_desc, None, Some(&mut staging_tex))
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:STAGING_TEXTURE:{e}"))?;
                let staging_tex = staging_tex.expect("CreateTexture2D wrote its handle");

                let ov_desc = D3D11_VIDEO_PROCESSOR_OUTPUT_VIEW_DESC {
                    ViewDimension: D3D11_VPOV_DIMENSION_TEXTURE2D,
                    Anonymous: D3D11_VIDEO_PROCESSOR_OUTPUT_VIEW_DESC_0 {
                        Texture2D: D3D11_TEX2D_VPOV { MipSlice: 0 },
                    },
                };
                let mut output_view: Option<ID3D11VideoProcessorOutputView> = None;
                self.video_device
                    .CreateVideoProcessorOutputView(
                        &output_tex,
                        &enumerator,
                        &ov_desc,
                        Some(&mut output_view),
                    )
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:OUTPUT_VIEW:{e}"))?;
                let output_view =
                    output_view.expect("CreateVideoProcessorOutputView wrote its handle");

                self.enumerator = Some(enumerator);
                self.processor = Some(processor);
                self.output_tex = Some(output_tex);
                self.staging_tex = Some(staging_tex);
                self.output_view = Some(output_view);
                self.chain_key = Some((in_w, in_h, out_w, out_h));
                Ok(())
            }
        }

        /// Per-frame input view over the captured pool texture (the texture
        /// identity changes every frame, so views are not cacheable).
        fn create_input_view(
            &self,
            texture: &ID3D11Texture2D,
        ) -> Result<ID3D11VideoProcessorInputView, String> {
            let iv_desc = D3D11_VIDEO_PROCESSOR_INPUT_VIEW_DESC {
                FourCC: 0,
                ViewDimension: D3D11_VPIV_DIMENSION_TEXTURE2D,
                Anonymous: D3D11_VIDEO_PROCESSOR_INPUT_VIEW_DESC_0 {
                    Texture2D: D3D11_TEX2D_VPIV { MipSlice: 0, ArraySlice: 0 },
                },
            };
            let mut view: Option<ID3D11VideoProcessorInputView> = None;
            let enumerator = self
                .enumerator
                .as_ref()
                .ok_or_else(|| "PREVIEW_PROCESS_FAILED:ENUMERATOR_MISSING".to_string())?;
            unsafe {
                self.video_device
                    .CreateVideoProcessorInputView(texture, enumerator, &iv_desc, Some(&mut view))
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:INPUT_VIEW:{e}"))?;
            }
            view.ok_or_else(|| "PREVIEW_PROCESS_FAILED:INPUT_VIEW_NULL".into())
        }

        /// Best-effort colorspace hints. PQ (HDR10 FP16 desktops) tone-maps
        /// toward sRGB when the driver honors `*ColorSpace1`; legacy drivers
        /// fall back to the bitfield color-space struct (SDR passthrough).
        fn set_colorspace(&self, format: crate::capture::SurfaceFormat) {
            let (stream_cs, output_cs) = match format {
                crate::capture::SurfaceFormat::Rgba16Float => (
                    DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020,
                    DXGI_COLOR_SPACE_RGB_FULL_G22_NONE_P709,
                ),
                crate::capture::SurfaceFormat::Bgra8 => (
                    DXGI_COLOR_SPACE_RGB_FULL_G22_NONE_P709,
                    DXGI_COLOR_SPACE_RGB_FULL_G22_NONE_P709,
                ),
            };
            let Some(processor) = self.processor.as_ref() else {
                return;
            };
            unsafe {
                if let Some(vc1) = &self.video_context1 {
                    vc1.VideoProcessorSetStreamColorSpace1(processor, 0, stream_cs);
                    vc1.VideoProcessorSetOutputColorSpace1(processor, output_cs);
                } else {
                    // Legacy path: Usage=0 (playback), nominal-range defaults.
                    let legacy = D3D11_VIDEO_PROCESSOR_COLOR_SPACE { _bitfield: 0 };
                    self.video_context.VideoProcessorSetStreamColorSpace(processor, 0, &legacy);
                    self.video_context.VideoProcessorSetOutputColorSpace(processor, &legacy);
                }
            }
        }

        /// Push one BGRA frame through the JPEG MFT and collect the bytes.
        fn encode_bgra_to_jpeg(&self, bgra: &[u8]) -> Result<Vec<u8>, String> {
            unsafe {
                let stream_info: MFT_OUTPUT_STREAM_INFO = self
                    .jpeg_encoder
                    .GetOutputStreamInfo(0)
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:STREAM_INFO:{e}"))?;
                let provides_samples =
                    (stream_info.dwFlags as i32 & MFT_OUTPUT_STREAM_PROVIDES_SAMPLES.0) != 0;

                // Upload the BGRA plane (row pitch already normalized away).
                let in_buffer = MFCreateMemoryBuffer(bgra.len() as u32)
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:IN_BUFFER:{e}"))?;
                {
                    let mut ptr: *mut u8 = std::ptr::null_mut();
                    in_buffer
                        .Lock(&mut ptr, None, None)
                        .map_err(|e| format!("PREVIEW_PROCESS_FAILED:BUFFER_LOCK:{e}"))?;
                    std::ptr::copy_nonoverlapping(bgra.as_ptr(), ptr, bgra.len());
                    in_buffer
                        .Unlock()
                        .map_err(|e| format!("PREVIEW_PROCESS_FAILED:BUFFER_UNLOCK:{e}"))?;
                    in_buffer
                        .SetCurrentLength(bgra.len() as u32)
                        .map_err(|e| format!("PREVIEW_PROCESS_FAILED:BUFFER_LENGTH:{e}"))?;
                }
                let sample = MFCreateSample()
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:SAMPLE:{e}"))?;
                sample
                    .AddBuffer(&in_buffer)
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:SAMPLE_BUFFER:{e}"))?;
                sample
                    .SetSampleTime(0)
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:SAMPLE_TIME:{e}"))?;
                sample
                    .SetSampleDuration(0)
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:SAMPLE_DURATION:{e}"))?;
                self.jpeg_encoder
                    .ProcessInput(0, &sample, 0)
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:PROCESS_INPUT:{e}"))?;

                let mut out = MFT_OUTPUT_DATA_BUFFER {
                    dwStreamID: 0,
                    pSample: ManuallyDrop::new(None),
                    dwStatus: 0,
                    pEvents: ManuallyDrop::new(None),
                };
                if !provides_samples {
                    // Caller-owned output sample sized from the MFT contract.
                    let size = stream_info.cbSize.max((bgra.len() as u32) / 4).max(256 * 1024);
                    let out_buffer = MFCreateMemoryBuffer(size)
                        .map_err(|e| format!("PREVIEW_PROCESS_FAILED:OUT_BUFFER:{e}"))?;
                    let os: IMFSample = MFCreateSample()
                        .map_err(|e| format!("PREVIEW_PROCESS_FAILED:OUT_SAMPLE:{e}"))?;
                    os.AddBuffer(&out_buffer)
                        .map_err(|e| format!("PREVIEW_PROCESS_FAILED:OUT_SAMPLE_BUFFER:{e}"))?;
                    out.pSample = ManuallyDrop::new(Some(os));
                }

                let mut outputs = [out];
                let mut status = 0u32;
                let output_result = self.jpeg_encoder.ProcessOutput(0, &mut outputs, &mut status);

                // Take the COM refs back out of the ManuallyDrop slots on EVERY
                // post-BLT path so neither success nor error leaks them.
                let out_sample = ManuallyDrop::take(&mut outputs[0].pSample);
                let _events = ManuallyDrop::take(&mut outputs[0].pEvents);

                if let Err(e) = output_result {
                    if e.code() == MF_E_TRANSFORM_NEED_MORE_INPUT {
                        // Still encoders can ask once more after stream setup;
                        // report honestly: empty JPEG means "retry next tick".
                        return Ok(Vec::new());
                    }
                    return Err(format!("PREVIEW_PROCESS_FAILED:PROCESS_OUTPUT:{e}"));
                }
                let Some(produced) = out_sample else {
                    return Err("PREVIEW_PROCESS_FAILED:NO_OUTPUT_SAMPLE".into());
                };

                let contiguous = produced
                    .ConvertToContiguousBuffer()
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:CONTIGUOUS:{e}"))?;
                let len = contiguous.GetCurrentLength().unwrap_or(0) as usize;
                let mut ptr: *mut u8 = std::ptr::null_mut();
                contiguous
                    .Lock(&mut ptr, None, None)
                    .map_err(|e| format!("PREVIEW_PROCESS_FAILED:OUT_LOCK:{e}"))?;
                let mut jpeg = Vec::<u8>::with_capacity(len.max(1));
                std::ptr::copy_nonoverlapping(ptr, jpeg.as_mut_ptr(), len);
                jpeg.set_len(len);
                let _ = contiguous.Unlock();

                if len == 0 {
                    return Err("PREVIEW_PROCESS_FAILED:EMPTY_JPEG".into());
                }
                Ok(jpeg)
            }
        }
    }

    impl Drop for GpuPreviewPipeline {
        fn drop(&mut self) {
            // Balance MFStartup — refcounted, safe alongside other users.
            if self.mf_started {
                unsafe {
                    let _ = MFShutdown();
                }
            }
        }
    }
}

#[cfg(windows)]
pub use imp::GpuPreviewPipeline;

/// Free-function constructor the pipeline/service layer binds against
/// (`service.rs` degrades a failed preview to `None` — never blocks the take,
/// §13). Identical semantics to [`GpuPreviewPipeline::new`].
#[cfg(windows)]
pub fn build_pipeline(
    device: &windows::Win32::Graphics::Direct3D11::ID3D11Device,
    context: &windows::Win32::Graphics::Direct3D11::ID3D11DeviceContext,
    config: &crate::preview::PreviewConfig,
) -> Result<GpuPreviewPipeline, String> {
    GpuPreviewPipeline::new(device, context, config)
}

// ─── Non-Windows fail-closed fallback ──────────────────────────────────────

#[cfg(not(windows))]
mod imp {
    /// Stub — the GPU preview path is Windows-first (ban_ke_hoach_v1.md §5).
    /// Every entry point fails closed; there is deliberately NO software
    /// fallback that could mask a broken native stack.
    pub struct GpuPreviewPipeline {
        _private: (),
    }

    impl GpuPreviewPipeline {
        pub fn new(
            _device: &(),
            _context: &(),
            _config: &crate::preview::PreviewConfig,
        ) -> Result<Self, String> {
            Err("PREVIEW_UNSUPPORTED_OS".into())
        }

        pub fn process(
            &mut self,
            _frame: &crate::capture::CapturedFrame,
        ) -> Result<crate::preview::PreviewJpeg, String> {
            Err("PREVIEW_UNSUPPORTED_OS".into())
        }
    }
}

#[cfg(not(windows))]
pub use imp::GpuPreviewPipeline;
