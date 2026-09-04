"""End-to-end integration test: Real Recording (WGC + NVENC) -> Ingest -> EDL -> Render (MP4)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from apps.desktop.src.recording_adapter import NativeRecordingAdapter
from windagent.modules.production.render import RenderJobState, RenderService


@pytest.mark.asyncio
async def test_record_to_render_integration(tmp_path: Path) -> None:
    """End-to-end pipeline: Live desktop capture to MKV, EDL assembly, and final MP4 render."""
    evidence_dir = Path("artifacts/video_production_repair/integration")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    recordings_dir = tmp_path / "recordings"
    adapter = NativeRecordingAdapter(recordings_dir)

    # 1. Start live screen recording
    take_id = "take-e2e-integ"
    plan_id = "plan-e2e-integ"
    start_info = adapter.start_take(take_id, plan_id, fps=60)
    assert start_info["ipc_status"] == "recorder_started"

    # Capture 5 seconds of real desktop frames
    await asyncio.sleep(5.0)

    # 2. Stop take and obtain real MKV artifact
    stop_info = adapter.stop_take(take_id)
    assert stop_info["ipc_status"] == "recorder_stopped"
    assert stop_info["file_size"] > 100_000
    mkv_path = Path(stop_info["artifact_path"])
    assert mkv_path.exists()

    # 3. Assemble domain EDL using segments from this real MKV recording
    mkv_hash = stop_info["checksum"]
    edl_data = {
        "edl_id": "EDL-E2E-INTEG",
        "title": "E2E Integration EDL",
        "items": [
            {
                "shot_id": "SCENE-01",
                "clip_hash": mkv_hash,
                "source_path": str(mkv_path),
                "in_point": 0.5,
                "out_point": 2.5,
                "target_duration": 2.0,
            },
            {
                "shot_id": "SCENE-02",
                "clip_hash": mkv_hash,
                "source_path": str(mkv_path),
                "in_point": 1.0,
                "out_point": 3.0,
                "target_duration": 2.0,
            },
        ],
        "metadata": {
            "source_take": take_id,
            "total_duration_s": 4.0,
        },
    }

    # 4. Render final MP4 via RenderService
    output_mp4 = tmp_path / "final_e2e_video.mp4"
    service = RenderService()
    state, validation, err = await service.execute_render_job(
        job_id="job-e2e-integ-01",
        edl_data=edl_data,
        output_path=output_mp4,
    )

    assert state == RenderJobState.READY, f"Render failed: {err}"
    assert validation is not None
    assert validation.is_valid
    assert output_mp4.exists()
    assert validation.file_size_bytes > 50_000
    assert validation.width == 1920
    assert validation.fps >= 50.0
    assert validation.decode_errors == 0

    # 5. Write evidence report
    report = {
        "pipeline": "Recording -> Ingest -> EDL -> Render",
        "status": "PASS",
        "recording_take": {
            "take_id": take_id,
            "artifact_path": str(mkv_path),
            "file_size": stop_info["file_size"],
            "duration_s": stop_info["duration_s"],
            "checksum": stop_info["checksum"],
            "measured_fps": stop_info["fps"],
        },
        "final_render": {
            "output_path": str(output_mp4),
            "file_size_bytes": validation.file_size_bytes,
            "duration_s": validation.duration_s,
            "width": validation.width,
            "height": validation.height,
            "fps": validation.fps,
            "codec": validation.codec,
            "container": validation.container,
            "decode_errors": validation.decode_errors,
            "checksum": validation.checksum,
        },
    }
    (evidence_dir / "record_to_render_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
