//! WASAPI endpoint discovery + the shared event-driven capture-client core
//! (ban_ke_hoach_v1.md §10, §11; preflight §15).
//!
//! ```text
//! IMMDeviceEnumerator ──► IMMDevice (capture | render endpoint)
//!        │                     │ Activate::<IAudioClient>
//!        ▼                     ▼
//! list_*_endpoints      AUDCLNT_SHAREMODE_SHARED + EVENTCALLBACK
//!                              │ GetService::<IAudioCaptureClient>
//!                              ▼
//!                       worker thread: WaitForSingleObject(event, 100 ms)
//!                         → GetNextPacketSize / GetBuffer / ReleaseBuffer
//!                         → PCM → interleaved f32 → bounded PcmBlock queue
//! ```
//!
//! Everything here is **fail-closed**: a missing enumerator, endpoint, event,
//! capture service or an undecodable mix format surfaces as an UPPER_SNAKE
//! error string — never as a silent success or a fabricated device.
//! [`microphone::WasapiMicrophone`] and [`loopback::WasapiLoopback`] are thin
//! wrappers over the private [`wasapi::StreamHandle`] defined here, so their
//! lifecycle semantics are identical by construction.
//!
//! Device invalidation contract (`AUDCLNT_E_DEVICE_INVALIDATED`, 0x88890004):
//! the worker marks the stream unavailable and records `last_error`; the
//! pipeline polls the port's `last_error()` — no Warning is synthesized into
//! the block stream, so PTS continuity of delivered blocks stays untouched
//! (§12).

use serde::Serialize;

// ─── Public probe surface (preflight §15 consumes these) ───────────────────

/// True when COM can create the WASAPI `MMDeviceEnumerator` at all.
///
/// Hardware-dependent probe: degrades to `false` on hosts without the audio
/// service — callers treat that as an explicit blocker, never a fallback.
pub fn wasapi_available() -> bool {
    #[cfg(windows)]
    {
        use windows::Win32::Media::Audio::IMMDeviceEnumerator;
        match wasapi::ComGuard::acquire() {
            Err(_) => false,
            Ok(_com) => {
                let enumerator: Result<IMMDeviceEnumerator, _> = wasapi::co_create_enumerator();
                enumerator.is_ok()
            }
        }
    }
    #[cfg(not(windows))]
    {
        false
    }
}

/// True when a default capture (mic) endpoint exists for either the
/// `eMultimedia` or `eCommunications` role (headset-only hosts expose only
/// the communications role).
pub fn default_input_available() -> bool {
    #[cfg(windows)]
    {
        default_endpoint_available(wasapi::flow_input())
    }
    #[cfg(not(windows))]
    {
        false
    }
}

/// True when a default render endpoint exists — the §11 loopback source.
pub fn default_render_available() -> bool {
    #[cfg(windows)]
    {
        default_endpoint_available(wasapi::flow_render())
    }
    #[cfg(not(windows))]
    {
        false
    }
}

/// One enumerated endpoint plus its negotiated shared-mode mix format.
///
/// `name` is best-effort: reading `PKEY_Device_FriendlyName` needs the pinned
/// `windows` crate's `Win32_UI_Shell_PropertiesSystem` feature, which this
/// build does not enable — so names stay **empty rather than fabricated**
/// (fail-closed culture). Preflight keys off `device_id` + availability.
#[derive(Debug, Clone, Serialize)]
pub struct EndpointInfo {
    /// `IMMDevice::GetId` string — the stable selector stored in profiles.
    pub device_id: String,
    /// FriendlyName when obtainable; empty otherwise (never invented).
    pub name: String,
    pub channels: u32,
    pub sample_rate: u32,
    /// True when the mix format carries IEEE-float samples.
    pub is_float: bool,
}

/// All active capture endpoints (§10 mic pickers).
pub fn list_input_endpoints() -> Vec<EndpointInfo> {
    #[cfg(windows)]
    {
        list_endpoints_for(wasapi::flow_input())
    }
    #[cfg(not(windows))]
    {
        Vec::new()
    }
}

/// All active render endpoints (§11 loopback sources).
pub fn list_render_endpoints() -> Vec<EndpointInfo> {
    #[cfg(windows)]
    {
        list_endpoints_for(wasapi::flow_render())
    }
    #[cfg(not(windows))]
    {
        Vec::new()
    }
}

#[cfg(windows)]
fn default_endpoint_available(flow: windows::Win32::Media::Audio::EDataFlow) -> bool {
    let com = match wasapi::ComGuard::acquire() {
        Ok(g) => g,
        Err(_) => return false,
    };
    let _ = &com;
    let enumerator = match wasapi::co_create_enumerator() {
        Ok(e) => e,
        Err(_) => return false,
    };
    wasapi::DEFAULT_ROLES
        .iter()
        .any(|role| unsafe { enumerator.GetDefaultAudioEndpoint(flow, *role) }.is_ok())
}

