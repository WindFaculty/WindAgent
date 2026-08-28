#!/usr/bin/env python3
"""soak_staircase.py - Phase 19 progressive soak benchmark (ban_ke_hoach_v1.md Section 23).

Drives the real recording-engine sidecar over the frozen JSONL stdio IPC:

    capabilities -> prepare(profile V2 1080p60) -> start -> status sampling @2Hz
    -> stop -> verify segments.

Staircase: each stage runs ONLY if the previous one PASSED. Stage PASS requires
the sidecar to answer every op, at least one playable MKV segment per manifest,
and max sampled dropped_pct within the frozen performance gate
(RECORDING_PERFORMANCE_GATES.dropped_frames_pct_max = 0.1).

Samples land in <stage>/samples.jsonl and every unsolicited engine event in
<stage>/events.jsonl; <root>/soak_report.json summarizes P50/P95/P99/max so the
"safe continuous recording duration" is decided from measured data - never
assumed (Section 24).

Why Python and not PowerShell: Windows PowerShell 5.1's Process.StandardInput
injects a UTF-8 BOM as the first bytes of the pipe, which serde_json rejects;
python writes raw UTF-8 with no preamble.

Usage:
    .venv/Scripts/python.exe scripts/live_record/soak_staircase.py --stages 5,15,30
"""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DEFAULT_BIN = REPO / "apps/desktop/native/recording-engine/target/release/windagent-recorder.exe"

# Frozen acceptance gate (contracts/recordingEngine.ts RECORDING_PERFORMANCE_GATES).
MAX_DROPPED_PCT = 0.1

# Engine profile V2 - quality-first default (ban_ke_hoach_v1.md Section 4).
PROFILE_V2: dict[str, Any] = {
    "capture_source": {"kind": "DISPLAY", "id": ""},
    "video": {
        "width": 1920,
        "height": 1080,
        "fps": 60,
        "encoder": "NVENC",
        "codec": "H264",
        "rate_control": "CQP",
        "cq": 16,
        "preset": "P7",
        "multipass": "FULL_RES",
        # Mirrors DEFAULT_ENGINE_PROFILE: lookahead=0 — no B-frames means
        # lookahead only delays packets (crash window) and starves sparse
        # idle-screen frame delivery.
        "lookahead": 0,
        "spatial_aq": True,
        "temporal_aq": True,
        # Mirrors DEFAULT_ENGINE_PROFILE: b_frames=0 — see engine lib.rs
        # (sync-mode single-bitstream B-chains complete out of decode order).
        "b_frames": 0,
        "gop_frames": 120,
    },
    "audio": {
        "microphone": {"enabled": True, "device_id": ""},
        "system": {"enabled": True, "device_id": ""},
        "sample_rate": 48000,
        "codec": "AAC",
    },
    "container": {"format": "MKV", "segment_minutes": 5},
}


class SidecarError(RuntimeError):
    pass


