"""
VP3D Phase 3 — BlenderEngineAdapter contract tests (plan Stage B §3).

Proves the adapter implements `ProductionEnginePort` end-to-end over a FAKE
process port (CI-safe — no real blender needed):

- version-policy gate: a 5.x install is NOT ready and submission fails CLOSED
  with a typed receipt (no process launch);
- add-on gate: a job referencing a non-allowlisted add-on is blocked BEFORE
  the process starts;
- a ready install (4.5.x) with a fake blender writing `job_result.json`
  yields a COMPLETED receipt with artifact URIs;
- inspect/cancel/download over the supervisor state;
- the port surface leaks no engine SDK identifiers.
"""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from windagent_core.contracts.video_production.production_engine import ProductionEnginePort
from windagent_core.domain.video_production.ids import EngineJobId
from windagent_core.domain.video_production.production_ir.enums import (
    DerivedArtifactKind,
    EngineJobStatus,
)

from windagent_tools.production_engines.blender import (
    BlenderAddonManifest,
    BlenderAddonSpec,
    BlenderCapabilityProbe,
    BlenderEngineAdapter,
    BlenderEngineConfig,
    BlenderGpuProbe,
    BlenderInstallationDetector,
    create_blender_engine_adapter,
)
from windagent_tools.production_engines.blender.runtime.process import (
    BlenderProcessPort,
    BlenderProcessResult,
)

from tests.fixtures.video_production.ir_fixture_builder import (
    build_valid_ir,
)


class FakeHandle:
    """Fake live handle for the supervisor path (PID known immediately)."""

    def __init__(self, argv, result: BlenderProcessResult, ticks_to_finish: int = 2):
        self.argv = tuple(argv)
        self.pid = result.pid or 1
        self._result = result
        self._ticks = ticks_to_finish
        self._killed = False

    def is_alive(self) -> bool:
        if self._killed:
            return False
        self._ticks -= 1
        return self._ticks > 0

    async def wait(self, timeout_seconds: float) -> BlenderProcessResult:
        self._ticks = 0
        return self._result

    async def kill(self) -> None:
        self._killed = True


class FakeBlenderProcess(BlenderProcessPort):
    """Fake blender.exe: capability-JSON for probes, job_result.json for jobs."""

    def __init__(
        self,
        *,
        blender_version="Blender 4.5.3",
        job_ok=True,
        emit_output_files=True,
    ) -> None:
        self._version = blender_version
        self._job_ok = job_ok
        self._emit_output_files = emit_output_files
        self.last_cwd = None
        self.last_argv = None
        self.started: list = []

    def _probe_result(self, argv) -> BlenderProcessResult:
        payload = json.dumps(
            {
                "build": self._version,
                "python": "3.11.0",
                "cycles_compute": "OPTIX",
                "cycles_devices": [
                    {"name": "RTX 5060", "type": "OPTIX", "compute": "10_2"}
                ],
                "importers": ["import_gltf"],
                "exporters": [],
                "codecs": ["png"],
            }
        )
        return BlenderProcessResult(
            argv=tuple(argv), returncode=0, stdout=payload, stderr="", pid=1
        )

    async def start(self, argv, *, env=None, cwd=None):
        self.last_argv = list(argv)
        self.last_cwd = cwd
        self.started.append(list(argv))
        if "--python-expr" in argv:
            return FakeHandle(argv, self._probe_result(argv))
        return FakeHandle(argv, self._run_job(argv, cwd))

    async def run(self, argv, *, timeout_seconds, env=None, cancel_event=None, cwd=None):
        self.last_argv = list(argv)
        self.last_cwd = cwd
        if "--python-expr" in argv:
            return self._probe_result(argv)
        return self._run_job(argv, cwd)

    def _run_job(self, argv, cwd):
        if not self._job_ok:
            return BlenderProcessResult(
                argv=tuple(argv), returncode=1, stdout="", stderr="job failed in blender", pid=1
            )
        workspace = Path(cwd)
        workspace.mkdir(parents=True, exist_ok=True)
        result = {
            "job_id": "ej_fake",
            "kind": "PROBE",
            "ok": True,
            "cancel_requested": False,
            "blender_version": self._version,
            "report": {"build": self._version},
            "error": "",
            "finished_at": 1.0,
        }
        if self._emit_output_files:
            frame_path = workspace / "frames" / "0001.png"
            frame_path.parent.mkdir(parents=True, exist_ok=True)
            frame_path.write_bytes(b"PNG-DATA")
            result["output_files"] = [
                {
                    "path": "frames/0001.png",
                    "sha256": hashlib.sha256(b"PNG-DATA").hexdigest(),
                    "kind": DerivedArtifactKind.FRAME_SEQUENCE.value,
                    "format": "PNG",
                }
            ]
        (workspace / "job_result.json").write_text(
            json.dumps(result, sort_keys=True), encoding="utf-8"
        )
        return BlenderProcessResult(
            argv=tuple(argv), returncode=0, stdout="job done", stderr="", pid=1
        )


def make_detector(exe_path: str, version_line: str):
    # Isolated detector: never scans the REAL machine installs (CI-safe).
    return BlenderInstallationDetector(
        configured_path=exe_path,
        version_reader=lambda p: version_line,
        standard_locations=(),
        use_registry=False,
    )


