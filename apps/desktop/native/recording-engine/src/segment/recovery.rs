//! Crash recovery — interrupted-take scan, validation, manifest rebuild
//! (ban_ke_hoach_v1.md §15).
//!
//! The commit marker is the atomic rename: only `close_segment` renames
//! `.tmp → .mkv` after fsync, so a renamed file is complete **by
//! construction**. Recovery therefore:
//!
//! 1. deletes every `*.mkv.tmp` (uncommitted tail — data loss is honest),
//! 2. validates every `segment_*.mkv` starts with the EBML magic and is
//!    non-empty,
//! 3. rebuilds `manifest.json` atomically from the surviving set.

use std::io::Write;
use std::path::{Path, PathBuf};

use crate::SegmentEntry;

#[derive(Debug, Clone, serde::Serialize)]
pub struct RecoveryReport {
    pub take_id: String,
    pub recovered_segments: Vec<SegmentEntry>,
    pub discarded_tmp_files: usize,
    pub invalid_files: Vec<String>,
    /// Last monotonic `t` in `timeline.jsonl` — the honest crash-time
    /// estimate of TOTAL take duration without demuxing. Individual segments
    /// keep `duration_sec: 0.0` (the container itself is their source of
    /// truth; export tooling derives real values from it).
    pub timeline_end_sec: Option<f64>,
}

/// Most recent take directory under `root` that contains recording artifacts.
/// `None` when nothing recoverable exists.
pub fn scan_latest_take(root: &Path) -> Option<PathBuf> {
    let mut candidates: Vec<(std::time::SystemTime, PathBuf)> = std::fs::read_dir(root)
        .ok()?
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir())
        .filter(|e| {
            let name = e.file_name().to_string_lossy().to_string();
            name.starts_with("take_")
        })
        .filter(|e| has_recording_artifacts(&e.path()))
        .filter_map(|e| {
            let modified = e.metadata().ok()?.modified().ok()?;
            Some((modified, e.path()))
        })
        .collect();
    candidates.sort_by(|a, b| b.0.cmp(&a.0));
    candidates.into_iter().next().map(|(_, p)| p)
}

fn has_recording_artifacts(dir: &Path) -> bool {
    std::fs::read_dir(dir)
        .map(|rd| {
            rd.filter_map(|e| e.ok()).any(|e| {
                let name = e.file_name().to_string_lossy().to_string();
                name.starts_with("segment_") && (name.ends_with(".mkv") || name.ends_with(".mkv.tmp"))
                    || name == "timeline.jsonl"
            })
        })
        .unwrap_or(false)
}

/// Validate + rebuild one take. Idempotent — safe to re-run after a crash.
pub fn recover_take(take_dir: &Path) -> Result<RecoveryReport, String> {
    let take_id = take_dir
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| "take_unknown".into());

    // 1. Discard uncommitted tails first — they are not segments. A stale
    //    half-written manifest temp (crash between tmp and rename) is internal
    //    scratch, not data, and goes too.
    let mut discarded_tmp = 0usize;
    for entry in list_files(take_dir)? {
        let name = entry.file_name().to_string_lossy().to_string();
        if name.ends_with(".mkv.tmp") {
            std::fs::remove_file(&entry.path())
                .map_err(|e| format!("RECOVERY_TMP_DELETE_FAILED:{e}"))?;
            discarded_tmp += 1;
        } else if name == "manifest.json.tmp" || name == "manifest.json.recovering" {
            let _ = std::fs::remove_file(&entry.path());
        }
    }

    // 2. Validate renamed segments in index order.
    let mut recovered = Vec::new();
    let mut invalid = Vec::new();
    for entry in list_files(take_dir)? {
        let name = entry.file_name().to_string_lossy().to_string();
        if !(name.starts_with("segment_") && name.ends_with(".mkv")) {
            continue;
        }
        match validate_segment(&entry.path()) {
            Ok(byte_len) => {
                let index = parse_segment_index(&name).unwrap_or(u32::MAX);
                recovered.push(SegmentEntry {
                    index,
                    file_token: format!("{take_id}/{name}"),
                    // Duration post-crash is unknown without demuxing; export
                    // tooling derives it from the container itself.
                    duration_sec: 0.0,
                    byte_len,
                    is_playable: true,
                });
            }
            Err(reason) => invalid.push(format!("{name}: {reason}")),
        }
    }
    recovered.sort_by_key(|s| s.index);

    // 3. Rebuild the manifest with the same durability ladder as finalize:
    //    `.tmp` → write → fsync → atomic rename.
    let manifest = crate::SegmentManifest {
        take_id: take_id.clone(),
        execution_plan_id: String::new(),
        segments: recovered.clone(),
        timeline_ref: format!("{take_id}/timeline.jsonl"),
        created_at: super::timeline_writer::rfc3339_now(),
    };
    let json = serde_json::to_string_pretty(&manifest)
        .map_err(|e| format!("RECOVERY_MANIFEST_SERIALIZE_FAILED:{e}"))?;
    let tmp = take_dir.join("manifest.json.tmp");
    std::fs::File::create(&tmp)
        .and_then(|mut f| {
            f.write_all(json.as_bytes())
                .and_then(|()| f.flush())
                .and_then(|()| f.sync_all())
        })
        .map_err(|e| format!("RECOVERY_MANIFEST_WRITE_FAILED:{e}"))?;
    std::fs::rename(tmp, take_dir.join("manifest.json"))
        .map_err(|e| format!("RECOVERY_MANIFEST_RENAME_FAILED:{e}"))?;

    Ok(RecoveryReport {
        take_id,
        recovered_segments: recovered,
        discarded_tmp_files: discarded_tmp,
        invalid_files: invalid,
        timeline_end_sec: timeline_end_sec(take_dir),
    })
}

