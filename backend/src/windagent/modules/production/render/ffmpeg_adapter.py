"""FFmpeg Media Renderer Adapter implementing MediaRendererPort."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from .contracts import (
    MediaValidationError,
    MediaValidationResult,
    RenderExecutionError,
    RenderPlan,
)

logger = logging.getLogger("windagent.production.render.ffmpeg")


class FFmpegRendererAdapter:
    """Renders compiled RenderPlan into real MP4 media using FFmpeg."""

    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe") -> None:
        self._ffmpeg = ffmpeg_bin
        self._ffprobe = ffprobe_bin

    async def render(self, plan: RenderPlan) -> MediaValidationResult:
        """Execute FFmpeg render process asynchronously and validate output."""
        plan.output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = self._build_ffmpeg_command(plan)
        logger.info("Executing FFmpeg render command: %s", " ".join(cmd))

        # Run render subprocess asynchronously
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr_bytes.decode("utf-8", errors="replace")
            # If NVENC failed, retry with libx264 CPU fallback
            if "nvenc" in " ".join(cmd).lower():
                logger.warning("NVENC render failed, retrying with libx264: %s", err_msg)
                cmd_fallback = self._build_ffmpeg_command(plan, force_cpu=True)
                proc_fb = await asyncio.create_subprocess_exec(
                    *cmd_fallback,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_fb, stderr_fb = await proc_fb.communicate()
                if proc_fb.returncode != 0:
                    raise RenderExecutionError(
                        f"FFmpeg render failed on both NVENC and libx264: {stderr_fb.decode('utf-8', errors='replace')}"
                    )
            else:
                raise RenderExecutionError(f"FFmpeg render process failed with code {proc.returncode}: {err_msg}")

        # Validate rendered media artifact
        return self._validate_rendered_artifact(plan.output_path, plan)

    def _build_ffmpeg_command(self, plan: RenderPlan, *, force_cpu: bool = False) -> list[str]:
        """Construct the complete FFmpeg command line from the RenderPlan."""
        cmd: list[str] = [self._ffmpeg, "-y", "-v", "error"]

        # Add inputs for each clip with seeking and duration
        for clip in plan.clips:
            cmd.extend([
                "-ss",
                f"{clip.in_point_s:.3f}",
                "-t",
                f"{clip.duration_s:.3f}",
                "-i",
                str(clip.source_path),
            ])

        # Build complex filtergraph for scaling and concatenation
        n_clips = len(plan.clips)
        filter_parts: list[str] = []
        concat_inputs: list[str] = []

        w = plan.encoding.width
        h = plan.encoding.height
        fps = plan.encoding.fps

        for idx in range(n_clips):
            # Scale each clip to target resolution while preserving aspect ratio, pad to 16:9, set fps & SAR
            filter_parts.append(
                f"[{idx}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps},setsar=1[v{idx}]"
            )
            concat_inputs.append(f"[v{idx}]")

        # Concat video streams
        filter_parts.append(f"{''.join(concat_inputs)}concat=n={n_clips}:v=1:a=0[outv]")
        full_filtergraph = ";".join(filter_parts)

        # Add silent audio track input BEFORE filter_complex and output maps
        cmd.extend([
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
        ])

        # Build filter_complex
        cmd.extend(["-filter_complex", full_filtergraph])

        # Output stream mappings
        cmd.extend([
            "-map",
            "[outv]",
            "-map",
            f"{n_clips}:a",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
        ])

        # Video encoding parameters
        use_nvenc = plan.encoding.use_nvenc and not force_cpu
        if use_nvenc:
            cmd.extend([
                "-c:v",
                "h264_nvenc",
                "-preset",
                "p5",
                "-cq",
                str(plan.encoding.crf),
                "-pix_fmt",
                plan.encoding.pixel_format,
            ])
        else:
            cmd.extend([
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                str(plan.encoding.crf),
                "-pix_fmt",
                plan.encoding.pixel_format,
            ])

        # MP4 container faststart
        cmd.extend(["-movflags", "+faststart", str(plan.output_path)])
        return cmd

    def _validate_rendered_artifact(self, artifact_path: Path, plan: RenderPlan) -> MediaValidationResult:
        """Perform comprehensive technical audit on the rendered media file."""
        if not artifact_path.exists():
            raise MediaValidationError(f"Rendered file does not exist: {artifact_path}")

        file_size = artifact_path.stat().st_size
        if file_size < 1000:
            raise MediaValidationError(f"Rendered file size is too small ({file_size} bytes): {artifact_path}")

        # Run ffprobe
        probe_cmd = [
            self._ffprobe,
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(artifact_path),
        ]
        try:
            res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            probe_data = json.loads(res.stdout)
        except Exception as err:
            raise MediaValidationError(f"ffprobe failed on rendered artifact: {err}") from err

        video_stream = next((s for s in probe_data.get("streams", []) if s.get("codec_type") == "video"), None)
        if not video_stream:
            raise MediaValidationError("Rendered media contains zero video streams.")

        audio_streams = [s for s in probe_data.get("streams", []) if s.get("codec_type") == "audio"]

        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        if width != plan.encoding.width or height != plan.encoding.height:
            raise MediaValidationError(
                f"Resolution mismatch: expected {plan.encoding.width}x{plan.encoding.height}, got {width}x{height}"
            )

        duration = float(probe_data.get("format", {}).get("duration", 0.0))
        if duration <= 0:
            raise MediaValidationError(f"Invalid duration reported by ffprobe: {duration}")

        r_fps = video_stream.get("r_frame_rate") or video_stream.get("avg_frame_rate", "60/1")
        fps_val = 60.0
        if "/" in r_fps:
            num, den = r_fps.split("/")
            fps_val = float(num) / max(1.0, float(den))
        else:
            fps_val = float(r_fps)

        # Verify decode cleanly
        decode_cmd = [self._ffmpeg, "-v", "error", "-i", str(artifact_path), "-f", "null", "-"]
        decode_res = subprocess.run(decode_cmd, capture_output=True, text=True)
        if decode_res.returncode != 0:
            raise MediaValidationError(f"Decode check failed on rendered file: {decode_res.stderr}")

        # Compute SHA-256
        sha256_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

        return MediaValidationResult(
            is_valid=True,
            artifact_path=str(artifact_path),
            container=plan.encoding.container,
            codec=video_stream.get("codec_name", "h264"),
            width=width,
            height=height,
            fps=round(fps_val, 2),
            duration_s=round(duration, 2),
            file_size_bytes=file_size,
            video_streams=1,
            audio_streams=len(audio_streams),
            decode_errors=0,
            checksum=sha256_hash,
            probe_raw=probe_data,
        )
