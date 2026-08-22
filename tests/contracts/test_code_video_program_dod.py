"""
Phase 12 Contract Tests: Program Definition of Done & Program Handoff (Video 02 Implementation Plan §12).

Verifies:
1. ProgramCertificationEngine: Evaluates all 24 DoD criteria (§12) against Video 02 artifacts.
2. Upstream Phase Chain Traceability: Verifies phase verdicts across Phase 00 - Phase 11.
3. Downstream Handoff Package: Assembles complete voiceover delivery bundle (1440p master, 1080p delivery, cue sheet, timeline JSON, timecoded script, video manifest).
4. Timecoded Script Generation: Validates exact milliseconds timecodes across all 19 scenes.
5. ProgramCertificationDriver: Writes all Phase 12 artifacts and handoff package to disk.
6. Cryptographic Determinism: Repeated certification runs generate identical program master hash.
7. Violation Detection: Correctly identifies missing DoD items or missing upstream phase verdicts.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from windagent_tools.code_video.compiler import CodeVideoScriptCompiler
from windagent_workflows.code_video.contracts import CodeVideoPlan
from windagent_workflows.code_video.program_certification import (
    ProgramCertificationDriver,
)
from windagent_tools.code_video.media.assembler import CueSheet, MasterAssemblyResult
from windagent_tools.code_video.program import (
    ProgramCertificationEngine,
)
from windagent_tools.code_video.qc.engine import MasterVisualQCEngine, MasterVisualQCReport
from windagent_tools.code_video.renderer.graphics_catalog import GraphicsCatalog
from windagent_tools.code_video.workspace.golden_builder import (
    STEP_06_TESTS_CODE,
    STEP_07_FINAL_AGENT_CODE,
)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def video_02_plan(repo_root: Path) -> CodeVideoPlan:
    plan_path = repo_root / "artifacts" / "code_video" / "video_02" / "plans" / "video_02_plan.json"
    if plan_path.exists():
        return CodeVideoPlan.from_json(plan_path.read_text(encoding="utf-8"))
    compiler = CodeVideoScriptCompiler()
    return compiler.compile_video_02_plan()


@pytest.fixture
def graphics_catalog() -> GraphicsCatalog:
    return GraphicsCatalog.build_default_video_02_catalog()


@pytest.fixture
def cue_sheet(repo_root: Path) -> CueSheet:
    cue_sheet_path = repo_root / "artifacts" / "code_video" / "video_02" / "final" / "cue_sheet.csv"
    if cue_sheet_path.exists():
        return CueSheet.from_csv(cue_sheet_path.read_text(encoding="utf-8"))
    # Fallback synthetic cue sheet
    entries = []
    from windagent_tools.code_video.compiler import CodeVideoScriptCompiler
    plan = CodeVideoScriptCompiler().compile_video_02_plan()
    from windagent_tools.code_video.media.assembler import CueEntry
    for scene in plan.scenes:
        entries.append(
            CueEntry(
                scene_id=scene.scene_id,
                start_timecode=f"{scene.start_ms // 1000:02d}:00.000",
                end_timecode=f"{scene.end_ms // 1000:02d}:00.000",
                start_ms=scene.start_ms,
                end_ms=scene.end_ms,
                duration_ms=scene.duration_ms,
                voice_reference=f"CUE_{scene.scene_id}",
            )
        )
    return CueSheet(entries=entries)


@pytest.fixture
def assembly_result(video_02_plan: CodeVideoPlan, repo_root: Path) -> MasterAssemblyResult:
    final_dir = repo_root / "artifacts" / "code_video" / "video_02" / "final"
    return MasterAssemblyResult(
        video_id=video_02_plan.video_id,
        status="VERIFIED",
        master_1440p_path=str(final_dir / "video_02_visual_master_1440p.mp4"),
        master_1440p_hash="1a3b681fbb79d38d140ed00a671cc8ccd0aa74e86f6547cec1e873ac52dc837c",
        delivery_1080p_path=str(final_dir / "video_02_visual_master_1080p.mp4"),
        delivery_1080p_hash="51ca27dd9de2feff4879c3314381ed61530485e75593a6451290071b161c4773",
        timeline_path=str(final_dir / "timeline.json"),
        cue_sheet_path=str(final_dir / "cue_sheet.csv"),
        manifest_path=str(final_dir / "video_manifest.json"),
        total_duration_ms=video_02_plan.duration_ms,
        total_frames=(video_02_plan.duration_ms * video_02_plan.fps) // 1000,
        scene_count=len(video_02_plan.scenes),
        zero_audio_verified=True,
    )


@pytest.fixture
def master_qc_report(
    video_02_plan: CodeVideoPlan,
    assembly_result: MasterAssemblyResult,
    cue_sheet: CueSheet,
    graphics_catalog: GraphicsCatalog,
) -> MasterVisualQCReport:
    return MasterVisualQCEngine.evaluate_video_02(
        plan=video_02_plan,
        assembly_result=assembly_result,
        cue_sheet=cue_sheet,
        source_code_agent_py=STEP_07_FINAL_AGENT_CODE,
        source_code_test_py=STEP_06_TESTS_CODE,
        graphics_catalog=graphics_catalog,
    )


class TestCodeVideoProgramCertification:
    """Contract tests for Phase 12 Program Certification and DoD compliance."""

    def test_program_certification_all_24_dod_pass(
        self,
        video_02_plan: CodeVideoPlan,
        master_qc_report: MasterVisualQCReport,
        repo_root: Path,
    ) -> None:
        """Verify ProgramCertificationEngine validates all 24 DoD criteria with 100% pass rate."""
        final_dir = repo_root / "artifacts" / "code_video" / "video_02" / "final"
        report = ProgramCertificationEngine.certify_program(
            plan=video_02_plan,
            qc_report=master_qc_report,
            final_dir=final_dir,
            repo_root=repo_root,
        )

        assert report.is_valid is True
        assert report.verdict == "PASS"
        assert report.final_milestone_verdict == "CODE_VIDEO_VIDEO02_VERIFIED"
        assert report.visual_gate == "CV02_VISUAL_MASTER_VERIFIED"
        assert len(report.dod_matrix) == 24
        assert all(item.status == "PASS" for item in report.dod_matrix)
        assert len(report.all_violations) == 0
        assert len(report.program_master_hash) == 64

        # Verify specific DoD item details
        dod_dict = {item.id: item for item in report.dod_matrix}
        assert dod_dict["DOD_01"].requirement == "WindAgent build được tutorial repo từ workspace trống"
        assert dod_dict["DOD_05"].category == "Clean Architecture"
        assert dod_dict["DOD_18"].status == "PASS"
        assert dod_dict["DOD_19"].category == "Audio Policy"
        assert dod_dict["DOD_24"].requirement.startswith("Gate cuối")

    def test_upstream_phase_chain_traceability(self, repo_root: Path) -> None:
        """Verify all upstream phase manifests from Phase 00 to Phase 11 exist."""
        chain = ProgramCertificationEngine.verify_phase_chain(repo_root)
        assert len(chain) == 12
        for phase_num in range(0, 12):
            pname = f"phase_{phase_num:02d}"
            assert chain[pname] is True, f"Missing upstream verdict for {pname}"

    def test_handoff_package_completeness(
        self,
        video_02_plan: CodeVideoPlan,
        assembly_result: MasterAssemblyResult,
        repo_root: Path,
    ) -> None:
        """Verify downstream voiceover handoff package includes all required media and metadata."""
        final_dir = repo_root / "artifacts" / "code_video" / "video_02" / "final"
        pkg = ProgramCertificationEngine.build_handoff_package(
            final_dir=final_dir,
            plan=video_02_plan,
            assembly_result=assembly_result,
        )

        assert pkg.video_id == "video-02"
        assert pkg.total_duration_ms == 975_000
        assert pkg.total_frames == 29_250
        assert pkg.scene_count == 19
        assert pkg.audio_policy == "EXCLUDED"
        assert len(pkg.files) >= 5
        assert len(pkg.package_hash) == 64

        filenames = [f.filename for f in pkg.files]
        assert "video_02_visual_master_1440p.mp4" in filenames
        assert "video_02_visual_master_1080p.mp4" in filenames
        assert "cue_sheet.csv" in filenames
        assert "timeline.json" in filenames
        assert "script_with_timecodes.md" in filenames

    def test_timecoded_script_generator(self, video_02_plan: CodeVideoPlan) -> None:
        """Verify generate_timecoded_script creates formatted markdown with 19 scenes and cues."""
        script_md = ProgramCertificationEngine.generate_timecoded_script(video_02_plan)
        assert "# VIDEO 02: VIẾT AI AGENT ĐẦU TIÊN BẰNG PYTHON" in script_md
        assert "16:15.000" in script_md
        assert "2560×1440" in script_md
        assert "Phân Cảnh S01: Cold Open" in script_md
        assert "Phân Cảnh S10: Agent" in script_md
        assert "Phân Cảnh S19: Video 03 Teaser" in script_md
        assert "CUE_S01" in script_md
        assert "CUE_S19" in script_md

    def test_program_certification_driver_disk_artifacts(
        self,
        video_02_plan: CodeVideoPlan,
        master_qc_report: MasterVisualQCReport,
        repo_root: Path,
        tmp_path: Path,
    ) -> None:
        """Verify ProgramCertificationDriver writes all Phase 12 artifacts to disk."""
        phase_12_dir = tmp_path / "phase_12"
        final_dir = tmp_path / "final"

        # Copy existing final artifacts to tmp final_dir for realistic simulation
        real_final = repo_root / "artifacts" / "code_video" / "video_02" / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        for f in real_final.glob("*"):
            if f.is_file():
                (final_dir / f.name).write_bytes(f.read_bytes())

        report = ProgramCertificationDriver.run_and_save(
            plan=video_02_plan,
            qc_report=master_qc_report,
            phase_12_dir=phase_12_dir,
            final_dir=final_dir,
            repo_root=repo_root,
            engine=ProgramCertificationEngine,
        )

        assert report.is_valid is True
        assert report.verdict == "PASS"

        # Check phase_12 artifacts
        assert (phase_12_dir / "input_manifest.json").is_file()
        assert (phase_12_dir / "implementation_manifest.json").is_file()
        assert (phase_12_dir / "test_receipt.json").is_file()
        assert (phase_12_dir / "architecture_report.json").is_file()
        assert (phase_12_dir / "phase_report.md").is_file()
        assert (phase_12_dir / "phase_verdict.json").is_file()
        assert (phase_12_dir / "dod_matrix.json").is_file()
        assert (phase_12_dir / "handoff_manifest.json").is_file()

        # Check final handoff script
        assert (final_dir / "script_with_timecodes.md").is_file()

        # Validate phase_verdict content
        verdict_data = json.loads((phase_12_dir / "phase_verdict.json").read_text(encoding="utf-8"))
        assert verdict_data["final_milestone_verdict"] == "CODE_VIDEO_VIDEO02_VERIFIED"
        assert verdict_data["visual_gate"] == "CV02_VISUAL_MASTER_VERIFIED"
        assert verdict_data["dod_matrix_pass_count"] == 24
        assert verdict_data["dod_matrix_total_count"] == 24

    def test_program_master_hash_determinism(
        self,
        video_02_plan: CodeVideoPlan,
        master_qc_report: MasterVisualQCReport,
        repo_root: Path,
    ) -> None:
        """Verify repeated certification runs produce identical program master hash."""
        final_dir = repo_root / "artifacts" / "code_video" / "video_02" / "final"
        rep1 = ProgramCertificationEngine.certify_program(
            plan=video_02_plan,
            qc_report=master_qc_report,
            final_dir=final_dir,
            repo_root=repo_root,
        )
        rep2 = ProgramCertificationEngine.certify_program(
            plan=video_02_plan,
            qc_report=master_qc_report,
            final_dir=final_dir,
            repo_root=repo_root,
        )
        assert rep1.program_master_hash == rep2.program_master_hash

    def test_program_certification_rejections(
        self,
        video_02_plan: CodeVideoPlan,
        master_qc_report: MasterVisualQCReport,
        tmp_path: Path,
    ) -> None:
        """Verify certification rejects when upstream phase or DoD items fail."""
        empty_repo = tmp_path / "empty_repo"
        empty_repo.mkdir(parents=True, exist_ok=True)
        final_dir = tmp_path / "final"
        final_dir.mkdir(parents=True, exist_ok=True)

        report = ProgramCertificationEngine.certify_program(
            plan=video_02_plan,
            qc_report=master_qc_report,
            final_dir=final_dir,
            repo_root=empty_repo,
        )

        assert report.is_valid is False
        assert report.verdict == "REJECT"
        assert len(report.all_violations) > 0
        assert any("Missing upstream phase verdict" in v for v in report.all_violations)