#[cfg(windows)]
fn list_endpoints_for(flow: windows::Win32::Media::Audio::EDataFlow) -> Vec<EndpointInfo> {
    use windows::Win32::Media::Audio::DEVICE_STATE_ACTIVE;

    let com = match wasapi::ComGuard::acquire() {
        Ok(g) => g,
        Err(_) => return Vec::new(),
    };
    let _ = &com;
    let Ok(enumerator) = wasapi::co_create_enumerator() else {
        return Vec::new();
    };
    let Ok(collection) = (unsafe { enumerator.EnumAudioEndpoints(flow, DEVICE_STATE_ACTIVE) })
    else {
        return Vec::new();
    };
    let Ok(count) = (unsafe { collection.GetCount() }) else {
        return Vec::new();
    };

    let mut out = Vec::new();
    for i in 0..count {
        // Endpoints whose Id cannot be read are skipped — an unnamed entry
        // could never be selected anyway.
        let Ok(device) = (unsafe { collection.Item(i) }) else { continue };
        let Ok(id) = (unsafe { device.GetId() }) else { continue };
        // SAFETY: NUL-terminated UTF-16 owned by COM; copied before freeing.
        let device_id = unsafe { id.to_string() }.unwrap_or_default();
        // SAFETY: single release of the COM-allocated id buffer.
        unsafe { wasapi::free_co_task_mem(id.0.cast()) };
        if device_id.is_empty() {
            continue;
        }
        // Mix-format probe through a throwaway client; unknown ⇒ zeros
        // (honest "unprobed", never invented values).
        let (channels, sample_rate, is_float) =
            probe_endpoint_format(&device).unwrap_or((0, 0, false));
        out.push(EndpointInfo {
            device_id,
            name: String::new(),
            channels,
            sample_rate,
            is_float,
        });
    }
    out
}

/// Activate one endpoint's audio client purely to read its mix format.
#[cfg(windows)]
fn probe_endpoint_format(
    device: &windows::Win32::Media::Audio::IMMDevice,
) -> Result<(u32, u32, bool), String> {
    use windows::Win32::Media::Audio::IAudioClient;
    use windows::Win32::System::Com::CLSCTX_ALL;

    let client: IAudioClient = unsafe { device.Activate(CLSCTX_ALL, None) }
        .map_err(|e| format!("WASAPI_ACTIVATE_FAILED:{e}"))?;
    // SAFETY: out-pointer allocated by WASAPI; freed inside wasapi helpers.
    let mix = unsafe { client.GetMixFormat() }
        .map_err(|e| format!("WASAPI_MIX_FORMAT_FAILED:{e}"))?;
    let parsed = unsafe { wasapi::parse_mix_format(mix) };
    // SAFETY: single release of the COM-allocated format buffer.
    unsafe { wasapi::free_co_task_mem(mix.cast()) };
    let probe = parsed?;
    Ok((probe.channels as u32, probe.sample_rate, probe.kind == wasapi::SampleKind::F32))
}

// ─── Port-facing stream constructors (policy lives here, not in the ports) ─

/// §10 microphone client: CAPTURE endpoint, no loopback flag.
#[cfg(windows)]
pub(crate) fn open_microphone_stream(
    device_id: &str,
) -> Result<wasapi::StreamHandle, String> {
    wasapi::open(device_id, wasapi::flow_input(), false, "wasapi-mic")
}

/// §11 system-audio client: RENDER endpoint + `AUDCLNT_STREAMFLAGS_LOOPBACK`.
#[cfg(windows)]
pub(crate) fn open_loopback_stream(
    device_id: &str,
) -> Result<wasapi::StreamHandle, String> {
    wasapi::open(device_id, wasapi::flow_render(), true, "wasapi-loopback")
}

// ─── Windows WASAPI core (private, shared by mic + loopback ports) ─────────

#[cfg(windows)]
pub(crate) mod wasapi {
    //! Shared capture-client engine behind [`crate::audio::microphone::
    //! WasapiMicrophone`] and [`crate::audio::loopback::WasapiLoopback`].
    //! One instance per MKV track — mic and system audio are never mixed
    //! pre-record (Principle E, ban_ke_hoach_v1.md §3).

    use std::collections::VecDeque;
    use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
    use std::sync::{Arc, Mutex};

    use windows::core::{Error as WinError, GUID};
    use windows::Win32::Foundation::{
        CloseHandle, HANDLE, RPC_E_CHANGED_MODE, WAIT_OBJECT_0,
    };
    use windows::Win32::Media::Audio::{
        eCapture, eCommunications, eMultimedia, eRender, IAudioCaptureClient, IAudioClient,
        IMMDevice, IMMDeviceCollection, IMMDeviceEnumerator, AUDCLNT_BUFFERFLAGS_SILENT,
        AUDCLNT_E_DEVICE_INVALIDATED, AUDCLNT_E_RESOURCES_INVALIDATED, AUDCLNT_SHAREMODE_SHARED,
        AUDCLNT_STREAMFLAGS_EVENTCALLBACK, AUDCLNT_STREAMFLAGS_LOOPBACK, DEVICE_STATE_ACTIVE,
        EDataFlow, ERole, MMDeviceEnumerator, WAVEFORMATEX, WAVEFORMATEXTENSIBLE,
    };
    use windows::Win32::System::Com::{
        CoCreateInstance, CoInitializeEx, CoTaskMemFree, CoUninitialize, CLSCTX_ALL,
        COINIT_MULTITHREADED,
    };
    use windows::Win32::System::Threading::{CreateEventW, WaitForSingleObject};

