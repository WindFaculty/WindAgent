//! Direct Windows Graphics Capture — production video source (ban_ke_hoach_v1.md §7).
//!
//! ```text
//! GraphicsCaptureItem (monitor | window, via IGraphicsCaptureItemInterop)
//!         ↓
//! Direct3D11CaptureFramePool::CreateFreeThreaded   (no DispatcherQueue)
//!         ↓ FrameArrived (WinRT threadpool thread)
//! IDirect3DSurface ──IDirect3DDxgiInterfaceAccess──► ID3D11Texture2D
//!         ↓ bounded queue (cap 8, overflow drops OLDEST)
//! CapturedFrame { texture, width, height, format, qpc, frame_number }
//! ```
//!
//! Zero-copy discipline (§3-A): the hot path hands the encoder the **GPU
//! texture itself** — pixels are never read back to CPU here. CPU readback
//! belongs exclusively to the preview tap (§13).
//!
//! Fail-closed (§3-B): when WGC cannot run, [`crate::capture::WGC_UNAVAILABLE`]
//! surfaces through `prepare()` and recording is blocked. There is no DDup /
//! GDI / ffmpeg fallback backend — FFmpeg stays a dev-only comparison tool.
//!
//! Source loss (§25): a window closing or a display disconnecting fires the
//! item `Closed` event → `CAPTURE_SOURCE_LOST` is recorded, `is_source_lost()`
//! flips true and `poll_frame()` drains down to `None`; the service finalizes
//! the take and stops.
//!
//! Cross-thread notes:
//! * `ID3D11Texture2D` bindings are `!Send`, but D3D11 resources are
//!   free-threaded COM objects. [`SendTexture`] crosses the handler→consumer
//!   boundary under a strict single-producer (WinRT `FrameArrived`) /
//!   single-consumer (`poll_frame` on the encode thread) discipline.
//! * The frame pool, session and capture item live in [`AgileCell`]: they are
//!   agile/free-threaded WinRT objects touched by the owner thread and the
//!   runtime's delegate thread; the Rust bindings mark every COM wrapper
//!   `!Send` uniformly, so an explicit (documented) `Send` impl is required.
//!
//! Feature pins: `Win32_System_WinRT*` is NOT enabled in Cargo.toml (frozen),
//! so `IGraphicsCaptureItemInterop` / `IDirect3DDxgiInterfaceAccess` and the
//! `CreateDirect3D11DeviceFromDXGIDevice` bridge are declared **locally**,
//! transcribing the ABI from the Windows SDK metadata (the same IIDs the
//! `windows` crate itself generates for these interfaces — verified stable
//! across windows 0.57/0.58/0.61). Everything else uses already-enabled
//! features only.

#![allow(clippy::too_many_arguments)]

use serde::Serialize;

#[cfg(not(windows))]
use crate::CaptureSource;
use crate::capture::SurfaceFormat;

// ─── Fail-closed error codes ─────────────────────────────────────────────────

/// §25: capture target vanished (window closed / display disconnected).
pub const CAPTURE_SOURCE_LOST: &str =
    "CAPTURE_SOURCE_LOST: capture target closed or display disconnected";

// ─── Queue sizing ────────────────────────────────────────────────────────────

/// Max queued textures between the `FrameArrived` producer and `poll_frame`.
/// Overflow drops the OLDEST queued frame (freshness-first) and increments
/// [`WgcCapture::dropped_frames`].
const FRAME_QUEUE_CAP: usize = 8;

/// Pool buffer count. Small on purpose: fewer pool slots ⇒ backpressure
/// reaches WGC sooner, keeping end-to-end latency tight; the queue above
/// absorbs consumer jitter.
const FRAME_POOL_BUFFERS: i32 = 3;

// ─── Frontend source-picker types (serialized to Tauri later) ────────────────

/// One enumerable display target for the frontend source picker.
#[derive(Debug, Clone, Serialize)]
pub struct MonitorInfo {
    /// Stable device path (EDID/DeviceID string) — the `CaptureSource.id`.
    pub id: String,
    pub name: String,
    pub width: u32,
    pub height: u32,
    pub is_primary: bool,
}

/// One enumerable window target for the frontend source picker.
#[derive(Debug, Clone, Serialize)]
pub struct WindowInfo {
    /// `HWND as isize.to_string()` — fed back verbatim as `CaptureSource.id`.
    pub hwnd_token: String,
    pub title: String,
    pub process_name: String,
}

// ─── Pure helpers (unit-tested on every host, Windows or not) ────────────────

/// Map a raw `DXGI_FORMAT` code onto the spine's [`SurfaceFormat`] (§7 HDR/SDR).
///
/// `87` = `DXGI_FORMAT_B8G8R8A8_UNORM` (SDR desktop composition),
/// `10` = `DXGI_FORMAT_R16G16B16A16_FLOAT` (HDR desktop).
pub(crate) fn map_surface_format(dxgi_code: u32) -> Option<SurfaceFormat> {
    match dxgi_code {
        87 => Some(SurfaceFormat::Bgra8),
        10 => Some(SurfaceFormat::Rgba16Float),
        _ => None,
    }
}

/// Raw `DXGI_FORMAT` code backing each spine format (pool creation input).
pub(crate) fn surface_format_dxgi_code(format: SurfaceFormat) -> u32 {
    match format {
        SurfaceFormat::Bgra8 => 87,
        SurfaceFormat::Rgba16Float => 10,
    }
}

/// Bounded MPSC frame queue with drop-oldest overflow policy.
///
/// Generic so the policy itself is unit-tested without any graphics hardware.
/// Lock poisoning is treated as data loss: the incoming frame counts as
/// dropped — telemetry never lies about lost frames.
#[derive(Debug)]
struct FrameQueue<T> {
    inner: std::sync::Mutex<std::collections::VecDeque<T>>,
    dropped: std::sync::atomic::AtomicU64,
    cap: usize,
}

impl<T> FrameQueue<T> {
    fn new(cap: usize) -> Self {
        Self {
            inner: std::sync::Mutex::new(std::collections::VecDeque::new()),
            dropped: std::sync::atomic::AtomicU64::new(0),
            cap,
        }
    }

    /// Push newest; when at capacity, evict the OLDEST and count the loss.
    fn push(&self, value: T) {
        match self.inner.lock() {
            Ok(mut q) => {
                if q.len() >= self.cap {
                    let _ = q.pop_front();
                    self.dropped
                        .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                }
                q.push_back(value);
            }
            Err(_) => {
                // Poisoned by a panicked consumer — drop honestly, keep going.
                self.dropped
                    .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
            }
        }
    }

    fn pop(&self) -> Option<T> {
        self.inner.lock().ok().and_then(|mut q| q.pop_front())
    }

    fn len(&self) -> usize {
        self.inner.lock().map(|q| q.len()).unwrap_or(0)
    }

    fn clear(&self) {
        if let Ok(mut q) = self.inner.lock() {
            q.clear();
        }
    }

    fn dropped(&self) -> u64 {
        self.dropped.load(std::sync::atomic::Ordering::Relaxed)
    }
}

// ─── OS support gate ─────────────────────────────────────────────────────────

/// True only when the OS exposes the Windows Graphics Capture contract
/// (Windows 10 1803+). Probed via `GraphicsCaptureSession::IsSupported()` —
/// activation-level truth, not a version guess.
#[cfg(windows)]
pub fn os_supports_wgc() -> bool {
    use windows::Graphics::Capture::GraphicsCaptureSession;
    GraphicsCaptureSession::IsSupported().unwrap_or(false)
}

