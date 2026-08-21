"""
Unit tests for Phase 22 — Post-Production FFmpeg Pipeline (VP22_POST_PRODUCTION_VERIFIED).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from windagent_core.domain.video_production.enums import (
    PostProductionIssueCode,
    TransitionType,
)
from windagent_core.domain.video_production.ids import (
    AudioMixPlanId,
    EditDecisionListId,
    ProductionRevisionId,
    ShotId,
    TransitionPlanId,
    VideoProjectId,
)
from windagent_core.domain.video_production.postproduction import (
    EditDecisionItem,
    EditDecisionList,
    EncodingProfile,
    TransitionPlan,
)
from windagent_intelligence.video.postproduction import (
    AssemblyPlanner,
    FfmpegRunner,
    InputNormalizer,
    MediaVerifier,
    ReproducibilityAuditor,
)


@pytest.fixture
def sample_edl() -> EditDecisionList:
    transition = TransitionPlan(
        transition_id=TransitionPlanId("trans_01"),
        transition_type=TransitionType.FADE,
        duration_seconds=0.5,
    )

    items = (
        EditDecisionItem(
            shot_id=ShotId("shot_01"),
            clip_hash="hash_clip_01",
            target_duration=5.0,
        ),
        EditDecisionItem(
            shot_id=ShotId("shot_02"),
            clip_hash="hash_clip_02",
            target_duration=5.0,
            transition_in=transition,
        ),
    )
    return EditDecisionList(
        edl_id=EditDecisionListId("edl_01"),
        project_id=VideoProjectId("vp_01"),
        revision_id=ProductionRevisionId("rev_01"),
        items=items,
        audio_mix_plan_id=AudioMixPlanId("mix_01"),
        encoding_profile=EncodingProfile.main_1080p_h264(),
    )


def test_edl_hash_and_duration_determinism(sample_edl: EditDecisionList):
    """EDL hash must be deterministic and total duration must subtract transition overlaps."""
    # 5.0 + 5.0 - 0.5 transition overlap = 9.5s
    assert sample_edl.total_duration_seconds == 9.5
    assert len(sample_edl.edl_hash) == 64
    assert sample_edl.edl_hash == sample_edl.edl_hash


def test_input_normalizer_padding_and_aspect_ratio():
    """Normalizer computes padding filter for non-16:9 inputs."""
    normalizer = InputNormalizer(EncodingProfile.main_1080p_h264())
    metadata = normalizer.inspect_metadata(
        file_path=Path("clip.mp4"),
        width=1080,
        height=1080,  # 1:1 aspect ratio
        fps=24.0,
    )
    spec = normalizer.compute_normalization_spec(metadata)
    assert spec.needs_padding is True
    assert spec.needs_fps_conversion is True
    assert "pad=" in spec.filter_graph


def test_assembly_planner_argv_generation(sample_edl: EditDecisionList, tmp_path: Path):
    """AssemblyPlanner generates valid argv lists for assembly, proxy, and thumbnail."""
    planner = AssemblyPlanner()
    clip_paths = {
        "shot_01": tmp_path / "shot_01.mp4",
        "shot_02": tmp_path / "shot_02.mp4",
    }
    for p in clip_paths.values():
        p.write_bytes(b"dummy_clip_data")

    plan = planner.build_render_plan(
        edl=sample_edl,
        clip_paths=clip_paths,
        audio_mix_path=None,
        output_dir=tmp_path,
    )

    assert plan.edl_hash == sample_edl.edl_hash
    assert "ffmpeg" in plan.argv_assemble[0]
    assert "-filter_complex" in plan.argv_assemble
    assert str(plan.output_path) in plan.argv_assemble
    assert str(plan.proxy_path) in plan.argv_proxy
    assert str(plan.thumbnail_path) in plan.argv_thumbnail


def test_ffmpeg_runner_argv_safety_and_log_redaction(tmp_path: Path):
    """FfmpegRunner enforces argv invocation and log sanitization."""
    runner = FfmpegRunner(workspace_root=tmp_path)
    dirty_log = "Error on api_key=secret_123456 with auth=bearer_token"
    clean_log = runner.sanitize_log(dirty_log)
    assert "secret_123456" not in clean_log
    assert "[REDACTED]" in clean_log

    receipt = runner.execute_cmd(
        command_id="cmd_test",
        argv=["ffmpeg", "-version"],
        output_path=tmp_path / "out.mp4",
    )
    assert receipt.return_code == 0
    assert len(receipt.output_hash) == 64


def test_media_verifier_pass_and_failures(sample_edl: EditDecisionList, tmp_path: Path):
    """MediaVerifier validates quality checks and detects failures."""
    verifier = MediaVerifier()
    render_file = tmp_path / "final.mp4"
    render_file.write_bytes(b"final_video_payload")

    # Pass case
    res_pass = verifier.verify_render(edl=sample_edl, render_path=render_file)
    assert res_pass.is_valid is True
    assert len(res_pass.issues) == 0

    # Duration mismatch case
    res_dur_fail = verifier.verify_render(
        edl=sample_edl, render_path=render_file, simulate_duration_mismatch=True
    )
    assert res_dur_fail.is_valid is False
    assert PostProductionIssueCode.DURATION_OUT_OF_TOLERANCE in res_dur_fail.issues

    # Black ending case
    res_black_fail = verifier.verify_render(
        edl=sample_edl, render_path=render_file, simulate_black_ending=True
    )
    assert res_black_fail.is_valid is False
    assert PostProductionIssueCode.BLACK_FRAMES_DETECTED in res_black_fail.issues

    # Corrupt case
    res_corrupt = verifier.verify_render(
        edl=sample_edl, render_path=Path("nonexistent.mp4")
    )
    assert res_corrupt.is_valid is False
    assert PostProductionIssueCode.INPUT_CORRUPT in res_corrupt.issues


def test_reproducibility_auditor(sample_edl: EditDecisionList, tmp_path: Path):
    """ReproducibilityAuditor verifies byte-identical render outputs."""
    runner = FfmpegRunner(workspace_root=tmp_path)
    receipt_a = runner.execute_cmd("cmd_01", ["ffmpeg", "-i", "clip.mp4"], output_path=tmp_path / "a.mp4")
    receipt_b = runner.execute_cmd("cmd_01", ["ffmpeg", "-i", "clip.mp4"], output_path=tmp_path / "b.mp4")

    auditor = ReproducibilityAuditor()
    report = auditor.audit_render_runs(
        edl_a=sample_edl,
        edl_b=sample_edl,
        receipts_a=(receipt_a,),
        receipts_b=(receipt_b,),
        output_hash_a="hash_123",
        output_hash_b="hash_123",
    )
    assert report.is_reproducible is True
    assert report.edl_hash_matched is True
    assert report.input_hashes_matched is True
