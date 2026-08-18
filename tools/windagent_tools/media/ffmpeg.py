"""
Generic FFmpeg/ffprobe runner for ASSEMBLE + VERIFY + TRANSCODE media boundaries.

Owns the secure FFmpeg process boundary:
- argv is ALWAYS a list (no shell interpolation);
- every command is time-bounded and stdout/stderr-bounded;
- the ffmpeg/ffprobe binary comes from config/detector, NEVER hard-coded;
- `FfmpegPort` is the fake-injectable seam so assembly and verification flows
  are fully contract-tested in CI without a real ffmpeg binary.
- `FfmpegVersion` is probed once and recorded so idempotency keys pin tool identity.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable

MAX_OUTPUT_BYTES = 1_000_000
DEFAULT_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class FfmpegResult:
    """Bounded result of one ffmpeg/ffprobe invocation."""

    argv: tuple
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    start_failed: bool = False

    @property
    def ok(self) -> bool:
        return not self.timed_out and not self.start_failed and self.returncode == 0

    def to_dict(self) -> dict:
        return {
            "argv": list(self.argv),
            "returncode": self.returncode,
            "stdout_chars": len(self.stdout),
            "stderr_chars": len(self.stderr),
            "timed_out": self.timed_out,
            "start_failed": self.start_failed,
        }


@runtime_checkable
class FfmpegPort(Protocol):
    """Run one bounded ffmpeg/ffprobe process (real or fake)."""

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> FfmpegResult:
        ...


class SubprocessFfmpegPort:
    """Real ffmpeg/ffprobe process: argv list, no shell, bounded output."""

    def __init__(
        self,
        *,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
    ) -> None:
        self._max_output_bytes = max_output_bytes

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> FfmpegResult:
        argv_tuple = tuple(str(a) for a in argv)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv_tuple,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as exc:
            return FfmpegResult(
                argv=argv_tuple,
                returncode=-1,
                stdout="",
                stderr=f"start failure: {exc}",
                start_failed=True,
            )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            with _suppress():
                proc.kill()
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            return FfmpegResult(
                argv=argv_tuple,
                returncode=-1,
                stdout="",
                stderr="timed out",
                timed_out=True,
            )
        return FfmpegResult(
            argv=argv_tuple,
            returncode=proc.returncode if proc.returncode is not None else -1,
            stdout=bytes(stdout_bytes[: self._max_output_bytes]).decode("utf-8", "replace"),
            stderr=bytes(stderr_bytes[: self._max_output_bytes]).decode("utf-8", "replace"),
        )


class _suppress:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return True


@dataclass(frozen=True)
class FfmpegVersion:
    """Probed ffmpeg/ffprobe identity (tool pin for idempotency)."""

    ffmpeg_path: str
    ffprobe_path: str
    ffmpeg_version_line: str = ""
    ffprobe_version_line: str = ""
    ffmpeg_version_hash: str = ""
    ffprobe_version_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "ffmpeg_path": self.ffmpeg_path,
            "ffprobe_path": self.ffprobe_path,
            "ffmpeg_version_line": self.ffmpeg_version_line,
            "ffprobe_version_line": self.ffprobe_version_line,
            "ffmpeg_version_hash": self.ffmpeg_version_hash,
            "ffprobe_version_hash": self.ffprobe_version_hash,
        }


@dataclass(frozen=True)
class FfmpegReceipt:
    """Audit receipt of one ASSEMBLE/VERIFY/TRANSCODE job."""

    job_id: str
    kind: str  # ASSEMBLE | VERIFY | TRANSCODE | CONCAT
    argv: tuple
    returncode: int
    output_hash: str = ""
    output_path: str = ""
    ffprobe: Dict = field(default_factory=dict)
    error: str = ""
    metadata: Dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.error

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "argv": list(self.argv),
            "returncode": self.returncode,
            "output_hash": self.output_hash,
            "output_path": self.output_path,
            "ffprobe": dict(self.ffprobe),
            "error": self.error,
            "metadata": dict(self.metadata),
        }


def _hash_line(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8", "replace")).hexdigest()


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def probe_ffmpeg_binaries(
    *,
    ffmpeg_path: Optional[str] = None,
    ffprobe_path: Optional[str] = None,
    port: Optional[FfmpegPort] = None,
) -> FfmpegVersion:
    """Locate ffmpeg/ffprobe (configured > PATH) and read their versions."""
    ffmpeg = ffmpeg_path or shutil.which("ffmpeg") or ""
    ffprobe = ffprobe_path or shutil.which("ffprobe") or ""

    def _version_line(binary: str) -> str:
        if not binary:
            return ""
        try:
            proc = subprocess.run(
                [binary, "-version"],
                capture_output=True,
                timeout=10.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if proc.returncode != 0:
            return ""
        lines = (proc.stdout or b"").splitlines()
        return lines[0].decode("utf-8", "replace").strip() if lines else ""

    ffmpeg_line = _version_line(ffmpeg)
    ffprobe_line = _version_line(ffprobe)
    return FfmpegVersion(
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        ffmpeg_version_line=ffmpeg_line,
        ffprobe_version_line=ffprobe_line,
        ffmpeg_version_hash=_hash_line(ffmpeg_line),
        ffprobe_version_hash=_hash_line(ffprobe_line),
    )


class FfmpegRunner:
    """Generic media processor: image sequence assembly, clip concat, transcoding, verification."""

    def __init__(
        self,
        *,
        version: FfmpegVersion,
        port: Optional[FfmpegPort] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._version = version
        self._port = port or SubprocessFfmpegPort()
        self._timeout = timeout_seconds

    @property
    def version(self) -> FfmpegVersion:
        return self._version

    def tool_hash(self) -> str:
        """Tool pin for idempotency keys (different ffmpeg -> different output)."""
        return hashlib.sha256(
            f"ffmpeg:{self._version.ffmpeg_version_hash}:"
            f"ffprobe:{self._version.ffprobe_version_hash}".encode("utf-8")
        ).hexdigest()

    # ------------------------------------------------------------------
    async def assemble_frames(
        self,
        *,
        job_id: str,
        workspace: str,
        frame_start: int,
        frame_end: int,
        fps: int,
        extension: str = "png",
        output_filename: str = "final.mp4",
    ) -> FfmpegReceipt:
        """FFmpeg image-sequence -> MP4."""
        ws = Path(workspace)
        output_path = ws / output_filename
        pattern = str(ws / f"frame_%04d.{extension}")
        argv = [
            self._version.ffmpeg_path,
            "-y",
            "-framerate",
            str(fps),
            "-start_number",
            str(frame_start),
            "-i",
            pattern,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        result = await self._port.run(argv, timeout_seconds=self._timeout)
        receipt = FfmpegReceipt(
            job_id=job_id,
            kind="ASSEMBLE",
            argv=tuple(argv),
            returncode=result.returncode,
            output_path=str(output_path),
            error="" if result.ok else (result.stderr or result.stdout)[:500],
            metadata={"frame_start": frame_start, "frame_end": frame_end, "fps": fps},
        )
        if result.ok and output_path.is_file():
            receipt = FfmpegReceipt(
                job_id=job_id,
                kind="ASSEMBLE",
                argv=tuple(argv),
                returncode=0,
                output_hash=_sha256_file(output_path),
                output_path=str(output_path),
                metadata={"frame_start": frame_start, "frame_end": frame_end, "fps": fps},
            )
        return receipt

    # ------------------------------------------------------------------
    async def assemble_clips(
        self,
        *,
        job_id: str,
        clip_paths: Sequence[str | Path],
        output_path: str | Path,
        fps: int = 30,
        an_flag: bool = True,
    ) -> FfmpegReceipt:
        """Concatenate multiple MP4 takes/clips into a single continuous visual master."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        
        # Build concat demuxer file or complex filter
        concat_file = out.parent / f"{job_id}_concat.txt"
        lines = [f"file '{Path(p).resolve().as_posix()}'" for p in clip_paths]
        concat_file.write_text("\n".join(lines), encoding="utf-8")

        argv = [
            self._version.ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
        ]
        if an_flag:
            argv.append("-an")  # Zero audio enforcement
        argv.append(str(out))

        result = await self._port.run(argv, timeout_seconds=self._timeout)
        concat_file.unlink(missing_ok=True)

        receipt = FfmpegReceipt(
            job_id=job_id,
            kind="CONCAT",
            argv=tuple(argv),
            returncode=result.returncode,
            output_path=str(out),
            error="" if result.ok else (result.stderr or result.stdout)[:500],
            metadata={"clip_count": len(clip_paths), "fps": fps, "zero_audio": an_flag},
        )
        if result.ok and out.is_file():
            receipt = FfmpegReceipt(
                job_id=job_id,
                kind="CONCAT",
                argv=tuple(argv),
                returncode=0,
                output_hash=_sha256_file(out),
                output_path=str(out),
                metadata={"clip_count": len(clip_paths), "fps": fps, "zero_audio": an_flag},
            )
        return receipt

    # ------------------------------------------------------------------
    async def transcode_resolution(
        self,
        *,
        job_id: str,
        input_path: str | Path,
        output_path: str | Path,
        target_resolution: str = "1920x1080",
        fps: int = 30,
    ) -> FfmpegReceipt:
        """Transcode visual master to downstream delivery profile (e.g. 1440p -> 1080p)."""
        inp = Path(input_path)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        width, height = target_resolution.split("x")
        argv = [
            self._version.ffmpeg_path,
            "-y",
            "-i",
            str(inp),
            "-vf",
            f"scale={width}:{height}:flags=lanczos",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-an",
            str(out),
        ]
        result = await self._port.run(argv, timeout_seconds=self._timeout)
        receipt = FfmpegReceipt(
            job_id=job_id,
            kind="TRANSCODE",
            argv=tuple(argv),
            returncode=result.returncode,
            output_path=str(out),
            error="" if result.ok else (result.stderr or result.stdout)[:500],
            metadata={"target_resolution": target_resolution, "fps": fps},
        )
        if result.ok and out.is_file():
            receipt = FfmpegReceipt(
                job_id=job_id,
                kind="TRANSCODE",
                argv=tuple(argv),
                returncode=0,
                output_hash=_sha256_file(out),
                output_path=str(out),
                metadata={"target_resolution": target_resolution, "fps": fps},
            )
        return receipt

    # ------------------------------------------------------------------
    async def verify_mp4(
        self,
        *,
        job_id: str,
        workspace: str = "",
        media_path: Optional[str | Path] = None,
        output_filename: str = "final.mp4",
    ) -> FfmpegReceipt:
        """ffprobe the final MP4: streams, dimensions, duration, frame count."""
        if media_path:
            mp = Path(media_path)
        else:
            ws = Path(workspace)
            mp = ws / output_filename

        if not mp.is_file():
            return FfmpegReceipt(
                job_id=job_id,
                kind="VERIFY",
                argv=(),
                returncode=1,
                error=f"final MP4 missing: {mp}",
            )
        argv = [
            self._version.ffprobe_path,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(mp),
        ]
        result = await self._port.run(argv, timeout_seconds=self._timeout)
        probe: Dict = {}
        if result.ok and result.stdout.strip():
            try:
                probe = json.loads(result.stdout)
            except (ValueError, TypeError):
                probe = {}
        return FfmpegReceipt(
            job_id=job_id,
            kind="VERIFY",
            argv=tuple(argv),
            returncode=result.returncode,
            output_path=str(mp),
            output_hash=_sha256_file(mp),
            ffprobe=probe,
            error="" if result.ok else (result.stderr or result.stdout)[:500],
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