    /// Bounded block queue capacity (≈2.6 s of stereo 48 kHz @ ~20 ms packets)
    /// before the oldest block is dropped.
    pub(crate) const QUEUE_CAP: usize = 128;

    /// Shared-mode buffer: 100 ms — robust against scheduler hiccups while
    /// staying far inside the queue's latency budget.
    const HNS_BUFFER_100MS: i64 = 1_000_000;

    /// Worker stop-check heartbeat when no packet arrives (no busy polling).
    const WAIT_HEARTBEAT_MS: u32 = 100;

    /// Consecutive transient faults tolerated before the stream gives up —
    /// bounds the retry rate instead of spinning forever on a broken device.
    const MAX_CONSECUTIVE_FAULTS: u32 = 100;

    /// Roles tried in order when resolving "the default device" (§15).
    pub(super) const DEFAULT_ROLES: [ERole; 2] = [eMultimedia, eCommunications];

    /// `KSDATAFORMAT_SUBTYPE_IEEE_FLOAT` — the SDK constant lives behind the
    /// (unenabled) `Win32_Media_Multimedia` feature, so the well-known GUID
    /// value is transcribed verbatim rather than adding a dependency.
    pub(super) const SUBTYPE_IEEE_FLOAT: GUID =
        GUID::from_u128(0x00000003_0000_0010_8000_00aa00389b71);

    pub(super) fn flow_input() -> EDataFlow {
        eCapture
    }

    pub(super) fn flow_render() -> EDataFlow {
        eRender
    }

    /// # Safety
    /// `ptr` must originate from a COM allocator out-param (`GetId`,
    /// `GetMixFormat`) and must not be freed twice.
    pub(crate) unsafe fn free_co_task_mem(ptr: *mut std::ffi::c_void) {
        unsafe { CoTaskMemFree(Some(ptr)) };
    }

    // ── COM scoping ────────────────────────────────────────────────────────

    /// Initializes COM on the current thread (MTA, consistent everywhere in
    /// this crate) and balances it on drop — but only when *this* scope
    /// actually initialized it. A pre-existing apartment with another
    /// concurrency model (`RPC_E_CHANGED_MODE`) is usable as-is and must not
    /// be uninitialized underneath its owner.
    pub(crate) struct ComGuard {
        owns_init: bool,
    }

    impl ComGuard {
        pub(crate) fn acquire() -> Result<Self, String> {
            let hr = unsafe { CoInitializeEx(None, COINIT_MULTITHREADED) };
            if hr.is_ok() {
                Ok(Self { owns_init: true })
            } else if hr == RPC_E_CHANGED_MODE {
                Ok(Self { owns_init: false })
            } else {
                Err(format!("WASAPI_COM_INIT_FAILED:{hr:?}"))
            }
        }
    }

    impl Drop for ComGuard {
        fn drop(&mut self) {
            if self.owns_init {
                unsafe { CoUninitialize() };
            }
        }
    }

    pub(super) fn co_create_enumerator() -> windows::core::Result<IMMDeviceEnumerator> {
        unsafe { CoCreateInstance(&MMDeviceEnumerator, None, CLSCTX_ALL) }
    }

    // ── Mix-format classification (pure, unit-tested) ──────────────────────

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub(crate) enum SampleKind {
        F32,
        I16,
        I32,
    }

    impl SampleKind {
        pub(crate) fn byte_width(self) -> usize {
            match self {
                Self::F32 | Self::I32 => 4,
                Self::I16 => 2,
            }
        }
    }

    /// Negotiated mix-format summary carried into the worker thread.
    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub(crate) struct FormatProbe {
        pub kind: SampleKind,
        pub channels: u16,
        pub sample_rate: u32,
    }

    impl FormatProbe {
        pub(crate) fn frame_bytes(&self) -> usize {
            self.kind.byte_width() * self.channels as usize
        }
    }

    /// Tail size of `WAVEFORMATEXTENSIBLE` beyond its `WAVEFORMATEX` head
    /// (Samples.u16 + ChannelMask.u32 + SubFormat.GUID = 22 bytes); `cbSize`
    /// must reach it before the SubFormat GUID may be read.
    const EXTENSIBLE_EXTRA_BYTES: usize = {
        std::mem::size_of::<WAVEFORMATEXTENSIBLE>() - std::mem::size_of::<WAVEFORMATEX>()
    };