/// Non-Windows hosts never support WGC — fail closed.
#[cfg(not(windows))]
pub fn os_supports_wgc() -> bool {
    false
}

// ═════════════════════════════════ Windows implementation ═══════════════════

#[cfg(windows)]
mod imp {
    use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
    use std::sync::{Arc, Mutex, OnceLock};

    use windows::core::{factory, IInspectable, Interface, PCWSTR, PWSTR};
    use windows::Foundation::{EventRegistrationToken, TypedEventHandler};
    use windows::Graphics::Capture::{
        Direct3D11CaptureFramePool, GraphicsCaptureItem, GraphicsCaptureSession,
    };
    use windows::Graphics::DirectX::Direct3D11::IDirect3DDevice;
    use windows::Graphics::DirectX::DirectXPixelFormat;
    use windows::Win32::Foundation::{CloseHandle, HMODULE, HWND, LPARAM};
    use windows::Win32::Graphics::Direct3D::{
        D3D_DRIVER_TYPE_HARDWARE, D3D_DRIVER_TYPE_UNKNOWN, D3D_FEATURE_LEVEL_11_0,
        D3D_FEATURE_LEVEL_11_1,
    };
    use windows::Win32::Graphics::Direct3D11::{
        D3D11CreateDevice, D3D11_CREATE_DEVICE_BGRA_SUPPORT, D3D11_TEXTURE2D_DESC, ID3D11Device,
        ID3D11Texture2D,
    };
    use windows::Win32::Graphics::Dxgi::{
        CreateDXGIFactory1, IDXGIAdapter, IDXGIAdapter1, IDXGIDevice, IDXGIFactory1,
        DXGI_ADAPTER_FLAG_SOFTWARE,
    };
    use windows::Win32::Graphics::Gdi::{
        EnumDisplayDevicesW, EnumDisplayMonitors, GetMonitorInfoW, HDC, HMONITOR, MONITORINFOEXW,
    };
    use windows::Win32::System::Com::{CoInitializeEx, CoUninitialize, COINIT_MULTITHREADED};
    use windows::Win32::System::Threading::{
        OpenProcess, QueryFullProcessImageNameW, PROCESS_QUERY_LIMITED_INFORMATION,
        PROCESS_NAME_WIN32,
    };
    use windows::Win32::UI::WindowsAndMessaging::{
        EnumWindows, GetWindowTextLengthW, GetWindowTextW, GetWindowThreadProcessId, IsWindow,
        IsWindowVisible, MONITORINFOF_PRIMARY,
    };

    use super::{
        map_surface_format, surface_format_dxgi_code, FrameQueue, CAPTURE_SOURCE_LOST,
        FRAME_POOL_BUFFERS, FRAME_QUEUE_CAP,
    };
    use crate::capture::{CapturedFrame, SurfaceFormat, WGC_UNAVAILABLE};
    use crate::CaptureSource;

    // ── Local COM interop declarations (feature-pinned out of the crate) ────

    /// Transcription of `IGraphicsCaptureItemInterop` (windows.graphics.capture.interop.h)
    /// — the crate cannot generate it because `Win32_System_WinRT_Graphics_Capture`
    /// is not an enabled feature. IID taken from the `windows` crate metadata
    /// (identical in 0.57/0.58/0.61, extracted from the Windows SDK winmd).
    #[repr(C)]
    struct IGraphicsCaptureItemInterop_Vtbl {
        query_interface: unsafe extern "system" fn(
            *mut std::ffi::c_void,
            *const windows::core::GUID,
            *mut *mut std::ffi::c_void,
        ) -> windows::core::HRESULT,
        add_ref: unsafe extern "system" fn(*mut std::ffi::c_void) -> u32,
        release: unsafe extern "system" fn(*mut std::ffi::c_void) -> u32,
        create_for_window: unsafe extern "system" fn(
            this: *mut std::ffi::c_void,
            window: HWND,
            riid: *const windows::core::GUID,
            result: *mut *mut std::ffi::c_void,
        ) -> windows::core::HRESULT,
        create_for_monitor: unsafe extern "system" fn(
            this: *mut std::ffi::c_void,
            monitor: HMONITOR,
            riid: *const windows::core::GUID,
            result: *mut *mut std::ffi::c_void,
        ) -> windows::core::HRESULT,
    }

    #[repr(transparent)]
    #[derive(Clone)]
    struct IGraphicsCaptureItemInterop(windows::core::IUnknown);

    unsafe impl Interface for IGraphicsCaptureItemInterop {
        type Vtable = IGraphicsCaptureItemInterop_Vtbl;
        const IID: windows::core::GUID =
            windows::core::GUID::from_u128(0x3628_e81b_3cac_4c60_b7f4_23ce_0e0c_3356);
    }

    impl IGraphicsCaptureItemInterop {
        /// `CreateForWindow` — wraps an HWND into a capture item.
        unsafe fn create_for_window(
            &self,
            window: HWND,
        ) -> windows::core::Result<GraphicsCaptureItem> {
            let mut raw: *mut std::ffi::c_void = std::ptr::null_mut();
            (self.vtable().create_for_window)(
                self.as_raw(),
                window,
                &GraphicsCaptureItem::IID,
                &mut raw,
            )
            .ok()?;
            finish_item(raw)
        }

        /// `CreateForMonitor` — wraps an HMONITOR into a capture item.
        unsafe fn create_for_monitor(
            &self,
            monitor: HMONITOR,
        ) -> windows::core::Result<GraphicsCaptureItem> {
            let mut raw: *mut std::ffi::c_void = std::ptr::null_mut();
            (self.vtable().create_for_monitor)(
                self.as_raw(),
                monitor,
                &GraphicsCaptureItem::IID,
                &mut raw,
            )
            .ok()?;
            finish_item(raw)
        }
    }

    /// Wrap the returned raw pointer as a typed item (null-checked, owned).
    unsafe fn finish_item(raw: *mut std::ffi::c_void) -> windows::core::Result<GraphicsCaptureItem> {
        if raw.is_null() {
            return Err(windows::core::Error::empty());
        }
        Ok(GraphicsCaptureItem::from_raw(raw))
    }

    /// Transcription of `IDirect3DDxgiInterfaceAccess` (the WinRT↔D3D11
    /// surface bridge) — likewise feature-pinned out of the generated crate.
    #[repr(C)]
    struct IDirect3DDxgiInterfaceAccess_Vtbl {
        query_interface: unsafe extern "system" fn(
            *mut std::ffi::c_void,
            *const windows::core::GUID,
            *mut *mut std::ffi::c_void,
        ) -> windows::core::HRESULT,
        add_ref: unsafe extern "system" fn(*mut std::ffi::c_void) -> u32,
        release: unsafe extern "system" fn(*mut std::ffi::c_void) -> u32,
        get_interface: unsafe extern "system" fn(
            this: *mut std::ffi::c_void,
            riid: *const windows::core::GUID,
            result: *mut *mut std::ffi::c_void,
        ) -> windows::core::HRESULT,
    }

    #[repr(transparent)]
    #[derive(Clone)]
    struct IDirect3DDxgiInterfaceAccess(windows::core::IUnknown);

    unsafe impl Interface for IDirect3DDxgiInterfaceAccess {
        type Vtable = IDirect3DDxgiInterfaceAccess_Vtbl;
        const IID: windows::core::GUID =
            windows::core::GUID::from_u128(0xa9b3_d012_3df2_4ee3_b8d1_8695_f457_d3c1);
    }

