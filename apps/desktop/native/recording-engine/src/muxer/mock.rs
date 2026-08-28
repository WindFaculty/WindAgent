//! Dev/CI simulation muxer — writes REAL files with an honest structure.
//!
//! Not an MKV: each segment file starts with the EBML magic bytes so crash
//! recovery's magic check has something true to validate, followed by
//! length-prefixed records of the actual encoded payloads it was handed.
//! Selected only under `WINDAGENT_RECORDER_ALLOW_MOCK=1`; production never
//! constructs it (Principle H — no fake status).

use std::io::Write;

use super::{MuxedSegment, MuxerPort, TrackId, TrackParams};
use crate::encoder::EncodedPacket;

/// EBML magic — same first four bytes a real MKV starts with.
pub const EBML_MAGIC: [u8; 4] = [0x1A, 0x45, 0xDF, 0xA3];

pub struct MockMuxer {
    output_dir: String,
    current_file: Option<std::fs::File>,
    current_path: Option<std::path::PathBuf>,
    current_index: u32,
    bytes_written_total: u64,
    segment_bytes: u64,
    first_pts_us: Option<u64>,
    last_pts_us: Option<u64>,
}

impl MockMuxer {
    pub fn new() -> Self {
        Self {
            output_dir: String::new(),
            current_file: None,
            current_path: None,
            current_index: 0,
            bytes_written_total: 0,
            segment_bytes: 0,
            first_pts_us: None,
            last_pts_us: None,
        }
    }

    fn segment_path(&self, index: u32, tmp: bool) -> std::path::PathBuf {
        std::path::Path::new(&self.output_dir)
            .join(format!("segment_{index:04}.mkv{}", if tmp { ".tmp" } else { "" }))
    }
}

impl Default for MockMuxer {
    fn default() -> Self {
        Self::new()
    }
}

impl MuxerPort for MockMuxer {
    fn prepare(&mut self, output_dir: &str) -> Result<(), String> {
        self.output_dir = output_dir.to_string();
        std::fs::create_dir_all(output_dir).map_err(|e| format!("MKV_DIR_FAILED:{e}"))
    }

    fn open_segment(&mut self, index: u32, _tracks: &[(TrackId, TrackParams)]) -> Result<(), String> {
        let path = self.segment_path(index, true);
        let mut file = std::fs::File::create(&path).map_err(|e| format!("MKV_OPEN_FAILED:{e}"))?;
        // Header: EBML magic + record-format version line.
        file.write_all(&EBML_MAGIC)
            .and_then(|_| writeln!(file, "windagent-mock-mkv v1 segment={index}"))
            .map_err(|e| format!("MKV_WRITE_FAILED:{e}"))?;
        self.current_file = Some(file);
        self.current_path = Some(path);
        self.current_index = index;
        self.segment_bytes = 0;
        self.first_pts_us = None;
        self.last_pts_us = None;
        Ok(())
    }

    fn write_packet(&mut self, track: TrackId, packet: &EncodedPacket) -> Result<(), String> {
        let file = self.current_file.as_mut().ok_or("MKV_WRITE_FAILED:no open segment")?;
        let data = &packet.data;
        // Record: track tag, length-prefixed payload, pts for replay tooling.
        writeln!(
            file,
            "pkt {} len={} pts={}",
            track.as_str(),
            data.len(),
            packet.pts_us
        )
        .and_then(|_| file.write_all(data))
        .map_err(|e| format!("MKV_WRITE_FAILED:{e}"))?;
        self.segment_bytes = self.segment_bytes.saturating_add(data.len() as u64 + 32);
        self.bytes_written_total += 32 + data.len() as u64;
        self.first_pts_us.get_or_insert(packet.pts_us);
        self.last_pts_us = Some(packet.pts_us.max(self.last_pts_us.unwrap_or(packet.pts_us)));
        Ok(())
    }

    fn close_segment(&mut self) -> Result<MuxedSegment, String> {
        let path = self.current_path.take().ok_or("MKV_CLOSE_FAILED:no open segment")?;
        let file = self.current_file.take().ok_or("MKV_CLOSE_FAILED:no open segment")?;
        // fsync the still-open WRITE handle then atomic rename — the commit
        // marker recovery trusts. (Reopening read-only cannot fsync on
        // Windows: FlushFileBuffers requires GENERIC_WRITE access.)
        file.sync_all().map_err(|e| format!("MKV_FSYNC_FAILED:{e}"))?;
        drop(file);
        let final_path = self.segment_path(self.current_index, false);
        std::fs::rename(&path, &final_path).map_err(|e| format!("MKV_RENAME_FAILED:{e}"))?;
        let duration_sec = match (self.first_pts_us, self.last_pts_us) {
            (Some(a), Some(b)) => b.saturating_sub(a) as f64 / 1_000_000.0,
            _ => 0.0,
        };
        Ok(MuxedSegment {
            index: self.current_index,
            file_token: format!(
                "{}/segment_{:04}.mkv",
                std::path::Path::new(&self.output_dir)
                    .file_name()
                    .map(|n| n.to_string_lossy().to_string())
                    .unwrap_or_default(),
                self.current_index
            ),
            duration_sec,
            byte_len: std::fs::metadata(&final_path).map(|m| m.len()).unwrap_or(0),
            is_playable: true,
        })
    }

    fn finalize_take(&mut self) -> Result<(), String> {
        Ok(())
    }

    fn bytes_written(&self) -> u64 {
        self.bytes_written_total
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pkt(pts: u64, key: bool) -> EncodedPacket {
        EncodedPacket {
            pts_us: pts,
            dts_us: pts as i64,
            is_keyframe: key,
            data: vec![7u8; 100],
            codec: "H264".into(),
        }
    }

    #[test]
    fn segments_are_fsynced_renamed_and_report_bytes() {
        let dir = std::env::temp_dir().join(format!(
            "windagent_mockmux_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let mut mux = MockMuxer::new();
        mux.prepare(dir.to_str().unwrap()).unwrap();
        let tracks = vec![(
            TrackId::Video,
            TrackParams::VideoH264 { width: 1920, height: 1080, fps: 60 },
        )];
        mux.open_segment(0, &tracks).unwrap();
        assert!(dir.join("segment_0000.mkv.tmp").exists());
        mux.write_packet(TrackId::Video, &pkt(0, true)).unwrap();
        mux.write_packet(TrackId::Video, &pkt(16_666, false)).unwrap();
        let seg = mux.close_segment().unwrap();
        assert_eq!(seg.index, 0);
        assert!(seg.byte_len > 200, "byte_len={}", seg.byte_len);
        assert!((seg.duration_sec - 16_666.0 / 1e6).abs() < 1e-6);
        let final_path = dir.join("segment_0000.mkv");
        assert!(!dir.join("segment_0000.mkv.tmp").exists());
        let head = std::fs::read(&final_path).unwrap();
        assert_eq!(&head[..4], &EBML_MAGIC, "commit marker must start with EBML magic");
        assert!(seg.is_playable);
        assert!(mux.bytes_written() > 0);
        mux.finalize_take().unwrap();
        let _ = std::fs::remove_dir_all(&dir);
    }
}
