"""
VP3D Phase 4 — Blender deterministic scene smoke test (plan Stage B §4).

Contract tests in CI with FAKE executables (no real blender/ffmpeg needed):

- compiler: locked config (seed, frame range, fps, color management,
  resolution, Cycles samples, denoise, device) + deterministic plan hash;
- fixture: typed cube/ground/camera/three lights/material/keyframes;
- frames: atomic temp -> validated final, resume from next valid frame,
  cancel publishes nothing;
- idempotency: reuse when keys match, invalidate when any hash differs;
- determinism: two runs of the same IR are structurally stable;
- ffmpeg: ASSEMBLE -> MP4, VERIFY -> ffprobe JSON over a fake port;
- pipeline: full COMPILE -> SAVE -> INSPECT -> RENDER_CHUNK -> ASSEMBLE ->
  VERIFY flow, plus cancel/resume/retry/reuse;
- execute_job: kind dispatch table + cancel-before-start + host-side kinds.
"""

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from windagent_core.domain.video_production.production_ir.models import (
    RenderIntent,
    SceneDescription,
    ShotExecutionIntent,
)

from windagent_tools.production_engines.blender import (
    ArtifactReusePolicy,
    BlenderFfmpegRunner,
    BlenderJobLauncher,
    BlenderJobSpec,
    BlenderProcessSupervisor,
    FfmpegVersion,
    FrameManifest,
    INVALIDATE,
    REUSE,
    ScenePlan,
    ScenePlanCompiler,
    job_idempotency_key,
)
from windagent_tools.production_engines.blender.ffmpeg import BlenderFfmpegPort
from windagent_tools.production_engines.blender.runtime.process import (
    BlenderProcessPort,
    BlenderProcessResult,
)
from windagent_tools.production_engines.blender.scene.determinism import (
    RunSnapshot,
    compare_runs,
)
from windagent_tools.production_engines.blender.scene.fixture import (
    THREE_LIGHTS,
    build_smoke_fixture,
    fixture_content_hash,
)
from windagent_tools.production_engines.blender.scene.frames import (
    CANCEL_TOKEN_FILENAME,
    FRAME_NAME_TEMPLATE,
    TEMP_SUFFIX,
)
from windagent_tools.production_engines.blender.scene.pipeline import (
    ASSEMBLE,
    COMPILE,
    INSPECT,
    RENDER_CHUNK,
    SAVE,
    VERIFY,
    BlenderSmokePipeline,
)
from windagent_tools.production_engines.blender.adapter import JOB_KIND_PROBE as PROBE
from windagent_tools.production_engines.blender.validator import BlenderVersionPolicy

from tests.fixtures.video_production.ir_fixture_builder import build_valid_ir

BLENDER_EXE = "C:/fake/blender.exe"


def fake_png_bytes(width: int, height: int) -> bytes:
    """A minimal but dimension-probeable PNG (IHDR width/height)."""
    ihdr = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + width.to_bytes(4, "big") + height.to_bytes(4, "big")
    return ihdr + b"\x00\x00\x00\x00IEND\xaeB\x60\x82"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeHandle:
    def __init__(self, argv, result_builder, ticks_to_finish: int = 1) -> None:
        self.argv = tuple(argv)
        self.pid = 4242
        self._result_builder = result_builder
        self._ticks = ticks_to_finish
        self._killed = False

    def is_alive(self) -> bool:
        if self._killed:
            return False
        self._ticks -= 1
        return self._ticks > 0

    async def wait(self, timeout_seconds: float) -> BlenderProcessResult:
        return self._result_builder(self.argv, killed=self._killed)

    async def kill(self) -> None:
        self._killed = True


def _kind_from_argv(argv) -> str:
    argv_list = list(argv)
    if "--kind" in argv_list:
        return argv_list[argv_list.index("--kind") + 1]
    return "PROBE"


