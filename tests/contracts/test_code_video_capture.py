"""
Phase 7 Contract Tests: Capture Engine for Video 02 (Video 02 Implementation Plan §PHASE 7).

Verifies:
1. CapturePort Protocol runtime compliance.
2. TakeReceipt, FrameReport, and MediaProbeReport validation, serializability, and zero-audio enforcement.
3. StudioCaptureEngine deterministic scene takes capture (2560x1440 @ 30fps).
4. Frame count precision across all 19 scenes (total 29,250 frames for 975,000 ms timeline).
5. Absolute determinism: repeated capture executions yield identical cryptographic SHA-256 hashes.
6. TakeAssembler contiguous timeline aggregation and manifest generation.
7. TakeVerifier gate compliance (CV02_P7_CAPTURE_VERIFIED).
"""

from __future__ import annotations

from pathlib import Path
import pytest

from windagent_core.errors.exceptions import ValidationError
from windagent_tools.code_video.compiler import CodeVideoScriptCompiler
from windagent_workflows.code_video.contracts import (
    CodeVideoPlan,
    Resolution,
)

from windagent_tools.code_video.capture import (
    BrowserCaptureAdapter,
    CapturePort,
    CaptureStatus,
    FrameMetadata,
    FrameReport,
    MediaProbeReport,
    StudioCaptureEngine,
    TakeReceipt,
)
from windagent_tools.code_video.media import (
    TakeAssembler,
    TakesManifest,
    TakeVerifier,
)


@pytest.fixture
def video_02_plan() -> CodeVideoPlan:
    plan_path = Path("artifacts/code_video/video_02/plans/video_02_plan.json")
    if plan_path.exists():
        return CodeVideoPlan.from_json(plan_path.read_text(encoding="utf-8"))
    Path("artifacts/code_video/video_02/source/script.md")
    compiler = CodeVideoScriptCompiler()
    return compiler.compile_video_02_plan()


