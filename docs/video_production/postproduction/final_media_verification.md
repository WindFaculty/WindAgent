# Final Media Verification Specification

## 1. Overview

Final media verification validates every post-production render deliverable before publishing. Deliverables that fail any verification check are quarantined and flagged as `FAILED`.

## 2. Verification Protocol & Quality Checks

A deliverable passes verification if and only if all of the following checks succeed:

### 2.1 Container & Stream Sanity (`ffprobe`)
- Container format must match expected extension (e.g., MP4).
- Must contain exactly 1 video stream and (if required by profile) 1 audio stream.
- Video codec must match profile (e.g. `h264`).
- Pixel format must match profile (`yuv420p`).
- Resolution must match profile (e.g. `1920x1080`).
- Frame rate must match target (e.g. `30 fps`).

### 2.2 Duration Tolerance
- Output duration must match target EDL duration within an approved tolerance window (e.g. ±0.1 seconds).
- Truncated videos or zero-duration files fail closed.

### 2.3 Frame Decode Test
- Sample frames decoded at start (t=0.5s), midpoint (t=50%), and end (t=duration - 0.5s).
- Frame decode errors or corrupted packets fail verification.

### 2.4 Black & Silence Detection
- Detection for accidental leading/trailing black frames or truncated video.
- Total continuous black frame sequence must not exceed 0.5s unless explicitly specified in EDL.
- Audio stream must not contain sustained digital zero / dropouts.

### 2.5 Audio Loudness & Peak Verification
- Integrated loudness must be within `-16.0 ± 1.0 LUFS`.
- True peak ceiling must not exceed `-1.0 dBFS`.

### 2.6 Subtitle Bounds Verification
- All subtitle cues must lie strictly within `[0.0, video_duration]`.
- Overlapping cues for the same speaker position are flagged.

### 2.7 Fingerprinting & Asset Linking
- SHA-256 hash computed for final video file.
- Corresponding proxy preview (`PROXY_720P_H264`) and thumbnail poster image generated and hash-linked to the deliverable record.

## 3. Verification Verdict

Output deliverable is published ONLY when `ffprobe_verification_receipt.json` status is `PASSED`.