    impl IDirect3DDxgiInterfaceAccess {
        /// Extract the native D3D11 object behind a WinRT surface/texture.
        unsafe fn get_interface<T: Interface>(&self) -> windows::core::Result<T> {
            let mut raw: *mut std::ffi::c_void = std::ptr::null_mut();
            (self.vtable().get_interface)(self.as_raw(), &T::IID, &mut raw).ok()?;
            if raw.is_null() {
                return Err(windows::core::Error::empty());
            }
            Ok(T::from_raw(raw))
        }
    }

    // `CreateDirect3D11DeviceFromDXGIDevice` — d3d11.dll export bridging the
    // native device into a WinRT `IDirect3DDevice` for the frame pool.
    #[link(name = "d3d11")]
    extern "system" {
        fn CreateDirect3D11DeviceFromDXGIDevice(
            dxgidevice: *mut std::ffi::c_void,
            graphicsdevice: *mut *mut std::ffi::c_void,
        ) -> windows::core::HRESULT;
    }

    // ── Send wrappers (single documented justification each) ────────────────

    /// `ID3D11Texture2D` crossing handler → consumer thread.
    ///
    /// SAFETY: D3D11 device-child resources are free-threaded COM objects
    /// (MSDN "D3D11 Threading": resource access is internally synchronized);
    /// the windows-rs bindings mark every COM wrapper `!Send` uniformly, not
    /// because the object is thread-affine. Discipline enforced here:
    /// produced ONLY by the `FrameArrived` delegate, consumed EXACTLY ONCE by
    /// `poll_frame` on the encode thread (single-producer/single-consumer);
    /// never dereferenced concurrently.
    struct SendTexture(ID3D11Texture2D);
    unsafe impl Send for SendTexture {}
    unsafe impl Sync for SendTexture {}

    /// Native D3D11 device shared by owner thread and `FrameArrived` delegate
    /// (used for pool `Recreate` bookkeeping paths).
    ///
    /// SAFETY: the D3D11 device object itself is free-threaded; usage is
    /// limited to passing it to WGC APIs (never immediate-context work here —
    /// §10 keeps all context calls on the encode thread).
    struct SendD3DDevice(ID3D11Device);
    unsafe impl Send for SendD3DDevice {}
    unsafe impl Sync for SendD3DDevice {}

    /// WinRT `IDirect3DDevice` (created by
    /// `CreateDirect3D11DeviceFromDXGIDevice`) — the object aggregates the
    /// free-threaded marshaler, i.e. it is agile by construction.
    struct SendWinrtDevice(IDirect3DDevice);
    unsafe impl Send for SendWinrtDevice {}
    unsafe impl Sync for SendWinrtDevice {}

    /// Cell holding the WGC session graph (pool/session/item + event tokens).
    ///
    /// SAFETY: all three are standard agile WinRT runtime objects
    /// (`Direct3D11CaptureFramePool` from `CreateFreeThreaded`,
    /// `GraphicsCaptureSession`, `GraphicsCaptureItem`); the bindings' blanket
    /// `!Send` is a conservative projection artifact. Access is additionally
    /// serialized through the inner `Mutex`, so even non-agile behavior could
    /// not race — only `Drop` timing differs.
    struct AgileCell<T> {
        cell: Mutex<T>,
    }
    unsafe impl<T> Send for AgileCell<T> {}
    unsafe impl<T> Sync for AgileCell<T> {}

    impl<T> AgileCell<T> {
        fn new(value: T) -> Self {
            Self { cell: Mutex::new(value) }
        }
    }

    /// Owner-side WGC objects; emptied on stop/drop.
    #[derive(Default)]
    struct WgcCore {
        pool: Option<Direct3D11CaptureFramePool>,
        session: Option<GraphicsCaptureSession>,
        item: Option<GraphicsCaptureItem>,
        frame_token: Option<EventRegistrationToken>,
        closed_token: Option<EventRegistrationToken>,
    }

    /// One queued captured frame (GPU texture + spine metadata).
    struct QueuedFrame {
        width: u32,
        height: u32,
        format: SurfaceFormat,
        qpc: u64,
        frame_number: u64,
        texture: SendTexture,
    }

