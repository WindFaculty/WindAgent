"""
VP3D Phase 3 — Blender Runtime Foundation unit tests (plan Stage B §3).

Covers the plan's test matrix:
- Detector with configured path, missing path, multiple versions, spaces in path.
- Capability probe CPU-only / CUDA / OptiX / unexpected output (fail closed).
- Timeout, cancel, process crash, invalid workspace, malicious argv, non-UTF8 stdout.
- Supervisor restart reattach or quarantine per policy.
- Add-on wrong hash/version blocked BEFORE process launch.
- Receipt redaction, hashing and failure classification.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from windagent_tools.production_engines.blender import (
    APPROVED,
    REJECTED,
    REQUIRES_HUMAN_APPROVAL,
    AddonGateError,
    BlenderAddonManifest,
    BlenderAddonRequest,
    BlenderAddonSpec,
    BlenderCapabilityProbe,
    BlenderCapabilityReport,
    BlenderExecutionReceipt,
    BlenderGpuProbe,
    BlenderInstallationCandidate,
    BlenderInstallationDetector,
    BlenderJobError,
    BlenderJobLauncher,
    BlenderJobSpec,
    BlenderProcessSupervisor,
    BlenderVersionValidator,
    redact_argv,
)
from windagent_tools.production_engines.blender.runtime.process import (
    BlenderProcessPort,
    BlenderProcessResult,
)
from windagent_tools.production_engines.blender.runtime.supervisor import (
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_QUARANTINED,
    STATE_RUNNING,
)
from windagent_tools.production_engines.blender.validator import (
    REASON_BINARY_MISSING,
    REASON_UNPARSEABLE,
    REASON_VERSION_MISMATCH,
    parse_blender_version,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeHandle:
    """Fake live process handle: PID known, controllable completion."""

    def __init__(
        self, argv, result_builder, *, pid=4242, ticks_to_finish=2
    ) -> None:
        self.argv = tuple(argv)
        self.pid = pid
        self._result_builder = result_builder
        self._ticks = ticks_to_finish
        self._killed = False

    def is_alive(self) -> bool:
        if self._killed:
            return False
        self._ticks -= 1
        return self._ticks > 0

    async def wait(self, timeout_seconds: float) -> BlenderProcessResult:
        result = self._result_builder(self.argv, killed=self._killed)
        self._ticks = 0
        return result

    async def kill(self) -> None:
        self._killed = True


class FakeProcessPort(BlenderProcessPort):
    """Fake process port that simulates blender.exe outcomes deterministically."""

    def __init__(self, script: dict | None = None) -> None:
        # script: {"mode": "ok"|"crash"|"timeout"|"bad_utf8"|"cancel", ...}
        self._script = script or {"mode": "ok"}
        self.started: list = []

    def _build_result(self, argv, *, killed=False) -> BlenderProcessResult:
        mode = self._script.get("mode", "ok")
        if mode == "crash":
            return BlenderProcessResult(
                argv=tuple(argv), returncode=1, stdout="", stderr="boom", pid=4242
            )
        if mode == "timeout":
            return BlenderProcessResult(
                argv=tuple(argv), returncode=-1, stdout="", stderr="", timed_out=True, pid=4242
            )
        if mode == "bad_utf8":
            return BlenderProcessResult(
                argv=tuple(argv),
                returncode=0,
                stdout=b"\xff\xfe garbage".decode("utf-8", "replace"),
                stderr="",
                pid=4242,
            )
        if killed:
            return BlenderProcessResult(
                argv=tuple(argv), returncode=-9, stdout="", stderr="", cancelled=True, pid=4242
            )
        # Default "ok" mode returns a VALID capability JSON so probe tests
        # exercise the real parse path.
        payload = json.dumps(
            {
                "build": "Blender 4.5.3",
                "python": "3.11.0",
                "cycles_compute": "OPTIX",
                "cycles_devices": [
                    {"name": "RTX 5060", "type": "OPTIX", "compute": "10_2"}
                ],
                "importers": ["import_gltf"],
                "exporters": ["export_gltf"],
                "codecs": ["png"],
            }
        )
        return BlenderProcessResult(
            argv=tuple(argv), returncode=0, stdout=payload, stderr="", pid=4242
        )

    async def start(self, argv, *, env=None, cwd=None):
        self.started.append({"argv": list(argv), "cwd": cwd})
        return FakeHandle(argv, self._build_result)

    async def run(self, argv, *, timeout_seconds, env=None, cancel_event=None, cwd=None):
        self.started.append({"argv": list(argv), "cwd": cwd})
        if cancel_event is not None and cancel_event.is_set():
            return self._build_result(argv, killed=True)
        return self._build_result(argv)


class NeverFinishingHandle(FakeHandle):
    """A process handle that NEVER exits on its own — for timeout tests.

    The supervisor must detect the deadline and kill() the process itself;
    without this handle a job would otherwise run forever.
    """

    def is_alive(self) -> bool:
        if self._killed:
            return False
        return True

    async def wait(self, timeout_seconds: float) -> BlenderProcessResult:
        result = self._result_builder(self.argv, killed=self._killed)
        self._killed = True
        return result


class TimeoutProcessPort(FakeProcessPort):
    """Process port whose spawned process never exits on its own."""

    async def start(self, argv, *, env=None, cwd=None):
        self.started.append({"argv": list(argv), "cwd": cwd})
        return NeverFinishingHandle(argv, self._build_result)


class FakeLauncher(BlenderJobLauncher):
    """Launcher whose process port is a deterministic fake."""

    def __init__(self, artifact_root: str, process_port: FakeProcessPort) -> None:
        super().__init__(artifact_root=artifact_root, process_port=process_port)
        self._fake = process_port


def make_spec(**overrides) -> BlenderJobSpec:
    base = dict(
        job_id="ej_001",
        kind="PROBE",
        executable_path="C:/Blender/blender.exe",
        script_path="C:/Blender/scripts/execute_job.py",
        job_workspace="jobs/ej_001",
        timeout_seconds=30.0,
    )
    base.update(overrides)
    return BlenderJobSpec(**base)


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


def isolated_detector(tmp_path, *, standard_locations=(), use_registry=False, **kwargs):
    """Detector that never scans the REAL machine installs (CI-safe)."""
    return BlenderInstallationDetector(
        standard_locations=standard_locations,
        use_registry=use_registry,
        **kwargs,
    )


class TestBlenderInstallationDetector:
    def test_configured_path_wins(self, tmp_path):
        fake_exe = tmp_path / "blender.exe"
        fake_exe.write_bytes(b"MZ")
        detector = isolated_detector(
            tmp_path,
            configured_path=str(fake_exe),
            version_reader=lambda p: "Blender 4.5.3",
        )
        candidates = detector.detect()
        assert len(candidates) == 1
        assert candidates[0].source == "configured"
        assert candidates[0].version_line == "Blender 4.5.3"

    def test_missing_configured_path_returns_empty(self, tmp_path):
        detector = isolated_detector(
            tmp_path,
            configured_path=str(tmp_path / "nope" / "blender.exe"),
            version_reader=lambda p: "Blender 4.5.3",
        )
        assert detector.detect() == []

    def test_multiple_versions_ordered_by_source(self, tmp_path, monkeypatch):
        # The standard-location scan is a Windows-only product behavior
        # (detector.py gates it on sys.platform); pin the platform so the scan
        # code path itself is exercised on every OS instead of silently skipped
        # on Linux CI.
        monkeypatch.setattr(sys, "platform", "win32")
        (tmp_path / "BF").mkdir()
        (tmp_path / "BF" / "Blender 4.5").mkdir()
        (tmp_path / "BF" / "Blender 5.1").mkdir()
        (tmp_path / "BF" / "Blender 4.5" / "blender.exe").write_bytes(b"a")
        (tmp_path / "BF" / "Blender 5.1" / "blender.exe").write_bytes(b"b")
        detector = isolated_detector(
            tmp_path,
            configured_path=str(tmp_path / "BF" / "Blender 4.5" / "blender.exe"),
            standard_locations=(str(tmp_path / "BF"),),
            version_reader=lambda p: f"Blender {Path(p).parent.name.split()[-1]}",
        )
        candidates = detector.detect()
        sources = [c.source for c in candidates]
        assert sources[0] == "configured"
        assert "standard_location" in sources
        assert len(candidates) == 2

    def test_path_with_spaces(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        spaced = tmp_path / "Blender Foundation" / "Blender 4.5"
        spaced.mkdir(parents=True)
        exe = spaced / "blender.exe"
        exe.write_bytes(b"MZ")
        detector = isolated_detector(
            tmp_path,
            standard_locations=(str(tmp_path / "Blender Foundation"),),
            version_reader=lambda p: "Blender 4.5.3",
        )
        candidates = detector.detect()
        assert any("Blender 4.5" in c.executable_path for c in candidates)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class TestBlenderVersionValidator:
    def test_accepts_4_5_x(self):
        candidate = BlenderInstallationCandidate(
            executable_path="C:/b/blender.exe", version_line="Blender 4.5.3"
        )
        result = BlenderVersionValidator().validate(candidate)
        assert result.is_ready
        assert (result.major, result.minor, result.patch) == (4, 5, 3)

    def test_rejects_5_x(self):
        candidate = BlenderInstallationCandidate(
            executable_path="C:/b/blender.exe", version_line="Blender 5.1.0"
        )
        result = BlenderVersionValidator().validate(candidate)
        assert not result.is_ready
        assert result.reason_code == REASON_VERSION_MISMATCH

    def test_rejects_4_6(self):
        candidate = BlenderInstallationCandidate(
            executable_path="C:/b/blender.exe", version_line="Blender 4.6.0"
        )
        assert not BlenderVersionValidator().validate(candidate).is_ready

    def test_unparseable_version(self):
        candidate = BlenderInstallationCandidate(
            executable_path="C:/b/blender.exe", version_line="not a version"
        )
        result = BlenderVersionValidator().validate(candidate)
        assert result.reason_code == REASON_UNPARSEABLE
        assert not result.is_ready

    def test_missing_binary_path(self):
        candidate = BlenderInstallationCandidate(executable_path="")
        result = BlenderVersionValidator().validate(candidate)
        assert result.reason_code == REASON_BINARY_MISSING

    def test_first_ready_skips_bad(self):
        candidates = [
            BlenderInstallationCandidate(
                executable_path="a", version_line="Blender 5.1.0"
            ),
            BlenderInstallationCandidate(
                executable_path="b", version_line="Blender 4.5.2"
            ),
        ]
        ready = BlenderVersionValidator().first_ready(candidates)
        assert ready is not None and ready.executable_path == "b"

    def test_parse_blender_version(self):
        assert parse_blender_version("Blender 4.5.3 (hash abc)") == (4, 5, 3)
        assert parse_blender_version("") is None
        assert parse_blender_version("garbage") is None


# ---------------------------------------------------------------------------
# Capability + GPU probes (fail closed)
# ---------------------------------------------------------------------------


class TestBlenderCapabilityProbe:
    async def _probe(self, mode: str) -> BlenderCapabilityReport:
        probe = BlenderCapabilityProbe(process_port=FakeProcessPort({"mode": mode}))
        return await probe.probe("C:/b/blender.exe")

    def test_valid_report(self):
        port = FakeProcessPort()

        async def _go():
            probe = BlenderCapabilityProbe(process_port=port)
            report = await probe.probe("C:/b/blender.exe")
            assert report.parsed_ok

        asyncio.run(_go())

    def test_parse_cpu_only_report(self):
        async def _go():
            class CpuPort(FakeProcessPort):
                async def run(self, argv, **kw):
                    payload = json.dumps(
                        {"build": "Blender 4.5.3", "cycles_devices": [], "codecs": []}
                    )
                    return BlenderProcessResult(
                        argv=tuple(argv), returncode=0, stdout=payload, stderr="", pid=1
                    )

            report = await BlenderCapabilityProbe(process_port=CpuPort()).probe("b")
            assert report.parsed_ok
            assert report.cycles_devices == []
            gpu = BlenderGpuProbe().classify(report)
            assert not gpu.gpu_ready

        asyncio.run(_go())

    def test_parse_optix_report(self):
        async def _go():
            class OptixPort(FakeProcessPort):
                async def run(self, argv, **kw):
                    payload = json.dumps(
                        {
                            "build": "Blender 4.5.3",
                            "cycles_devices": [
                                {"name": "RTX 5060", "type": "OPTIX", "compute": "10_2"}
                            ],
                        }
                    )
                    return BlenderProcessResult(
                        argv=tuple(argv), returncode=0, stdout=payload, stderr="", pid=1
                    )

            report = await BlenderCapabilityProbe(process_port=OptixPort()).probe("b")
            gpu = BlenderGpuProbe().classify(report)
            assert gpu.gpu_ready
            assert gpu.backend == "OPTIX"
            assert gpu.gpu_devices[0].name == "RTX 5060"

        asyncio.run(_go())

    def test_parse_cuda_report(self):
        """A CUDA device is distinguished from CPU-only (plan test matrix)."""
        async def _go():
            class CudaPort(FakeProcessPort):
                async def run(self, argv, **kw):
                    payload = json.dumps(
                        {
                            "build": "Blender 4.5.3",
                            "cycles_devices": [
                                {"name": "RTX 5060", "type": "CUDA", "compute": "10_2"},
                                {"name": "CPU", "type": "CPU", "compute": ""},
                            ],
                        }
                    )
                    return BlenderProcessResult(
                        argv=tuple(argv), returncode=0, stdout=payload, stderr="", pid=1
                    )

            report = await BlenderCapabilityProbe(process_port=CudaPort()).probe("b")
            gpu = BlenderGpuProbe().classify(report)
            assert gpu.gpu_ready
            assert gpu.backend == "CUDA"
            # Only the GPU device counts; the CPU device is never GPU-ready.
            assert len(gpu.gpu_devices) == 1
            assert gpu.gpu_devices[0].name == "RTX 5060"

        asyncio.run(_go())

    def test_non_utf8_stdout_does_not_crash(self):
        """Non-UTF-8 stdout is decode-with-replace; parsing then fails closed."""
        async def _go():
            report = await BlenderCapabilityProbe(
                process_port=FakeProcessPort({"mode": "bad_utf8"})
            ).probe("b")
            assert not report.parsed_ok
            assert report.probe_error  # typed probe failure, never a crash

        asyncio.run(_go())

    def test_unexpected_output_fails_closed(self):
        async def _go():
            class GarbagePort(FakeProcessPort):
                async def run(self, argv, **kw):
                    return BlenderProcessResult(
                        argv=tuple(argv), returncode=0, stdout="not json at all", stderr="", pid=1
                    )

            report = await BlenderCapabilityProbe(process_port=GarbagePort()).probe("b")
            assert not report.parsed_ok
            assert "no parseable JSON" in report.probe_error

        asyncio.run(_go())

    def test_crash_output_fails_closed(self):
        async def _go():
            class CrashPort(FakeProcessPort):
                async def run(self, argv, **kw):
                    return BlenderProcessResult(
                        argv=tuple(argv), returncode=1, stdout="", stderr="segfault", pid=1
                    )

            report = await BlenderCapabilityProbe(process_port=CrashPort()).probe("b")
            assert not report.parsed_ok

        asyncio.run(_go())

    def test_banner_text_before_json_still_parses(self):
        """Real blender prints a banner line before the JSON payload."""
        async def _go():
            class BannerPort(FakeProcessPort):
                async def run(self, argv, **kw):
                    payload = (
                        "Blender 5.1.2\n"
                        "Read prefs: C:/Users/x/AppData/Roaming/Blender Foundation/5.1/config/userpref.blend\n"
                        + json.dumps(
                            {
                                "build": "5.1.2",
                                "cycles_devices": [
                                    {"name": "RTX 5060", "type": "OPTIX", "compute": "10_2"}
                                ],
                            }
                        )
                    )
                    return BlenderProcessResult(
                        argv=tuple(argv), returncode=0, stdout=payload, stderr="", pid=1
                    )

            report = await BlenderCapabilityProbe(process_port=BannerPort()).probe("b")
            assert report.parsed_ok
            assert report.build == "5.1.2"
            assert report.cycles_devices[0].is_gpu

        asyncio.run(_go())


# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------


class TestBlenderJobLauncher:
    def test_invalid_workspace_escapes_root(self, tmp_path):
        launcher = BlenderJobLauncher(
            artifact_root=str(tmp_path), process_port=FakeProcessPort()
        )
        with pytest.raises(BlenderJobError):
            launcher.validate_workspace(str(tmp_path.parent / "outside"))

    def test_malicious_argv_rejected(self):
        launcher = BlenderJobLauncher(
            artifact_root="artifacts", process_port=FakeProcessPort()
        )
        make_spec(job_workspace="jobs/x")
        with pytest.raises(BlenderJobError):
            launcher.validate_argv(["blender", "--python", "x\x00y", ""])

    def test_env_allowlist_drops_secrets(self):
        launcher = BlenderJobLauncher(
            artifact_root="artifacts", process_port=FakeProcessPort()
        )
        env = launcher.build_env(
            make_spec(job_workspace="jobs/x", env_additions={"BLENDER_ADDON_PATH": "/addons"}),
            base_env={
                "PATH": "/usr/bin",
                "AWS_SECRET_ACCESS_KEY": "supersecret",
                "TEMP": "/tmp",
            },
        )
        assert "AWS_SECRET_ACCESS_KEY" not in env
        assert "PATH" in env
        assert env["BLENDER_ADDON_PATH"] == "/addons"

    def test_build_argv_is_list_no_shell(self):
        launcher = BlenderJobLauncher(
            artifact_root="artifacts", process_port=FakeProcessPort()
        )
        argv = launcher.build_argv(make_spec(job_workspace="jobs/x"))
        assert isinstance(argv, list)
        assert all(isinstance(a, str) for a in argv)
        assert "--background" in argv

    def test_launch_writes_job_spec_and_runs(self, tmp_path):
        workspace = tmp_path / "jobs" / "ej_001"
        launcher = BlenderJobLauncher(artifact_root=str(tmp_path), process_port=FakeProcessPort())
        spec = make_spec(
            job_workspace=str(workspace),
            spec_payload={"ir_hash": "abc", "kind": "PROBE"},
        )

        async def _go():
            result, receipt = await launcher.launch(spec)
            assert result.returncode == 0
            assert receipt.failure_classification == "SUCCESS"
            assert (workspace / "job_spec.json").is_file()
            spec_json = json.loads((workspace / "job_spec.json").read_text(encoding="utf-8"))
            assert spec_json["ir_hash"] == "abc"

        asyncio.run(_go())

    def test_cancel_event_honored(self, tmp_path):
        workspace = tmp_path / "jobs" / "ej_002"
        launcher = BlenderJobLauncher(artifact_root=str(tmp_path), process_port=FakeProcessPort())
        spec = make_spec(job_workspace=str(workspace))

        async def _go():
            cancel_event = asyncio.Event()
            cancel_event.set()
            result, receipt = await launcher.launch(spec, cancel_event=cancel_event)
            assert result.cancelled
            assert receipt.failure_classification == "CANCELLED"

        asyncio.run(_go())


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------


def make_supervisor(tmp_path, launcher, **kwargs):
    return BlenderProcessSupervisor(
        state_dir=str(tmp_path / "state"),
        launcher=launcher,
        heartbeat_seconds=0.05,
        cancel_grace_seconds=0.1,
        **kwargs,
    )


class TestBlenderProcessSupervisor:
    def test_launch_persists_locator_and_completes(self, tmp_path):
        state_dir = tmp_path / "state"
        workspace = tmp_path / "jobs" / "ej_003"
        launcher = BlenderJobLauncher(artifact_root=str(tmp_path), process_port=FakeProcessPort())
        supervisor = make_supervisor(tmp_path, launcher)
        spec = make_spec(job_id="ej_003", job_workspace=str(workspace))

        async def _go():
            locator, receipt = await supervisor.launch(spec)
            assert locator.state == STATE_COMPLETED
            assert (state_dir / "ej_003.locator.json").is_file()
            loaded = supervisor.load("ej_003")
            assert loaded is not None and loaded.state == STATE_COMPLETED

        asyncio.run(_go())

    def test_process_crash_marked_failed(self, tmp_path):
        tmp_path / "state"
        workspace = tmp_path / "jobs" / "ej_crash"
        launcher = BlenderJobLauncher(
            artifact_root=str(tmp_path), process_port=FakeProcessPort({"mode": "crash"})
        )
        supervisor = make_supervisor(tmp_path, launcher)
        spec = make_spec(job_workspace=str(workspace))

        async def _go():
            locator, receipt = await supervisor.launch(spec)
            assert locator.state == STATE_FAILED
            assert receipt.exit_code == 1

        asyncio.run(_go())

    def test_timeout_enforced_kills_process_and_marks_failed(self, tmp_path):
        """A job that never exits is killed after its deadline (plan: timeout)."""
        state_dir = tmp_path / "state"
        workspace = tmp_path / "jobs" / "ej_timeout"
        port = TimeoutProcessPort()
        launcher = BlenderJobLauncher(artifact_root=str(tmp_path), process_port=port)
        supervisor = BlenderProcessSupervisor(
            state_dir=str(state_dir),
            launcher=launcher,
            heartbeat_seconds=0.02,
            cancel_grace_seconds=0.1,
        )
        spec = make_spec(
            job_id="ej_timeout",
            job_workspace=str(workspace),
            timeout_seconds=0.2,
        )

        async def _go():
            locator, receipt = await supervisor.launch(spec)
            assert locator.state == STATE_FAILED
            assert receipt.failure_classification == "TIMEOUT"
            assert "exceeded its time budget" in locator.reason

        asyncio.run(_go())

    def test_cancel_via_token(self, tmp_path):
        tmp_path / "state"
        workspace = tmp_path / "jobs" / "ej_cancel"
        launcher = BlenderJobLauncher(artifact_root=str(tmp_path), process_port=FakeProcessPort())
        supervisor = make_supervisor(tmp_path, launcher)
        spec = make_spec(job_workspace=str(workspace))

        async def _go():
            # Write the token BEFORE launch -> graceful cancel path.
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "cancel.token").write_text("cancel\n", encoding="utf-8")
            locator, receipt = await supervisor.launch(spec)
            assert locator.state == "CANCELLED"
            assert receipt.cancel_requested

        asyncio.run(_go())

    def test_reconcile_reattaches_or_quarantines(self, tmp_path):
        state_dir = tmp_path / "state"
        launcher = BlenderJobLauncher(artifact_root=str(tmp_path), process_port=FakeProcessPort())
        supervisor = BlenderProcessSupervisor(state_dir=str(state_dir), launcher=launcher)

        import json as _json

        # A locator with a LIVE pid (this test process) should reattach.
        live = {
            "job_id": "ej_live",
            "kind": "PROBE",
            "executable_path": "b",
            "workspace": str(tmp_path / "jobs" / "ej_live"),
            "state": "RUNNING",
            "pid": os.getpid(),
            "started_at": 0.0,
            "heartbeat_at": 0.0,
            "reason": "",
        }
        (state_dir / "ej_live.locator.json").write_text(
            _json.dumps(live), encoding="utf-8"
        )

        # A locator with a dead pid (999999) should quarantine.
        dead = dict(live, job_id="ej_dead", pid=999999, workspace=str(tmp_path / "jobs" / "ej_dead"))
        (state_dir / "ej_dead.locator.json").write_text(
            _json.dumps(dead), encoding="utf-8"
        )

        results = supervisor.reconcile()
        by_id = {r.job_id: r for r in results}
        assert by_id["ej_live"].state == STATE_RUNNING
        assert by_id["ej_dead"].state == STATE_QUARANTINED

    def test_reconcile_skips_terminal(self, tmp_path):
        state_dir = tmp_path / "state"
        launcher = BlenderJobLauncher(artifact_root=str(tmp_path), process_port=FakeProcessPort())
        supervisor = BlenderProcessSupervisor(state_dir=str(state_dir), launcher=launcher)

        import json as _json

        terminal = {
            "job_id": "ej_done",
            "kind": "PROBE",
            "executable_path": "b",
            "workspace": str(tmp_path / "jobs" / "ej_done"),
            "state": "COMPLETED",
            "pid": os.getpid(),
            "started_at": 0.0,
            "heartbeat_at": 0.0,
            "reason": "",
        }
        (state_dir / "ej_done.locator.json").write_text(
            _json.dumps(terminal), encoding="utf-8"
        )
        assert supervisor.reconcile() == []


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------


class TestBlenderExecutionReceipt:
    def test_redacts_secrets_in_argv(self):
        redacted = redact_argv(["blender", "--api-key", "sk-1234567890abcdef"])
        assert "sk-1234567890abcdef" not in str(redacted)

    def test_failure_classification(self):
        result = BlenderProcessResult(
            argv=("b",), returncode=1, stdout="", stderr="error: bad blend", pid=1
        )
        receipt = BlenderExecutionReceipt.from_process_result(
            job_id="ej_1",
            kind="PROBE",
            executable_path="b",
            argv=result.argv,
            result=result,
            started_at=0.0,
        )
        assert receipt.failure_classification == "PROCESS_CRASH"
        assert receipt.stderr_hash and receipt.stdout_hash
        assert "error: bad blend" in receipt.error_snippet

    def test_receipt_serializes(self):
        result = BlenderProcessResult(
            argv=("b",), returncode=0, stdout="ok", stderr="", pid=1
        )
        receipt = BlenderExecutionReceipt.from_process_result(
            job_id="ej_2",
            kind="PROBE",
            executable_path="b",
            argv=result.argv,
            result=result,
            started_at=0.0,
        )
        payload = receipt.to_dict()
        assert payload["failure_classification"] == "SUCCESS"
        assert "redacted_argv" in payload


# ---------------------------------------------------------------------------
# Add-on manifest
# ---------------------------------------------------------------------------


class TestBlenderAddonManifest:
    def make_manifest(self) -> BlenderAddonManifest:
        return BlenderAddonManifest(
            [
                BlenderAddonSpec(
                    module_id="io_scene_gltf2",
                    version="4.5.3",
                    sha256="a" * 64,
                    source="bundled",
                    permissions=frozenset({"execute_code"}),
                )
            ]
        )

    def test_approved_when_matching(self):
        decision = self.make_manifest().check(
            BlenderAddonRequest(
                module_id="io_scene_gltf2", version="4.5.3", sha256="a" * 64
            )
        )
        assert decision.status == APPROVED and decision.allowed

    def test_unknown_addon_requires_human_approval(self):
        decision = self.make_manifest().check(
            BlenderAddonRequest(module_id="evil_addon", version="1.0.0")
        )
        assert decision.status == REQUIRES_HUMAN_APPROVAL
        assert not decision.allowed

    def test_wrong_version_requires_human_approval(self):
        decision = self.make_manifest().check(
            BlenderAddonRequest(module_id="io_scene_gltf2", version="9.9.9")
        )
        assert decision.status == REQUIRES_HUMAN_APPROVAL

    def test_wrong_hash_rejected(self):
        decision = self.make_manifest().check(
            BlenderAddonRequest(
                module_id="io_scene_gltf2", version="4.5.3", sha256="b" * 64
            )
        )
        assert decision.status == REJECTED

    def test_empty_manifest_blocks_everything(self):
        manifest = BlenderAddonManifest.empty()
        decision = manifest.check(
            BlenderAddonRequest(module_id="io_scene_gltf2", version="4.5.3")
        )
        assert decision.status == REQUIRES_HUMAN_APPROVAL

    def test_ensure_all_approved_raises_before_launch(self):
        manifest = self.make_manifest()
        with pytest.raises(AddonGateError):
            manifest.ensure_all_approved(
                [
                    BlenderAddonRequest(module_id="io_scene_gltf2", version="4.5.3"),
                    BlenderAddonRequest(module_id="unknown", version="1"),
                ]
            )
        # Approved-only passes.
        decisions = manifest.ensure_all_approved(
            [BlenderAddonRequest(module_id="io_scene_gltf2", version="4.5.3", sha256="a" * 64)]
        )
        assert decisions[0].allowed
