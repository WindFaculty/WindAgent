"""
WindAgent Media Infrastructure Package.

Provides generic, bounded, and secure FFmpeg and media processing process boundaries.
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

__all__ = [
    "MAX_OUTPUT_BYTES",
    "DEFAULT_TIMEOUT_SECONDS",
    "FfmpegResult",
    "FfmpegPort",
    "SubprocessFfmpegPort",
    "FfmpegVersion",
    "FfmpegReceipt",
    "probe_ffmpeg_binaries",
    "FfmpegRunner",
]
