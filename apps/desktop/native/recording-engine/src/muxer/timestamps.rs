//! Timestamp math + segment-boundary routing (ban_ke_hoach_v1.md §9, §12).
//!
//! Pure functions — unit-tested without any native dependency.

use crate::encoder::EncodedPacket;

/// MKV timebase used for every track: 1/1000 ns ticks? No — we use
/// microseconds (1/1_000_000) which divides cleanly into QPC-derived PTS.
pub const TIMEBASE_DEN: u32 = 1_000_000;

/// QPC-micros → stream timestamp in the 1/TIMEBASE_DEN timebase.
#[inline]
pub fn pts_from_micros(micros: u64) -> i64 {
    micros as i64
}

#[inline]
pub fn micros_from_pts(pts: i64) -> u64 {
    pts.max(0) as u64
}

/// What the mux driver must do with an incoming packet.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RouteAction {
    /// Packet belongs to the currently open segment.
    Current,
    /// Close current segment; open `index`. The packet starts the new file.
    RollTo(u32),
    /// Packet chronologically belongs to a segment that has not opened yet
    /// and arrived before its keyframe — hold it until [`RouteAction::RollTo`]
    /// fires (B-frame reordering can only cause this for the boundary frame).
    HoldForNext,
}

/// Decides segment membership by PTS so B-frame reordering never corrupts a
/// boundary: every packet with `pts < boundary` belongs to the current file;
/// the first keyframe at-or-after the boundary opens the next one.
///
/// One instance per take. `request_roll` arms the next boundary.
#[derive(Debug)]
pub struct SegmentRouter {
    pub segment_index: u32,
    boundary_pts_us: Option<u64>,
    pending_next: Vec<EncodedPacket>,
}

impl SegmentRouter {
    pub fn new() -> Self {
        Self {
            segment_index: 0,
            boundary_pts_us: None,
            pending_next: Vec::new(),
        }
    }

    /// Arm a roll: the first keyframe whose PTS ≥ `boundary_pts_us` opens
    /// segment `segment_index + 1`.
    pub fn request_roll(&mut self, boundary_pts_us: u64) {
        self.boundary_pts_us = Some(boundary_pts_us);
    }

    pub fn is_roll_armed(&self) -> bool {
        self.boundary_pts_us.is_some()
    }

    pub fn route(&mut self, packet: &EncodedPacket) -> RouteAction {
        let Some(boundary) = self.boundary_pts_us else {
            return RouteAction::Current;
        };
        if packet.pts_us < boundary {
            return RouteAction::Current;
        }
        if packet.is_keyframe {
            self.segment_index += 1;
            self.boundary_pts_us = None;
            return RouteAction::RollTo(self.segment_index);
        }
        // Non-keyframe past the boundary — can only be a reordered B/P frame
        // that chronologically sits inside the *next* GOP window. Hold until
        // the IDR opens that segment.
        RouteAction::HoldForNext
    }

    /// Drain frames held for the not-yet-opened next segment.
    pub fn take_pending(&mut self) -> Vec<EncodedPacket> {
        std::mem::take(&mut self.pending_next)
    }
}

impl Default for SegmentRouter {
    fn default() -> Self {
        Self::new()
    }
}

/// Monotonicity guard for mux-side timestamps (fail loud on clock bugs).
pub fn assert_monotonic(last: &mut Option<i64>, next: i64, what: &str) -> Result<(), String> {
    if let Some(prev) = last {
        if next < *prev {
            return Err(format!(
                "TIMESTAMP_REGRESSION: {what} went {next} after {}",
                prev
            ));
        }
    }
    *last = Some(next);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pkt(pts_us: u64, key: bool) -> EncodedPacket {
        EncodedPacket {
            pts_us,
            dts_us: pts_us as i64 - 48_000, // typical B-reorder lag
            is_keyframe: key,
            data: vec![1],
            codec: "H264".into(),
        }
    }

    #[test]
    fn packets_before_boundary_stay_current() {
        let mut r = SegmentRouter::new();
        r.request_roll(300_000_000); // 5 min
        assert_eq!(r.route(&pkt(299_999_999, false)), RouteAction::Current);
        assert_eq!(r.route(&pkt(100_000_000, true)), RouteAction::Current);
    }

    #[test]
    fn idr_at_boundary_opens_next_segment() {
        let mut r = SegmentRouter::new();
        r.request_roll(300_000_000);
        assert_eq!(r.route(&pkt(300_000_000, true)), RouteAction::RollTo(1));
        assert!(!r.is_roll_armed());
        // After the roll everything continues in the new segment.
        assert_eq!(r.route(&pkt(300_033_000, false)), RouteAction::Current);
    }

    #[test]
    fn non_keyframe_past_boundary_is_held_not_routed() {
        let mut r = SegmentRouter::new();
        r.request_roll(300_000_000);
        // Reordered frame with pts past boundary arriving before the IDR.
        assert_eq!(r.route(&pkt(300_016_000, false)), RouteAction::HoldForNext);
        assert_eq!(r.route(&pkt(300_000_000, true)), RouteAction::RollTo(1));
    }

    #[test]
    fn monotonic_guard_rejects_regressions() {
        let mut last = None;
        assert!(assert_monotonic(&mut last, 10, "v").is_ok());
        assert!(assert_monotonic(&mut last, 11, "v").is_ok());
        assert!(assert_monotonic(&mut last, 5, "v").is_err());
    }
}