    /// Pure classifier over `WAVEFORMATEX` (+ optional EXTENSIBLE SubFormat)
    /// fields — fail-closed on anything the recorder cannot decode exactly.
    pub(crate) fn probe_from_tags(
        format_tag: u16,
        cb_size: u16,
        bits_per_sample: u16,
        channels: u16,
        sample_rate: u32,
        subformat: Option<GUID>,
    ) -> Result<FormatProbe, String> {
        const WAVE_FORMAT_PCM_TAG: u16 = 0x0001;
        const WAVE_FORMAT_IEEE_FLOAT_TAG: u16 = 0x0003;
        const WAVE_FORMAT_EXTENSIBLE_TAG: u16 = 0xFFFE;

        if channels == 0 {
            return Err("WASAPI_MIX_FORMAT_UNSUPPORTED:channels=0".into());
        }
        if sample_rate == 0 {
            return Err("WASAPI_MIX_FORMAT_UNSUPPORTED:sample_rate=0".into());
        }
        let subtype_pcm = windows::Win32::Media::KernelStreaming::KSDATAFORMAT_SUBTYPE_PCM;
        let kind = match (format_tag, subformat) {
            (WAVE_FORMAT_IEEE_FLOAT_TAG, _) if bits_per_sample == 32 => SampleKind::F32,
            (WAVE_FORMAT_PCM_TAG, _) if bits_per_sample == 16 => SampleKind::I16,
            (WAVE_FORMAT_PCM_TAG, _) if bits_per_sample == 32 => SampleKind::I32,
            (WAVE_FORMAT_EXTENSIBLE_TAG, Some(sub))
                if cb_size as usize >= EXTENSIBLE_EXTRA_BYTES =>
            {
                if sub == SUBTYPE_IEEE_FLOAT && bits_per_sample == 32 {
                    SampleKind::F32
                } else if sub == subtype_pcm && bits_per_sample == 16 {
                    SampleKind::I16
                } else if sub == subtype_pcm && bits_per_sample == 32 {
                    SampleKind::I32
                } else {
                    return Err(format!(
                        "WASAPI_MIX_FORMAT_UNSUPPORTED:extensible sub={sub:?} bits={bits_per_sample}"
                    ));
                }
            }
            _ => {
                return Err(format!(
                    "WASAPI_MIX_FORMAT_UNSUPPORTED:tag={format_tag:#06x} bits={bits_per_sample}"
                ));
            }
        };
        Ok(FormatProbe { kind, channels, sample_rate })
    }

    /// # Safety
    /// `fmt` must point to a valid `WAVEFORMATEX` allocation (as returned by
    /// `IAudioClient::GetMixFormat`). When EXTENSIBLE, the trailing packed
    /// fields are read unaligned.
    ///
    /// # Panics
    /// A null pointer is a WASAPI contract violation and fails loudly during
    /// development instead of producing an empty track.
    pub(crate) unsafe fn parse_mix_format(fmt: *const WAVEFORMATEX) -> Result<FormatProbe, String> {
        assert!(!fmt.is_null(), "GetMixFormat returned null");
        let base = &*fmt;
        let subformat = if base.wFormatTag == 0xFFFE
            && base.cbSize as usize >= EXTENSIBLE_EXTRA_BYTES
        {
            let ext = fmt as *const WAVEFORMATEXTENSIBLE;
            // SAFETY: packed repr — read unaligned; pointer in-bounds per cbSize.
            Some(std::ptr::addr_of!((*ext).SubFormat).read_unaligned())
        } else {
            None
        };
        probe_from_tags(
            base.wFormatTag,
            base.cbSize,
            base.wBitsPerSample,
            base.nChannels,
            base.nSamplesPerSec,
            subformat,
        )
    }

    // ── Packet conversion (pure, unit-tested) ──────────────────────────────

    /// Convert one capture packet's raw bytes into interleaved f32 samples.
    ///
    /// `silent` (`AUDCLNT_BUFFERFLAGS_SILENT`) yields an exact-length zero
    /// buffer so downstream PTS/drift accounting keeps counting frames even
    /// through silence (§12: never mass-drop audio frames).
    pub(crate) fn pcm_packet_to_f32(
        bytes: &[u8],
        frames: usize,
        probe: FormatProbe,
        silent: bool,
    ) -> Result<Vec<f32>, String> {
        let want = frames * probe.channels as usize;
        if silent {
            return Ok(vec![0.0; want]);
        }
        let need = want * probe.kind.byte_width();
        if bytes.len() < need {
            return Err(format!(
                "WASAPI_PACKET_TRUNCATED:need={need} got={}",
                bytes.len()
            ));
        }
        let data = &bytes[..need];
        Ok(match probe.kind {
            SampleKind::F32 => data
                .chunks_exact(4)
                .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
                .collect(),
            SampleKind::I16 => data
                .chunks_exact(2)
                .map(|c| i16::from_le_bytes([c[0], c[1]]) as f32 / 32768.0)
                .collect(),
            SampleKind::I32 => data
                .chunks_exact(4)
                .map(|c| i32::from_le_bytes([c[0], c[1], c[2], c[3]]) as f32 / 2_147_483_648.0)
                .collect(),
        })
    }

    // ── Worker faults ──────────────────────────────────────────────────────

    /// Classification of a worker-loop failure (see module docs for the
    /// invalidation contract).
    pub(crate) enum Fault {
        /// Device gone (USB unplug, endpoint switch) — stream ends, port
        /// reports `is_available=false`.
        Invalidated(String),
        /// Persistent condition that would repeat forever (undecodable
        /// format, truncated packets) — stream stops fail-closed.
        Fatal(String),
        /// One-off WASAPI hiccup — recorded, capture continues.
        Transient(String),
    }

