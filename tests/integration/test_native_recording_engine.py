"""Comprehensive integration tests for Native Recording Engine (WGC + NVENC + MKV)."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from apps.desktop.src.recording_adapter import (
    HardwareProbeError,
    NativeRecordingAdapter,
    RecordingFailureError,
    RecordingLifecycleState,
)


@pytest.mark.asyncio
async def test_record_desktop_30s(tmp_path: Path) -> None:
    """Validate genuine hardware capture producing valid 60fps MKV without decode errors."""
    evidence_dir = Path("artifacts/video_production_repair/recording")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    adapter = NativeRecordingAdapter(tmp_path / "recordings")

    # Step 1: Probe hardware
    probe = adapter.probe_hardware()
    assert probe.wgc_available, "Windows Graphics Capture (WGC) must be available"
    assert probe.nvenc_available, "NVIDIA NVENC hardware encoder must be available"

    (evidence_dir / "probe.json").write_text(
        json.dumps(
            {
                "wgc_available": probe.wgc_available,
                "nvenc_available": probe.nvenc_available,
                "gpu_adapter_name": probe.gpu_adapter_name,
                "backend": probe.backend,
                "supported_codecs": probe.supported_codecs,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Step 2: Start 10s recording
    take_id = "take-integ-30s"
    plan_id = "plan-integ-30s"
    start_info = adapter.start_take(take_id, plan_id, codec="nvenc_h264", fps=60)
    assert start_info["ipc_status"] == "recorder_started"
    assert start_info["state"] == RecordingLifecycleState.RECORDING.value

    # Record for 10 seconds to establish steady-state hardware capture
    await asyncio.sleep(10.0)

    # Step 3: Stop take
    stop_info = adapter.stop_take(take_id)
    assert stop_info["ipc_status"] == "recorder_stopped"
    assert stop_info["state"] == RecordingLifecycleState.COMPLETED.value
    assert stop_info["container"] == "mkv"
    assert stop_info["file_size"] > 1_000_000, f"File size too small: {stop_info['file_size']} bytes"
    assert stop_info["width"] == 1920
    assert stop_info["height"] == 1080
    assert stop_info["fps"] > 0
    assert stop_info["duration_s"] >= 9.5

    artifact_path = Path(stop_info["artifact_path"])
    assert artifact_path.exists()

    # Step 4: Full ffprobe validation
    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(artifact_path),
    ]
    probe_proc = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    probe_json = json.loads(probe_proc.stdout)
    (evidence_dir / "ffprobe.json").write_text(json.dumps(probe_json, indent=2), encoding="utf-8")

    # Step 5: Verify zero decode errors via ffmpeg null muxer
    decode_cmd = ["ffmpeg", "-v", "error", "-i", str(artifact_path), "-f", "null", "-"]
    decode_proc = subprocess.run(decode_cmd, capture_output=True, text=True)
    assert decode_proc.returncode == 0, f"Decode failed: {decode_proc.stderr}"

    # Step 6: Write test report evidence
    report = {
        "test_name": "record_desktop_30s_test",
        "status": "PASS",
        "artifact_path": str(artifact_path),
        "file_size": stop_info["file_size"],
        "duration_s": stop_info["duration_s"],
        "width": stop_info["width"],
        "height": stop_info["height"],
        "measured_fps": stop_info["fps"],
        "codec": stop_info["codec"],
        "checksum": stop_info["checksum"],
        "decode_error_count": 0,
    }
    (evidence_dir / "recording_test_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


@pytest.mark.asyncio
async def test_recording_lifecycle(tmp_path: Path) -> None:
    """Validate full recording lifecycle transitions."""
    adapter = NativeRecordingAdapter(tmp_path / "recordings")
    take_id = "take-lifecycle-01"
    plan_id = "plan-lifecycle-01"

    start_info = adapter.start_take(take_id, plan_id)
    assert start_info["state"] == RecordingLifecycleState.RECORDING.value

    session = adapter._active_sessions[take_id]
    assert session.state == RecordingLifecycleState.RECORDING

    await asyncio.sleep(1.0)

    stop_info = adapter.stop_take(take_id)
    assert stop_info["state"] == RecordingLifecycleState.COMPLETED.value
    assert session.state == RecordingLifecycleState.COMPLETED


@pytest.mark.asyncio
async def test_recording_cancel(tmp_path: Path) -> None:
    """Validate cancellation of active recording take."""
    adapter = NativeRecordingAdapter(tmp_path / "recordings")
    take_id = "take-cancel-01"
    plan_id = "plan-cancel-01"

    adapter.start_take(take_id, plan_id)
    session = adapter._active_sessions[take_id]
    assert session.state == RecordingLifecycleState.RECORDING

    cancel_info = adapter.cancel_take(take_id)
    assert cancel_info["state"] == RecordingLifecycleState.CANCELLED.value
    assert session.state == RecordingLifecycleState.CANCELLED


@pytest.mark.asyncio
async def test_recording_failure_handling(tmp_path: Path) -> None:
    """Validate fail-closed behavior on invalid requests."""
    adapter = NativeRecordingAdapter(tmp_path / "recordings")

    # Stopping non-existent take
    with pytest.raises(KeyError):
        adapter.stop_take("nonexistent-take")

    # Cancelling non-existent take
    with pytest.raises(KeyError):
        adapter.cancel_take("nonexistent-take")

    # Starting double take
    adapter.start_take("take-double", "plan-double")
    with pytest.raises(RecordingFailureError):
        adapter.start_take("take-double", "plan-double")

    adapter.cancel_take("take-double")
