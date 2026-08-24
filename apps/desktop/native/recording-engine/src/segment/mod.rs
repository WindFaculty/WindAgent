//! Segmented MKV recording — Phase 9 (ban_ke_hoach_v1.md Section 17)
//!
//! ```text
//! take_0001/
//!  ├── segment_0001.mkv
//!  ├── segment_0002.mkv
//!  ├── timeline.jsonl   ← every event with t (seconds since take start)
//!  └── manifest.json
//! ```
//! Segment 5 or 10 min; every segment independently playable (MKV, not MP4
//! in-recording — MP4 moov requires finalization). Crash recovery retains
//! all completed segments.

pub mod timeline_writer;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SegmentInfo {
    pub index: u32,
    pub file_token: String,
    pub started_at_ms: u64,
    pub ended_at_ms: Option<u64>,
    pub duration_sec: f64,
    pub is_playable: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimelineEvent {
    pub t: f64,
    pub event_type: String,
    pub scene_id: Option<String>,
    pub cue_id: Option<String>,
    pub action_id: Option<String>,
    pub execution_id: Option<String>,
    pub marker_type: Option<String>,
    pub detail: String,
}

pub struct Segmenter {
    pub segment_minutes: u32,
    pub segments: Vec<SegmentInfo>,
    pub timeline: Vec<TimelineEvent>,
    next_index: u32,
    current_started_at_ms: Option<u64>,
}

impl Segmenter {
    pub fn new(segment_minutes: u32) -> Self {
        Self {
            segment_minutes,
            segments: vec![],
            timeline: vec![],
            next_index: 0,
            current_started_at_ms: None,
        }
    }

    pub fn start_take(&mut self, take_id: &str, started_at_ms: u64) {
        self.segments.clear();
        self.timeline.clear();
        self.next_index = 0;
        self.current_started_at_ms = Some(started_at_ms);
        self.push_timeline(TimelineEvent {
            t: 0.0,
            event_type: "SESSION_START".into(),
            scene_id: None,
            cue_id: None,
            action_id: None,
            execution_id: Some(take_id.to_string()),
            marker_type: None,
            detail: "take started".into(),
        });
    }

    pub fn should_roll_segment(&self, elapsed_ms: u64) -> bool {
        let segment_ms = self.segment_minutes as u64 * 60 * 1000;
        elapsed_ms >= segment_ms
    }

    pub fn roll_segment(&mut self, take_id: &str, now_ms: u64) -> SegmentInfo {
        let started = self.current_started_at_ms.unwrap_or(now_ms);
        let duration_sec = (now_ms.saturating_sub(started) as f64) / 1000.0;
        let info = SegmentInfo {
            index: self.next_index,
            file_token: format!("{}/segment_{:04}.mkv", take_id, self.next_index),
            started_at_ms: started,
            ended_at_ms: Some(now_ms),
            duration_sec,
            is_playable: true,
        };
        self.segments.push(info.clone());
        self.next_index += 1;
        self.current_started_at_ms = Some(now_ms);
        self.push_timeline(TimelineEvent {
            t: duration_sec,
            event_type: "SEGMENT_END".into(),
            scene_id: None,
            cue_id: None,
            action_id: None,
            execution_id: None,
            marker_type: None,
            detail: format!("segment {} finalized", info.index),
        });
        info
    }

    pub fn push_timeline(&mut self, event: TimelineEvent) {
        // Enforce monotonic t for TTS alignment (Section 25)
        if let Some(last) = self.timeline.last() {
            debug_assert!(
                event.t >= last.t,
                "timeline must be monotonic: {} < {}",
                event.t,
                last.t
            );
        }
        self.timeline.push(event);
    }

    pub fn manifest(&self, take_id: &str, execution_plan_id: &str) -> crate::SegmentManifest {
        crate::SegmentManifest {
            take_id: take_id.to_string(),
            execution_plan_id: execution_plan_id.to_string(),
            segments: self
                .segments
                .iter()
                .map(|s| crate::SegmentEntry {
                    index: s.index,
                    file_token: s.file_token.clone(),
                    duration_sec: s.duration_sec,
                    is_playable: s.is_playable,
                })
                .collect(),
            timeline_ref: format!("{}/timeline.jsonl", take_id),
            created_at: timeline_writer::rfc3339_now(),
        }
    }
}
