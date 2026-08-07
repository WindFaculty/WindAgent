# Edit Decision List (EDL) Specification

## 1. Overview

The Edit Decision List (EDL) defines the deterministic assembly structure for post-production video editing in the WindAgent Video Production pipeline. An EDL specifies the exact sequence of approved video shots, audio tracks, subtitle overlays, and transitions required to render a final video deliverable.

## 2. Content Addressing & Traceability

Every clip and asset referenced in an EDL must be content-addressed by its SHA-256 hash. An EDL NEVER relies solely on transient file system paths.

- **Shot Clip Hash**: SHA-256 hash of the generated/approved video shot candidate.
- **Audio Track Hash**: SHA-256 hash of the final audio mix or dialogue track.
- **Subtitle Track Hash**: SHA-256 hash of the timed subtitle track.
- **EDL Hash**: SHA-256 hash derived deterministically from the canonical JSON representation of the EDL structure.

## 3. Schema & Data Model

An EDL contains:

1. `edl_id`: Unique opaque identifier (`edl_...`).
2. `project_id`: Associated video project ID.
3. `revision_id`: Target production revision ID.
4. `items`: Sequential list of shot edit decision items:
   - `shot_id`: Associated shot ID.
   - `clip_hash`: Content SHA-256 of the source video clip.
   - `in_point`: In-point timestamp in seconds (default 0.0).
   - `out_point`: Out-point timestamp in seconds.
   - `target_duration`: Duration of shot in output timeline.
   - `transition_in`: Optional `TransitionPlan` for entering this shot.
5. `audio_mix_plan_id`: Reference to the `AudioMixPlan` defining dialogue, SFX, BGM, and ducking.
6. `subtitle_track_id`: Optional reference to `SubtitleTrack`.
7. `encoding_profile_id`: Target `EncodingProfile` ID (e.g. `MAIN_1080P_H264`).

## 4. Input Normalization Rules

Before concatenation, all input video clips referenced by an EDL must be validated and normalized:
- **Resolution**: Scaled/padded to target aspect ratio (16:9, e.g. 1920x1080) without illegal stretch.
- **Frame Rate**: Converted to target constant frame rate (fps: 24, 30, or 60).
- **Time Base & Pixel Format**: Standardized to `yuv420p` with 1/1000000 time base.
- **Audio Sample Rate**: Re-sampled to 48kHz stereo 16-bit PCM.

## 5. Invalidation Scopes

- Modifying any video shot or transition invalidates the entire EDL and final render.
- Modifying BGM invalidates the audio mix and final render, but does NOT invalidate video shot clips or dialogue alignment.
- Modifying dialogue invalidates audio alignment, audio mix, EDL, and final render.
