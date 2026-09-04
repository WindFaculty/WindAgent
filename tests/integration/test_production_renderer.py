"""Integration tests for Production Media Renderer (EDL Compiler, FFmpeg Adapter, Validation)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from windagent.modules.production.render import (
    EdlCompiler,
    FFmpegRendererAdapter,
    MediaValidationError,
    RenderEncodingSpec,
    RenderJobState,
    RenderPlan,
    RenderService,
    RenderValidationError,
)


def _generate_test_clip(path: Path, *, duration_s: int = 2, color: str = "blue", text: str = "TEST") -> Path:
    """Generate a genuine H264 MP4 clip for testing using FFmpeg lavfi testsrc."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration_s}:size=1920x1080:rate=60",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    subprocess.run(cmd, check=True)
    return path


@pytest.mark.asyncio
async def test_three_clip_render(tmp_path: Path) -> None:
    """Focused test: three_clip_render_test producing a real MP4 from three distinct video clips."""
    evidence_dir = Path("artifacts/video_production_repair/render")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create 3 genuine test clips
    clip1 = _generate_test_clip(tmp_path / "clip_01.mp4", duration_s=2, text="SCENE-01")
    clip2 = _generate_test_clip(tmp_path / "clip_02.mp4", duration_s=3, text="SCENE-02")
    clip3 = _generate_test_clip(tmp_path / "clip_03.mp4", duration_s=2, text="SCENE-03")

    hash1 = hashlib.sha256(clip1.read_bytes()).hexdigest()
    hash2 = hashlib.sha256(clip2.read_bytes()).hexdigest()
    hash3 = hashlib.sha256(clip3.read_bytes()).hexdigest()

    # 2. Build domain EDL structure
    edl_data = {
        "edl_id": "EDL-TEST-3CLIPS",
        "title": "Three Clip Test",
        "items": [
            {"shot_id": "SHOT-1", "clip_hash": hash1, "source_path": str(clip1), "in_point": 0.0, "out_point": 2.0, "target_duration": 2.0},
            {"shot_id": "SHOT-2", "clip_hash": hash2, "source_path": str(clip2), "in_point": 0.0, "out_point": 3.0, "target_duration": 3.0},
            {"shot_id": "SHOT-3", "clip_hash": hash3, "source_path": str(clip3), "in_point": 0.0, "out_point": 2.0, "target_duration": 2.0},
        ],
        "metadata": {"total_duration_s": 7.0},
    }

    output_mp4 = tmp_path / "three_clip_output.mp4"

    # 3. Compile and Render via RenderService
    service = RenderService()
    state, validation, err = await service.execute_render_job(
        job_id="job-3clip-01",
        edl_data=edl_data,
        output_path=output_mp4,
    )

    assert state == RenderJobState.READY, f"Render failed: {err}"
    assert validation is not None
    assert validation.is_valid
    assert output_mp4.exists()
    assert validation.file_size_bytes > 50_000
    assert validation.width == 1920
    assert validation.height == 1080
    assert validation.fps == 60.0
    assert abs(validation.duration_s - 7.0) < 0.5
    assert validation.decode_errors == 0

    # Save evidence artifacts
    (evidence_dir / "render_plan.json").write_text(
        json.dumps(
            {
                "job_id": "job-3clip-01",
                "clips_count": 3,
                "total_duration_s": 7.0,
                "output_path": str(output_mp4),
                "encoding": {"width": 1920, "height": 1080, "fps": 60, "codec": "h264"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (evidence_dir / "ffprobe.json").write_text(json.dumps(validation.probe_raw, indent=2), encoding="utf-8")
    (evidence_dir / "ffmpeg_command_or_graph.txt").write_text(
        f"Output MP4: {output_mp4}\nSize: {validation.file_size_bytes} bytes\nDuration: {validation.duration_s}s\nFPS: {validation.fps}\nChecksum: {validation.checksum}",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_edl_compiler_validation(tmp_path: Path) -> None:
    """Validate EDL Compiler fail-closed checks on invalid or missing assets."""
    compiler = EdlCompiler()

    # Case 1: Missing items
    with pytest.raises(RenderValidationError):
        compiler.compile(job_id="j1", edl_data={"items": []}, output_path=tmp_path / "out.mp4")

    # Case 2: Missing asset file on disk
    with pytest.raises(RenderValidationError, match="Source media file.*does not exist"):
        compiler.compile(
            job_id="j2",
            edl_data={
                "items": [
                    {"shot_id": "S1", "clip_hash": "abc", "source_path": str(tmp_path / "nonexistent.mp4"), "target_duration": 5.0}
                ]
            },
            output_path=tmp_path / "out.mp4",
        )

    # Case 3: Negative duration
    existing_file = _generate_test_clip(tmp_path / "dummy.mp4", duration_s=1)
    with pytest.raises(RenderValidationError, match=r"Illegal.*(negative|zero)"):
        compiler.compile(
            job_id="j3",
            edl_data={
                "items": [
                    {"shot_id": "S1", "clip_hash": "abc", "source_path": str(existing_file), "target_duration": -1.0}
                ]
            },
            output_path=tmp_path / "out.mp4",
        )


@pytest.mark.asyncio
async def test_render_failure_handling(tmp_path: Path) -> None:
    """Validate that corrupted source clips cause fail-closed RENDER_FAILED / VALIDATION_FAILED state."""
    corrupted_clip = tmp_path / "corrupted.mp4"
    corrupted_clip.write_bytes(b"THIS IS NOT A VALID MP4 VIDEO FILE")
    clip_hash = hashlib.sha256(corrupted_clip.read_bytes()).hexdigest()

    edl_data = {
        "items": [
            {"shot_id": "S1", "clip_hash": clip_hash, "source_path": str(corrupted_clip), "target_duration": 2.0}
        ]
    }

    service = RenderService()
    state, validation, err = await service.execute_render_job(
        job_id="job-fail-01",
        edl_data=edl_data,
        output_path=tmp_path / "corrupted_out.mp4",
    )

    assert state in (RenderJobState.RENDER_FAILED, RenderJobState.VALIDATION_FAILED)
    assert validation is None
    assert err is not None