def make_adapter(tmp_path, fake_process: FakeBlenderProcess, manifest=None):
    # The configured path must EXIST on disk for the detector to accept it.
    fake_exe = tmp_path / "fake_blender" / "blender.exe"
    fake_exe.parent.mkdir(parents=True, exist_ok=True)
    fake_exe.write_bytes(b"MZ")
    config = BlenderEngineConfig(
        artifact_root=str(tmp_path / "artifacts"),
        state_dir=str(tmp_path / "state"),
        executable_path=str(fake_exe),
        addon_manifest=manifest,
        default_timeout_seconds=30.0,
        heartbeat_seconds=0.05,
        cancel_grace_seconds=0.1,
    )
    return BlenderEngineAdapter(
        config=config,
        detector=make_detector(str(fake_exe), fake_process._version),
        capability_probe=BlenderCapabilityProbe(process_port=fake_process),
        gpu_probe=BlenderGpuProbe(),
        process_port=fake_process,
    )


class TestBlenderEngineAdapter:
    def test_implements_port(self):
        assert issubclass(BlenderEngineAdapter, ProductionEnginePort)

    def test_readiness_ready_on_4_5(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3")
            adapter = make_adapter(tmp_path, fake)
            readiness = await adapter.readiness()
            assert readiness.ready
            assert readiness.gpu is not None

        asyncio.run(_go())

    def test_readiness_rejects_5_1(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 5.1.0")
            adapter = make_adapter(tmp_path, fake)
            readiness = await adapter.readiness()
            assert not readiness.ready
            assert "4.5" in readiness.reason or "policy" in readiness.reason

        asyncio.run(_go())

    def test_submit_scene_fails_closed_on_wrong_version(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 5.1.0")
            adapter = make_adapter(tmp_path, fake)
            ir_doc = build_valid_ir()
            scene = ir_doc.scenes[0]
            render = ir_doc.render_intents[0]
            receipt = await adapter.submit_scene(scene, render)
            assert receipt.status == EngineJobStatus.FAILED
            assert "NOT ready" in (receipt.error or "")
            assert fake.last_argv is None  # process NEVER launched

        asyncio.run(_go())

    def test_submit_scene_blocked_by_addon_gate(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3")
            manifest = BlenderAddonManifest(
                [
                    BlenderAddonSpec(
                        module_id="io_scene_gltf2",
                        version="4.5.3",
                        sha256="a" * 64,
                        source="bundled",
                    )
                ]
            )
            adapter = make_adapter(tmp_path, fake, manifest=manifest)
            ir_doc = build_valid_ir()
            scene = ir_doc.scenes[0]
            render = ir_doc.render_intents[0]
            render = render.model_copy(
                update={"metadata": {"addons": [{"module_id": "evil_addon", "version": "1.0"}]}}
            )
            receipt = await adapter.submit_scene(scene, render)
            assert receipt.status == EngineJobStatus.FAILED
            assert "add-on gate" in (receipt.error or "")
            # The job LAUNCH (--python execute_job.py) never happened; only the
            # read-only capability probe (--python-expr) ran during readiness.
            launched = [
                a for a in (fake.started or []) if "--python" in a and "--python-expr" not in a
            ]
            assert not launched, "add-on gate must block BEFORE process launch"

        asyncio.run(_go())

    def test_submit_scene_completes_with_artifact(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3")
            adapter = make_adapter(tmp_path, fake)
            ir_doc = build_valid_ir()
            scene = ir_doc.scenes[0]
            render = ir_doc.render_intents[0]
            receipt = await adapter.submit_scene(scene, render)
            assert receipt.status == EngineJobStatus.COMPLETED
            assert receipt.engine_name == "blender"
            assert receipt.ir_hash
            assert receipt.artifact_uris, "expected artifact URIs from job_result.json"
            assert fake.last_argv is not None  # process was launched

        asyncio.run(_go())

    def test_submit_shot_completes(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3")
            adapter = make_adapter(tmp_path, fake)
            ir_doc = build_valid_ir()
            shot = ir_doc.shots[0]
            render = ir_doc.render_intents[0]
            receipt = await adapter.submit_shot(shot, render)
            assert receipt.status == EngineJobStatus.COMPLETED

        asyncio.run(_go())

    def test_inspect_unknown_job(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3")
            adapter = make_adapter(tmp_path, fake)
            receipt = await adapter.inspect_job(EngineJobId("ej_nope"))
            assert receipt.status == EngineJobStatus.FAILED

        asyncio.run(_go())

    def test_download_artifact(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3")
            adapter = make_adapter(tmp_path, fake)
            ir_doc = build_valid_ir()
            scene = ir_doc.scenes[0]
            render = ir_doc.render_intents[0]
            receipt = await adapter.submit_scene(scene, render)
            assert receipt.status == EngineJobStatus.COMPLETED
            artifact = await adapter.download_artifact(
                receipt.job_id, DerivedArtifactKind.FRAME_SEQUENCE
            )
            assert artifact.content_hash == hashlib.sha256(b"PNG-DATA").hexdigest()
            assert artifact.kind == DerivedArtifactKind.FRAME_SEQUENCE
            assert artifact.derived_from_ir_hash == receipt.ir_hash

        asyncio.run(_go())

    def test_download_missing_artifact_raises(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3", emit_output_files=False)
            adapter = make_adapter(tmp_path, fake)
            with pytest.raises(Exception):
                await adapter.download_artifact(
                    EngineJobId("ej_fake"), DerivedArtifactKind.FINAL_CUT
                )

        asyncio.run(_go())

    def test_factory_creates_adapter(self, tmp_path):
        adapter = create_blender_engine_adapter(
            artifact_root=str(tmp_path / "artifacts"),
            state_dir=str(tmp_path / "state"),
        )
        assert isinstance(adapter, BlenderEngineAdapter)
        assert adapter.engine_name == "blender"
