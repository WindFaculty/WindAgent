//! Crash-safe on-disk timeline + manifest — Phase 9 (ban_ke_hoach_v1.md Section 17).
//!
//! ```text
//! take_xxx/
//!  ├── segment_0001.mkv
//!  ├── timeline.jsonl   ← {"t":<monotonic sec>,"type":<event>} one per line
//!  └── manifest.json
//! ```
//!
//! Every line is flushed the moment it is appended so a crash mid-take keeps
//! a coherent prefix of the timeline (crash recovery contract, Section 17).

use std::io::Write;
use std::path::Path;

use serde::Serialize;

use super::TimelineEvent;
use crate::SegmentManifest;

/// Serialize one timeline event to the frozen JSONL shape
/// (`{"t":..,"type":..}` with optional context keys).
#[derive(Serialize)]
struct TimelineLine<'a> {
    t: f64,
    #[serde(rename = "type")]
    event_type: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    scene_id: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    cue_id: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    action_id: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    execution_id: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    marker_type: Option<&'a str>,
    detail: &'a str,
}

impl<'a> From<&'a TimelineEvent> for TimelineLine<'a> {
    fn from(e: &'a TimelineEvent) -> Self {
        Self {
            t: e.t,
            event_type: e.event_type.as_str(),
            scene_id: e.scene_id.as_deref(),
            cue_id: e.cue_id.as_deref(),
            action_id: e.action_id.as_deref(),
            execution_id: e.execution_id.as_deref(),
            marker_type: e.marker_type.as_deref(),
            detail: e.detail.as_str(),
        }
    }
}

/// Append-only JSONL writer with per-line flush (crash-safe prefix).
pub struct TimelineWriter {
    file: std::fs::File,
}

impl TimelineWriter {
    /// Create (or truncate) `{dir}/timeline.jsonl` for a fresh take.
    pub fn create(dir: &Path) -> Result<Self, String> {
        std::fs::create_dir_all(dir)
            .map_err(|e| format!("TIMELINE_DIR_FAILED: {}", e))?;
        let file = std::fs::OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(dir.join("timeline.jsonl"))
            .map_err(|e| format!("TIMELINE_CREATE_FAILED: {}", e))?;
        Ok(Self { file })
    }

    pub fn append(&mut self, event: &TimelineEvent) -> Result<(), String> {
        let line = serde_json::to_string(&TimelineLine::from(event))
            .map_err(|e| format!("TIMELINE_SERIALIZE_FAILED: {}", e))?;
        writeln!(self.file, "{line}").map_err(|e| format!("TIMELINE_WRITE_FAILED: {}", e))?;
        self.file
            .flush()
            .map_err(|e| format!("TIMELINE_FLUSH_FAILED: {}", e))
    }
}

/// Write `manifest.json` at finalize time — crash-safe ladder identical to
/// the MKV segments (§17): `.tmp` → write → fsync → atomic rename, so a torn
/// manifest never exists under its final name and recovery always sees
/// either the previous complete file or the new one.
pub fn write_manifest(dir: &Path, manifest: &SegmentManifest) -> Result<(), String> {
    let json = serde_json::to_string_pretty(manifest)
        .map_err(|e| format!("MANIFEST_SERIALIZE_FAILED: {}", e))?;
    let tmp_path = dir.join("manifest.json.tmp");
    {
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&tmp_path)
            .map_err(|e| format!("MANIFEST_WRITE_FAILED: {}", e))?;
        file.write_all(json.as_bytes())
            .and_then(|()| file.flush())
            .and_then(|()| file.sync_all())
            .map_err(|e| format!("MANIFEST_WRITE_FAILED: {}", e))?;
    }
    std::fs::rename(&tmp_path, dir.join("manifest.json"))
        .map_err(|e| format!("MANIFEST_WRITE_FAILED: rename: {}", e))
}

