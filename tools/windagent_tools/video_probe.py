"""
Phase 15 — Real `ffprobe` video inspector (plan 04 §23.3).

The browser-driven generation adapters must never launch processes (Phase 13/14
architecture tests forbid subprocess inside adapter packages), so the real
decoder adapter lives here in the tools layer and is injected into
`VideoCandidateDownloader` at the composition root — exactly like the Phase 12
browser runtime owns the process boundary.

`FfprobeVideoInspector` follows the process-boundary rules (plan 04 §8.2):

- argv list, no shell interpolation;
- every command is time-bounded;
- stdout/stderr are bounded;
- missing binary / start failure / timeout / non-zero exit are classified;
- malformed input never raises — it yields a `VideoInspection` with
  `has_video_stream=False` (fail closed, plan §23.3).

Offline determinism: tests and the phase verifier inject a fake
`VideoInspectorPort`, so the gate never requires an ffprobe binary. This real
adapter is used by the live path and by optional smoke tests gated on
`shutil.which("ffprobe")`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from windagent_core.contracts.video_production.video_inspection import (
    VideoInspection,
    VideoInspectionError,
    VideoInspectorPort,
    VideoProbeUnavailableError,
)

DEFAULT_TIMEOUT_SECONDS = 20.0
MAX_OUTPUT_BYTES = 1_000_000


class FfprobeVideoInspector(VideoInspectorPort):
    """Runs a bounded `ffprobe` process to decode candidate bytes (§23.3)."""

    def __init__(
        self,
        *,
        ffprobe_path: Optional[str] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._ffprobe = ffprobe_path or shutil.which("ffprobe")
        self._timeout = timeout_seconds

    # ------------------------------------------------------------------
    def inspect(self, data: bytes) -> VideoInspection:
        """Decode candidate bytes with ffprobe (fail closed on any error)."""
        if not self._ffprobe:
            raise VideoProbeUnavailableError(
                "ffprobe binary not found; cannot technically validate video"
            )
        if not data:
            return VideoInspection(has_video_stream=False)

        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            return self._inspect_path(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    def _inspect_path(self, path: Path) -> VideoInspection:
        argv = [
            self._ffprobe,
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise VideoInspectionError("ffprobe timed out") from exc
        except OSError as exc:
            raise VideoInspectionError(
                f"ffprobe start failure: {exc}"
            ) from exc

        stdout = proc.stdout[:MAX_OUTPUT_BYTES]
        if proc.returncode != 0:
            # malformed / non-video input → fail closed, never raise
            return VideoInspection(
                has_video_stream=False,
                probe_error=proc.stderr[:500].decode("utf-8", "replace"),
            )

        try:
            payload = json.loads(stdout.decode("utf-8", "replace"))
        except ValueError as exc:
            raise VideoInspectionError(
                "ffprobe returned invalid JSON"
            ) from exc

        streams = payload.get("streams", []) or []
        video_streams = [
            s for s in streams
            if s.get("codec_type") == "video"
        ]
        if not video_streams:
            return VideoInspection(
                has_video_stream=False,
                container=payload.get("format", {}).get("format_name", ""),
            )
        stream = video_streams[0]
        duration = _as_float(
            stream.get("duration")
            or (payload.get("format", {}) or {}).get("duration")
        )
        width = stream.get("width")
        height = stream.get("height")
        frame_rate = _parse_frame_rate(stream.get("avg_frame_rate")
                                       or stream.get("r_frame_rate"))
        return VideoInspection(
            has_video_stream=True,
            duration_seconds=duration,
            width=width,
            height=height,
            frame_rate=frame_rate,
            container=payload.get("format", {}).get("format_name", ""),
            codec=stream.get("codec_name", ""),
        )


def _as_float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_frame_rate(value) -> Optional[float]:
    """Parse '30000/1001' or '30' into a float; None when malformed."""
    if value in (None, "", "0/0"):
        return None
    try:
        if "/" in value:
            num, _, den = value.partition("/")
            den = float(den) if den else 1.0
            if den == 0:
                return None
            return float(num) / den
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["FfprobeVideoInspector"]