    impl std::fmt::Debug for QueuedFrame {
        fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            f.debug_struct("QueuedFrame")
                .field("width", &self.width)
                .field("height", &self.height)
                .field("format", &self.format)
                .field("qpc", &self.qpc)
                .field("frame_number", &self.frame_number)
                .finish_non_exhaustive()
        }
    }

    /// State shared between the `FrameArrived` delegate and the owner/consumer.
    struct WgcShared {
        queue: FrameQueue<QueuedFrame>,
        /// Monotonic per-instance frame counter (never reset — spine contract).
        frames_arrived: AtomicU64,
        source_lost: AtomicBool,
        /// Current pool pixel format as raw DXGI code (0 = unset).
        format_code: AtomicU32,
        /// Last seen capture size — resize detection.
        size: Mutex<(u32, u32)>,
        last_error: Mutex<Option<String>>,
        device: OnceLock<SendD3DDevice>,
        winrt_device: OnceLock<SendWinrtDevice>,
        gpu_vendor_id: OnceLock<u32>,
    }

    impl std::fmt::Debug for WgcShared {
        fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            f.debug_struct("WgcShared")
                .field("queued", &self.queue.len())
                .field("frames_arrived", &self.frames_arrived.load(Ordering::Relaxed))
                .field("dropped", &self.queue.dropped())
                .field("source_lost", &self.source_lost.load(Ordering::Relaxed))
                .field("format_code", &self.format_code.load(Ordering::Relaxed))
                .finish_non_exhaustive()
        }
    }

    impl WgcShared {
        fn set_last_error(&self, msg: String) {
            if let Ok(mut slot) = self.last_error.lock() {
                *slot = Some(msg);
            }
        }

        fn last_error(&self) -> Option<String> {
            self.last_error.lock().ok().and_then(|e| e.clone())
        }
    }

    // ── D3D11 device creation (NVIDIA preferred — §8 zero-copy pairing) ─────

    const NVIDIA_VENDOR_ID: u32 = 0x10DE;
    const AMD_VENDOR_ID: u32 = 0x1002;
    const INTEL_VENDOR_ID: u32 = 0x8086;

    /// Vendor preference order for the capture/NVENC-shared device.
    fn vendor_rank(vendor_id: u32) -> u32 {
        match vendor_id {
            NVIDIA_VENDOR_ID => 0,
            AMD_VENDOR_ID => 1,
            INTEL_VENDOR_ID => 2,
            _ => 3,
        }
    }

    /// Vendor id of the adapter behind an existing device (`0` = unknown) —
    /// used when the device was bound externally via `with_shared_device`.
    pub(super) fn adapter_vendor_of(device: &ID3D11Device) -> u32 {
        unsafe {
            device
                .cast::<IDXGIDevice>()
                .ok()
                .and_then(|dxgi| dxgi.GetAdapter().ok())
                .and_then(|adapter| adapter.cast::<IDXGIAdapter1>().ok())
                .and_then(|a| a.GetDesc1().ok())
                .map(|d| d.VendorId)
                .unwrap_or(0)
        }
    }

    /// Create the D3D11 device backing the frame pool, preferring the NVIDIA
    /// adapter so WGC textures register directly with NVENC (§8 zero-copy).
    /// Falls back to the best hardware adapter, then to the OS default —
    /// capture itself is adapter-agnostic; hybrid-GPU risk is reported by the
    /// probe layer (`NVIDIA_ADAPTER_NOT_SELECTED`), not hidden here.
    fn create_capture_device() -> Result<(SendD3DDevice, u32), String> {
        unsafe {
            let candidate: Option<(IDXGIAdapter1, u32)> =
                (|| -> Result<Option<(IDXGIAdapter1, u32)>, String> {
                let factory: IDXGIFactory1 = CreateDXGIFactory1()
                    .map_err(|e| format!("WGC_DXGI_FACTORY_FAILED:{e}"))?;
                let mut best: Option<(IDXGIAdapter1, u32)> = None;
                let mut index = 0u32;
                loop {
                    let adapter = match factory.EnumAdapters1(index) {
                        Ok(a) => a,
                        Err(_) => break, // DXGI_ERROR_NOT_FOUND terminates the walk.
                    };
                    index += 1;
                    let desc = adapter
                        .GetDesc1()
                        .map_err(|e| format!("WGC_ADAPTER_DESC_FAILED:{e}"))?;
                    if desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE.0 as u32 != 0 {
                        continue; // Never capture on a software (WARP) adapter.
                    }
                    let rank = vendor_rank(desc.VendorId);
                    if best.as_ref().map_or(true, |(_, b_rank)| rank < *b_rank) {
                        best = Some((adapter, desc.VendorId));
                    }
                    if rank == 0 {
                        break; // NVIDIA found — stop early.
                    }
                }
                    Ok(best)
                })()?;

            let feature_levels = [D3D_FEATURE_LEVEL_11_1, D3D_FEATURE_LEVEL_11_0];

            // Preferred path: explicit hardware adapter.
            if let Some((adapter, vendor_id)) = candidate {
                let adapter_iface: IDXGIAdapter = adapter
                    .cast()
                    .map_err(|e| format!("WGC_ADAPTER_CAST_FAILED:{e}"))?;
                let mut device: Option<ID3D11Device> = None;
                D3D11CreateDevice(
                    Some(&adapter_iface),
                    D3D_DRIVER_TYPE_UNKNOWN, // Required when an adapter is given.
                    HMODULE::default(),
                    D3D11_CREATE_DEVICE_BGRA_SUPPORT, // WGC surfaces are BGRA.
                    Some(&feature_levels),
                    7, // D3D11_SDK_VERSION
                    Some(&mut device),
                    None,
                    None,
                )
                .map_err(|e| format!("WGC_D3D11_DEVICE_FAILED:{e}"))?;
                if let Some(d) = device {
                    return Ok((SendD3DDevice(d), vendor_id));
                }
            }

            // Fallback: OS default hardware adapter.
            let mut device: Option<ID3D11Device> = None;
            D3D11CreateDevice(
                None,
                D3D_DRIVER_TYPE_HARDWARE,
                HMODULE::default(),
                D3D11_CREATE_DEVICE_BGRA_SUPPORT,
                Some(&feature_levels),
                7,
                Some(&mut device),
                None,
                None,
            )
            .map_err(|e| format!("WGC_D3D11_DEVICE_FAILED:{e}"))?;
            device
                .map(|d| (SendD3DDevice(d), 0))
                .ok_or_else(|| "WGC_D3D11_DEVICE_FAILED:null device".to_string())
        }
    }

    /// Bridge the native device into the WinRT `IDirect3DDevice` the pool wants.
    fn create_winrt_device(native: &SendD3DDevice) -> Result<SendWinrtDevice, String> {
        unsafe {
            let dxgi: IDXGIDevice = native
                .0
                .cast()
                .map_err(|e| format!("WGC_DXGI_DEVICE_CAST_FAILED:{e}"))?;
            let mut inspectable: *mut std::ffi::c_void = std::ptr::null_mut();
            CreateDirect3D11DeviceFromDXGIDevice(dxgi.as_raw(), &mut inspectable)
                .ok()
                .map_err(|e| format!("WGC_WINRT_DEVICE_FAILED:{e}"))?;
            if inspectable.is_null() {
                return Err("WGC_WINRT_DEVICE_FAILED:null inspectable".into());
            }
            let unknown = windows::core::IUnknown::from_raw(inspectable);
            let dev: IDirect3DDevice = unknown
                .cast()
                .map_err(|e| format!("WGC_WINRT_DEVICE_CAST_FAILED:{e}"))?;
            Ok(SendWinrtDevice(dev))
        }
    }

    // ── Monitor / window enumeration (frontend picker + target resolution) ──

    #[derive(Clone)]
    struct MonitorEntry {
        id: String,
        name: String,
        width: u32,
        height: u32,
        is_primary: bool,
        handle: HMONITOR,
    }

    fn wide_to_string(wide: &[u16]) -> String {
        let len = wide.iter().position(|&c| c == 0).unwrap_or(wide.len());
        String::from_utf16_lossy(&wide[..len])
    }

    fn nul_terminated(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }

    unsafe extern "system" fn monitor_enum_proc(
        hmonitor: HMONITOR,
        _hdc: HDC,
        _rect: *mut windows::Win32::Foundation::RECT,
        lparam: LPARAM,
    ) -> windows::Win32::Foundation::BOOL {
        let out = &mut *(lparam.0 as *mut Vec<MonitorEntry>);
        let mut info = MONITORINFOEXW::default();
        info.monitorInfo.cbSize = std::mem::size_of::<MONITORINFOEXW>() as u32;
        if !GetMonitorInfoW(hmonitor, &mut info.monitorInfo as *mut _).as_bool() {
            // Unreadable monitor: skip it but keep the enumeration alive.
            return windows::Win32::Foundation::BOOL(1);
        }
        let gdi_device = wide_to_string(&info.szDevice);

        // Stable identity: the display device's EDID DeviceID when available;
        // otherwise the GDI device name (still unique per adapter attachment).
        let mut dd = windows::Win32::Graphics::Gdi::DISPLAY_DEVICEW::default();
        dd.cb = std::mem::size_of::<windows::Win32::Graphics::Gdi::DISPLAY_DEVICEW>() as u32;
        let gdi_wide = nul_terminated(&gdi_device);
        let mut id = gdi_device.clone();
        let mut friendly = String::new();
        if EnumDisplayDevicesW(PCWSTR(gdi_wide.as_ptr()), 0, &mut dd, 0).as_bool() {
            let device_id = wide_to_string(&dd.DeviceID);
            if !device_id.is_empty() {
                id = device_id;
            }
            friendly = wide_to_string(&dd.DeviceString);
        }
        let name = if friendly.is_empty() { gdi_device.clone() } else { friendly };

        let rc = info.monitorInfo.rcMonitor;
        out.push(MonitorEntry {
            id,
            name,
            width: (rc.right - rc.left).max(0) as u32,
            height: (rc.bottom - rc.top).max(0) as u32,
            is_primary: info.monitorInfo.dwFlags & MONITORINFOF_PRIMARY != 0,
            handle: hmonitor,
        });
        windows::Win32::Foundation::BOOL(1)
    }

    /// Enumerate attached monitors WITH their handles (resolution needs them).
    fn enumerate_monitors() -> Vec<MonitorEntry> {
        let mut out: Vec<MonitorEntry> = Vec::new();
        unsafe {
            let _ = EnumDisplayMonitors(
                HDC::default(),
                None,
                Some(monitor_enum_proc),
                LPARAM(&mut out as *mut _ as isize),
            );
        }
        out
    }

    /// Frontend source-picker projection (no handles cross the boundary).
    pub(super) fn enumerate_monitors_public() -> Vec<super::MonitorInfo> {
        enumerate_monitors()
            .into_iter()
            .map(|m| super::MonitorInfo {
                id: m.id,
                name: m.name,
                width: m.width,
                height: m.height,
                is_primary: m.is_primary,
            })
            .collect()
    }

    unsafe extern "system" fn window_enum_proc(
        hwnd: HWND,
        lparam: LPARAM,
    ) -> windows::Win32::Foundation::BOOL {
        let out = &mut *(lparam.0 as *mut Vec<HWND>);
        // Visible top-level windows with a title bar caption only.
        if !IsWindowVisible(hwnd).as_bool() {
            return windows::Win32::Foundation::BOOL(1);
        }
        if GetWindowTextLengthW(hwnd) <= 0 {
            return windows::Win32::Foundation::BOOL(1);
        }
        out.push(hwnd);
        windows::Win32::Foundation::BOOL(1)
    }

    /// Human process name for a pid ("chrome", "devenv") — empty on failure;
    /// enumeration must never fail because one window is unreadable.
    fn process_name_for_pid(pid: u32) -> String {
        if pid == 0 {
            return String::new();
        }
        unsafe {
            let Ok(handle) =
                OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid)
            else {
                return String::new();
            };
            let mut buf = [0u16; 1024];
            let mut len = buf.len() as u32;
            let name = if QueryFullProcessImageNameW(
                handle,
                PROCESS_NAME_WIN32,
                PWSTR(buf.as_mut_ptr()),
                &mut len,
            )
            .is_ok()
                && len > 0
            {
                let full = String::from_utf16_lossy(&buf[..len as usize]);
                std::path::Path::new(&full)
                    .file_stem()
                    .map(|s| s.to_string_lossy().into_owned())
                    .unwrap_or(full)
            } else {
                String::new()
            };
            let _ = CloseHandle(handle);
            name
        }
    }

    fn hwnd_to_window_info(hwnd: HWND) -> Option<super::WindowInfo> {
        unsafe {
            // Re-check visibility/liveness at read time — windows can vanish
            // between enumeration and projection.
            if !IsWindowVisible(hwnd).as_bool() {
                return None;
            }
            let mut title_buf = [0u16; 512];
            let written = GetWindowTextW(hwnd, &mut title_buf);
            if written <= 0 {
                return None;
            }
            let title = String::from_utf16_lossy(&title_buf[..written.min(512) as usize]);
            let mut pid = 0u32;
            GetWindowThreadProcessId(hwnd, Some(&mut pid));
            let process_name = process_name_for_pid(pid);
            Some(super::WindowInfo {
                hwnd_token: (hwnd.0 as isize).to_string(),
                title,
                process_name,
            })
        }
    }

    /// Frontend source-picker projection of capturable windows (z-order).
    pub(super) fn enumerate_windows_public() -> Vec<super::WindowInfo> {
        let mut hwnds: Vec<HWND> = Vec::new();
        unsafe {
            let _ = EnumWindows(
                Some(window_enum_proc),
                LPARAM(&mut hwnds as *mut _ as isize),
            );
        }
        hwnds.into_iter().filter_map(hwnd_to_window_info).collect()
    }

    /// Parse a window token (`HWND as isize.to_string()`) — rejects ≤0.
    pub(super) fn parse_window_token(token: &str) -> Option<isize> {
        token.trim().parse::<isize>().ok().filter(|v| *v > 0)
    }

    /// Resolve the profile's capture source into a live `GraphicsCaptureItem`
    /// via the COM interop factory (works Win10 1803+ through Win11+).
    fn resolve_capture_item(source: &CaptureSource) -> Result<(GraphicsCaptureItem, String), String> {
        let interop: IGraphicsCaptureItemInterop = factory::<GraphicsCaptureItem, IGraphicsCaptureItemInterop>()
            .map_err(|e| format!("WGC_ITEM_CREATION_FAILED:interop_factory:{e}"))?;

        unsafe {
            match source.kind {
                crate::CaptureSourceKind::Display => {
                    let monitors = enumerate_monitors();
                    let entry = if source.id.is_empty() {
                        monitors.iter().find(|m| m.is_primary).cloned()
                    } else {
                        monitors.iter().find(|m| m.id == source.id).cloned()
                    };
                    let entry = entry.ok_or_else(|| {
                        format!("WGC_ITEM_CREATION_FAILED:display_not_found:{}", source.id)
                    })?;
                    let item = interop
                        .create_for_monitor(entry.handle)
                        .map_err(|e| format!("WGC_ITEM_CREATION_FAILED:create_for_monitor:{e}"))?;
                    Ok((item, entry.name))
                }
                crate::CaptureSourceKind::Window => {
                    let hwnd = parse_window_token(&source.id)
                        .map(|v| HWND(v as *mut std::ffi::c_void))
                        .ok_or_else(|| {
                            format!("WGC_ITEM_CREATION_FAILED:bad_window_token:{}", source.id)
                        })?;
                    if !IsWindow(hwnd).as_bool() {
                        return Err(format!(
                            "WGC_ITEM_CREATION_FAILED:window_not_found:{}",
                            source.id
                        ));
                    }
                    let item = interop
                        .create_for_window(hwnd)
                        .map_err(|e| format!("WGC_ITEM_CREATION_FAILED:create_for_window:{e}"))?;
                    Ok((item, format!("hwnd:{}", source.id)))
                }
            }
        }
    }

    /// Map a spine format onto the WinRT pixel-format enum (pool creation).
    fn pixel_format(format: SurfaceFormat) -> DirectXPixelFormat {
        match format {
            SurfaceFormat::Bgra8 => DirectXPixelFormat::B8G8R8A8UIntNormalized,
            SurfaceFormat::Rgba16Float => DirectXPixelFormat::R16G16B16A16Float,
        }
    }

    // ── FrameArrived delegate ────────────────────────────────────────────────

    /// Producer half (runs on a WinRT threadpool thread). Stamps each frame
    /// with its WGC composition QPC, detects surface format + size changes
    /// (Recreate), converts the surface to a native texture and queues it
    /// (drop-oldest).
    fn on_frame_arrived(state: &Arc<WgcShared>, pool: &Direct3D11CaptureFramePool) {
        // Only used if the frame reports no SystemRelativeTime.
        let qpc = crate::clock::qpc_now();

        if let Err(err) = acquire_one(state, pool, qpc) {
            state.set_last_error(format!("WGC_FRAME_HANDLER_ERROR:{err}"));
        }
    }

    fn acquire_one(
        state: &Arc<WgcShared>,
        pool: &Direct3D11CaptureFramePool,
        fallback_qpc: u64,
    ) -> Result<(), String> {
        unsafe {
            let frame = pool.TryGetNextFrame().map_err(|e| format!("acquire:{e}"))?;
            // Composition QPC from WGC itself — the instant THIS frame was
            // composed. Arrival-time `qpc_now()` would stamp frames delivered
            // in a burst (idle screen) within microseconds of each other,
            // which the muxer's millisecond timebase then rounds into
            // duplicate DTS.
            let qpc = frame
                .SystemRelativeTime()
                .map(|t| crate::clock::hundred_ns_to_qpc_ticks(t.Duration))
                .unwrap_or_else(|_| fallback_qpc);
            let surface = frame.Surface().map_err(|e| format!("surface:{e}"))?;

            // WinRT surface → native texture (zero-copy — §3-A: no pixel bytes
            // ever touch the CPU on this path).
            let access: IDirect3DDxgiInterfaceAccess = surface
                .cast()
                .map_err(|e| format!("dxgi_access:{e}"))?;
            let texture: ID3D11Texture2D = access
                .get_interface()
                .map_err(|e| format!("texture_query:{e}"))?;

            let mut desc = D3D11_TEXTURE2D_DESC::default();
            texture.GetDesc(&mut desc);
            let width = desc.Width;
            let height = desc.Height;
            let dxgi_code = desc.Format.0 as u32;

            let format = map_surface_format(dxgi_code).ok_or_else(|| {
                format!("WGC_UNSUPPORTED_SURFACE_FORMAT:{dxgi_code}")
            })?;

            let expected_code = state.format_code.load(Ordering::Relaxed) as i32;
            let size_changed = {
                let cur = state
                    .size
                    .lock()
                    .map(|s| *s)
                    .unwrap_or((0, 0));
                cur != (width, height)
            };

            if expected_code != desc.Format.0 || size_changed {
                // Resolution change / window resize / HDR flip (§7): rebuild
                // the pool for the NEW geometry, discard this transitional
                // frame; the next arrival lands in the recreated pool.
                let winrt = state
                    .winrt_device
                    .get()
                    .ok_or_else(|| "no_winrt_device".to_string())?;
                pool.Recreate(
                    &winrt.0,
                    pixel_format(format),
                    FRAME_POOL_BUFFERS,
                    windows::Graphics::SizeInt32 {
                        Width: width as i32,
                        Height: height as i32,
                    },
                )
                .map_err(|e| format!("recreate:{e}"))?;
                state.format_code.store(dxgi_code, Ordering::Relaxed);
                if let Ok(mut s) = state.size.lock() {
                    *s = (width, height);
                }
                return Ok(());
            }

            let frame_number = state.frames_arrived.fetch_add(1, Ordering::Relaxed) + 1;
            state.queue.push(QueuedFrame {
                width,
                height,
                format,
                qpc,
                frame_number,
                texture: SendTexture(texture),
            });
            Ok(())
        }
    }

    fn on_item_closed(state: &Arc<WgcShared>) {
        state.source_lost.store(true, Ordering::SeqCst);
        state.set_last_error(CAPTURE_SOURCE_LOST.to_string());
    }

    // ── Public capture backend ───────────────────────────────────────────────

    /// Direct WGC capture backend (production, §7).
    ///
    /// Construction NEVER fails — `new()` only records the target; every
    /// capability gap is reported fail-closed by `prepare()`.
    pub struct WgcCapture {
        source: CaptureSource,
        core: AgileCell<WgcCore>,
        shared: Arc<WgcShared>,
        com_owned: AtomicBool,
        prepared: AtomicBool,
        started: AtomicBool,
    }

    impl WgcCapture {
        pub fn new(source: &crate::CaptureSource) -> Self {
            Self {
                source: source.clone(),
                core: AgileCell::new(WgcCore::default()),
                shared: Arc::new(WgcShared {
                    queue: FrameQueue::new(FRAME_QUEUE_CAP),
                    frames_arrived: AtomicU64::new(0),
                    source_lost: AtomicBool::new(false),
                    format_code: AtomicU32::new(0),
                    size: Mutex::new((0, 0)),
                    last_error: Mutex::new(None),
                    device: OnceLock::new(),
                    winrt_device: OnceLock::new(),
                    gpu_vendor_id: OnceLock::new(),
                }),
                com_owned: AtomicBool::new(false),
                prepared: AtomicBool::new(false),
                started: AtomicBool::new(false),
            }
        }

        /// Bind the pipeline-wide D3D11 device (§6: ONE device for capture,
        /// NVENC and preview). When set before `prepare`, the capture never
        /// creates its own device and derives the GPU vendor id from this one;
        /// zero-copy into NVENC is then guaranteed by construction, not by a
        /// vendor-walk coincidence.
        pub fn with_shared_device(self, device: &ID3D11Device) -> Self {
            let _ = self.shared.device.set(SendD3DDevice(device.clone()));
            self
        }

        /// §25 source-loss flag (window closed / display disconnected).
        pub fn is_source_lost(&self) -> bool {
            self.shared.source_lost.load(Ordering::SeqCst)
        }

        /// Last fail-closed error recorded on the capture path, if any.
        pub fn last_error(&self) -> Option<String> {
            self.shared.last_error()
        }

        /// Frames evicted by the bounded queue (telemetry honesty).
        pub fn dropped_frames(&self) -> u64 {
            self.shared.queue.dropped()
        }

        /// Total frames delivered by WGC since construction.
        pub fn frames_captured(&self) -> u64 {
            self.shared.frames_arrived.load(Ordering::Relaxed)
        }

        /// Detected surface format once the first frame fixed the pool.
        pub fn captured_format(&self) -> Option<SurfaceFormat> {
            map_surface_format(self.shared.format_code.load(Ordering::Relaxed))
        }

        /// Vendor id of the adapter the capture device was created on.
        pub fn gpu_vendor_id(&self) -> Option<u32> {
            self.shared.gpu_vendor_id.get().copied()
        }

        fn ensure_com(&self) -> Result<(), String> {
            if self.com_owned.load(Ordering::SeqCst) {
                return Ok(());
            }
            let hr = unsafe { CoInitializeEx(None, COINIT_MULTITHREADED) };
            if hr.is_ok() {
                // S_OK or S_FALSE — we own an MTA reference either way.
                self.com_owned.store(true, Ordering::SeqCst);
                return Ok(());
            }
            if hr == windows::Win32::Foundation::RPC_E_CHANGED_MODE {
                // Caller owns the apartment — fine for agile WinRT paths;
                // we simply do not own a balancing release.
                return Ok(());
            }
            Err(format!("WGC_COM_INIT_FAILED:{hr:?}"))
        }

        fn release_com(&self) {
            if self.com_owned.swap(false, Ordering::SeqCst) {
                unsafe { CoUninitialize() };
            }
        }

        /// Reset per-take stream state so a re-prepare starts clean while
        /// frame numbering stays monotonic for the instance.
        fn reset_stream_state(&self) {
            self.shared.source_lost.store(false, Ordering::SeqCst);
            self.shared.format_code.store(0, Ordering::Relaxed);
            self.shared.queue.clear();
            if let Ok(mut s) = self.shared.size.lock() {
                *s = (0, 0);
            }
            if let Ok(mut e) = self.shared.last_error.lock() {
                *e = None;
            }
        }
    }

    impl crate::capture::CapturePort for WgcCapture {
        /// Validate + build the entire capture graph WITHOUT starting it:
        /// COM apartment, D3D11 device, WinRT device bridge, capture item
        /// (fail-closed: `WGC_UNAVAILABLE` / `WGC_ITEM_CREATION_FAILED:<ctx>`),
        /// frame pool and the `FrameArrived` wiring.
        fn prepare(&mut self) -> Result<(), String> {
            if self.prepared.load(Ordering::SeqCst) {
                return Err("WGC_ALREADY_PREPARED".into());
            }
            if !super::os_supports_wgc() {
                return Err(WGC_UNAVAILABLE.to_string());
            }
            self.ensure_com()?;
            self.reset_stream_state();

            // 1. D3D11 device — the pipeline-wide one when bound via
            //    `with_shared_device` (§6), else a self-created
            //    NVIDIA-preferred one for standalone/probe use.
            if self.shared.device.get().is_none() {
                let (device, vendor_id) = create_capture_device()?;
                let _ = self.shared.device.set(device);
                let _ = self.shared.gpu_vendor_id.set(vendor_id);
            } else if self.shared.gpu_vendor_id.get().is_none() {
                let vendor_id = self
                    .shared
                    .device
                    .get()
                    .map(|d| adapter_vendor_of(&d.0))
                    .unwrap_or(0);
                let _ = self.shared.gpu_vendor_id.set(vendor_id);
            }
            let device = self.shared.device.get().expect("device just set");

            // 2. WinRT device bridge for the frame pool.
            if self.shared.winrt_device.get().is_none() {
                let winrt = create_winrt_device(device)?;
                let _ = self.shared.winrt_device.set(winrt);
            }
            let winrt = self
                .shared
                .winrt_device
                .get()
                .ok_or("WGC_WINRT_DEVICE_FAILED:not initialized")?;

            // 3. Capture item (monitor or window, §7).
            let (item, label) = resolve_capture_item(&self.source)?;

            // 4. Frame pool — free-threaded: no DispatcherQueue dependency.
            let item_size = item.Size().map_err(|e| format!("WGC_ITEM_SIZE_FAILED:{e}"))?;
            let initial_size = windows::Graphics::SizeInt32 {
                Width: item_size.Width,
                Height: item_size.Height,
            };
            let pool = Direct3D11CaptureFramePool::CreateFreeThreaded(
                &winrt.0,
                pixel_format(SurfaceFormat::Bgra8),
                FRAME_POOL_BUFFERS,
                initial_size,
            )
            .map_err(|e| format!("WGC_POOL_CREATE_FAILED:{e}"))?;

            // Seed expected geometry so the first frame does not force a
            // needless Recreate; genuine resize/HDR flips still re-sync.
            self.shared.format_code.store(surface_format_dxgi_code(SurfaceFormat::Bgra8), Ordering::Relaxed);
            if let Ok(mut s) = self.shared.size.lock() {
                *s = (item_size.Width.max(0) as u32, item_size.Height.max(0) as u32);
            }

            // 5. Source-loss path (§25): window close / display disconnect.
            let shared_closed = Arc::clone(&self.shared);
            let closed_handler = TypedEventHandler::new(
                move |_item: &Option<GraphicsCaptureItem>,
                      _args: &Option<IInspectable>|
                      -> windows::core::Result<()> {
                    on_item_closed(&shared_closed);
                    Ok(())
                },
            );
            let closed_token = item
                .Closed(&closed_handler)
                .map_err(|e| format!("WGC_CLOSED_HANDLER_FAILED:{e}"))?;

            // 6. Frame arrival pump.
            let shared_frames = Arc::clone(&self.shared);
            let frame_handler = TypedEventHandler::new(
                move |sender: &Option<Direct3D11CaptureFramePool>,
                      _args: &Option<IInspectable>|
                      -> windows::core::Result<()> {
                    // The runtime always delivers a live pool reference here.
                    if let Some(pool) = sender.as_ref() {
                        on_frame_arrived(&shared_frames, pool);
                    }
                    Ok(())
                },
            );
            let frame_token = pool
                .FrameArrived(&frame_handler)
                .map_err(|e| format!("WGC_FRAME_HANDLER_FAILED:{e}"))?;

            // 7. Session object (StartCapture deferred to start()).
            let session = pool
                .CreateCaptureSession(&item)
                .map_err(|e| format!("WGC_SESSION_CREATE_FAILED:{e}"))?;

            {
                let mut core = self.core.cell.lock().map_err(|_| "WGC_CORE_POISONED".to_string())?;
                core.item = Some(item);
                core.pool = Some(pool);
                core.session = Some(session);
                core.frame_token = Some(frame_token);
                core.closed_token = Some(closed_token);
            }
            self.prepared.store(true, Ordering::SeqCst);
            let _ = label; // Reserved for future timeline events (§15).
            Ok(())
        }

        fn start(&mut self) -> Result<(), String> {
            if !self.prepared.load(Ordering::SeqCst) {
                return Err("WGC_NOT_PREPARED".into());
            }
            if self.started.load(Ordering::SeqCst) {
                return Err("WGC_ALREADY_STARTED".into());
            }
            let core = self.core.cell.lock().map_err(|_| "WGC_CORE_POISONED".to_string())?;
            let session = core.session.as_ref().ok_or("WGC_NOT_PREPARED")?;
            session
                .StartCapture()
                .map_err(|e| format!("WGC_START_FAILED:{e}"))?;
            drop(core);
            self.started.store(true, Ordering::SeqCst);
            Ok(())
        }

        /// Unregister handlers, close the session + pool, drain the queue.
        fn stop(&mut self) -> Result<(), String> {
            let mut failures: Vec<String> = Vec::new();
            {
                let core = self.core.cell.lock().map_err(|_| "WGC_CORE_POISONED".to_string())?;
                if let (Some(token), Some(pool)) = (core.frame_token, &core.pool) {
                    if let Err(e) = pool.RemoveFrameArrived(token) {
                        failures.push(format!("remove_frame_handler:{e}"));
                    }
                }
                if let (Some(token), Some(item)) = (core.closed_token, &core.item) {
                    if let Err(e) = item.RemoveClosed(token) {
                        failures.push(format!("remove_closed_handler:{e}"));
                    }
                }
                if let Some(session) = &core.session {
                    if let Err(e) = session.Close() {
                        failures.push(format!("session_close:{e}"));
                    }
                }
                if let Some(pool) = &core.pool {
                    if let Err(e) = pool.Close() {
                        failures.push(format!("pool_close:{e}"));
                    }
                }
            }
            // Drain any queued textures (releases pool buffer references).
            self.shared.queue.clear();

            {
                let mut core = self
                    .core
                    .cell
                    .lock()
                    .map_err(|_| "WGC_CORE_POISONED".to_string())?;
                *core = WgcCore::default();
            }
            self.started.store(false, Ordering::SeqCst);
            self.prepared.store(false, Ordering::SeqCst);
            self.release_com();

            if failures.is_empty() {
                Ok(())
            } else {
                Err(format!("WGC_STOP_FAILED:{}", failures.join(";")))
            }
        }

        fn poll_frame(&mut self) -> Option<CapturedFrame> {
            let qf = self.shared.queue.pop()?;
            Some(CapturedFrame {
                width: qf.width,
                height: qf.height,
                format: qf.format,
                qpc: qf.qpc,
                frame_number: qf.frame_number,
                texture: Some(qf.texture.0),
            })
        }

        fn pending_frames(&self) -> usize {
            self.shared.queue.len()
        }

        fn is_available(&self) -> bool {
            super::os_supports_wgc() && !self.is_source_lost()
        }

        fn backend_name(&self) -> &'static str {
            "WGC"
        }
    }

    impl Drop for WgcCapture {
        fn drop(&mut self) {
            // Best-effort teardown — errors are irrelevant during drop.
            let _ = crate::capture::CapturePort::stop(self);
        }
    }
}