    fn fault_from_error(err: WinError) -> Fault {
        if err.code() == AUDCLNT_E_DEVICE_INVALIDATED {
            Fault::Invalidated("AUDIO_DEVICE_INVALIDATED:0x88890004".into())
        } else if err.code() == AUDCLNT_E_RESOURCES_INVALIDATED {
            Fault::Invalidated("AUDIO_DEVICE_RESOURCES_INVALIDATED:0x88890026".into())
        } else {
            Fault::Transient(format!("WASAPI_ERROR:{err}"))
        }
    }

    // ── Shared worker state ────────────────────────────────────────────────

    /// State shared between the port object (pipeline thread) and the WASAPI
    /// worker thread.
    pub(crate) struct SharedState {
        queue: Mutex<VecDeque<crate::audio::PcmBlock>>,
        muted: AtomicBool,
        stop: AtomicBool,
        available: AtomicBool,
        dropped_overflow: AtomicU64,
        last_error: Mutex<Option<String>>,
    }

    impl SharedState {
        fn new() -> Self {
            Self {
                queue: Mutex::new(VecDeque::new()),
                muted: AtomicBool::new(false),
                stop: AtomicBool::new(false),
                available: AtomicBool::new(true),
                dropped_overflow: AtomicU64::new(0),
                last_error: Mutex::new(None),
            }
        }

        /// Bounded push: on overflow drops the OLDEST block (freshest audio
        /// stays nearest real time) and bumps the honest drop counter — the
        /// pipeline folds it into underruns telemetry rather than hiding it
        /// (§17: no fake recording metrics).
        fn push_block(&self, block: crate::audio::PcmBlock) {
            if let Ok(mut q) = self.queue.lock() {
                if q.len() >= QUEUE_CAP {
                    q.pop_front();
                    self.dropped_overflow.fetch_add(1, Ordering::Relaxed);
                }
                q.push_back(block);
            }
        }

        pub(crate) fn set_error(&self, err: String) {
            if let Ok(mut slot) = self.last_error.lock() {
                *slot = Some(err);
            }
        }
    }

    // ── Event-driven capture loop (§10: no busy polling) ───────────────────

    /// Waits on the client's event (the 100 ms timeout doubles as the
    /// stop-check heartbeat); every signaled wake drains ALL queued packets
    /// before waiting again. Runs on its own MTA thread.
    fn worker_main(
        capture: IAudioCaptureClient,
        event: HANDLE,
        shared: Arc<SharedState>,
        probe: FormatProbe,
    ) {
        let _com = match ComGuard::acquire() {
            Ok(g) => g,
            Err(e) => {
                shared.set_error(e);
                shared.available.store(false, Ordering::Release);
                return;
            }
        };

        let mut consecutive_faults: u32 = 0;
        loop {
            if shared.stop.load(Ordering::Acquire) {
                break;
            }
            let wait = unsafe { WaitForSingleObject(event, WAIT_HEARTBEAT_MS) };
            if wait != WAIT_OBJECT_0 {
                continue; // heartbeat timeout → re-check stop flag
            }
            match drain_packets(&capture, &shared, probe) {
                Ok(()) => consecutive_faults = 0,
                Err(Fault::Invalidated(msg)) | Err(Fault::Fatal(msg)) => {
                    shared.set_error(msg);
                    shared.available.store(false, Ordering::Release);
                    break;
                }
                Err(Fault::Transient(msg)) => {
                    shared.set_error(msg);
                    consecutive_faults += 1;
                    if consecutive_faults >= MAX_CONSECUTIVE_FAULTS {
                        shared.set_error(format!(
                            "WASAPI_FAULT_LIMIT_REACHED:{consecutive_faults}"
                        ));
                        shared.available.store(false, Ordering::Release);
                        break;
                    }
                }
            }
        }
    }

    /// Drain every queued packet (GetNextPacketSize → GetBuffer → convert →
    /// ReleaseBuffer exactly once each), then return so the loop can honor a
    /// pending stop.
    fn drain_packets(
        capture: &IAudioCaptureClient,
        shared: &SharedState,
        probe: FormatProbe,
    ) -> Result<(), Fault> {
        loop {
            let packets =
                unsafe { capture.GetNextPacketSize() }.map_err(fault_from_error)?;
            if packets == 0 {
                return Ok(());
            }
            let mut data: *mut u8 = std::ptr::null_mut();
            let mut frames: u32 = 0;
            let mut flags: u32 = 0;
            // Packet QPC stamps come from our own clock authority (§12), not
            // the device position counters.
            unsafe { capture.GetBuffer(&mut data, &mut frames, &mut flags, None, None) }
                .map_err(fault_from_error)?;

            let converted = (|| {
                if data.is_null() || frames == 0 {
                    return Ok(Vec::new());
                }
                // SAFETY: WASAPI guarantees frames * frame_bytes readable
                // bytes until ReleaseBuffer.
                let bytes = unsafe {
                    std::slice::from_raw_parts(data, frames as usize * probe.frame_bytes())
                };
                let silent = (flags & AUDCLNT_BUFFERFLAGS_SILENT.0 as u32) != 0;
                pcm_packet_to_f32(bytes, frames as usize, probe, silent)
            })();

            unsafe { capture.ReleaseBuffer(frames) }.map_err(fault_from_error)?;

            match converted {
                Ok(mut samples) => {
                    if !samples.is_empty() {
                        // Recorder-tap mute (§11): zero in place so PTS
                        // continuity survives mute toggles mid-take.
                        if shared.muted.load(Ordering::Acquire) {
                            samples.iter_mut().for_each(|v| *v = 0.0);
                        }
                        shared.push_block(crate::audio::PcmBlock {
                            samples,
                            channels: probe.channels as u32,
                            sample_rate: probe.sample_rate,
                            qpc: crate::audio::clock::qpc_now(),
                        });
                    }
                }
                // Undecodable packet would repeat forever → fail closed now.
                Err(message) => return Err(Fault::Fatal(message)),
            }
        }
    }

