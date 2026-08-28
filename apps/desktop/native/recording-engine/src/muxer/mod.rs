//! Muxer — real libavformat MKV writer (ban_ke_hoach_v1.md §9).
//!
//! `libav_loader` loads `avformat`/`avutil` DLLs at runtime (no import-lib
//! linking); `libav` implements the segmented MKV writer on top; `tracks`
//! builds Matroska CodecPrivate records (avcC/hvcC/AAC ASC); `timestamps`
//! owns PTS conversion and segment-boundary routing.
//!
//! Segmentation rule (§9): never cut mid-GOP — an IDR is forced at every
//! boundary; the segment closes only after all packets belonging to it
//! (by PTS) have been written; each file is finished (trailer + fsync +
//! atomic rename from `.tmp`) so it is independently playable.

pub mod libav;
pub mod libav_loader;
/// Dev/CI simulation writer — never selected in production (Principle H).
pub mod mock;
pub mod timestamps;
pub mod tracks;

use serde::{Deserialize, Serialize};

use crate::encoder::EncodedPacket;

/// Logical MKV tracks — mic and system audio are NEVER mixed pre-record.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TrackId {
    Video,
    Mic,
    System,
}

impl TrackId {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Video => "video",
            Self::Mic => "mic",
            Self::System => "system",
        }
    }
}

/// Per-track stream parameters fixed at take start.
#[derive(Debug, Clone)]
pub enum TrackParams {
    VideoH264 { width: u32, height: u32, fps: u32 },
    VideoHevc { width: u32, height: u32, fps: u32 },
    Aac { sample_rate: u32, channels: u32 },
}

/// Report for one closed segment file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MuxedSegment {
    pub index: u32,
    /// Tokenized delivery ref (`take_xxx/segment_NNNN.mkv`) — never a raw path.
    pub file_token: String,
    pub duration_sec: f64,
    pub byte_len: u64,
    pub is_playable: bool,
}

/// Abstract muxer port. One segment is open at a time; the driver routes
/// packets by [`timestamps::SegmentRouter`] so B-frame reordering stays
/// correct across boundaries.
pub trait MuxerPort: Send {
    fn prepare(&mut self, output_dir: &str) -> Result<(), String>;
    /// Begin a new `.tmp` segment with the given track layout.
    fn open_segment(&mut self, index: u32, tracks: &[(TrackId, TrackParams)]) -> Result<(), String>;
    /// Stage video CodecPrivate (avcC/hvcC) into the open segment while its
    /// header is still lazy — must run between `open_segment` and the first
    /// `write_packet` (§9 handshake). Simulation backends ignore it.
    fn stage_video_extradata(&mut self, _avcc_or_hvcc: &[u8]) -> Result<(), String> {
        Ok(())
    }
    /// Stage AAC AudioSpecificConfig for one audio track, same timing
    /// contract as [`MuxerPort::stage_video_extradata`].
    fn stage_audio_extradata(&mut self, _track: TrackId, _asc: &[u8]) -> Result<(), String> {
        Ok(())
    }
    fn write_packet(&mut self, track: TrackId, packet: &EncodedPacket) -> Result<(), String>;
    /// Finish the open segment: trailer → flush → fsync → atomic rename.
    fn close_segment(&mut self) -> Result<MuxedSegment, String>;
    fn finalize_take(&mut self) -> Result<(), String>;
    /// Bytes written to the currently open segment (telemetry).
    fn bytes_written(&self) -> u64 {
        0
    }
}

/// Fail-closed error surfaced when the bundled libav runtime is absent.
pub const LIBAV_UNAVAILABLE: &str =
    "LIBAV_UNAVAILABLE: avformat/avutil runtime DLLs not found — recording blocked";