class FakeBlenderProcess(BlenderProcessPort):
    """Fake blender.exe simulating the Phase 4 job kinds deterministically."""

    def __init__(self, *, blender_version="Blender 4.5.3", fail_kind: str | None = None) -> None:
        self._version = blender_version
        self._fail_kind = fail_kind
        self.started: list = []
        self.last_workspace = None

    def _execute_job(self, argv, cwd):
        workspace = Path(cwd)
        self.last_workspace = workspace
        kind = _kind_from_argv(argv)
        if self._fail_kind == kind:
            (workspace / "job_result.json").write_text(
                json.dumps({"ok": False, "kind": kind, "error": "fake failure"}),
                encoding="utf-8",
            )
            return BlenderProcessResult(
                argv=tuple(argv), returncode=1, stdout="", stderr="fake failure", pid=4242
            )
        if kind == COMPILE:
            (workspace / "scene.blend").write_bytes(b"BLEND-DATA-4.5.3")
        elif kind == SAVE:
            (workspace / "scene.blend").write_bytes(b"BLEND-DATA-4.5.3")
        elif kind == INSPECT:
            pass
        elif kind == RENDER_CHUNK:
            spec = json.loads((workspace / "job_spec.json").read_text(encoding="utf-8"))
            frame_start, frame_end = int(spec["frame_start"]), int(spec["frame_end"])
            extension = str(spec.get("extension", "png"))
            resolution = spec.get("resolution") or {"width": 640, "height": 360}
            if (workspace / CANCEL_TOKEN_FILENAME).is_file():
                pass
            else:
                # Mirror execute_job.py: render each frame to a TEMP path then
                # atomically finalize + MERGE into the existing manifest
                # (frame_manifest.json) so earlier chunks survive.
                ej_module = _load_execute_job()
                for frame in range(frame_start, frame_end + 1):
                    temp = workspace / (
                        FRAME_NAME_TEMPLATE.format(frame=frame, ext=extension) + TEMP_SUFFIX
                    )
                    temp.write_bytes(fake_png_bytes(resolution["width"], resolution["height"]))
                    entry = ej_module._finalize_frame_atomic(workspace, frame, extension)
                    if entry is None:
                        return BlenderProcessResult(
                            argv=tuple(argv), returncode=1, stdout="",
                            stderr=f"frame {frame} not finalized", pid=4242,
                        )
        result_payload = {
            "job_id": "ej_fake",
            "kind": kind,
            "ok": True,
            "cancel_requested": False,
            "blender_version": self._version,
            "report": {"kind": kind, "build": self._version},
            "error": "",
            "finished_at": 1.0,
        }
        (workspace / "job_result.json").write_text(
            json.dumps(result_payload, sort_keys=True), encoding="utf-8"
        )
        return BlenderProcessResult(
            argv=tuple(argv), returncode=0, stdout="ok", stderr="", pid=4242
        )

    async def start(self, argv, *, env=None, cwd=None):
        self.started.append(list(argv))
        return FakeHandle(argv, lambda a, killed=False: self._execute_job(a, cwd))

    async def run(self, argv, *, timeout_seconds, env=None, cancel_event=None, cwd=None):
        self.started.append(list(argv))
        return self._execute_job(argv, cwd)


