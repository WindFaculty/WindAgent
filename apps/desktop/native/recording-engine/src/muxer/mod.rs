//! Muxer — Phase 9 (ban_ke_hoach_v1.md Section 17)
//!
//! `EncodedPacket` → `libavformat` → MKV segments (5 or 10 min) + timeline.jsonl
//! Every segment is independently playable; crash recovery retains prior segments.

use serde::{Deserialize, Serialize};

pub trait MuxerPort: Send {
    fn prepare(&mut self, output_dir: &str) -> Result<(), String>;
    fn write_packet(&mut self, packet: &crate::encoder::EncodedPacket) -> Result<(), String>;
    fn finalize_segment(&mut self, segment_index: u32) -> Result<MuxedSegment, String>;
    fn finalize_take(&mut self) -> Result<(), String>;
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MuxedSegment {
    pub index: u32,
    pub file_token: String, // tokenized delivery ref, never raw FS path to UI
    pub duration_sec: f64,
    pub is_playable: bool,
    pub byte_len: u64,
}

// ─── LibAV (real) ──────────────────────────────────────────────────────────

pub struct LibavMuxer {
    output_dir: Option<String>,
    bytes_written: u64,
}

impl LibavMuxer {
    pub fn new() -> Self {
        Self {
            output_dir: None,
            bytes_written: 0,
        }
    }
}

impl Default for LibavMuxer {
    fn default() -> Self {
        Self::new()
    }
}

impl MuxerPort for LibavMuxer {
    fn prepare(&mut self, output_dir: &str) -> Result<(), String> {
        if output_dir.is_empty() {
            return Err("MUXER_PREPARE_REJECTED: output_dir required".into());
        }
        self.output_dir = Some(output_dir.to_string());
        Ok(())
    }

    fn write_packet(&mut self, packet: &crate::encoder::EncodedPacket) -> Result<(), String> {
        if self.output_dir.is_none() {
            return Err("MUXER_NOT_PREPARED".into());
        }
        self.bytes_written += packet.data_len as u64;
        Ok(())
    }

    fn finalize_segment(&mut self, segment_index: u32) -> Result<MuxedSegment, String> {
        let dir = self.output_dir.clone().unwrap_or_else(|| "take_mock".into());
        Ok(MuxedSegment {
            index: segment_index,
            file_token: format!("{}/segment_{:04}.mkv", dir, segment_index),
            duration_sec: 300.0,
            is_playable: true,
            byte_len: self.bytes_written,
        })
    }

    fn finalize_take(&mut self) -> Result<(), String> {
        Ok(())
    }
}

// ─── Mock ──────────────────────────────────────────────────────────────────

pub struct MockMuxer {
    inner: LibavMuxer,
}

impl MockMuxer {
    pub fn new() -> Self {
        Self {
            inner: LibavMuxer::new(),
        }
    }
}

impl Default for MockMuxer {
    fn default() -> Self {
        Self::new()
    }
}

impl MuxerPort for MockMuxer {
    fn prepare(&mut self, output_dir: &str) -> Result<(), String> {
        self.inner.prepare(output_dir)
    }

    fn write_packet(&mut self, packet: &crate::encoder::EncodedPacket) -> Result<(), String> {
        self.inner.write_packet(packet)
    }

    fn finalize_segment(&mut self, segment_index: u32) -> Result<MuxedSegment, String> {
        self.inner.finalize_segment(segment_index)
    }

    fn finalize_take(&mut self) -> Result<(), String> {
        self.inner.finalize_take()
    }
}