class Sidecar:
    """One recording-engine process speaking the frozen JSONL stdio protocol."""

    def __init__(self, bin_path: Path, events_path: Path | None = None):
        self.proc = subprocess.Popen(
            [str(bin_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self._events_path = events_path
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        for raw in iter(self.proc.stdout.readline, b""):
            self._lines.put(raw.decode("utf-8", "replace").strip())
        self._lines.put(None)

    def request(self, op: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        """Send one request; return its payload. Events seen en route are archived."""
        assert self.proc.stdin is not None
        wire = json.dumps(op, separators=(",", ":"))
        self.proc.stdin.write(wire.encode("utf-8") + b"\n")
        self.proc.stdin.flush()

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timeout waiting for response to op '{op.get('op')}'")
            try:
                line = self._lines.get(timeout=min(remaining, 0.25))
            except queue.Empty:
                continue
            if line is None:
                raise SidecarError("sidecar exited before answering")
            value = json.loads(line)
            if "resp" in value:
                if value["resp"] != "ok":
                    raise SidecarError(
                        f"op '{op.get('op')}' FAILED: [{value.get('code')}] {value.get('message')}"
                    )
                return value.get("payload") or {}
            # Unsolicited event - archive it, keep waiting for the response.
            if self._events_path is not None:
                with open(self._events_path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")

    def close(self) -> int:
        """EOF on stdin means 'shut down'; returns the exit code."""
        if self.proc.poll() is None:
            assert self.proc.stdin is not None
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        return self.proc.returncode or 0


def percentile(sorted_vals: list[float], p: float) -> float:
    """Nearest-rank percentile."""
    idx = max(0, min(len(sorted_vals) - 1, math.ceil(p * len(sorted_vals)) - 1))
    return sorted_vals[idx]


def stats(values: list[float]) -> dict[str, Any] | None:
    if not values:
        return None
    srt = sorted(values)
    return {
        "p50": round(percentile(srt, 0.50), 3),
        "p95": round(percentile(srt, 0.95), 3),
        "p99": round(percentile(srt, 0.99), 3),
        "max": round(srt[-1], 3),
        "n": len(srt),
    }


def run_stage(
    minutes: int,
    root: Path,
    bin_path: Path,
    sample_interval: float,
    ffprobe: str | None,
) -> dict[str, Any]:
    name = f"stage_{minutes}min"
    stage_dir = root / name
    stage_dir.mkdir(parents=True, exist_ok=True)
    samples_path = stage_dir / "samples.jsonl"
    events_path = stage_dir / "events.jsonl"
    events_path.write_text("", encoding="utf-8")

    print()
    print(f"== {name} : prepare 1080p60 NVENC CQP16, MKV/5min ==")
    result: dict[str, Any] = {
        "stage": name,
        "minutes": minutes,
        "pass": False,
        "reason": None,
        "segments": [],
        "max_dropped_pct": None,
    }

    sc = Sidecar(bin_path, events_path)
    try:
        caps = sc.request({"op": "capabilities"})
        if not caps.get("nvenc_available"):
            raise SidecarError("NVENC unavailable on this machine - soak refuses to run (fail-closed)")

        out_dir = str(stage_dir.resolve()).replace("\\", "/")
        sc.request(
            {
                "op": "prepare",
                "args": {
                    "execution_plan_id": "plan_soak",
                    "execution_plan_hash": "0" * 64,
                    "episode_id": "ep_soak",
                    "output_dir": out_dir,
                    "profile": PROFILE_V2,
                },
            }
        )
        sc.request(
            {
                "op": "start",
                "args": {
                    "execution_plan_id": "plan_soak",
                    "take_id": f"take_soak_{minutes}m",
                },
            }
        )
        print(f"   recording... (sampling every {sample_interval:g}s)")

        end_at = time.monotonic() + minutes * 60
        while time.monotonic() < end_at:
            time.sleep(sample_interval)
            if sc.proc.poll() is not None:
                raise SidecarError(f"sidecar died mid-stage (exit {sc.proc.returncode})")
            status = sc.request({"op": "status"}, timeout=15)
            sample = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "state": status.get("state"),
                "elapsed_sec": status.get("elapsed_sec"),
                "capture_fps": status.get("capture_fps"),
                "encode_fps": status.get("encode_fps"),
                "frames_dropped": status.get("frames_dropped"),
                "dropped_pct": status.get("dropped_pct"),
                "bitrate_mbps": status.get("bitrate_mbps"),
                "disk_write_mbps": status.get("disk_write_mbps"),
                "resource_stage": status.get("resource_stage"),
                "nvenc_status": status.get("nvenc_status"),
                "segment_index": status.get("current_segment_index"),
            }
            with open(samples_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(sample, separators=(",", ":")) + "\n")
            print(
                f"   t={status.get('elapsed_sec', 0):>6}s"
                f"  cap={status.get('capture_fps', 0):.1f}fps"
                f"  enc={status.get('encode_fps', 0):.1f}fps"
                f"  drop={status.get('dropped_pct', 0):.3f}%"
                f"  seg={status.get('current_segment_index', 0)}"
            )

        summary = sc.request({"op": "stop"}, timeout=120)
        # The stop response is only a summary (segment count + total bytes);
        # the engine's real take manifest lives under <take_id>/.
        (stage_dir / "stop_response.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        take_id = summary.get("take_id") or f"take_soak_{minutes}m"
        manifest_path = stage_dir / str(take_id) / "manifest.json"
        if not manifest_path.exists():
            result["reason"] = f"take manifest missing: {manifest_path}"
            return result
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        segments = list(manifest.get("segments") or [])
        if not segments:
            result["reason"] = "manifest has no segments"
            return result
        bad = [s for s in segments if not s.get("is_playable")]
        if bad:
            result["reason"] = f"{len(bad)} segment(s) marked not playable"
            return result

        for mkv in sorted((stage_dir / str(take_id)).glob("*.mkv")):
            if mkv.stat().st_size <= 1024:
                result["reason"] = f"{mkv.name}: suspiciously small ({mkv.stat().st_size} B)"
                return result
            if ffprobe:
                proc = subprocess.run(
                    [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mkv)],
                    capture_output=True,
                    text=True,
                )
                dur = proc.stdout.strip()
                try:
                    dur_f = float(dur) if dur else 0.0
                except ValueError:
                    dur_f = 0.0
                if dur_f <= 0:
                    result["reason"] = f"{mkv.name}: ffprobe could not read a positive duration"
                    return result
                print(f"   verified {mkv.name}: {dur_f:.1f}s, {mkv.stat().st_size / 1048576:.1f} MB")
        if len(segments) < 1 and not list((stage_dir / str(take_id)).glob("*.mkv")):
            result["reason"] = "no MKV products on disk"
            return result

        result["segments"] = [
            {"index": s["index"], "seconds": s["duration_sec"], "bytes": s["byte_len"]} for s in segments
        ]

        # Gate: max sampled dropped_pct must stay within the frozen gate.
        drops: list[float] = []
        if samples_path.exists():
            for line in samples_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    drops.append(float(json.loads(line)["dropped_pct"]))
        if drops:
            max_drop = max(drops)
            result["max_dropped_pct"] = round(max_drop, 4)
            if max_drop > MAX_DROPPED_PCT:
                result["reason"] = f"max dropped_pct {max_drop} exceeds gate {MAX_DROPPED_PCT}"
                return result

        result["pass"] = True
        print(f"   {name} PASS")
        return result
    except Exception as exc:  # noqa: BLE001 - report every failure into the summary
        result["reason"] = str(exc)
        try:
            sc.request({"op": "stop"})
        except Exception:
            pass
        if sc.proc.poll() is None:
            sc.proc.kill()
        return result
    finally:
        sc.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stages", default="5,15", help="comma-separated stage durations in minutes")
    parser.add_argument("--bin", type=Path, default=DEFAULT_BIN, help="recorder sidecar binary")
    parser.add_argument("--root", type=Path, default=None, help="output root (default %TEMP%/windagent_soak_<ts>)")
    parser.add_argument("--sample-interval", type=float, default=2.0, help="status sampling period in seconds")
    args = parser.parse_args()

    stages = [int(x) for x in str(args.stages).split(",") if x.strip()]
    bin_path = args.bin.resolve()
    if not bin_path.exists():
        print(f"error: sidecar binary not found: {bin_path}", file=sys.stderr)
        return 2
    root = args.root or (Path(os.environ.get("TEMP", ".")) / f"windagent_soak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    root.mkdir(parents=True, exist_ok=True)
    ffprobe = shutil.which("ffprobe")

    print(f"Soak staircase: stages(min) = {' -> '.join(str(s) for s in stages)}  root={root}")

    all_passed = True
    summary: list[dict[str, Any]] = []
    for minutes in stages:
        if not all_passed:
            print(f"-- skipping stage {minutes} min (previous stage failed) --")
            summary.append(
                {"stage": f"stage_{minutes}min", "minutes": minutes, "pass": False, "reason": "skipped: previous stage failed"}
            )
            continue
        r = run_stage(minutes, root, bin_path, args.sample_interval, ffprobe)
        summary.append(r)
        if not r["pass"]:
            all_passed = False

    # Final report (Section 24): per-stage P50/P95/P99/max of key counters.
    report_stages: list[dict[str, Any]] = []
    for entry in summary:
        entry_stats: dict[str, Any] = {
            "stage": entry["stage"],
            "pass": entry["pass"],
            "reason": entry["reason"],
        }
        samples_file = root / str(entry["stage"]) / "samples.jsonl"
        if samples_file.exists():
            rows = [json.loads(line) for line in samples_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            for field in ("capture_fps", "encode_fps", "bitrate_mbps", "disk_write_mbps", "dropped_pct"):
                vals = [float(r[field]) for r in rows if r.get(field) is not None]
                s = stats(vals)
                if s:
                    entry_stats[field] = s
        report_stages.append(entry_stats)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "gate_max_dropped_pct": MAX_DROPPED_PCT,
        "all_passed": all_passed,
        "stages": report_stages,
    }
    report_path = root / "soak_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print()
    print("=== SOAK REPORT ===")
    for entry in summary:
        tag = "PASS" if entry["pass"] else f"FAIL ({entry['reason']})"
        print(f"  {entry['stage']:<16} {tag}")
    print(f"report: {report_path}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
