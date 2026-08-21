"""
VP3D Phase 4 — FFmpeg/ffprobe runner for ASSEMBLE + VERIFY (plan Stage B §4).

Backward compatibility module wrapping `windagent_tools.media.ffmpeg`.
Maintains all original interfaces and signatures for Blender workflows.
"""

from __future__ import annotations


from windagent_tools.media.ffmpeg import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_OUTPUT_BYTES,
    FfmpegPort,
    FfmpegReceipt,
    FfmpegResult,
    FfmpegRunner,
    FfmpegVersion,
    SubprocessFfmpegPort,
    probe_ffmpeg_binaries,
)

# Compatibility aliases
BlenderFfmpegPort = FfmpegPort
BlenderFfmpegRunner = FfmpegRunner


__all__ = [
    "MAX_OUTPUT_BYTES",
    "DEFAULT_TIMEOUT_SECONDS",
    "FfmpegResult",
    "BlenderFfmpegPort",
    "FfmpegPort",
    "SubprocessFfmpegPort",
    "FfmpegVersion",
    "FfmpegReceipt",
    "probe_ffmpeg_binaries",
    "BlenderFfmpegRunner",
    "FfmpegRunner",
]