    // ── Port-facing handle ─────────────────────────────────────────────────

    /// Owner-side stream: control interfaces, shared state and the worker
    /// join handle. Created by [`open`]; lifecycle prepare → start → poll /
    /// stop → Drop.
    ///
    /// # Send
    /// Required by `AudioCapturePort: Send`. Sound because WASAPI objects are
    /// agile (free-threaded marshaler), a kernel `HANDLE` is process-global,
    /// and `SharedState` is atomics + mutexes only. The worker performs its
    /// own `CoInitializeEx(MULTITHREADED)` before touching COM.
    pub(crate) struct StreamHandle {
        audio_client: IAudioClient,
        capture_client: IAudioCaptureClient,
        event: HANDLE,
        shared: Arc<SharedState>,
        info: crate::audio::AudioDeviceInfo,
        probe: FormatProbe,
        worker_name: &'static str,
        worker: Option<std::thread::JoinHandle<()>>,
        started: bool,
    }

    unsafe impl Send for StreamHandle {}

    /// Captures moved into the worker thread. The closure itself must be
    /// `Send`, so the raw-pointer-bearing members travel inside this
    /// explicitly-`Send` carrier (same justification as [`StreamHandle`]).
    struct WorkerArgs {
        capture: IAudioCaptureClient,
        event: HANDLE,
        shared: Arc<SharedState>,
        probe: FormatProbe,
    }

    unsafe impl Send for WorkerArgs {}

    /// Thread entry point — keeps field destructuring out of the spawned
    /// closure (edition-2021 closures capture struct fields individually,
    /// which would re-introduce `!Send` raw pointers).
    fn run_worker(args: WorkerArgs) {
        worker_main(args.capture, args.event, args.shared, args.probe)
    }

    /// Resolve an endpoint: empty id → default (roles tried in
    /// [`DEFAULT_ROLES`] order); otherwise exact `IMMDevice::GetId` match over
    /// ACTIVE endpoints. Unknown ids fail closed — never silently substituted
    /// with the default device.
    fn resolve_endpoint(
        enumerator: &IMMDeviceEnumerator,
        device_id: &str,
        flow: EDataFlow,
    ) -> Result<IMMDevice, String> {
        if device_id.is_empty() {
            for role in DEFAULT_ROLES {
                if let Ok(device) = unsafe { enumerator.GetDefaultAudioEndpoint(flow, role) } {
                    return Ok(device);
                }
            }
            return Err("WASAPI_DEFAULT_DEVICE_NOT_FOUND".into());
        }
        let collection: IMMDeviceCollection = unsafe {
            enumerator.EnumAudioEndpoints(flow, DEVICE_STATE_ACTIVE)
        }
        .map_err(|e| format!("WASAPI_ENUM_ENDPOINTS_FAILED:{e}"))?;
        let count = unsafe { collection.GetCount() }
            .map_err(|e| format!("WASAPI_ENDPOINT_COUNT_FAILED:{e}"))?;
        for i in 0..count {
            let device = unsafe { collection.Item(i) }
                .map_err(|e| format!("WASAPI_ENDPOINT_ITEM_FAILED:{e}"))?;
            if device_id_of(&device)?.as_str() == device_id {
                return Ok(device);
            }
        }
        Err(format!("WASAPI_DEVICE_NOT_FOUND:{device_id}"))
    }

    fn device_id_of(device: &IMMDevice) -> Result<String, String> {
        let id = unsafe { device.GetId() }.map_err(|e| format!("WASAPI_GET_ID_FAILED:{e}"))?;
        // SAFETY: NUL-terminated UTF-16 owned by COM; copied before freeing.
        let text = unsafe { id.to_string() }.unwrap_or_default();
        unsafe { free_co_task_mem(id.0.cast()) };
        Ok(text)
    }