/// Last valid `t` in the frozen JSONL timeline. The crash-safe prefix
/// contract guarantees every flushed line is coherent, so scanning from the
/// tail recovers the latest recorded moment without demuxing MKV.
fn timeline_end_sec(take_dir: &Path) -> Option<f64> {
    let text = std::fs::read_to_string(take_dir.join("timeline.jsonl")).ok()?;
    text.lines().rev().find_map(|line| {
        let v: serde_json::Value = serde_json::from_str(line).ok()?;
        v.get("t")?.as_f64()
    })
}

fn list_files(dir: &Path) -> Result<Vec<std::fs::DirEntry>, String> {
    std::fs::read_dir(dir)
        .map_err(|e| format!("RECOVERY_READ_DIR_FAILED:{e}"))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| format!("RECOVERY_READ_DIR_FAILED:{e}"))
}

/// EBML magic + non-trivial size. Returns the validated byte length.
fn validate_segment(path: &Path) -> Result<u64, String> {
    let meta = std::fs::metadata(path).map_err(|e| format!("STAT:{e}"))?;
    if meta.len() < 16 {
        return Err(format!("too small ({} bytes)", meta.len()));
    }
    let mut head = [0u8; 4];
    std::fs::File::open(path)
        .and_then(|mut f| std::io::Read::read_exact(&mut f, &mut head))
        .map_err(|e| format!("READ:{e}"))?;
    if head != crate::muxer::mock::EBML_MAGIC {
        return Err("missing EBML magic".into());
    }
    Ok(meta.len())
}

fn parse_segment_index(name: &str) -> Option<u32> {
    name.strip_prefix("segment_")?
        .strip_suffix(".mkv")?
        .parse()
        .ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp_root() -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "windagent_recovery_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&root).unwrap();
        root
    }

    #[test]
    fn recovers_committed_segments_and_discards_tmp_tail() {
        let root = tmp_root();
        let take = root.join("take_x1");
        std::fs::create_dir_all(&take).unwrap();
        // Two committed segments (valid magic, ≥16 bytes) + one crashed .tmp
        // tail.
        for (name, body) in [
            ("segment_0000.mkv", [0x1A, 0x45, 0xDF, 0xA3, 9u8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
            ("segment_0001.mkv", [0x1A, 0x45, 0xDF, 0xA3, 8u8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
        ] {
            std::fs::write(take.join(name), body).unwrap();
        }
        std::fs::write(take.join("segment_0002.mkv.tmp"), b"partial garbage").unwrap();
        // Frozen crash-safe prefix of the timeline + a torn manifest temp.
        std::fs::write(take.join("timeline.jsonl"), "{\"t\":0.0}\n{\"t\":42.5}\n").unwrap();
        std::fs::write(take.join("manifest.json.recovering"), b"{torn").unwrap();

        let report = recover_take(&take).unwrap();
        assert_eq!(report.take_id, "take_x1");
        assert_eq!(report.discarded_tmp_files, 1);
        assert!(!take.join("segment_0002.mkv.tmp").exists());
        assert_eq!(report.timeline_end_sec, Some(42.5));
        assert!(!take.join("manifest.json.recovering").exists());
        assert_eq!(report.recovered_segments.len(), 2);
        assert_eq!(report.recovered_segments[0].index, 0);
        assert_eq!(
            report.recovered_segments[0].file_token,
            "take_x1/segment_0000.mkv"
        );
        assert!(report.invalid_files.is_empty());
        let manifest_text =
            std::fs::read_to_string(take.join("manifest.json")).unwrap();
        assert!(manifest_text.contains("\"segments\""));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn flags_invalid_segments_without_dying() {
        let root = tmp_root();
        let take = root.join("take_x2");
        std::fs::create_dir_all(&take).unwrap();
        std::fs::write(take.join("segment_0000.mkv"), b"not mkv at all").unwrap();
        let report = recover_take(&take).unwrap();
        assert!(report.recovered_segments.is_empty());
        assert_eq!(report.invalid_files.len(), 1);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn scan_picks_most_recent_recoverable_take() {
        let root = tmp_root();
        let older = root.join("take_a");
        let newer = root.join("take_b");
        for d in [&older, &newer] {
            std::fs::create_dir_all(d).unwrap();
        }
        std::fs::write(newer.join("segment_0000.mkv"), [0x1Au8, 0x45, 0xDF, 0xA3, 1]).unwrap();
        // `older` has no artifacts → must be skipped even though it exists.
        std::thread::sleep(std::time::Duration::from_millis(20));
        std::fs::write(newer.join("timeline.jsonl"), "{}\n").unwrap();
        let found = scan_latest_take(&root).unwrap();
        assert_eq!(found.file_name().unwrap().to_string_lossy(), "take_b");
        let none = scan_latest_take(&std::env::temp_dir().join("definitely-missing-windagent"));
        assert!(none.is_none());
        let _ = std::fs::remove_dir_all(&root);
    }
}