#[cfg(windows)]
pub use imp::WgcCapture;

// ══════════════════════ Non-Windows fail-closed fallback ════════════════════

#[cfg(not(windows))]
pub struct WgcCapture {
    source: CaptureSource,
}

#[cfg(not(windows))]
impl WgcCapture {
    pub fn new(source: &CaptureSource) -> Self {
        Self { source: source.clone() }
    }

    pub fn is_source_lost(&self) -> bool {
        false
    }

    pub fn last_error(&self) -> Option<String> {
        None
    }

    pub fn dropped_frames(&self) -> u64 {
        0
    }

    pub fn frames_captured(&self) -> u64 {
        0
    }

    pub fn captured_format(&self) -> Option<SurfaceFormat> {
        None
    }

    pub fn gpu_vendor_id(&self) -> Option<u32> {
        None
    }
}

#[cfg(not(windows))]
impl crate::capture::CapturePort for WgcCapture {
    fn prepare(&mut self) -> Result<(), String> {
        Err(crate::capture::WGC_UNAVAILABLE.to_string())
    }

    fn start(&mut self) -> Result<(), String> {
        Err(crate::capture::WGC_UNAVAILABLE.to_string())
    }

    fn stop(&mut self) -> Result<(), String> {
        Ok(())
    }

    fn poll_frame(&mut self) -> Option<crate::capture::CapturedFrame> {
        None
    }

