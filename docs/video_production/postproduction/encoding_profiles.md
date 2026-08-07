# Post-Production Encoding Profiles Specification

## 1. Overview

Encoding profiles establish deterministic, target-specific encoding standards for final video deliverables, proxy previews, and intermediate render stages in the WindAgent Video Production pipeline.

## 2. Standard Profiles

### 2.1 `MAIN_1080P_H264` (Final Deliverable)
- **Container**: MP4 (`.mp4`)
- **Video Codec**: H.264 (`libx264`)
- **Video Profile**: High Profile, Level 4.1
- **Pixel Format**: `yuv420p`
- **Resolution**: 1920 x 1080 (16:9)
- **Frame Rate**: 30 fps (constant frame rate)
- **Video Bitrate**: Constant Rate Factor (CRF) 18 (Max Bitrate 12 Mbps)
- **Audio Codec**: AAC (`aac`)
- **Audio Channels**: 2 (Stereo)
- **Audio Sample Rate**: 48,000 Hz
- **Audio Bitrate**: 192 kbps
- **Audio Loudness**: Target -16 LUFS (Integrated), Peak Ceiling -1.0 dBFS

### 2.2 `PROXY_720P_H264` (Web/Desktop Preview)
- **Container**: MP4 (`.mp4`)
- **Video Codec**: H.264 (`libx264`)
- **Video Profile**: Main Profile
- **Pixel Format**: `yuv420p`
- **Resolution**: 1280 x 720 (16:9)
- **Frame Rate**: 30 fps
- **Video Bitrate**: CRF 24 (Max Bitrate 3 Mbps)
- **Audio Codec**: AAC (`aac`)
- **Audio Channels**: 2 (Stereo)
- **Audio Sample Rate**: 44,100 Hz
- **Audio Bitrate**: 96 kbps

### 2.3 `THUMBNAIL_JPEG` (Poster Image)
- **Format**: JPEG (`.jpg`)
- **Resolution**: 1920 x 1080
- **Quality**: 90%

## 3. Aspect Ratio & Padding Policy

All videos must maintain an exact 16:9 aspect ratio.
- If input aspect ratio matches 16:9, scale directly.
- If input aspect ratio differs, apply letterboxing/pillarboxing with black pads (`black` border color) via `scale=w:h:force_original_aspect_ratio=decrease,pad=w:h:(ow-iw)/2:(oh-ih)/2`.
- Silent stretching or non-standard aspect distortion is forbidden.

## 4. Audio Loudness Policy

- Final output audio streams must be normalized using EBU R128 loudness standards.
- Integrated Loudness target: `-16.0 LUFS` (tolerance ±1.0 LUFS).
- True Peak ceiling: `-1.0 dBFS`.
- Loudness range target: `11.0 LU`.