class TestCodeVideoCaptureContracts:
    """Test suite for Phase 7 Capture Engine and Media verification."""

    def test_capture_port_protocol_adherence(self) -> None:
        """Verify StudioCaptureEngine and BrowserCaptureAdapter adhere to CapturePort protocol."""
        engine = StudioCaptureEngine()
        assert isinstance(engine, CapturePort)

        adapter = BrowserCaptureAdapter(engine=engine)
        assert isinstance(adapter, CapturePort)

    def test_take_receipt_schema_and_zero_audio_enforcement(self) -> None:
        """Verify TakeReceipt enforces valid timings, frame calculations, and zero audio."""
        receipt = TakeReceipt(
            take_id="S10_T01",
            scene_id="S10",
            start_ms=410000,
            duration_ms=95000,
            resolution="2560x1440",
            fps=30,
            frame_count=2850,
            output_hash="a" * 64,
            status="VERIFIED",
            audio_enabled=False,
        )
        assert receipt.expected_frame_count == 2850
        assert receipt.end_ms == 505000

        # Roundtrip JSON
        json_str = receipt.to_json()
        restored = TakeReceipt.from_json(json_str)
        assert restored == receipt

        # Reject audio_enabled = True
        with pytest.raises(ValidationError, match="Audio is EXCLUDED"):
            TakeReceipt(
                take_id="S10_T01",
                scene_id="S10",
                start_ms=410000,
                duration_ms=95000,
                audio_enabled=True,
            )

        # Reject negative start_ms
        with pytest.raises(ValidationError, match="start_ms must be non-negative"):
            TakeReceipt(
                take_id="S10_T01",
                scene_id="S10",
                start_ms=-100,
                duration_ms=95000,
            )

    def test_frame_report_and_media_probe_models(self) -> None:
        """Verify FrameReport and MediaProbeReport structure and serialization."""
        f_meta = FrameMetadata(
            frame_index=0,
            timestamp_ms=410000,
            scene_id="S10",
            visual_mode="CODE_STUDIO",
            frame_hash="f" * 64,
            is_keyframe=True,
            active_file="src/agent.py",
            cursor_position=[10, 1],
            event_label="Start S10",
        )
        frame_report = FrameReport(
            take_id="S10_T01",
            scene_id="S10",
            total_frames=2850,
            duration_ms=95000,
            fps=30,
            keyframe_count=1,
            keyframe_hashes=["f" * 64],
            frame_samples=[f_meta],
        )
        assert len(frame_report.frame_samples) == 1
        rep_json = frame_report.to_json()
        rep_restored = FrameReport.from_json(rep_json)
        assert rep_restored.take_id == "S10_T01"

        probe = MediaProbeReport(
            take_id="S10_T01",
            scene_id="S10",
            container="mp4",
            codec="h264",
            width=2560,
            height=1440,
            frame_rate=30.0,
            frame_count=2850,
            duration_seconds=95.0,
            audio_streams_count=0,
            has_video_stream=True,
            has_audio_stream=False,
        )
        probe_json = probe.to_json()
        probe_restored = MediaProbeReport.from_json(probe_json)
        assert probe_restored.audio_streams_count == 0
        assert probe_restored.has_audio_stream is False

    def test_studio_capture_engine_single_scene(self, video_02_plan: CodeVideoPlan) -> None:
        """Verify capturing S10 (Agent Implementation) produces valid 2,850 frames take."""
        scene_s10 = video_02_plan.get_scene("S10")
        assert scene_s10 is not None

        engine = StudioCaptureEngine()
        receipt, frame_report, probe_report = engine.capture_scene(
            scene=scene_s10,
            take_id="S10_T01",
            resolution=Resolution(2560, 1440),
            fps=30,
        )

        assert receipt.take_id == "S10_T01"
        assert receipt.scene_id == "S10"
        assert receipt.duration_ms == 95000
        assert receipt.frame_count == 2850
        assert receipt.resolution == "2560x1440"
        assert receipt.fps == 30
        assert receipt.status == "VERIFIED"
        assert receipt.audio_enabled is False
        assert len(receipt.output_hash) == 64

        assert frame_report.total_frames == 2850
        assert len(frame_report.keyframe_hashes) > 0
        assert len(frame_report.frame_samples) > 0

        assert probe_report.width == 2560
        assert probe_report.height == 1440
        assert probe_report.audio_streams_count == 0
        assert probe_report.has_video_stream is True
        assert probe_report.has_audio_stream is False

    def test_studio_capture_engine_session_lifecycle(self, video_02_plan: CodeVideoPlan) -> None:
        """Verify CapturePort start, mark, stop, inspect interactive lifecycle."""
        scene_s01 = video_02_plan.get_scene("S01")
        assert scene_s01 is not None

        engine = StudioCaptureEngine()
        assert engine.status == CaptureStatus.INITIALIZED

        take_id = engine.start(scene_s01, resolution=Resolution(2560, 1440), fps=30)
        assert take_id == "S01_T01"
        assert engine.status == CaptureStatus.RECORDING

        engine.mark(5000, {"event": "terminal_command_started"})
        engine.mark(20000, {"event": "terminal_output_completed"})

        receipt = engine.stop()
        assert engine.status == CaptureStatus.VERIFIED
        assert receipt.take_id == "S01_T01"
        assert receipt.duration_ms == 25000
        assert receipt.frame_count == 750

        inspected_probe = engine.inspect("S01_T01")
        assert inspected_probe.frame_count == 750
        assert inspected_probe.audio_streams_count == 0

    def test_capture_all_19_scenes_frame_precision(self, video_02_plan: CodeVideoPlan) -> None:
        """
        Verify all 19 scenes produce exactly 29,250 total frames across 975,000 ms timeline.
        """
        engine = StudioCaptureEngine()
        results = engine.capture_all_scenes(
            plan=video_02_plan,
            resolution=Resolution(2560, 1440),
            fps=30,
        )

        assert len(results) == 19

        total_frames = 0
        total_duration = 0

        for scene in video_02_plan.scenes:
            receipt, frame_rep, probe_rep = results[scene.scene_id]
            assert receipt.scene_id == scene.scene_id
            assert receipt.duration_ms == scene.duration_ms
            expected_fc = (scene.duration_ms * 30) // 1000
            assert receipt.frame_count == expected_fc
            assert receipt.audio_enabled is False
            assert probe_rep.audio_streams_count == 0

            total_frames += receipt.frame_count
            total_duration += receipt.duration_ms

        assert total_duration == 975_000
        assert total_frames == 29_250

    def test_capture_engine_determinism(self, video_02_plan: CodeVideoPlan) -> None:
        """
        Verify that 2 separate runs of capture_all_scenes on the same plan produce identical hashes.
        """
        engine1 = StudioCaptureEngine()
        results1 = engine1.capture_all_scenes(video_02_plan)

        engine2 = StudioCaptureEngine()
        results2 = engine2.capture_all_scenes(video_02_plan)

        for scene in video_02_plan.scenes:
            r1 = results1[scene.scene_id][0]
            r2 = results2[scene.scene_id][0]
            assert r1.output_hash == r2.output_hash, f"Hash mismatch in scene {scene.scene_id}"

    def test_take_assembler_and_manifest(self, video_02_plan: CodeVideoPlan) -> None:
        """Verify TakeAssembler consolidates 19 takes into contiguous TakesManifest."""
        engine = StudioCaptureEngine()
        results = engine.capture_all_scenes(video_02_plan)
        takes = [res[0] for res in results.values()]

        manifest = TakeAssembler.assemble(
            takes=takes,
            video_id="video-02",
            expected_duration_ms=975_000,
            expected_take_count=19,
            fps=30,
            master_resolution="2560x1440",
        )

        assert manifest.video_id == "video-02"
        assert manifest.total_takes == 19
        assert manifest.total_duration_ms == 975_000
        assert manifest.total_frames == 29_250
        assert manifest.audio_policy == "EXCLUDED"

        # Roundtrip JSON
        m_json = manifest.to_json()
        m_restored = TakesManifest.from_json(m_json)
        assert m_restored.total_frames == 29_250

    def test_take_assembler_rejects_gaps_and_overlaps(self) -> None:
        """Verify TakeAssembler detects temporal gaps or overlapping scenes."""
        take1 = TakeReceipt("S01_T01", "S01", 0, 25000, frame_count=750, output_hash="1"*64)
        take2_gap = TakeReceipt("S02_T01", "S02", 26000, 25000, frame_count=750, output_hash="2"*64)

        with pytest.raises(ValidationError, match="Gap before take 'S02_T01'"):
            TakeAssembler.assemble(
                takes=[take1, take2_gap],
                expected_duration_ms=51000,
                expected_take_count=2,
            )

        take2_overlap = TakeReceipt("S02_T01", "S02", 24000, 25000, frame_count=750, output_hash="2"*64)
        with pytest.raises(ValidationError, match="overlaps preceding take"):
            TakeAssembler.assemble(
                takes=[take1, take2_overlap],
                expected_duration_ms=49000,
                expected_take_count=2,
            )

    def test_take_verifier_gate_pass(self, video_02_plan: CodeVideoPlan) -> None:
        """Verify TakeVerifier successfully certifies all 19 takes for Phase 7 gate."""
        engine = StudioCaptureEngine()
        results = engine.capture_all_scenes(video_02_plan)

        for scene in video_02_plan.scenes:
            receipt, frame_report, probe_report = results[scene.scene_id]

            rec_ver = TakeVerifier.verify_take_receipt(receipt, scene=scene)
            assert rec_ver.is_valid is True, f"Receipt verification failed for {scene.scene_id}: {rec_ver.errors}"

            probe_ver = TakeVerifier.verify_media_probe(probe_report)
            assert probe_ver.is_valid is True, f"Probe verification failed for {scene.scene_id}: {probe_ver.errors}"

    def test_browser_capture_adapter(self, video_02_plan: CodeVideoPlan) -> None:
        """Verify BrowserCaptureAdapter delegates cleanly to capture engine."""
        scene_s02 = video_02_plan.get_scene("S02")
        assert scene_s02 is not None

        adapter = BrowserCaptureAdapter()
        receipt, f_rep, p_rep = adapter.capture_scene(scene_s02, resolution=Resolution(2560, 1440), fps=30)
        assert receipt.take_id == "S02_T01"
        assert receipt.frame_count == 750
        assert p_rep.has_video_stream is True
        assert p_rep.audio_streams_count == 0
