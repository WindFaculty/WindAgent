"""
Phase 11 Contract Tests: Final Visual QC & Certification (Video 02 Implementation Plan §PHASE 11).

Verifies:
1. StructuralQCVerifier: 19 scenes, 8 code scenes, required graphics, exact 975,000ms.
2. CodeCorrectnessVerifier: AST token normalizer, required classes & tests, forbidden SDK detection.
3. TerminalCorrectnessVerifier: 7 mandatory commands, pytest '2 passed', zero SCRIPT_RUNTIME_MISMATCH.
4. SecretQCVerifier: Multi-tier regex scanner, zero-tolerance secret rejection, safe placeholder whitelist.
5. ReadabilityQCVerifier: 2560x1440 canvas, 5%/10% safe area insets, typography scale, WCAG AA contrast.
6. TimingQCVerifier: Exact 975,000 ms (29,250 frames @ 30fps), 0 audio streams, cue sheet timecodes.
7. MasterVisualQCEngine: 24 Definition of Done (§12) criteria, final gate certification CV02_VISUAL_MASTER_VERIFIED.
8. FinalQCStepExecutor & FinalQCDriver: Disk artifact generation across phase_11/ and final/ dirs.
9. Determinism: Repeated QC evaluations generate identical cryptographic QC hashes.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from windagent_core.errors.exceptions import ValidationError
from windagent_tools.code_video.compiler import CodeVideoScriptCompiler
from windagent_workflows.code_video.contracts import CodeVideoPlan
from windagent_workflows.code_video.qc import FinalQCDriver, FinalQCStepExecutor
from windagent_tools.code_video.capture.receipts import TakeReceipt
from windagent_tools.code_video.media import (
    CueSheet,
    MasterAssemblyResult,
    VisualMasterAssembler,
)
from windagent_tools.code_video.qc import (
    CodeCorrectnessVerifier,
    CodeQCReport,
    DOD_CRITERIA,
    MasterVisualQCEngine,
    MasterVisualQCReport,
    ReadabilityQCReport,
    ReadabilityQCVerifier,
    SecretFinding,
    SecretQCReport,
    SecretQCVerifier,
    StructuralQCReport,
    StructuralQCVerifier,
    TerminalCorrectnessVerifier,
    TerminalQCReport,
    TimingQCReport,
    TimingQCVerifier,
    contrast_ratio,
    hex_to_rgb,
    relative_luminance,
)
from windagent_tools.code_video.renderer.graphics_catalog import GraphicsCatalog
from windagent_tools.code_video.renderer.theme import CodeVideoVisualTheme
from windagent_tools.code_video.workspace.golden_builder import (
    STEP_05_AGENT_CODE,
    STEP_06_TESTS_CODE,
    STEP_07_FINAL_AGENT_CODE,
)


@pytest.fixture
def video_02_plan() -> CodeVideoPlan:
    plan_path = Path("artifacts/code_video/video_02/plans/video_02_plan.json")
    if plan_path.exists():
        return CodeVideoPlan.from_json(plan_path.read_text(encoding="utf-8"))
    compiler = CodeVideoScriptCompiler()
    return compiler.compile_video_02_plan()


@pytest.fixture
def graphics_catalog() -> GraphicsCatalog:
    return GraphicsCatalog.build_default_video_02_catalog()


@pytest.fixture
def synthetic_takes(video_02_plan: CodeVideoPlan) -> list[TakeReceipt]:
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


@pytest.fixture
def assembly_result(
    video_02_plan: CodeVideoPlan, synthetic_takes: list[TakeReceipt], tmp_path: Path
) -> MasterAssemblyResult:
    assembler = VisualMasterAssembler()
    return assembler.assemble_master(
        plan=video_02_plan,
        takes=synthetic_takes,
        output_dir=tmp_path / "assembly",
    )


@pytest.fixture
def cue_sheet(video_02_plan: CodeVideoPlan) -> CueSheet:
    return CueSheet.from_plan(video_02_plan)


class TestCodeVideoFinalQCContracts:
    """Comprehensive contract tests for Phase 11 Visual QC & Certification."""

    # 1. Structural QC
    def test_structural_qc_valid_and_violations(
        self, video_02_plan: CodeVideoPlan, graphics_catalog: GraphicsCatalog
    ) -> None:
        """Verify StructuralQCVerifier validates valid plan and catches missing scenes or timing gaps."""
        report = StructuralQCVerifier.verify_plan(video_02_plan, graphics_catalog)
        assert report.is_valid is True
        assert report.total_scenes == 19
        assert report.total_duration_ms == 975_000
        assert report.total_frames == 29_250
        assert len(report.missing_scenes) == 0
        assert len(report.missing_code_scenes) == 0
        assert len(report.missing_graphics) == 0

        # Mutilate plan: remove scene S06
        mutilated_scenes = [s for s in video_02_plan.scenes if s.scene_id != "S06"]
        bad_plan = CodeVideoPlan(
            video_id=video_02_plan.video_id,
            schema_version=video_02_plan.schema_version,
            title=video_02_plan.title,
            duration_ms=video_02_plan.duration_ms - 55_000,
            resolution=video_02_plan.resolution,
            fps=video_02_plan.fps,
            scenes=mutilated_scenes,
            source_hash=video_02_plan.source_hash,
        )
        bad_report = StructuralQCVerifier.verify_plan(bad_plan)
        assert bad_report.is_valid is False
        assert "S06" in bad_report.missing_scenes
        assert "S06" in bad_report.missing_code_scenes

    # 2. Code Correctness QC
    def test_code_correctness_qc_valid_and_violations(self) -> None:
        """Verify CodeCorrectnessVerifier validates AST structure and rejects SDK leaks."""
        # Valid code
        report = CodeCorrectnessVerifier.verify_source_code(
            agent_py_source=STEP_07_FINAL_AGENT_CODE,
            test_agent_py_source=STEP_06_TESTS_CODE,
        )
        assert report.is_valid is True
        assert report.source_ast_valid is True
        assert report.test_ast_valid is True
        assert "Message" in report.classes_found
        assert "AgentConfig" in report.classes_found
        assert "LLMClient" in report.classes_found
        assert "FakeLLMClient" in report.classes_found
        assert "Agent" in report.classes_found
        assert len(report.missing_classes) == 0
        assert len(report.missing_test_functions) == 0
        assert len(report.forbidden_imports_found) == 0

        # Reject forbidden SDK leak
        leaked_code = "import openai\n" + STEP_07_FINAL_AGENT_CODE
        leak_report = CodeCorrectnessVerifier.verify_source_code(agent_py_source=leaked_code)
        assert leak_report.is_valid is False
        assert "openai" in leak_report.forbidden_imports_found

        # Reject missing class
        incomplete_code = "class Message: pass\nclass AgentConfig: pass"
        incomplete_report = CodeCorrectnessVerifier.verify_source_code(agent_py_source=incomplete_code)
        assert incomplete_report.is_valid is False
        assert "Agent" in incomplete_report.missing_classes

    # 3. Terminal Correctness QC
    def test_terminal_correctness_qc_valid_and_violations(
        self, video_02_plan: CodeVideoPlan
    ) -> None:
        """Verify TerminalCorrectnessVerifier verifies 7 commands and rejects missing commands."""
        report = TerminalCorrectnessVerifier.verify_plan_terminal_actions(video_02_plan)
        assert report.is_valid is True
        assert report.pytest_verified is True
        assert len(report.missing_mandatory_commands) == 0

        # Missing mandatory command violation
        plan_without_git = CodeVideoPlan(
            video_id=video_02_plan.video_id,
            schema_version=video_02_plan.schema_version,
            title=video_02_plan.title,
            duration_ms=video_02_plan.duration_ms,
            resolution=video_02_plan.resolution,
            fps=video_02_plan.fps,
            scenes=[s for s in video_02_plan.scenes if s.scene_id != "S05"],  # removes git init
            source_hash=video_02_plan.source_hash,
        )
        bad_term_report = TerminalCorrectnessVerifier.verify_plan_terminal_actions(plan_without_git)
        assert bad_term_report.is_valid is False
        assert "git init" in bad_term_report.missing_mandatory_commands

    # 4. Secret QC
    def test_secret_qc_clean_and_rejection(self) -> None:
        """Verify SecretQCVerifier detects real credentials and allows safe placeholders."""
        # Safe targets
        safe_targets = {
            "agent.py": STEP_07_FINAL_AGENT_CODE,
            ".env.example": "OPENAI_API_KEY=your_api_key_here\nANTHROPIC_API_KEY=sk-...\n",
            "overlay_card": "api_key = 'sk-...' ✕",
        }
        clean_report = SecretQCVerifier.scan_collection(safe_targets)
        assert clean_report.is_clean is True
        assert clean_report.verdict == "PASS"
        assert clean_report.findings_count == 0

        # Real secret injections
        dirty_targets = {
            "agent.py": "api_key = 'sk-abcdef1234567890abcdef1234567890abcdef12'",
            "google.py": "google_key = 'AIzaSyA12345678901234567890123456789012'",
            "groq.py": "gsk_1234567890abcdef1234567890",
            "aws.py": "aws_key = 'AKIA1234567890ABCDEF'",
            "rsa.key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...",
        }
        dirty_report = SecretQCVerifier.scan_collection(dirty_targets)
        assert dirty_report.is_clean is False
        assert dirty_report.verdict == "REJECT"
        assert dirty_report.findings_count == 5

    # 5. Readability & Safe Area QC
    def test_readability_qc_theme_and_safe_area(self) -> None:
        """Verify ReadabilityQCVerifier tests safe area insets, typography, and contrast."""
        theme = CodeVideoVisualTheme()
        report = ReadabilityQCVerifier.verify_theme(theme)
        assert report.is_valid is True
        assert report.canvas_resolution == "2560x1440"
        assert report.typography_scale_valid is True
        assert report.wcag_contrast_valid is True
        assert report.safe_area_valid is True
        assert report.metrics["body_contrast_ratio"] >= 4.5

        # Small font violation
        from windagent_tools.code_video.renderer.theme import TypographyScale
        bad_theme = CodeVideoVisualTheme(typography=TypographyScale(minimum_body_font_px=16))
        bad_report = ReadabilityQCVerifier.verify_theme(bad_theme)
        assert bad_report.is_valid is False
        assert bad_report.typography_scale_valid is False

        # Contrast utility tests
        assert contrast_ratio("#ffffff", "#000000") == 21.0
        assert hex_to_rgb("#ffffff") == (255, 255, 255)
        assert relative_luminance((0, 0, 0)) == 0.0

    # 6. Timing & Zero-Audio QC
    def test_timing_and_zero_audio_qc(
        self, assembly_result: MasterAssemblyResult, cue_sheet: CueSheet
    ) -> None:
        """Verify TimingQCVerifier checks 975,000ms, zero audio, and cue sheet continuity."""
        report = TimingQCVerifier.verify_assembly_result(assembly_result, cue_sheet)
        assert report.is_valid is True
        assert report.total_duration_ms == 975_000
        assert report.total_frames == 29_250
        assert report.scene_count == 19
        assert report.zero_audio_verified is True
        assert report.cuesheet_verified is True

        # Duration mismatch violation
        bad_assembly = MasterAssemblyResult(
            video_id=assembly_result.video_id,
            status=assembly_result.status,
            master_1440p_path="test_1440p.mp4",
            master_1440p_hash="x" * 64,
            delivery_1080p_path="test_1080p.mp4",
            delivery_1080p_hash="y" * 64,
            timeline_path="timeline.json",
            cue_sheet_path="cue_sheet.csv",
            manifest_path="video_manifest.json",
            total_duration_ms=900_000,
            total_frames=27_000,
            scene_count=18,
            zero_audio_verified=False,
        )
        bad_timing_report = TimingQCVerifier.verify_assembly_result(bad_assembly)
        assert bad_timing_report.is_valid is False
        assert bad_timing_report.zero_audio_verified is False

    # 7. Master Visual QC Engine End-to-End Evaluation
    def test_master_visual_qc_engine_evaluation(
        self,
        video_02_plan: CodeVideoPlan,
        assembly_result: MasterAssemblyResult,
        cue_sheet: CueSheet,
        graphics_catalog: GraphicsCatalog,
    ) -> None:
        """Verify MasterVisualQCEngine verifies all 24 DoD items and certifies gate."""
        report = MasterVisualQCEngine.evaluate_video_02(
            plan=video_02_plan,
            assembly_result=assembly_result,
            cue_sheet=cue_sheet,
            source_code_agent_py=STEP_07_FINAL_AGENT_CODE,
            source_code_test_py=STEP_06_TESTS_CODE,
            graphics_catalog=graphics_catalog,
        )

        assert report.is_valid is True
        assert report.verdict == "PASS"
        assert report.gate == "CV02_VISUAL_MASTER_VERIFIED"
        assert len(report.all_violations) == 0
        assert len(report.dod_checklist) == 24
        assert all(report.dod_checklist.values())
        assert len(report.qc_hash) == 64

    # 8. Final QC Step Executor and Driver Disk Generation
    def test_final_qc_step_executor_and_driver_disk_artifacts(
        self,
        video_02_plan: CodeVideoPlan,
        assembly_result: MasterAssemblyResult,
        cue_sheet: CueSheet,
        graphics_catalog: GraphicsCatalog,
        tmp_path: Path,
    ) -> None:
        """Verify FinalQCDriver writes complete phase_11 and final deliverables."""
        phase_11_dir = tmp_path / "phase_11"
        final_dir = tmp_path / "final"

        report = FinalQCDriver.run_and_save(
            plan=video_02_plan,
            assembly_result=assembly_result,
            cue_sheet=cue_sheet,
            source_code_agent_py=STEP_07_FINAL_AGENT_CODE,
            source_code_test_py=STEP_06_TESTS_CODE,
            phase_11_dir=phase_11_dir,
            final_dir=final_dir,
            graphics_catalog=graphics_catalog,
        )

        assert report.is_valid is True
        assert report.gate == "CV02_VISUAL_MASTER_VERIFIED"

        # Verify Phase 11 artifacts
        assert (phase_11_dir / "input_manifest.json").is_file()
        assert (phase_11_dir / "implementation_manifest.json").is_file()
        assert (phase_11_dir / "test_receipt.json").is_file()
        assert (phase_11_dir / "architecture_report.json").is_file()
        assert (phase_11_dir / "phase_report.md").is_file()
        assert (phase_11_dir / "phase_verdict.json").is_file()

        # Verify Final deliverables
        assert (final_dir / "final_video_hash.json").is_file()
        assert (final_dir / "timeline_report.json").is_file()
        assert (final_dir / "secret_scan.json").is_file()
        assert (final_dir / "visual_qc.json").is_file()

        # Verify phase_verdict content
        verdict_data = json.loads((phase_11_dir / "phase_verdict.json").read_text(encoding="utf-8"))
        assert verdict_data["gate"] == "CV02_VISUAL_MASTER_VERIFIED"
        assert verdict_data["verdict"] == "PASS"

    # 9. Determinism (Tri-Hash Determinism)
    def test_qc_report_determinism(
        self,
        video_02_plan: CodeVideoPlan,
        assembly_result: MasterAssemblyResult,
        cue_sheet: CueSheet,
        graphics_catalog: GraphicsCatalog,
    ) -> None:
        """Verify repeated QC runs produce identical cryptographic QC hash."""
        rep1 = MasterVisualQCEngine.evaluate_video_02(
            plan=video_02_plan,
            assembly_result=assembly_result,
            cue_sheet=cue_sheet,
            source_code_agent_py=STEP_07_FINAL_AGENT_CODE,
            source_code_test_py=STEP_06_TESTS_CODE,
            graphics_catalog=graphics_catalog,
        )
        rep2 = MasterVisualQCEngine.evaluate_video_02(
            plan=video_02_plan,
            assembly_result=assembly_result,
            cue_sheet=cue_sheet,
            source_code_agent_py=STEP_07_FINAL_AGENT_CODE,
            source_code_test_py=STEP_06_TESTS_CODE,
            graphics_catalog=graphics_catalog,
        )
        assert rep1.qc_hash == rep2.qc_hash