class FakeFfmpegPort(BlenderFfmpegPort):
    """Fake ffmpeg/ffprobe: writes an MP4, then probes it as JSON."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list = []

    async def run(self, argv, *, timeout_seconds):
        self.calls.append(list(argv))
        if self.fail:
            return _ff_result(argv, returncode=1, stderr="fake ffmpeg failure")
        if "ffprobe" in str(argv[0]) or "-show_format" in argv:
            # ffprobe: build a valid JSON payload
            payload = {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1920,
                        "height": 1080,
                        "avg_frame_rate": "24/1",
                        "duration": "5.000000",
                    }
                ],
                "format": {"format_name": "mov,mp4", "duration": "5.000000"},
            }
            return _ff_result(argv, returncode=0, stdout=json.dumps(payload))
        # ffmpeg: create the output file (last argv entry)
        out = Path(argv[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"MP4-DATA")
        return _ff_result(argv, returncode=0, stdout="ffmpeg ok")


def _ff_result(argv, *, returncode, stdout="", stderr=""):
    from windagent_tools.production_engines.blender.ffmpeg import FfmpegResult

    return FfmpegResult(
        argv=tuple(argv), returncode=returncode, stdout=stdout, stderr=stderr
    )


def make_ffmpeg_runner(fake_port: FakeFfmpegPort | None = None) -> BlenderFfmpegRunner:
    version = FfmpegVersion(
        ffmpeg_path="C:/fake/ffmpeg.exe",
        ffprobe_path="C:/fake/ffprobe.exe",
        ffmpeg_version_line="ffmpeg version 6.1",
        ffprobe_version_line="ffprobe version 6.1",
        ffmpeg_version_hash="a" * 64,
        ffprobe_version_hash="b" * 64,
    )
    return BlenderFfmpegRunner(version=version, port=fake_port or FakeFfmpegPort())


def make_pipeline(tmp_path, *, fake_blender=None, ffmpeg_port=None, **kwargs) -> BlenderSmokePipeline:
    process_port = fake_blender or FakeBlenderProcess()
    launcher = BlenderJobLauncher(artifact_root=str(tmp_path / "artifacts"), process_port=process_port)
    supervisor = BlenderProcessSupervisor(
        state_dir=str(tmp_path / "state"),
        launcher=launcher,
        heartbeat_seconds=0.02,
        cancel_grace_seconds=0.1,
    )
    runner = make_ffmpeg_runner(ffmpeg_port)
    defaults = dict(
        artifact_root=str(tmp_path / "artifacts"),
        state_dir=str(tmp_path / "pipeline_state"),
        launcher=launcher,
        supervisor=supervisor,
        ffmpeg_runner=runner,
        chunk_frames=5,
        extension="png",
    )
    defaults.update(kwargs)
    return BlenderSmokePipeline(**defaults)


def ir_fixture() -> tuple[SceneDescription, RenderIntent, ShotExecutionIntent]:
    doc = build_valid_ir()
    return doc.scenes[0], doc.render_intents[0], doc.shots[0]


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------
class TestScenePlanCompiler:
    def test_locks_all_required_config(self):
        scene, render, shot = ir_fixture()
        plan = ScenePlanCompiler().compile(scene, render, shot)
        assert plan.seed is not None
        assert plan.frame_start >= 1 and plan.frame_end > plan.frame_start
        assert plan.fps == 24
        assert plan.color_management in ("Standard", "Filmic", "AgX")
        assert plan.resolution["width"] > 0 and plan.resolution["height"] > 0
        assert plan.cycles_samples > 0
        assert isinstance(plan.denoise, bool)
        assert plan.device in ("CPU", "OPTIX", "CUDA", "NONE")
        # typed fixture: cube + ground
        assert [o.kind for o in plan.objects] == ["CUBE", "PLANE"]
        # three lights
        assert len(plan.lights) == 3
        # one material + keyframed animation
        assert plan.material.name
        assert plan.animation.target_object == "Cube"

    def test_same_ir_same_plan_hash_deterministic(self):
        scene, render, shot = ir_fixture()
        compiler = ScenePlanCompiler()
        plan_a = compiler.compile(scene, render, shot)
        plan_b = compiler.compile(scene, render, shot)
        assert plan_a.plan_hash() == plan_b.plan_hash()
        assert plan_a.idempotency_key() == plan_b.idempotency_key()
        assert plan_a.to_dict() == plan_b.to_dict()

    def test_input_hash_change_invalidates_key(self):
        scene, render, shot = ir_fixture()
        compiler = ScenePlanCompiler()
        plan_a = compiler.compile(scene, render, shot)
        scene_b = scene.model_copy(update={"action": "changed action"})
        plan_b = compiler.compile(scene_b, render, shot)
        assert plan_a.input_hash != plan_b.input_hash
        assert plan_a.idempotency_key() != plan_b.idempotency_key()

    def test_device_change_invalidates_key(self):
        scene, render, shot = ir_fixture()
        compiler = ScenePlanCompiler()
        plan_cpu = compiler.compile(scene, render, shot, device="CPU")
        plan_gpu = compiler.compile(scene, render, shot, device="OPTIX")
        assert plan_cpu.config_hash != plan_gpu.config_hash
        assert plan_cpu.idempotency_key() != plan_gpu.idempotency_key()

    def test_seed_locked_explicit(self):
        scene, render, shot = ir_fixture()
        plan = ScenePlanCompiler().compile(scene, render, shot, seed=99)
        assert plan.seed == 99

    def test_frame_end_derived_from_duration_when_zero(self):
        scene, render, shot = ir_fixture()
        render_zero = render.model_copy(update={"frame_end": 0})
        plan = ScenePlanCompiler().compile(scene, render_zero, shot)
        expected = plan.frame_start + int(round(shot.duration_seconds * 24)) - 1
        assert plan.frame_end == expected

    def test_build_script_is_pinned_and_hashes_stable(self):
        scene, render, shot = ir_fixture()
        compiler = ScenePlanCompiler()
        plan = compiler.compile(scene, render, shot)
        script_a = compiler.build_script(plan)
        script_b = compiler.build_script(plan)
        assert script_a == script_b
        assert "bpy" in script_a
        assert "scene_plan.json" in script_a
        # script is pure text: no import of windagent (runs inside blender)
        assert "windagent" not in script_a

    def test_tool_hash_changes_when_script_version_changes(self):
        scene, render, shot = ir_fixture()
        c1 = ScenePlanCompiler()
        plan = c1.compile(scene, render, shot)
        # simulate a tool identity change -> different key
        key = job_idempotency_key(
            kind=COMPILE, input_hash=plan.input_hash, config_hash=plan.config_hash,
            tool_hash="different-tool-hash",
        )
        assert key != plan.idempotency_key()


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------
class TestSmokeFixture:
    def test_typed_fixture_shape(self):
        fx = build_smoke_fixture()
        assert fx["cube"]["kind"] == "CUBE"
        assert fx["ground"]["kind"] == "PLANE"
        assert fx["camera"]["lens_mm"] > 0
        assert len(fx["lights"]) == 3
        assert fx["material"]["name"]
        assert fx["animation"]["target_object"] == "Cube"

    def test_fixture_content_hash_stable(self):
        assert fixture_content_hash() == fixture_content_hash()


# ---------------------------------------------------------------------------
# FrameManifest
# ---------------------------------------------------------------------------
class TestFrameManifest:
    def _manifest(self, tmp_path, frame_range=(1, 10), expected=None):
        return FrameManifest(
            workspace=tmp_path,
            frame_range=frame_range,
            extension="png",
            expected_dimensions=expected,
        )

    def test_atomic_finalize_moves_temp_to_final(self, tmp_path):
        manifest = self._manifest(tmp_path)
        tmp = manifest.temp_path(3)
        tmp.write_bytes(fake_png_bytes(10, 10))
        entry = manifest.finalize_frame(3)
        assert entry is not None
        assert not tmp.exists()
        assert manifest.final_path(3).is_file()
        assert manifest.has_frame(3)
        assert entry.sha256

    def test_cancel_publishes_nothing(self, tmp_path):
        manifest = self._manifest(tmp_path, expected={"width": 10, "height": 10})
        # wrong-dimension temp frame -> validation fails -> nothing published
        tmp = manifest.temp_path(5)
        tmp.write_bytes(fake_png_bytes(99, 99))
        entry = manifest.finalize_frame(5)
        assert entry is None
        assert not manifest.final_path(5).exists()
        assert not manifest.has_frame(5)

    def test_resume_from_next_valid_frame(self, tmp_path):
        manifest = self._manifest(tmp_path, frame_range=(1, 10))
        for f in (1, 2, 3):
            manifest.temp_path(f).write_bytes(fake_png_bytes(10, 10))
            manifest.finalize_frame(f)
        # resume starts at frame 4
        assert manifest.next_frame() == 4

    def test_manifest_hash_stable(self, tmp_path):
        m1 = self._manifest(tmp_path / "a")
        m1.temp_path(1).write_bytes(fake_png_bytes(10, 10))
        m1.finalize_frame(1)
        h1 = m1.manifest_hash()
        m2 = FrameManifest(workspace=tmp_path / "a", frame_range=(1, 10), extension="png")
        assert m2.manifest_hash() == h1


# ---------------------------------------------------------------------------
# Idempotency / reuse
# ---------------------------------------------------------------------------
class TestArtifactReusePolicy:
    def test_reuse_when_keys_match(self):
        decision = ArtifactReusePolicy().decide(
            requested_key="k1",
            recorded_job_id="ej_1",
            recorded_state="COMPLETED",
            recorded_key="k1",
        )
        assert decision.decision == REUSE and decision.can_serve

    def test_invalidate_when_key_differs(self):
        decision = ArtifactReusePolicy().decide(
            requested_key="k1",
            recorded_job_id="ej_1",
            recorded_state="COMPLETED",
            recorded_key="k2",
        )
        assert decision.decision == INVALIDATE
        assert not decision.can_serve

    def test_fresh_when_no_prior_job(self):
        decision = ArtifactReusePolicy().decide(
            requested_key="k1", recorded_job_id=None, recorded_state=None, recorded_key=None
        )
        assert decision.decision == "FRESH"

    def test_non_terminal_requires_reconcile(self):
        decision = ArtifactReusePolicy().decide(
            requested_key="k1",
            recorded_job_id="ej_1",
            recorded_state="RUNNING",
            recorded_key="k1",
        )
        assert decision.decision == "NON_TERMINAL"

    def test_invalidate_removes_stale_outputs(self, tmp_path):
        (tmp_path / "frame_0001.png").write_bytes(b"old")
        (tmp_path / "scene.blend").write_bytes(b"old")
        (tmp_path / "job_spec.json").write_bytes(b"keep")
        ArtifactReusePolicy().invalidate_outputs(tmp_path, keep=("job_spec.json",))
        assert not (tmp_path / "frame_0001.png").exists()
        assert not (tmp_path / "scene.blend").exists()
        assert (tmp_path / "job_spec.json").exists()

    def test_job_key_combines_all_three_hashes(self):
        key = job_idempotency_key(kind=COMPILE, input_hash="i", config_hash="c", tool_hash="t")
        key2 = job_idempotency_key(kind=COMPILE, input_hash="i2", config_hash="c", tool_hash="t")
        assert key != key2


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
class TestDeterminism:
    def test_identical_runs_pass(self):
        snapshot = RunSnapshot(
            run_label="a",
            scene_plan_hash="h1",
            idempotency_key="k1",
            frame_manifest_hash="m1",
            frame_hashes={"1": "f1", "2": "f2"},
            final_mp4_hash="mp4",
            ffprobe={"duration": "5.0"},
            hardware_profile={"device": "CPU", "build": "4.5.3", "driver": "", "color_management": "Standard"},
        )
        report = compare_runs(snapshot, snapshot)
        assert report.passed
        assert report.structural_stable and report.frame_hashes_stable

    def test_frame_hash_diff_fails_on_identical_hardware(self):
        a = RunSnapshot(
            run_label="a", scene_plan_hash="h", idempotency_key="k",
            frame_hashes={"1": "f1"}, hardware_profile={"device": "CPU"},
        )
        b = RunSnapshot(
            run_label="b", scene_plan_hash="h", idempotency_key="k",
            frame_hashes={"1": "DIFFERENT"}, hardware_profile={"device": "CPU"},
        )
        report = compare_runs(a, b)
        assert not report.frame_hashes_stable
        assert not report.passed

    def test_pixel_parity_only_enforced_on_identical_hardware(self):
        a = RunSnapshot(
            run_label="a", scene_plan_hash="h", idempotency_key="k",
            frame_hashes={"1": "f1"}, hardware_profile={"device": "OPTIX"},
        )
        b = RunSnapshot(
            run_label="b", scene_plan_hash="h", idempotency_key="k",
            frame_hashes={"1": "f2"}, hardware_profile={"device": "CPU"},
        )
        # different hardware -> pixel parity NOT enforced -> structural pass
        report = compare_runs(a, b)
        assert not report.hardware_identical
        assert not report.pixel_parity_enforced


# ---------------------------------------------------------------------------
# FFmpeg runner
# ---------------------------------------------------------------------------
class TestFfmpegRunner:
    def test_assemble_writes_mp4_and_hash(self, tmp_path):
        port = FakeFfmpegPort()
        runner = make_ffmpeg_runner(port)
        result = asyncio.run(
            runner.assemble_frames(
                job_id="ej_a",
                workspace=str(tmp_path),
                frame_start=1,
                frame_end=10,
                fps=24,
            )
        )
        assert result.ok
        assert (tmp_path / "final.mp4").is_file()
        assert result.output_hash

    def test_assemble_failure_fails_closed(self, tmp_path):
        runner = make_ffmpeg_runner(FakeFfmpegPort(fail=True))
        result = asyncio.run(
            runner.assemble_frames(
                job_id="ej_b", workspace=str(tmp_path), frame_start=1, frame_end=10, fps=24
            )
        )
        assert not result.ok
        assert "fake ffmpeg failure" in result.error

    def test_verify_parses_ffprobe(self, tmp_path):
        (tmp_path / "final.mp4").write_bytes(b"MP4-DATA")
        runner = make_ffmpeg_runner()
        result = asyncio.run(
            runner.verify_mp4(job_id="ej_c", workspace=str(tmp_path))
        )
        assert result.ok
        assert result.ffprobe.get("streams")
        assert result.ffprobe["streams"][0]["codec_type"] == "video"

    def test_verify_missing_mp4_fails(self, tmp_path):
        runner = make_ffmpeg_runner()
        result = asyncio.run(
            runner.verify_mp4(job_id="ej_d", workspace=str(tmp_path))
        )
        assert not result.ok
        assert "missing" in result.error

    def test_tool_hash_pins_ffmpeg_identity(self):
        runner = make_ffmpeg_runner()
        assert len(runner.tool_hash()) == 64


# ---------------------------------------------------------------------------
# Pipeline — full flow
# ---------------------------------------------------------------------------
class TestBlenderSmokePipeline:
    def test_full_flow_completes(self, tmp_path):
        pipeline = make_pipeline(tmp_path)
        ir = build_valid_ir()
        result = asyncio.run(
            pipeline.run_smoke(ir, executable_path=BLENDER_EXE)
        )
        assert result.ok, result.error
        kinds = [o.kind for o in result.job_outcomes]
        assert COMPILE in kinds and SAVE in kinds and INSPECT in kinds
        assert RENDER_CHUNK in kinds and ASSEMBLE in kinds and VERIFY in kinds
        assert result.final_mp4_hash
        assert result.frame_manifest_hash
        assert result.ffprobe.get("streams")

    def test_compile_reuse_on_second_run(self, tmp_path):
        pipeline = make_pipeline(tmp_path)
        ir = build_valid_ir()
        first = asyncio.run(pipeline.run_smoke(ir, executable_path=BLENDER_EXE))
        assert first.ok
        second = asyncio.run(pipeline.run_smoke(ir, executable_path=BLENDER_EXE))
        assert second.ok
        compile_outcomes = [o for o in second.job_outcomes if o.kind == COMPILE]
        assert compile_outcomes and compile_outcomes[0].reused
        # identical artifacts
        assert first.final_mp4_hash == second.final_mp4_hash
        assert first.frame_manifest_hash == second.frame_manifest_hash

    def test_cancel_mid_chunk_publishes_nothing_then_resume(self, tmp_path):
        ir = build_valid_ir()
        shot = ir.shots[0]
        # The pipeline uses shot=None by default (frame_end = 1s worth); pass
        # the shot so plan + pipeline agree on the frame range.
        plan = ScenePlanCompiler().compile(ir.scenes[0], ir.render_intents[0], shot)
        frame_end = plan.frame_end
        # First run: cancel after the first render chunk.
        pipeline = make_pipeline(tmp_path)
        cancelled = asyncio.run(
            pipeline.run_smoke(ir, shot=shot, executable_path=BLENDER_EXE, cancel_after_chunk=1)
        )
        assert not cancelled.ok
        assert "cancelled" in cancelled.error
        workspace = Path(cancelled.workspace)
        manifest = FrameManifest(
            workspace=workspace, frame_range=(1, frame_end), extension="png"
        )
        rendered = manifest.validated_frames
        assert rendered, "expected first chunk rendered"
        assert len(rendered) < frame_end

        # Resume: second run completes the remaining frames.
        resumed = asyncio.run(
            pipeline.run_smoke(ir, shot=shot, executable_path=BLENDER_EXE)
        )
        assert resumed.ok, resumed.error
        manifest2 = FrameManifest(
            workspace=workspace, frame_range=(1, frame_end), extension="png"
        )
        assert manifest2.next_frame() is None  # full range now validated
        assert len(manifest2.validated_frames) == frame_end

    def test_render_chunk_failure_fails_closed(self, tmp_path):
        pipeline = make_pipeline(tmp_path, fake_blender=FakeBlenderProcess(fail_kind=RENDER_CHUNK))
        ir = build_valid_ir()
        result = asyncio.run(pipeline.run_smoke(ir, executable_path=BLENDER_EXE))
        assert not result.ok
        assert "RENDER_CHUNK" in result.error

    def test_determinism_check_passes(self, tmp_path):
        pipeline = make_pipeline(tmp_path)
        ir = build_valid_ir()
        report = asyncio.run(
            pipeline.determinism_check(ir, executable_path=BLENDER_EXE)
        )
        assert report.passed
        assert report.structural_stable
        assert report.frame_hashes_stable
        assert report.final_mp4_stable
        assert report.ffprobe_stable


# ---------------------------------------------------------------------------
# execute_job dispatch (pure stdlib import, no blender)
# ---------------------------------------------------------------------------
def _load_execute_job():
    script = (
        Path(__file__).resolve().parents[3]
        / "tools" / "windagent_tools" / "production_engines" / "blender"
        / "scripts" / "execute_job.py"
    )
    spec = importlib.util.spec_from_file_location("execute_job", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestExecuteJobDispatch:
    def test_unknown_kind_refused(self, tmp_path):
        ej = _load_execute_job()
        rc = ej.main(["--job-id", "j1", "--kind", "NONSENSE", "--job-spec", str(tmp_path / "job_spec.json")])
        assert rc == 2

    def test_host_side_kinds_fail_closed(self, tmp_path):
        ej = _load_execute_job()
        workspace = tmp_path
        (workspace / "job_spec.json").write_text(json.dumps({"ir_hash": "x"}), encoding="utf-8")
        for kind in (ASSEMBLE, VERIFY):
            rc = ej.main(["--job-id", "j1", "--kind", kind, "--job-spec", str(workspace / "job_spec.json")])
            assert rc == 1
            result = json.loads((workspace / "job_result.json").read_text(encoding="utf-8"))
            assert result["ok"] is False
            assert "host-side" in result["error"]

    def test_cancel_before_start_clean_stop(self, tmp_path):
        ej = _load_execute_job()
        workspace = tmp_path
        (workspace / "job_spec.json").write_text(json.dumps({"ir_hash": "x"}), encoding="utf-8")
        (workspace / CANCEL_TOKEN_FILENAME).write_text("cancel\n", encoding="utf-8")
        rc = ej.main(["--job-id", "j1", "--kind", PROBE, "--job-spec", str(workspace / "job_spec.json")])
        assert rc == 0
        result = json.loads((workspace / "job_result.json").read_text(encoding="utf-8"))
        assert result["cancel_requested"] is True

    def test_atomic_frame_finalize_contract(self, tmp_path):
        ej = _load_execute_job()
        workspace = tmp_path
        ext = "png"
        temp = workspace / (FRAME_NAME_TEMPLATE.format(frame=7, ext=ext) + TEMP_SUFFIX)
        temp.write_bytes(fake_png_bytes(10, 10))
        entry = ej._finalize_frame_atomic(workspace, 7, ext)
        assert entry is not None
        assert entry["frame"] == 7
        assert not temp.exists()
        manifest = json.loads((workspace / ej.FRAME_MANIFEST_FILENAME).read_text(encoding="utf-8"))
        assert any(e["frame"] == 7 for e in manifest["frames"])