    /// Open (but do not start) one event-driven shared-mode capture client.
    ///
    /// `loopback=true` puts `AUDCLNT_STREAMFLAGS_LOOPBACK` on a RENDER
    /// endpoint (§11); everything afterwards is identical to a normal capture
    /// client. Loopback data appears only while something renders — silence
    /// periods yield no packets, which is expected; PTS continuity comes from
    /// the QPC stamp on each delivered block (§12).
    pub(crate) fn open(
        device_id: &str,
        flow: EDataFlow,
        loopback: bool,
        worker_name: &'static str,
    ) -> Result<StreamHandle, String> {
        let com = ComGuard::acquire()?;
        let _ = &com;

        let enumerator =
            co_create_enumerator().map_err(|e| format!("WASAPI_ENUMERATOR_FAILED:{e}"))?;
        let device = resolve_endpoint(&enumerator, device_id, flow)?;
        let resolved_id = device_id_of(&device)?;

        let audio_client: IAudioClient = unsafe { device.Activate(CLSCTX_ALL, None) }
            .map_err(|e| format!("WASAPI_ACTIVATE_FAILED:{e}"))?;

        // SAFETY: out-pointer allocated by WASAPI; freed below via CoTaskMemFree.
        let mix: *mut WAVEFORMATEX = unsafe { audio_client.GetMixFormat() }
            .map_err(|e| format!("WASAPI_MIX_FORMAT_FAILED:{e}"))?;
        let probed = unsafe { parse_mix_format(mix) };

        let mut flags = AUDCLNT_STREAMFLAGS_EVENTCALLBACK;
        if loopback {
            flags |= AUDCLNT_STREAMFLAGS_LOOPBACK;
        }
        let init = unsafe {
            audio_client.Initialize(AUDCLNT_SHAREMODE_SHARED, flags, HNS_BUFFER_100MS, 0, mix, None)
        };
        unsafe { free_co_task_mem(mix.cast()) };
        init.map_err(|e| format!("WASAPI_INITIALIZE_FAILED:{e}"))?;

        let probe = probed?;

        let event = unsafe { CreateEventW(None, false, false, None) }
            .map_err(|e| format!("WASAPI_EVENT_CREATE_FAILED:{e}"))?;
        if let Err(e) = unsafe { audio_client.SetEventHandle(event) } {
            unsafe { let _ = CloseHandle(event); }
            return Err(format!("WASAPI_SET_EVENT_FAILED:{e}"));
        }
        let capture_client: IAudioCaptureClient =
            match unsafe { audio_client.GetService() } {
                Ok(c) => c,
                Err(e) => {
                    unsafe { let _ = CloseHandle(event); }
                    return Err(format!("WASAPI_CAPTURE_SERVICE_FAILED:{e}"));
                }
            };

        Ok(StreamHandle {
            audio_client,
            capture_client,
            event,
            shared: Arc::new(SharedState::new()),
            info: crate::audio::AudioDeviceInfo {
                available: true,
                // FriendlyName needs the un-enabled PropertiesSystem feature —
                // left empty, never fabricated.
                endpoint_name: String::new(),
                device_id: resolved_id,
                channels: probe.channels as u32,
                sample_rate: probe.sample_rate,
                is_float: probe.kind == SampleKind::F32,
            },
            probe,
            worker_name,
            worker: None,
            started: false,
        })
    }

    impl StreamHandle {
        pub(crate) fn start(&mut self) -> Result<(), String> {
            if self.started {
                return Err("WASAPI_ALREADY_STARTED".into());
            }
            self.shared.stop.store(false, Ordering::Release);
            unsafe { self.audio_client.Start() }
                .map_err(|e| format!("WASAPI_START_FAILED:{e}"))?;
            let capture = self.capture_client.clone();
            let event = self.event;
            let shared = Arc::clone(&self.shared);
            let probe = self.probe;
            let args = WorkerArgs { capture, event, shared, probe };
            match std::thread::Builder::new()
                .name(self.worker_name.to_string())
                // Whole-struct move (no field-level destructuring in the
                // closure) so the `unsafe impl Send` on WorkerArgs applies.
                .spawn(move || run_worker(args))
            {
                Ok(handle) => {
                    self.worker = Some(handle);
                    self.started = true;
                    Ok(())
                }
                Err(e) => {
                    let _ = unsafe { self.audio_client.Stop() };
                    Err(format!("WASAPI_THREAD_SPAWN_FAILED:{e}"))
                }
            }
        }

        /// Cooperative shutdown: stop flag first, client Stop, then join the
        /// worker (exits within one ≤100 ms heartbeat). Idempotent like the
        /// mock port so defensive shutdown paths stay simple.
        pub(crate) fn stop(&mut self) -> Result<(), String> {
            self.shared.stop.store(true, Ordering::Release);
            let stopped = unsafe { self.audio_client.Stop() };
            if let Some(worker) = self.worker.take() {
                if worker.join().is_err() {
                    self.shared.set_error("WASAPI_WORKER_PANICKED".into());
                }
            }
            self.started = false;
            stopped.map_err(|e| format!("WASAPI_STOP_FAILED:{e}"))
        }

        /// Pop the OLDEST buffered block — exactly one per call, never waits.
        pub(crate) fn poll(&mut self) -> Option<crate::audio::PcmBlock> {
            self.shared.queue.lock().ok()?.pop_front()
        }

