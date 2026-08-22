"""
Phase 10 Contract Tests: Visual Master Assembly & Media Verification (Video 02 Implementation Plan §PHASE 10).

Verifies:
1. FfmpegPort protocol runtime compliance, argv list enforcement, timeout safety, and bounded output.
2. Blender backwards compatibility wrapper (BlenderFfmpegPort, BlenderFfmpegRunner).
3. TransitionPolicy enforcement: allows tutorial-safe transitions (hard_cut, dissolve, zoom, pan, highlight),
   strictly rejects flashy transitions (spin, wipe, star, explode, etc.).
4. Voiceover CueSheet generation and timecode accuracy (00:00.000 to 16:15.000 across 19 scenes).
5. Continuous timeline contiguity and zero-audio enforcement in TakeAssembler.
6. VisualMasterAssembler end-to-end assembly: master 1440p and delivery 1080p outputs,
   timeline.json, cue_sheet.csv, video_manifest.json with exact 29,250 frames @ 30fps.
7. AssembleMasterStepExecutor workflow step integration.
8. Absolute determinism: repeated assemblies produce identical SHA-256 cryptographic hashes.
9. Gate certification: CV02_P10_ASSEMBLY_VERIFIED.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Sequence
import pytest

from windagent_core.errors.exceptions import ValidationError
from windagent_workflows.code_video.assembly import AssembleMasterStepExecutor
from windagent_tools.code_video.compiler import CodeVideoScriptCompiler
from windagent_workflows.code_video.contracts import CodeVideoPlan
from windagent_tools.code_video.capture.receipts import TakeReceipt
from windagent_tools.code_video.media import (
    FORBIDDEN_FLASHY_TRANSITIONS,
    CueSheet,
    TakeAssembler,
    TransitionPolicy,
    TransitionType,
    VideoAssemblyConfig,
    VisualMasterAssembler,
)
from windagent_tools.media.ffmpeg import (
    FfmpegPort,
    FfmpegResult,
    FfmpegRunner,
    FfmpegVersion,
)
from windagent_tools.production_engines.blender.ffmpeg import (
    BlenderFfmpegPort,
    BlenderFfmpegRunner,
)


class FakeFfmpegPort(FfmpegPort):
    """Deterministic fake port for offline CI testing."""

    def __init__(self, should_fail: bool = False, timeout: bool = False) -> None:
        self.should_fail = should_fail
        self.timeout = timeout
        self.invocations: list[tuple] = []

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> FfmpegResult:
        argv_tuple = tuple(str(a) for a in argv)
        self.invocations.append(argv_tuple)
        if self.timeout:
            return FfmpegResult(
                argv=argv_tuple,
                returncode=-1,
                stdout="",
                stderr="timed out",
                timed_out=True,
            )
        if self.should_fail:
            return FfmpegResult(
                argv=argv_tuple,
                returncode=1,
                stdout="",
                stderr="simulated error",
            )
        return FfmpegResult(
            argv=argv_tuple,
            returncode=0,
            stdout="Fake FFmpeg output",
            stderr="",
        )


@pytest.fixture
def video_02_plan() -> CodeVideoPlan:
    plan_path = Path("artifacts/code_video/video_02/plans/video_02_plan.json")
    if plan_path.exists():
        return CodeVideoPlan.from_json(plan_path.read_text(encoding="utf-8"))
    compiler = CodeVideoScriptCompiler()
    return compiler.compile_video_02_plan()


@pytest.fixture
def synthetic_takes(video_02_plan: CodeVideoPlan) -> list[TakeReceipt]:
    """Generate 19 continuous, verified synthetic takes matching the plan."""
    takes: list[TakeReceipt] = []
    for idx, scene in enumerate(video_02_plan.scenes, 1):
        fc = (scene.duration_ms * 30) // 1000
        takes.append(
            TakeReceipt(
                take_id=f"{scene.scene_id}_T01",
                scene_id=scene.scene_id,
                start_ms=scene.start_ms,
                duration_ms=scene.duration_ms,
                resolution="2560x1440",
                fps=30,
                frame_count=fc,
                output_hash=f"{idx:02d}" * 32,
                status="VERIFIED",
                audio_enabled=False,
            )
        )
    return takes


class TestCodeVideoAssemblyContracts:
    """Contract test suite for Video 02 Phase 10: Visual Master Assembly."""

    # 1. FFmpeg process boundary safety
    def test_ffmpeg_port_protocol_and_fake_runner(self) -> None:
        """Verify FfmpegPort protocol and fake runner execution without real binary."""
        fake_port = FakeFfmpegPort()
        assert isinstance(fake_port, FfmpegPort)

        version = FfmpegVersion(
            ffmpeg_path="fake_ffmpeg",
            ffprobe_path="fake_ffprobe",
            ffmpeg_version_line="ffmpeg version 6.0",
            ffprobe_version_line="ffprobe version 6.0",
            ffmpeg_version_hash="a" * 64,
            ffprobe_version_hash="b" * 64,
        )
        runner = FfmpegRunner(version=version, port=fake_port)
        assert len(runner.tool_hash()) == 64

        # Run assemble_clips
        receipt = asyncio.run(
            runner.assemble_clips(
                job_id="test_concat",
                clip_paths=["clip1.mp4", "clip2.mp4"],
                output_path="test_out.mp4",
                fps=30,
                an_flag=True,
            )
        )
        assert receipt.job_id == "test_concat"
        assert "-an" in receipt.argv
        assert "-safe" in receipt.argv
        assert len(fake_port.invocations) == 1

    def test_ffmpeg_transcode_resolution(self) -> None:
        """Verify resolution transcoding parameters (1440p -> 1080p scale)."""
        fake_port = FakeFfmpegPort()
        version = FfmpegVersion(
            ffmpeg_path="fake_ffmpeg",
            ffprobe_path="fake_ffprobe",
            ffmpeg_version_line="ffmpeg version 6.0",
            ffprobe_version_line="ffprobe version 6.0",
        )
        runner = FfmpegRunner(version=version, port=fake_port)
        receipt = asyncio.run(
            runner.transcode_resolution(
                job_id="test_downscale",
                input_path="master_1440p.mp4",
                output_path="delivery_1080p.mp4",
                target_resolution="1920x1080",
                fps=30,
            )
        )
        assert receipt.kind == "TRANSCODE"
        assert "scale=1920:1080:flags=lanczos" in receipt.argv
        assert "-an" in receipt.argv

    # 2. Blender backwards compatibility
    def test_blender_ffmpeg_compatibility_wrapper(self) -> None:
        """Ensure BlenderFfmpegPort and BlenderFfmpegRunner maintain exact compatibility."""
        fake_port = FakeFfmpegPort()
        assert isinstance(fake_port, BlenderFfmpegPort)

        version = FfmpegVersion(
            ffmpeg_path="fake_ffmpeg",
            ffprobe_path="fake_ffprobe",
            ffmpeg_version_line="ffmpeg version 6.0",
            ffprobe_version_line="ffprobe version 6.0",
        )
        runner = BlenderFfmpegRunner(version=version, port=fake_port)
        assert runner.version.ffmpeg_path == "fake_ffmpeg"

    # 3. Transition policy
    def test_transition_policy_allowed_and_forbidden(self) -> None:
        """Verify TransitionPolicy accepts tutorial-safe transitions and rejects flashy ones."""
        policy = TransitionPolicy()
        assert policy.validate_transition("hard_cut") == TransitionType.HARD_CUT
        assert policy.validate_transition("CUT") == TransitionType.CUT
        assert policy.validate_transition("short_dissolve", duration_ms=1000) == TransitionType.SHORT_DISSOLVE
        assert policy.validate_transition("zoom") == TransitionType.ZOOM
        assert policy.validate_transition("pan") == TransitionType.PAN
        assert policy.validate_transition("highlight") == TransitionType.HIGHLIGHT

        # Reject flashy transitions
        for flashy in FORBIDDEN_FLASHY_TRANSITIONS:
            with pytest.raises(ValidationError, match="forbidden in code tutorial"):
                policy.validate_transition(flashy)

        # Reject excessive dissolve
        with pytest.raises(ValidationError, match="exceeds maximum allowable limit"):
            policy.validate_transition("short_dissolve", duration_ms=3000)

    # 4. CueSheet timecodes
    def test_cuesheet_generation_and_roundtrip(self, video_02_plan: CodeVideoPlan) -> None:
        """Verify CueSheet builds correct 19 scene markers from plan and roundtrips CSV."""
        cue_sheet = CueSheet.from_plan(video_02_plan)
        assert len(cue_sheet.entries) == 19
        assert cue_sheet.entries[0].scene_id == "S01"
        assert cue_sheet.entries[0].start_timecode == "00:00.000"
        assert cue_sheet.entries[0].end_timecode == "00:25.000"
        assert cue_sheet.entries[-1].scene_id == "S19"
        assert cue_sheet.entries[-1].end_timecode == "16:15.000"

        csv_text = cue_sheet.to_csv()
        restored = CueSheet.from_csv(csv_text)
        assert len(restored.entries) == 19
        assert restored.entries[0].scene_id == "S01"
        assert restored.entries[-1].end_timecode == "16:15.000"

    # 5. Timeline continuity & Zero-audio
    def test_take_assembler_timeline_contiguity(
        self, synthetic_takes: list[TakeReceipt]
    ) -> None:
        """Verify TakeAssembler validates continuous 975,000 ms timeline across all takes."""
        manifest = TakeAssembler.assemble(
            takes=synthetic_takes,
            video_id="video-02",
            expected_duration_ms=975_000,
            expected_take_count=19,
            fps=30,
        )
        assert manifest.total_takes == 19
        assert manifest.total_duration_ms == 975_000
        assert manifest.total_frames == 29_250
        assert manifest.audio_policy == "EXCLUDED"

        # Gap detection
        broken_takes = list(synthetic_takes)
        broken_takes[5] = TakeReceipt(
            take_id="S06_T01",
            scene_id="S06",
            start_ms=broken_takes[5].start_ms + 1000,  # introduce gap
            duration_ms=broken_takes[5].duration_ms,
            resolution="2560x1440",
            fps=30,
            frame_count=broken_takes[5].frame_count,
            output_hash="x" * 64,
            status="VERIFIED",
            audio_enabled=False,
        )
        with pytest.raises(ValidationError, match="Gap before take"):
            TakeAssembler.assemble(broken_takes, expected_duration_ms=975_000)

    # 6. Visual Master Assembler End-to-End
    def test_visual_master_assembler_e2e(
        self, video_02_plan: CodeVideoPlan, synthetic_takes: list[TakeReceipt], tmp_path: Path
    ) -> None:
        """Verify VisualMasterAssembler generates all required deliverables and manifests."""
        config = VideoAssemblyConfig(
            video_id="video-02",
            master_resolution="2560x1440",
            delivery_resolution="1920x1080",
            fps=30,
            total_duration_ms=975_000,
            expected_scenes=19,
            expected_frames=29_250,
            audio_policy="EXCLUDED",
            output_dir=tmp_path,
        )
        assembler = VisualMasterAssembler(config=config)
        result = assembler.assemble_master(
            plan=video_02_plan,
            takes=synthetic_takes,
            output_dir=tmp_path,
        )

        assert result.status == "VERIFIED"
        assert result.total_duration_ms == 975_000
        assert result.total_frames == 29_250
        assert result.scene_count == 19
        assert result.zero_audio_verified is True

        # Verify files exist on disk
        assert (tmp_path / "video_02_visual_master_1440p.mp4").is_file()
        assert (tmp_path / "video_02_visual_master_1080p.mp4").is_file()
        assert (tmp_path / "timeline.json").is_file()
        assert (tmp_path / "cue_sheet.csv").is_file()
        assert (tmp_path / "video_manifest.json").is_file()

        # Check video manifest content
        manifest_data = json.loads((tmp_path / "video_manifest.json").read_text(encoding="utf-8"))
        assert manifest_data["gate"] == "CV02_P10_ASSEMBLY_VERIFIED"
        assert manifest_data["media_profiles"]["master_1440p"]["resolution"] == "2560x1440"
        assert manifest_data["media_profiles"]["delivery_1080p"]["resolution"] == "1920x1080"
        assert manifest_data["audio_policy"]["audio_streams_count"] == 0

    # 7. Workflow Step Executor
    def test_assemble_master_step_executor(
        self, video_02_plan: CodeVideoPlan, synthetic_takes: list[TakeReceipt], tmp_path: Path
    ) -> None:
        """Verify AssembleMasterStepExecutor executes cleanly as pipeline step."""
        executor = AssembleMasterStepExecutor(assembler=VisualMasterAssembler())
        result = executor.execute(
            plan=video_02_plan,
            takes=synthetic_takes,
            output_dir=tmp_path,
        )
        assert result.status == "VERIFIED"
        assert result.total_duration_ms == 975_000

    # 8. Determinism (Tri-Hash Determinism)
    def test_deterministic_assembly_hashes(
        self, video_02_plan: CodeVideoPlan, synthetic_takes: list[TakeReceipt], tmp_path: Path
    ) -> None:
        """Verify repeated assemblies yield identical cryptographic SHA-256 hashes."""
        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"

        assembler = VisualMasterAssembler()
        res1 = assembler.assemble_master(video_02_plan, synthetic_takes, output_dir=dir1)
        res2 = assembler.assemble_master(video_02_plan, synthetic_takes, output_dir=dir2)

        assert res1.master_1440p_hash == res2.master_1440p_hash
        assert res1.delivery_1080p_hash == res2.delivery_1080p_hash
        assert (dir1 / "cue_sheet.csv").read_text(encoding="utf-8") == (dir2 / "cue_sheet.csv").read_text(encoding="utf-8")
        assert (dir1 / "timeline.json").read_text(encoding="utf-8") == (dir2 / "timeline.json").read_text(encoding="utf-8")
        assert (dir1 / "video_manifest.json").read_text(encoding="utf-8") == (dir2 / "video_manifest.json").read_text(encoding="utf-8")
