//! Capture pipeline — Direct Windows Graphics Capture → D3D11 texture.
//! Gate: LIVE_RECORD_V2_CONTRACT_FROZEN (ban_ke_hoach_v1.md §7)
//!
//! Hot path contract (Principle A — zero-copy): [`CapturedFrame`] owns the
//! captured **GPU texture**, never pixel bytes. CPU readback exists only in
//! the preview path (≤1280×720 JPEG at ≤2 FPS).
//!
//! Production backend is [`wgc::WgcCapture`]. If WGC is unavailable the
//! engine fail-closes into BLOCK RECORDING — silently falling back to another
//! capture backend is forbidden (§3-B).
//!
//! `ffmpeg_dev` module stays available for development comparison only and
//! is never referenced by the production service.

pub mod d3d11_device;
/// Development-only comparison backend — never imported by production service.
#[cfg(feature = "ffmpeg-dev")]
pub mod ffmpeg_capture;
pub mod wgc;

use serde::{Deserialize, Serialize};

/// Pixel format of a captured GPU surface.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SurfaceFormat {
    /// Standard SDR desktop composition format — registers directly with NVENC.
    Bgra8,
    /// HDR desktop format — requires a GPU tone-map pass to Bgra8 before H264.
    Rgba16Float,
}

impl SurfaceFormat {
    pub fn bytes_per_pixel(self) -> u32 {
        match self {
            Self::Bgra8 => 4,
            Self::Rgba16Float => 8,
        }
    }
}

/// Owned handle to one captured D3D11 texture.
///
/// On Windows this wraps an `ID3D11Texture2D` acquired from the WGC frame
/// pool. Dropping it releases the texture back to the pool — implementations
/// must not hold pool frames longer than one pipeline stage.
#[derive(Debug)]
pub struct CapturedFrame {
    pub width: u32,
    pub height: u32,
    pub format: SurfaceFormat,
    pub qpc: u64,
    pub frame_number: u64,
    #[cfg(windows)]
    pub texture: Option<windows::Win32::Graphics::Direct3D11::ID3D11Texture2D>,
    #[cfg(not(windows))]
    pub _texture_absent: (),
}

impl CapturedFrame {
    /// Metadata-only frame (no texture) — used by tests/metrics paths.
    pub fn metadata(width: u32, height: u32, format: SurfaceFormat, qpc: u64, frame_number: u64) -> Self {
        Self {
            width,
            height,
            format,
            qpc,
            frame_number,
            #[cfg(windows)]
            texture: None,
            #[cfg(not(windows))]
            _texture_absent: (),
        }
    }

    pub fn has_texture(&self) -> bool {
        #[cfg(windows)]
        {
            self.texture.is_some()
        }
        #[cfg(not(windows))]
        {
            false
        }
    }
}

/// Abstract capture port — data plane boundary.
///
/// Real backends buffer arrived frames internally (WGC `FrameArrived` → queue);
/// `poll_frame` drains exactly one queued frame per call and returns `None`
/// when the queue is empty (never busy-waits).
pub trait CapturePort: Send {
    fn prepare(&mut self) -> Result<(), String>;
    fn start(&mut self) -> Result<(), String>;
    fn stop(&mut self) -> Result<(), String>;
    fn poll_frame(&mut self) -> Option<CapturedFrame>;
    /// Queue depth between prepare/start and drain — telemetry feeds on this.
    fn pending_frames(&self) -> usize {
        0
    }
    fn is_available(&self) -> bool;
    fn backend_name(&self) -> &'static str;
}

// ─── Production backend marker ──────────────────────────────────────────────

/// Fail-closed error every production caller receives when direct WGC cannot
/// run. There is intentionally NO alternative capture backend.
pub const WGC_UNAVAILABLE: &str =
    "WGC_UNAVAILABLE: Windows Graphics Capture unavailable on this host — recording blocked";

// ─── Mock (tests / CI without Windows graphics) ─────────────────────────────

/// Synthetic-frame capture for dev/CI simulation. Never selected in
/// production unless the operator explicitly sets
/// `WINDAGENT_RECORDER_ALLOW_MOCK=1`.
pub struct MockCapture {
    pub resolution: (u32, u32),
    pub fps: u32,
    started: bool,
    frame_counter: u64,
    last_emit: Option<std::time::Instant>,
    queue: std::collections::VecDeque<CapturedFrame>,
}

impl MockCapture {
    pub fn new(resolution: (u32, u32), fps: u32) -> Self {
        Self {
            resolution,
            fps,
            started: false,
            frame_counter: 0,
            last_emit: None,
            queue: std::collections::VecDeque::new(),
        }
    }
}

impl CapturePort for MockCapture {
    fn prepare(&mut self) -> Result<(), String> {
        Ok(())
    }

    fn start(&mut self) -> Result<(), String> {
        self.started = true;
        Ok(())
    }

    fn stop(&mut self) -> Result<(), String> {
        self.started = false;
        Ok(())
    }

    fn poll_frame(&mut self) -> Option<CapturedFrame> {
        if !self.started {
            return None;
        }
        // Pace synthetic frames to nominal FPS using wall time.
        let interval = std::time::Duration::from_millis((1000 / self.fps.max(1)) as u64);
        let now = std::time::Instant::now();
        match self.last_emit {
            Some(last) if now.duration_since(last) < interval => {}
            _ => {
                self.last_emit = Some(now);
                self.frame_counter += 1;
                self.queue.push_back(CapturedFrame::metadata(
                    self.resolution.0,
                    self.resolution.1,
                    SurfaceFormat::Bgra8,
                    crate::clock::qpc_now(),
                    self.frame_counter,
                ));
            }
        }
        self.queue.pop_front()
    }

    fn pending_frames(&self) -> usize {
        self.queue.len()
    }

    fn is_available(&self) -> bool {
        true
    }

    fn backend_name(&self) -> &'static str {
        "MOCK"
    }
}
