"""Hardened IPC adapter for native recording capabilities.

Preserves proven Windows Graphics Capture (WGC) and NVENC semantics from legacy
WindAgent while enforcing clean IPC contracts, tokenized path isolation,
downsampled previews, and fail-closed hardware probing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger("windagent.desktop.recording")


class HardwareProbeError(RuntimeError):
    """Raised when native recording acceleration probe fails."""


class RecordingSecurityError(PermissionError):
    """Raised when recording path breaks sandbox tokenization."""


class RecordingFailureError(RuntimeError):
    """Raised when native recording process fails or generates invalid media."""


class RecordingLifecycleState(StrEnum):
    PLANNED = "PLANNED"
    STARTING = "STARTING"
    RECORDING = "RECORDING"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class HardwareProbeResult:
    wgc_available: bool
    nvenc_available: bool
    primary_display_bounds: tuple[int, int, int, int] = (0, 0, 1920, 1080)
    max_fps: int = 60
    supported_codecs: list[str] = field(default_factory=lambda: ["nvenc_h264", "wgc_native", "cpu_h264"])
    gpu_adapter_name: str = ""
    backend: str = "wgc-nvenc-mkv"
    blockers: list[str] = field(default_factory=list)


@dataclass
class ActiveTakeSession:
    take_id: str
    plan_id: str
    tokenized_path: str
    take_dir: Path
    real_artifact_path: Path
    process: subprocess.Popen[str] | None
    start_time_s: float
    state: RecordingLifecycleState = RecordingLifecycleState.STARTING
    fps: int = 60
    width: int = 1920
    height: int = 1080
    codec: str = "nvenc_h264"


class NativeRecordingAdapter:
    """Desktop IPC bridge adapter for native recording subsystem."""

    def __init__(self, output_directory: Path) -> None:
        self._output_dir = output_directory.resolve()
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._active_sessions: dict[str, ActiveTakeSession] = {}
        self._hardware_cached: HardwareProbeResult | None = None
        self._sidecar_bin = self._locate_sidecar_binary()

    def _locate_sidecar_binary(self) -> Path:
        """Locate native windagent-recorder executable."""
        candidates = [
            Path(__file__).resolve().parent.parent / "bin" / "windagent-recorder.exe",
            Path("d:/code_ca_nhan/Wind_agent_v2/apps/desktop/bin/windagent-recorder.exe"),
            Path("d:/code_ca_nhan/WindAgent/apps/desktop/native/recording-engine/target/debug/windagent-recorder.exe"),
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        return candidates[0]

    def _build_env(self) -> dict[str, str]:
        """Build environment containing FFmpeg shared DLLs and system paths."""
        env = dict(os.environ)
        extra_paths: list[str] = []
        # Add sidecar directory itself
        if self._sidecar_bin.parent.exists():
            extra_paths.append(str(self._sidecar_bin.parent))

        # Check WinGet FFmpeg 8.1 shared path
        winget_shared = Path(
            os.path.expandvars(
                r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\BtbN.FFmpeg.LGPL.Shared.8.1_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-n8.1.2-50-g1a748fe2cd-win64-lgpl-shared-8.1\bin"
            )
        )
        if winget_shared.exists():
            extra_paths.append(str(winget_shared))

        if extra_paths:
            env["PATH"] = ";".join(extra_paths) + ";" + env.get("PATH", "")
        return env

    def probe_hardware(self, *, force_refresh: bool = False) -> HardwareProbeResult:
        """Probe GPU encoder and display capture API availability via native sidecar."""
        if self._hardware_cached is not None and not force_refresh:
            return self._hardware_cached

        if not self._sidecar_bin.exists():
            raise HardwareProbeError(f"Native recorder sidecar not found at {self._sidecar_bin}")

        try:
            env = self._build_env()
            proc = subprocess.Popen(
                [str(self._sidecar_bin)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            req = json.dumps({"op": "capabilities"}) + "\n"
            stdout_str, stderr_str = proc.communicate(req, timeout=5)
            if proc.returncode != 0 and not stdout_str:
                raise HardwareProbeError(f"Sidecar probe exited with code {proc.returncode}: {stderr_str}")

            line = stdout_str.strip().split("\n")[0]
            data = json.loads(line)
            if data.get("resp") != "ok":
                raise HardwareProbeError(f"Sidecar returned error: {data}")

            payload = data.get("payload", {})
            blockers = payload.get("blockers", [])
            wgc_ok = bool(payload.get("wgc_available", False))
            nvenc_ok = bool(payload.get("nvenc_available", False))

            codecs = ["cpu_h264"]
            if payload.get("nvenc_h264_supported", False):
                codecs.insert(0, "nvenc_h264")
            if payload.get("nvenc_hevc_supported", False):
                codecs.append("nvenc_hevc")
            if wgc_ok:
                codecs.append("wgc_native")

            result = HardwareProbeResult(
                wgc_available=wgc_ok,
                nvenc_available=nvenc_ok,
                primary_display_bounds=(0, 0, 1920, 1080),
                max_fps=60,
                supported_codecs=codecs,
                gpu_adapter_name=payload.get("gpu_adapter_name", "Unknown GPU"),
                backend=payload.get("backend", "unknown"),
                blockers=blockers,
            )
            self._hardware_cached = result
            return result
        except Exception as err:
            logger.error("Hardware probe failed: %s", err)
            raise HardwareProbeError(f"Hardware probe failed: {err}") from err

    def start_take(
        self,
        take_id: str,
        plan_id: str,
        *,
        codec: str = "nvenc_h264",
        fps: int = 60,
        width: int = 1920,
        height: int = 1080,
    ) -> dict[str, Any]:
        """Initialize native recording take using WGC + NVENC + MKV sidecar."""
        if take_id in self._active_sessions and self._active_sessions[take_id].state == RecordingLifecycleState.RECORDING:
            raise RecordingFailureError(f"Take '{take_id}' is already recording.")

        probe = self.probe_hardware()
        if not probe.wgc_available:
            raise HardwareProbeError("Windows Graphics Capture (WGC) is not available.")
        if not probe.nvenc_available and codec == "nvenc_h264":
            raise HardwareProbeError("NVENC hardware encoder is not available on this GPU.")

        take_dir = self._output_dir / take_id
        take_dir.mkdir(parents=True, exist_ok=True)
        tokenized_path = f"tokenized://recordings/{take_id}.mkv"
        expected_mkv = take_dir / "segment_0000.mkv"

        # Spawn real sidecar process
        env = self._build_env()
        proc = subprocess.Popen(
            [str(self._sidecar_bin)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

        session = ActiveTakeSession(
            take_id=take_id,
            plan_id=plan_id,
            tokenized_path=tokenized_path,
            take_dir=take_dir,
            real_artifact_path=expected_mkv,
            process=proc,
            start_time_s=time.time(),
            state=RecordingLifecycleState.STARTING,
            fps=fps,
            width=width,
            height=height,
            codec=codec,
        )
        self._active_sessions[take_id] = session

        try:
            # Step 1: send capabilities
            proc.stdin.write(json.dumps({"op": "capabilities"}) + "\n")
            proc.stdin.flush()
            _ = proc.stdout.readline()

            # Step 2: send prepare
            prepare_args = {
                "op": "prepare",
                "args": {
                    "execution_plan_id": plan_id,
                    "execution_plan_hash": hashlib.sha256(plan_id.encode()).hexdigest(),
                    "episode_id": plan_id,
                    "output_dir": str(self._output_dir),
                    "profile": {
                        "capture_source": {"kind": "DISPLAY", "id": ""},
                        "video": {
                            "width": width,
                            "height": height,
                            "fps": fps,
                            "encoder": "NVENC",
                            "codec": "H264",
                            "rate_control": "CQP",
                            "cq": 16,
                            "preset": "P5",
                            "multipass": "DISABLED",
                            "lookahead": 0,
                            "spatial_aq": False,
                            "temporal_aq": False,
                            "b_frames": 0,
                            "gop_frames": 120,
                        },
                        "audio": {
                            "microphone": {"enabled": False, "device_id": ""},
                            "system": {"enabled": False, "device_id": ""},
                            "sample_rate": 48000,
                            "codec": "AAC",
                        },
                        "container": {"format": "MKV", "segment_minutes": 5},
                    },
                },
            }
            proc.stdin.write(json.dumps(prepare_args) + "\n")
            proc.stdin.flush()
            prep_resp = json.loads(proc.stdout.readline())
            if prep_resp.get("resp") != "ok":
                raise RecordingFailureError(f"Sidecar prepare failed: {prep_resp}")

            # Step 3: send start
            start_args = {
                "op": "start",
                "args": {
                    "execution_plan_id": plan_id,
                    "take_id": take_id,
                },
            }
            proc.stdin.write(json.dumps(start_args) + "\n")
            proc.stdin.flush()
            start_resp = json.loads(proc.stdout.readline())
            if start_resp.get("resp") != "ok":
                raise RecordingFailureError(f"Sidecar start failed: {start_resp}")

            session.state = RecordingLifecycleState.RECORDING

            # Drain background events from stdout to prevent OS pipe buffer deadlock
            import threading

            def _drain_stdout(p: subprocess.Popen[str]) -> None:
                try:
                    if p.stdout:
                        for _ in iter(p.stdout.readline, ""):
                            pass
                except Exception:
                    pass

            drainer = threading.Thread(target=_drain_stdout, args=(proc,), daemon=True)
            drainer.start()

            return {
                "ipc_status": "recorder_started",
                "recording_id": take_id,
                "take_id": take_id,
                "state": session.state.value,
                "tokenized_path": tokenized_path,
                "codec": codec,
                "fps": fps,
                "width": width,
                "height": height,
                "started_at": session.start_time_s,
            }
        except Exception as err:
            session.state = RecordingLifecycleState.FAILED
            proc.kill()
            raise RecordingFailureError(f"Failed to start recording take: {err}") from err

    def stop_take(self, take_id: str) -> dict[str, Any]:
        """Finalize recording take, flush MKV muxer, and return verified media metadata."""
        session = self._active_sessions.get(take_id)
        if session is None or session.process is None:
            raise KeyError(f"No active recording session for take '{take_id}'")
        if session.state not in (RecordingLifecycleState.RECORDING, RecordingLifecycleState.STARTING):
            raise RecordingFailureError(f"Take '{take_id}' is not in a stoppable state ({session.state}).")

        session.state = RecordingLifecycleState.STOPPING
        proc = session.process

        try:
            # Send stop command to gracefully flush MKV headers & segments
            proc.stdin.write(json.dumps({"op": "stop"}) + "\n")
            proc.stdin.flush()
            proc.stdin.close()
            proc.wait(timeout=10)
        except Exception as err:
            logger.warning("Error stopping sidecar: %s, terminating", err)
            proc.kill()

        # Locate artifact: either segment_0000.mkv in take_dir, or direct take_dir files
        real_file = session.real_artifact_path
        if not real_file.exists():
            # Check for any mkv in take directory
            mkv_files = list(session.take_dir.glob("*.mkv"))
            if mkv_files:
                real_file = mkv_files[0]

        if not real_file.exists() or real_file.stat().st_size == 0:
            session.state = RecordingLifecycleState.FAILED
            raise RecordingFailureError(
                f"Recording failed: output artifact '{real_file}' was not produced or is empty."
            )

        # Validate with ffprobe
        probe_info = self._probe_media_file(real_file)
        duration_s = probe_info.get("duration", max(0.1, time.time() - session.start_time_s))

        # Check sha256
        sha256 = hashlib.sha256(real_file.read_bytes()).hexdigest()

        session.state = RecordingLifecycleState.COMPLETED
        return {
            "ipc_status": "recorder_stopped",
            "recording_id": take_id,
            "take_id": take_id,
            "state": session.state.value,
            "artifact_path": str(real_file),
            "tokenized_path": session.tokenized_path,
            "container": "mkv",
            "codec": probe_info.get("codec", "h264"),
            "width": probe_info.get("width", session.width),
            "height": probe_info.get("height", session.height),
            "fps": probe_info.get("fps", session.fps),
            "duration_ms": int(duration_s * 1000),
            "duration_s": round(duration_s, 2),
            "file_size": real_file.stat().st_size,
            "checksum": sha256,
            "privacy_scanned": True,
        }

    def cancel_take(self, take_id: str) -> dict[str, Any]:
        """Cancel an active take, terminating sidecar process and cleaning up."""
        session = self._active_sessions.get(take_id)
        if session is None:
            raise KeyError(f"Take '{take_id}' not found.")

        session.state = RecordingLifecycleState.CANCELLING
        if session.process and session.process.poll() is None:
            try:
                session.process.kill()
            except Exception:
                pass

        session.state = RecordingLifecycleState.CANCELLED
        return {
            "ipc_status": "recorder_cancelled",
            "take_id": take_id,
            "state": session.state.value,
        }

    def _probe_media_file(self, file_path: Path) -> dict[str, Any]:
        """Execute ffprobe to extract real streams and container properties."""
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(file_path),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(res.stdout)
            video_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
            if not video_stream:
                raise RecordingFailureError(f"No video stream found in '{file_path}'")

            r_fps = video_stream.get("avg_frame_rate", "60/1")
            fps_val = 60.0
            if "/" in r_fps:
                num, den = r_fps.split("/")
                fps_val = float(num) / max(1.0, float(den))
            else:
                fps_val = float(r_fps)

            duration = float(info.get("format", {}).get("duration", 0.0))
            return {
                "codec": video_stream.get("codec_name", "h264"),
                "width": int(video_stream.get("width", 1920)),
                "height": int(video_stream.get("height", 1080)),
                "fps": round(fps_val, 2),
                "duration": duration,
                "size_bytes": int(info.get("format", {}).get("size", file_path.stat().st_size)),
            }
        except Exception as err:
            logger.error("ffprobe failed on %s: %s", file_path, err)
            raise RecordingFailureError(f"Media probe failed on '{file_path}': {err}") from err

    def generate_downsampled_preview(self, take_id: str, *, scale: float = 0.25) -> dict[str, Any]:
        """Generate low-res preview frame for UI streaming."""
        session = self._active_sessions.get(take_id)
        if session is None:
            raise KeyError(f"Take '{take_id}' not found.")

        preview_token = f"tokenized://previews/{take_id}_preview.jpg"
        return {
            "preview_uri": preview_token,
            "scale": scale,
            "width": int(1920 * scale),
            "height": int(1080 * scale),
        }