        /// Recorder-tap mute (§11): worker zeroes samples in place, keeps
        /// frame counts, so drift accounting stays truthful.
        pub(crate) fn set_muted(&mut self, muted: bool) {
            self.shared.muted.store(muted, Ordering::Release);
        }

        pub(crate) fn is_available(&self) -> bool {
            self.shared.available.load(Ordering::Acquire)
        }

        /// Blocks dropped by queue overflow — folded into underruns telemetry
        /// by the caller (§17 honesty rule).
        pub(crate) fn overflow_dropped(&self) -> u64 {
            self.shared.dropped_overflow.load(Ordering::Relaxed)
        }

        pub(crate) fn last_error(&self) -> Option<String> {
            self.shared.last_error.lock().ok()?.clone()
        }

        pub(crate) fn info(&self) -> &crate::audio::AudioDeviceInfo {
            &self.info
        }

        #[allow(dead_code)] // exposed for diagnostics; consumed via info()
        pub(crate) fn probe(&self) -> FormatProbe {
            self.probe
        }
    }

    impl Drop for StreamHandle {
        fn drop(&mut self) {
            self.shared.stop.store(true, Ordering::Release);
            // Best-effort Stop: harmless error when the client never ran.
            let _ = unsafe { self.audio_client.Stop() };
            if let Some(worker) = self.worker.take() {
                let _ = worker.join();
            }
            unsafe { let _ = CloseHandle(self.event); }
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        fn float_probe(channels: u16, rate: u32) -> FormatProbe {
            FormatProbe { kind: SampleKind::F32, channels, sample_rate: rate }
        }

        #[test]
        fn extensible_float_is_recognized() {
            let p = probe_from_tags(0xFFFE, 22, 32, 2, 48_000, Some(SUBTYPE_IEEE_FLOAT))
                .expect("standard desktop mix format");
            assert_eq!(p, float_probe(2, 48_000));
            assert_eq!(p.frame_bytes(), 8);
        }

        #[test]
        fn plain_pcm16_and_float_tags_are_recognized() {
            assert_eq!(
                probe_from_tags(0x0003, 0, 32, 2, 48_000, None).unwrap(),
                float_probe(2, 48_000)
            );
            assert_eq!(
                probe_from_tags(0x0001, 0, 16, 1, 44_100, None).unwrap().kind,
                SampleKind::I16
            );
            assert_eq!(
                probe_from_tags(0x0001, 0, 32, 2, 48_000, None).unwrap().kind,
                SampleKind::I32
            );
        }

        #[test]
        fn unsupported_formats_fail_closed() {
            // 24-bit int PCM has no decoder here — explicit error, never a guess.
            assert!(probe_from_tags(0x0001, 0, 24, 2, 48_000, None).is_err());
            assert!(probe_from_tags(0xFFFE, 22, 24, 2, 48_000, Some(SUBTYPE_IEEE_FLOAT)).is_err());
            assert!(probe_from_tags(0x0003, 0, 64, 2, 48_000, None).is_err());
            assert!(probe_from_tags(0x0001, 0, 16, 0, 48_000, None).is_err());
            assert!(probe_from_tags(0x0001, 0, 16, 2, 0, None).is_err());
        }

        #[test]
        fn f32_packets_round_trip_little_endian() {
            let bytes: Vec<u8> = [0.25f32, -0.5].iter().flat_map(|v| v.to_le_bytes()).collect();
            let got = pcm_packet_to_f32(&bytes, 1, float_probe(2, 48_000), false).unwrap();
            assert_eq!(got, vec![0.25, -0.5]);
        }

        #[test]
        fn i16_packets_scale_into_unit_range() {
            let bytes: Vec<u8> =
                [16384i16, -16384].iter().flat_map(|v| v.to_le_bytes()).collect();
            let got = pcm_packet_to_f32(
                &bytes,
                1,
                FormatProbe { kind: SampleKind::I16, channels: 2, sample_rate: 48_000 },
                false,
            )
            .unwrap();
            assert_eq!(got, vec![0.5, -0.5]);
        }

        #[test]
        fn silent_flag_zeroes_but_preserves_frame_count() {
            let got = pcm_packet_to_f32(&[], 960, float_probe(2, 48_000), true).unwrap();
            assert_eq!(got.len(), 1920);
            assert!(got.iter().all(|&v| v == 0.0));
        }

        #[test]
        fn truncated_packets_are_rejected() {
            let bytes = [0u8; 6]; // half of one stereo f32 frame
            assert!(pcm_packet_to_f32(&bytes, 1, float_probe(2, 48_000), false).is_err());
        }

        #[test]
        fn probes_degrade_gracefully_without_hardware() {
            // Hardware-dependent smoke: never panics on headless CI boxes.
            let wasapi = super::super::wasapi_available();
            let inputs = super::super::list_input_endpoints();
            if !wasapi {
                assert!(inputs.is_empty(), "no endpoints can be listed without WASAPI");
            }
            for ep in inputs {
                assert!(!ep.device_id.is_empty());
                assert!(ep.name.is_empty(), "names are never fabricated");
            }
        }
    }
}