/// Current UTC time as RFC3339 with millisecond precision (`…T…Z`).
pub fn rfc3339_now() -> String {
    let millis = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);
    rfc3339_from_millis(millis)
}

/// RFC3339 formatting without any external date dependency.
pub fn rfc3339_from_millis(millis: u64) -> String {
    let secs = millis / 1000;
    let ms = millis % 1000;
    let days = (secs / 86400) as i64;
    let secs_of_day = secs % 86400;
    let (year, month, day) = civil_from_days(days);
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}.{:03}Z",
        year,
        month,
        day,
        secs_of_day / 3600,
        (secs_of_day % 3600) / 60,
        secs_of_day % 60,
        ms
    )
}

/// Days-since-epoch → (year, month, day) — Howard Hinnant's civil_from_days.
fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = (z - era * 146_097) as u64; // [0, 146096]
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365; // [0, 399]
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100); // [0, 365]
    let mp = (5 * doy + 2) / 153; // [0, 11]
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32; // [1, 31]
    let m = if mp < 10 { mp + 3 } else { mp - 9 }; // [1, 12]
    (if m <= 2 { y + 1 } else { y }, m as u32, d)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rfc3339_known_timestamps() {
        assert_eq!(rfc3339_from_millis(0), "1970-01-01T00:00:00.000Z");
        // 2026-08-23T00:00:00Z == 1787443200
        assert_eq!(
            rfc3339_from_millis(1_787_443_200_000),
            "2026-08-23T00:00:00.000Z"
        );
        // Leap-year day: 2024-02-29T12:34:56.789Z == 1709210096.789
        assert_eq!(
            rfc3339_from_millis(1_709_210_096_789),
            "2024-02-29T12:34:56.789Z"
        );
    }

    #[test]
    fn appends_frozen_jsonl_shape_and_flushes_per_line() {
        let dir = std::env::temp_dir().join(format!(
            "windagent_timeline_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        {
            let mut writer = TimelineWriter::create(&dir).unwrap();
            writer
                .append(&TimelineEvent {
                    t: 1.5,
                    event_type: "SESSION_START".into(),
                    scene_id: None,
                    cue_id: None,
                    action_id: None,
                    execution_id: Some("take_1".into()),
                    marker_type: None,
                    detail: "take started".into(),
                })
                .unwrap();
            writer
                .append(&TimelineEvent {
                    t: 2.0,
                    event_type: "ACTION_SUCCESS".into(),
                    scene_id: Some("sc_1".into()),
                    cue_id: Some("cue_1".into()),
                    action_id: Some("act_1".into()),
                    execution_id: None,
                    marker_type: None,
                    detail: String::new(),
                })
                .unwrap();
        }
        let content =
            std::fs::read_to_string(dir.join("timeline.jsonl")).unwrap();
        let lines: Vec<&str> = content.lines().collect();
        assert_eq!(lines.len(), 2);
        assert_eq!(
            lines[0],
            r#"{"t":1.5,"type":"SESSION_START","execution_id":"take_1","detail":"take started"}"#
        );
        assert!(lines[1].contains(r#""type":"ACTION_SUCCESS""#));
        assert!(lines[1].contains(r#""action_id":"act_1""#));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn manifest_roundtrips_with_real_created_at() {
        let dir = std::env::temp_dir().join(format!(
            "windagent_manifest_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let manifest = SegmentManifest {
            take_id: "take_1".into(),
            execution_plan_id: "plan_1".into(),
            segments: vec![],
            timeline_ref: "take_1/timeline.jsonl".into(),
            created_at: rfc3339_now(),
        };
        write_manifest(&dir, &manifest).unwrap();
        let text = std::fs::read_to_string(dir.join("manifest.json")).unwrap();
        assert!(text.contains("\"created_at\": \"20"), "{text}");
        assert!(!text.contains("2026-08-23T00:00:00Z")); // no hardcoded stamp
        let _ = std::fs::remove_dir_all(&dir);
    }
}