    fn is_available(&self) -> bool {
        false
    }

    fn backend_name(&self) -> &'static str {
        "WGC"
    }
}

// ─── Frontend enumeration entry points ───────────────────────────────────────

#[cfg(windows)]
pub fn list_monitors() -> Vec<MonitorInfo> {
    imp::enumerate_monitors_public()
}

#[cfg(windows)]
pub fn list_windows() -> Vec<WindowInfo> {
    imp::enumerate_windows_public()
}

// ─── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::capture::CapturePort as _;

    #[test]
    fn os_support_probe_is_total() {
        // Must answer without panicking on every host; non-Windows is always
        // false (fail-closed).
        let supported = os_supports_wgc();
        #[cfg(not(windows))]
        assert!(!supported);
        #[cfg(windows)]
        {
            let _ = supported; // Desktop Windows: either answer is legitimate.
        }
    }

    #[test]
    fn surface_format_mapping_covers_sdr_and_hdr() {
        assert_eq!(map_surface_format(87), Some(SurfaceFormat::Bgra8));
        assert_eq!(map_surface_format(10), Some(SurfaceFormat::Rgba16Float));
        assert_eq!(map_surface_format(28), None); // R8G8B8A8_UNORM unsupported
        assert_eq!(map_surface_format(0), None);  // DXGI_FORMAT_UNKNOWN
    }

    #[test]
    fn surface_format_codes_round_trip() {
        for format in [SurfaceFormat::Bgra8, SurfaceFormat::Rgba16Float] {
            let code = surface_format_dxgi_code(format);
            assert_eq!(map_surface_format(code), Some(format));
        }
    }

    #[test]
    fn frame_queue_overflow_drops_oldest_and_counts() {
        let q: FrameQueue<u32> = FrameQueue::new(2);
        q.push(1);
        q.push(2);
        assert_eq!(q.len(), 2);
        q.push(3); // Evicts `1`.
        assert_eq!(q.len(), 2);
        assert_eq!(q.dropped(), 1);
        assert_eq!(q.pop(), Some(2)); // Oldest-first drain order preserved.
        assert_eq!(q.pop(), Some(3));
        assert_eq!(q.pop(), None);
    }

    #[test]
    fn frame_queue_clear_drains_without_counting_drops() {
        let q: FrameQueue<u8> = FrameQueue::new(4);
        q.push(1);
        q.push(2);
        q.clear();
        assert_eq!(q.len(), 0);
        assert_eq!(q.dropped(), 0); // Deliberate drain ≠ overflow loss.
    }

    #[test]
    fn window_tokens_must_be_positive_integers() {
        #[cfg(windows)]
        {
            assert_eq!(imp::parse_window_token("12345"), Some(12345));
            assert_eq!(imp::parse_window_token("  42 "), Some(42));
            assert_eq!(imp::parse_window_token("abc"), None);
            assert_eq!(imp::parse_window_token("-7"), None);
            assert_eq!(imp::parse_window_token(""), None);
            assert_eq!(imp::parse_window_token("0"), None);
        }
    }

    #[test]
    fn lifecycle_fails_closed_without_wgc() {
        if !os_supports_wgc() {
            let source = crate::CaptureSource {
                kind: crate::CaptureSourceKind::Display,
                id: String::new(),
            };
            let mut capture = WgcCapture::new(&source);
            let err = capture.prepare().err().expect("prepare must fail closed");
            assert!(err.contains("WGC_UNAVAILABLE"), "got: {err}");
            assert!(!capture.is_available());
            assert_eq!(capture.backend_name(), "WGC");
            assert!(capture.poll_frame().is_none());
            assert_eq!(capture.pending_frames(), 0);
        }
        // With WGC present the lifecycle needs a live desktop session —
        // exercised by integration tests, never asserted here (CI-safe).
    }

    #[cfg(windows)]
    #[test]
    fn monitor_enumeration_never_panics_and_entries_are_valid() {
        let monitors = list_monitors();
        for m in &monitors {
            assert!(!m.id.is_empty(), "monitor id must be non-empty");
            assert!(m.width > 0 && m.height > 0, "monitor dims must be positive");
        }
        // At most one primary monitor.
        assert!(monitors.iter().filter(|m| m.is_primary).count() <= 1);
    }

    #[cfg(windows)]
    #[test]
    fn window_enumeration_never_panics_and_entries_are_valid() {
        let windows_list = list_windows();
        for w in &windows_list {
            assert!(!w.hwnd_token.is_empty());
            assert!(w.hwnd_token.parse::<isize>().is_ok(), "token must be isize");
            assert!(!w.title.is_empty());
            assert!(!w.process_name.is_empty());
        }
    }

    #[cfg(windows)]
    #[test]
    fn unknown_display_id_fails_closed_with_ctx_error() {
        let source = crate::CaptureSource {
            kind: crate::CaptureSourceKind::Display,
            id: "WINDAGENT_TEST_NO_SUCH_DISPLAY".into(),
        };
        let mut capture = WgcCapture::new(&source);
        if let Err(err) = capture.prepare() {
            assert!(
                err.contains("WGC_ITEM_CREATION_FAILED"),
                "expected item-creation failure, got: {err}"
            );
        }
        // If prepare unexpectedly SUCCEEDED the test machine matched the bogus
        // id — impossible by construction; no assertion needed beyond the
        // error arm above.
    }

    #[cfg(windows)]
    #[test]
    fn shared_device_vendor_derives_from_bound_adapter() {
        // On hosts with a usable GPU the derived vendor id must equal the one
        // the preferred-device walk recorded — proving `with_shared_device`
        // keeps telemetry honest without its own adapter scan. No GPU at all:
        // nothing to assert (CI-safe, mirrors d3d11_device tests).
        let Ok(bundle) = crate::capture::d3d11_device::create_preferred_device() else {
            return;
        };
        let vid = imp::adapter_vendor_of(&bundle.device);
        if bundle.info.vendor_id != 0 {
            assert_eq!(
                vid, bundle.info.vendor_id,
                "derived vendor {vid:#x} != walked vendor {:#x} ({})",
                bundle.info.vendor_id, bundle.info.description
            );
        }
        assert!(matches!(vid, 0x10DE | 0x1002 | 0x8086 | 0x1414 | 0), "vendor {vid:#x}");
    }
}
