"""Unit tests for Desktop supervisor and NativeRecordingAdapter."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from apps.desktop.src.config import DesktopConfig
from apps.desktop.src.desktop_app import DesktopSupervisor
from apps.desktop.src.recording_adapter import NativeRecordingAdapter


@pytest.mark.asyncio
async def test_desktop_supervisor_lifecycle(tmp_path: Path) -> None:
    config = DesktopConfig(
        api_port=8005,
        tokenized_recordings_dir=tmp_path / "recordings",
        enable_tray=False,
    )
    supervisor = DesktopSupervisor(config)

    assert not supervisor.get_status().is_running
    await supervisor.start()

    status = supervisor.get_status()
    assert status.is_running
    assert status.api_online
    assert status.worker_online

    # IPC Status query
    res = await supervisor.handle_ipc_message({"command": "status"})
    assert res["status"] == "ok"
    assert res["is_running"]

    await supervisor.stop()
    assert not supervisor.get_status().is_running


@pytest.mark.asyncio
async def test_native_recording_adapter_flow(tmp_path: Path) -> None:
    adapter = NativeRecordingAdapter(tmp_path / "recordings")
    probe = adapter.probe_hardware()
    assert probe.wgc_available
    assert probe.nvenc_available
    assert "nvenc_h264" in probe.supported_codecs

    # Start take
    take_info = adapter.start_take("take-01", "plan-01", codec="nvenc_h264", fps=60)
    assert take_info["ipc_status"] == "recorder_started"
    assert take_info["tokenized_path"].startswith("tokenized://recordings/")

    # Generate preview
    preview = adapter.generate_downsampled_preview("take-01", scale=0.25)
    assert preview["scale"] == 0.25
    assert preview["width"] == 480

    # Allow real frames to be captured
    await asyncio.sleep(1.0)

    # Stop take
    stop_info = adapter.stop_take("take-01")
    assert stop_info["ipc_status"] == "recorder_stopped"
    assert stop_info["privacy_scanned"]
    assert stop_info["duration_s"] > 0


@pytest.mark.asyncio
async def test_desktop_ipc_recording_commands(tmp_path: Path) -> None:
    config = DesktopConfig(tokenized_recordings_dir=tmp_path / "recordings")
    supervisor = DesktopSupervisor(config)
    await supervisor.start()

    # Hardware probe via IPC
    probe_res = await supervisor.handle_ipc_message({"command": "probe_hardware"})
    assert probe_res["status"] == "ok"
    assert probe_res["nvenc_available"]

    # Start take via IPC
    start_res = await supervisor.handle_ipc_message({
        "command": "start_take",
        "take_id": "take-ipc-1",
        "plan_id": "plan-ipc-1",
    })
    assert start_res["ipc_status"] == "recorder_started"

    # Allow real frames to be captured
    await asyncio.sleep(1.0)

    # Stop take via IPC
    stop_res = await supervisor.handle_ipc_message({
        "command": "stop_take",
        "take_id": "take-ipc-1",
    })
    assert stop_res["ipc_status"] == "recorder_stopped"

    # Unknown command
    err_res = await supervisor.handle_ipc_message({"command": "nonexistent_cmd"})
    assert err_res["status"] == "error"

    await supervisor.stop()
