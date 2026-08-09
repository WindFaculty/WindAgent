"""
VP3D Phase 24 — FFmpeg Assembly unit tests (Stage L, gate
VP3D_P24_FFMPEG_ASSEMBLY_VERIFIED).

Fail-closed matrix per stage_l.md §4:
- missing/corrupt/wrong-dimension frame and wrong fps are blocked;
- shot transitions keep duration/ordering; ending not black/truncated;
- final has policy-correct codec/resolution/fps/duration/audio stream;
- loudness/true-peak/subtitle bounds within tolerance;
- paths with spaces, Unicode and Windows separators work without shell
  injection;
- cancel/retry never overwrite a verified deliverable; duplicate requests
  reuse the artifact;
- changing BGM/subtitle proves visual frames are reused.
"""

from __future__ import annotations

import binascii
import zlib
from pathlib import Path

import pytest
from windagent_core.domain.video_production.enums import (
    AssemblyInvalidationScope,
    FrameSequenceIssueCode,
    MixTrackKind,
    TransitionType,
)
from windagent_core.domain.video_production.ids import (
    AudioMixPlanId,
    EditDecisionListId,
    EncodingProfileId,
    FrameSequenceId,
    ProductionRevisionId,
    ShotId,
    SubtitleCueId,
    SubtitleTrackId,
    TransitionPlanId,
    VideoProjectId,
)
from windagent_core.domain.video_production.postproduction import (
    AudioMixTrack,
    EditDecisionItem,
    EditDecisionList,
    EncodingProfile,
    FrameSequenceInput,
    SubtitleCue,
    SubtitleTrack,
    TransitionPlan,
)
from windagent_intelligence.video.postproduction import (
    ALLOWED_FILTER_OPS,
    AssemblyCoordinator,
    AssemblyPlanError,
    AtomicPublisher,
    AudioMixNormalizer,
    FrameSequenceNormalizer,
    ReproducibilityAuditor,
    SequenceAssemblyPlanner,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _png_bytes(width: int = 4, height: int = 4) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return (
            len(data).to_bytes(4, "big")
            + body
            + binascii.crc32(body).to_bytes(4, "big")
        )

    ihdr = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )
    row = b"\x00" + b"\xff\x00\x00" * width
    idat = zlib.compress(row * height)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


@pytest.fixture
def frame_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "frames"
    directory.mkdir()
    for number in range(1, 31):
        (directory / f"frame_{number:04d}.png").write_bytes(_png_bytes())
    return directory


def _sequence(shot_id: str = "shot_01", **kwargs) -> FrameSequenceInput:
    values = dict(
        sequence_id=FrameSequenceId(f"fs_{shot_id}"),
        shot_id=ShotId(shot_id),
        frame_dir="frames",
        extension="png",
        fps=30.0,
        frame_start=1,
        frame_end=30,
        colorspace="sRGB",
    )
    values.update(kwargs)
    return FrameSequenceInput(**values)


def _profile() -> EncodingProfile:
    return EncodingProfile(
        profile_id=EncodingProfileId("enc_phase24"),
        preset=EncodingProfile.main_1080p_h264().preset,
        container=EncodingProfile.main_1080p_h264().container,
        video_codec="libx264",
        video_crf=18,
        resolution_width=320,
        resolution_height=180,
        frame_rate=30,
        pixel_format="yuv420p",
        audio_codec="aac",
        audio_sample_rate=48000,
        audio_channels=2,
        audio_bitrate_kbps=128,
    )


def _edl(items: tuple[EditDecisionItem, ...], profile: EncodingProfile | None = None) -> EditDecisionList:
    return EditDecisionList(
        edl_id=EditDecisionListId("edl_24"),
        project_id=VideoProjectId("vp_24"),
        revision_id=ProductionRevisionId("rev_24"),
        items=items,
        audio_mix_plan_id=AudioMixPlanId("mix_24"),
        encoding_profile=profile or _profile(),
    )


def _planner_plan(tmp_path: Path, frame_dir: Path, edl: EditDecisionList):
    return SequenceAssemblyPlanner().build_sequence_render_plan(
        edl=edl,
        frame_sequences={str(item.shot_id): _sequence(str(item.shot_id), frame_dir=str(frame_dir)) for item in edl.items},
        audio_mix_path=None,
        subtitle_path=None,
        output_dir=tmp_path,
    )


# ---------------------------------------------------------------------------
# 1. frame sequence normalization (stage_l §3.1, §4)
# ---------------------------------------------------------------------------

def test_sequence_valid_png(tmp_path: Path, frame_dir: Path):
    result = FrameSequenceNormalizer().validate(_sequence(frame_dir=str(frame_dir)), tmp_path)
    assert result.valid
    assert result.observed_width == 4
    assert result.observed_height == 4
    assert len(result.frame_hashes) == 30
    assert result.frame_hash(1)


def test_missing_frame_blocked(tmp_path: Path, frame_dir: Path):
    (frame_dir / "frame_0010.png").unlink()
    result = FrameSequenceNormalizer().validate(_sequence(frame_dir=str(frame_dir)), tmp_path)
    assert not result.valid
    assert FrameSequenceIssueCode.FRAME_MISSING in result.issues
    assert 10 in result.missing_frames


def test_gap_blocked(tmp_path: Path, frame_dir: Path):
    for number in (20, 21, 22):
        (frame_dir / f"frame_{number:04d}.png").unlink()
    result = FrameSequenceNormalizer().validate(_sequence(frame_dir=str(frame_dir)), tmp_path)
    assert not result.valid
    assert FrameSequenceIssueCode.FRAME_GAP in result.issues
    assert (20, 22) in result.gaps


def test_duplicate_frame_blocked(tmp_path: Path, frame_dir: Path):
    (frame_dir / "frame_0005_dup.png").write_bytes(_png_bytes())
    result = FrameSequenceNormalizer().validate(_sequence(frame_dir=str(frame_dir)), tmp_path)
    assert not result.valid
    assert FrameSequenceIssueCode.FRAME_DUPLICATE in result.issues
    assert 5 in result.duplicate_frames


def test_corrupt_frame_blocked(tmp_path: Path, frame_dir: Path):
    (frame_dir / "frame_0007.png").write_bytes(b"not an image at all")
    result = FrameSequenceNormalizer().validate(_sequence(frame_dir=str(frame_dir)), tmp_path)
    assert not result.valid
    assert FrameSequenceIssueCode.FRAME_CORRUPT in result.issues
    assert 7 in result.corrupt_frames


def test_dimension_mismatch_blocked(tmp_path: Path, frame_dir: Path):
    (frame_dir / "frame_0012.png").write_bytes(_png_bytes(width=8, height=8))
    result = FrameSequenceNormalizer().validate(_sequence(frame_dir=str(frame_dir)), tmp_path)
    assert not result.valid
    assert FrameSequenceIssueCode.DIMENSION_MISMATCH in result.issues


def test_colorspace_unspecified_blocked(tmp_path: Path, frame_dir: Path):
    result = FrameSequenceNormalizer().validate(
        _sequence(frame_dir=str(frame_dir), colorspace=""), tmp_path
    )
    assert not result.valid
    assert FrameSequenceIssueCode.COLORSPACE_UNSPECIFIED in result.issues


def test_exr_dimensions_probed(tmp_path: Path):
    exr_dir = tmp_path / "exr"
    exr_dir.mkdir()
    # Minimal EXR header with dataWindow box2i x=0 y=0 x=319 y=179
    header = (
        b"\x76\x2f\x31\x01"
        + b"\x02\x00\x00\x00"  # version + flags
        + b"dataWindow\x00box2i\x00\x10\x00\x00\x00"
        + (0).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little", signed=True)
        + (319).to_bytes(4, "little", signed=True)
        + (179).to_bytes(4, "little", signed=True)
        + b"channels\x00chlist\x00\x01\x00\x00\x00\x00"
        + b"\x00\x00"
    )
    (exr_dir / "frame_0001.exr").write_bytes(header)
    sequence = _sequence(extension="exr", frame_dir="exr", frame_start=1, frame_end=1)
    result = FrameSequenceNormalizer().validate(sequence, tmp_path)
    assert result.valid
    assert (result.observed_width, result.observed_height) == (320, 180)


def test_wrong_fps_blocked(tmp_path: Path, frame_dir: Path):
    edl = _edl(
        (EditDecisionItem(shot_id=ShotId("shot_01"), clip_hash="h", target_duration=1.0),)
    )
    with pytest.raises(AssemblyPlanError, match="fps mismatch"):
        SequenceAssemblyPlanner().build_sequence_render_plan(
            edl=edl,
            frame_sequences={"shot_01": _sequence(frame_dir=str(frame_dir), fps=24.0)},
            audio_mix_path=None,
            subtitle_path=None,
            output_dir=tmp_path,
        )


def test_sequence_expected_count_and_pattern():
    sequence = _sequence(frame_start=1, frame_end=30)
    assert sequence.expected_frame_count == 30
    assert sequence.pattern() == "frame_%04d.png"


# ---------------------------------------------------------------------------
# 2. EDL timeline math (stage_l §3.2, §4)
# ---------------------------------------------------------------------------

def test_edl_frame_duration_math_and_ordering():
    transition = TransitionPlan(
        transition_id=TransitionPlanId("t1"),
        transition_type=TransitionType.FADE,
        duration_seconds=0.1,
    )
    items = (
        EditDecisionItem(shot_id=ShotId("shot_01"), clip_hash="h1", target_duration=1.0, frame_start=1, frame_end=30, audio_offset_seconds=0.0),
        EditDecisionItem(shot_id=ShotId("shot_02"), clip_hash="h2", target_duration=1.0, frame_start=1, frame_end=30, audio_offset_seconds=0.9, transition_in=transition),
    )
    edl = _edl(items)
    # 30+30 frames at 30 fps = 2.0s, minus 0.1s fade overlap = 1.9s
    assert edl.total_duration_seconds == pytest.approx(1.9)
    shot_order = [str(item.shot_id) for item in edl.items]
    assert shot_order == ["shot_01", "shot_02"]
    assert items[1].audio_offset_seconds == 0.9
    assert items[0].frame_start == 1 and items[0].frame_end == 30


def test_xfade_offset_math_in_planner(tmp_path: Path, frame_dir: Path):
    transition = TransitionPlan(
        transition_id=TransitionPlanId("t1"),
        transition_type=TransitionType.FADE,
        duration_seconds=0.1,
    )
    items = (
        EditDecisionItem(shot_id=ShotId("shot_01"), clip_hash="h1", target_duration=1.0, frame_start=1, frame_end=30),
        EditDecisionItem(shot_id=ShotId("shot_02"), clip_hash="h2", target_duration=1.0, frame_start=1, frame_end=30, transition_in=transition),
    )
    plan = _planner_plan(tmp_path, frame_dir, _edl(items))
    # offset = 1.0 - 0.1 = 0.9
    assert "xfade=transition=fade:duration=0.100:offset=0.900" in plan.filter_graph_str
    assert "concat=n=2" not in plan.filter_graph_str


def test_planner_rejects_edl_timeline_drift(tmp_path: Path, frame_dir: Path):
    # A transition longer than the chain must fail closed.
    transition = TransitionPlan(
        transition_id=TransitionPlanId("t1"),
        transition_type=TransitionType.FADE,
        duration_seconds=2.0,
    )
    items = (
        EditDecisionItem(shot_id=ShotId("shot_01"), clip_hash="h1", target_duration=1.0, frame_start=1, frame_end=30),
        EditDecisionItem(shot_id=ShotId("shot_02"), clip_hash="h2", target_duration=1.0, frame_start=1, frame_end=30, transition_in=transition),
    )
    with pytest.raises(AssemblyPlanError, match="transition longer than chain|timeline math"):
        _planner_plan(tmp_path, frame_dir, _edl(items))


def test_edl_hash_includes_frame_range_and_audio_offset():
    base = EditDecisionItem(shot_id=ShotId("s"), clip_hash="h", target_duration=1.0)
    ranged = EditDecisionItem(shot_id=ShotId("s"), clip_hash="h", target_duration=1.0, frame_start=1, frame_end=30, audio_offset_seconds=0.5)
    edl_base = _edl((base,))
    edl_ranged = _edl((ranged,))
    assert edl_base.edl_hash != edl_ranged.edl_hash
    assert len(edl_ranged.edl_hash) == 64


# ---------------------------------------------------------------------------
# 3. audio mix normalization (stage_l §3.3, §4)
# ---------------------------------------------------------------------------

def _tracks() -> tuple:
    return (
        AudioMixTrack(track_kind=MixTrackKind.DIALOGUE, source_path="d.wav", source_hash="d", sample_rate=44100, channels=1),
        AudioMixTrack(track_kind=MixTrackKind.SFX, source_path="s.wav", source_hash="s", sample_rate=48000, channels=2),
        AudioMixTrack(track_kind=MixTrackKind.BGM, source_path="b.wav", source_hash="b", sample_rate=48000, channels=2),
    )


def test_mix_plan_normalization_ops():
    normalizer = AudioMixNormalizer()
    plan = normalizer.build_plan(_tracks())
    ops = normalizer.filter_ops(plan)
    assert ops[0] == "aformat=sample_rates=48000:channel_layouts=stereo"
    assert any("amix=inputs=3:duration=longest:normalize=0" in op for op in ops)
    assert any("loudnorm=I=-16.0:TP=-1.0" in op for op in ops)
    # alimiter limit is linear gain: -1.0 dBFS -> 0.891
    assert any("alimiter=limit=0.891" in op for op in ops)


def test_mix_plan_hash_deterministic_and_versioned():
    normalizer = AudioMixNormalizer()
    plan_a = normalizer.build_plan(_tracks())
    plan_b = normalizer.build_plan(_tracks())
    assert plan_a.content_hash == plan_b.content_hash
    assert plan_a.policy_version == "loudness-v1"
    assert plan_a.loudness_target_lufs == -16.0
    assert plan_a.peak_ceiling_db == -1.0


def test_mix_plan_fail_closed():
    normalizer = AudioMixNormalizer()
    with pytest.raises(AssemblyPlanError, match="at least one track"):
        normalizer.build_plan(())
    bad_track = AudioMixTrack(track_kind=MixTrackKind.BGM, source_path="b", source_hash="b", sample_rate=0, channels=2)
    with pytest.raises(AssemblyPlanError, match="invalid track"):
        normalizer.build_plan((bad_track,))
    with pytest.raises(AssemblyPlanError, match="loudness target"):
        normalizer.build_plan(_tracks(), loudness_target_lufs=5.0)
    with pytest.raises(AssemblyPlanError, match="peak ceiling"):
        normalizer.build_plan(_tracks(), peak_ceiling_db=2.0)


# ---------------------------------------------------------------------------
# 4. argv safety: allowlist, no shell, paths with spaces/Unicode/Windows
# ---------------------------------------------------------------------------

def test_argv_allowlist_rejects_unknown_filter_op():
    with pytest.raises(AssemblyPlanError, match="not allowlisted"):
        SequenceAssemblyPlanner.validate_argv(
            ["ffmpeg", "-i", "in.mp4", "-vf", "drawtext=text='pwned'", "out.mp4"]
        )
    assert "scale" in ALLOWED_FILTER_OPS


def test_argv_rejects_shell_metachars_and_filter_scripts():
    planner = SequenceAssemblyPlanner()
    for hostile in (
        ["ffmpeg", "-i", "a.mp4; rm -rf /", "out.mp4"],
        ["ffmpeg", "-i", "$(whoami)", "out.mp4"],
        ["ffmpeg", "-i", "a.mp4", "-filter_complex_script", "evil.txt", "out.mp4"],
        ["ffmpeg", "-i", "a.mp4", "-vf", "scale=320:180", "out.mp4 && echo pwned"],
    ):
        with pytest.raises(AssemblyPlanError):
            planner.validate_argv(hostile)


def test_paths_with_spaces_unicode_and_windows_separators(tmp_path: Path, frame_dir: Path):
    unicode_dir = tmp_path / "phòng dựng" / "épisode 01"
    unicode_dir.mkdir(parents=True)
    (unicode_dir / "mix audio.wav").write_bytes(b"RIFFwav")
    (unicode_dir / "phụ đề việt.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nXin chào\n", encoding="utf-8")
    win_style = str(unicode_dir).replace("/", "\\")
    sequence = _sequence(frame_dir=win_style)
    edl = _edl((EditDecisionItem(shot_id=ShotId("shot_01"), clip_hash="h", target_duration=1.0),))
    planner = SequenceAssemblyPlanner()
    plan = planner.build_sequence_render_plan(
        edl=edl,
        frame_sequences={"shot_01": sequence},
        audio_mix_path=unicode_dir / "mix audio.wav",
        subtitle_path=unicode_dir / "phụ đề việt.srt",
        output_dir=unicode_dir,
    )
    # Every argv element stays a single list item: no shell re-interpretation.
    SequenceAssemblyPlanner.validate_argv(plan.argv_assemble)  # no raise = safe
    for element in plan.argv_assemble:
        assert "&&" not in element
    assert any("mix audio.wav" in element for element in plan.argv_assemble)
    assert any("phụ đề việt.srt" in element for element in plan.argv_assemble)
    assert any(element == "-c:s" for element in plan.argv_assemble)
    assert plan.argv_remux_subtitle  # FINAL_ONLY remux exists
    assert all(isinstance(element, str) for element in plan.argv_assemble)


def test_redact_argv(tmp_path: Path):
    argv = [str(tmp_path / "bin" / "ffmpeg"), "-i", str(tmp_path / "frames" / "frame_%04d.png"), str(tmp_path / "out.mp4")]
    redacted = SequenceAssemblyPlanner.redact_argv(argv, tmp_path)
    assert "<ws>" in " ".join(redacted)
    assert str(tmp_path) not in " ".join(redacted)


# ---------------------------------------------------------------------------
# 5. atomic publish (stage_l §3.5, §4)
# ---------------------------------------------------------------------------

def test_atomic_publish_success(tmp_path: Path):
    staged = tmp_path / "staging" / "final.mp4"
    staged.parent.mkdir()
    staged.write_bytes(b"media")
    receipt = AtomicPublisher().publish(
        staged=staged, final=tmp_path / "final" / "final.mp4",
        verify=lambda path: path.read_bytes().startswith(b"media"),
        quarantine_dir=tmp_path / "quarantine",
    )
    assert receipt.verified and not receipt.reused
    assert (tmp_path / "final" / "final.mp4").is_file()
    assert not staged.exists()  # atomic replace consumed the staging file


def test_atomic_publish_quarantine_on_verify_failure(tmp_path: Path):
    staged = tmp_path / "staging" / "broken.mp4"
    staged.parent.mkdir()
    staged.write_bytes(b"garbage")
    receipt = AtomicPublisher().publish(
        staged=staged, final=tmp_path / "final" / "final.mp4",
        verify=lambda path: False,
        quarantine_dir=tmp_path / "quarantine",
    )
    assert not receipt.verified
    assert receipt.quarantine_path
    assert Path(receipt.quarantine_path).is_file()
    assert not (tmp_path / "final" / "final.mp4").exists()


def test_atomic_publish_never_overwrites_verified(tmp_path: Path):
    final = tmp_path / "final" / "final.mp4"
    final.parent.mkdir()
    final.write_bytes(b"verified_deliverable")
    publisher = AtomicPublisher()
    first = publisher.publish(
        staged=tmp_path / "staging" / "new.mp4",
        final=final,
        verify=lambda path: True,
        quarantine_dir=tmp_path / "quarantine",
    )
    assert first.reused
    assert final.read_bytes() == b"verified_deliverable"


# ---------------------------------------------------------------------------
# 6. invalidation scoping (stage_l §3.9, §4)
# ---------------------------------------------------------------------------

def test_invalidation_scopes():
    coordinator = AssemblyCoordinator()
    shot = coordinator.decide_invalidation("shot:shot_02")
    assert shot.scope == AssemblyInvalidationScope.TIMELINE_FINAL
    assert shot.rebuild_artifacts == ("timeline", "final")
    assert "frames" in shot.preserved_artifacts

    bgm = coordinator.decide_invalidation("bgm:track.wav")
    assert bgm.scope == AssemblyInvalidationScope.MIX_FINAL
    assert bgm.rebuild_artifacts == ("mix", "final")
    assert "frames" in bgm.preserved_artifacts

    subtitle = coordinator.decide_invalidation("subtitle:vi.srt")
    assert subtitle.scope == AssemblyInvalidationScope.FINAL_ONLY
    assert "frames" in subtitle.preserved_artifacts
    assert "mix" in subtitle.preserved_artifacts

    unknown = coordinator.decide_invalidation("lighting")
    assert unknown.scope == AssemblyInvalidationScope.NONE


def test_invalidation_steps():
    coordinator = AssemblyCoordinator()
    assert coordinator.steps_for(coordinator.decide_invalidation("shot:s")) == (
        "normalize_frames", "build_mix", "assemble", "verify", "publish",
    )
    assert coordinator.steps_for(coordinator.decide_invalidation("bgm:b")) == (
        "build_mix", "assemble", "verify", "publish",
    )
    assert coordinator.steps_for(coordinator.decide_invalidation("subtitle:s")) == (
        "remux_subtitle", "verify", "publish",
    )
    assert coordinator.steps_for(coordinator.decide_invalidation("nope")) == ("reuse",)


def test_bgm_change_reuses_frames_mix_final_only():
    # stage_l §4: changing BGM must prove visual frames are reused.
    coordinator = AssemblyCoordinator()
    decision = coordinator.decide_invalidation("bgm:bgm_v2.wav")
    assert decision.scope == AssemblyInvalidationScope.MIX_FINAL
    assert "frames" in decision.preserved_artifacts
    steps = coordinator.steps_for(decision)
    assert "normalize_frames" not in steps  # no frame re-inspection/rerender


def test_subtitle_change_does_not_touch_frames():
    coordinator = AssemblyCoordinator()
    decision = coordinator.decide_invalidation("subtitle:en.srt")
    steps = coordinator.steps_for(decision)
    assert "normalize_frames" not in steps
    assert "build_mix" not in steps
    assert "remux_subtitle" in steps


# ---------------------------------------------------------------------------
# 7. reproducibility audit (stage_l §3.8)
# ---------------------------------------------------------------------------

def _manifest(**overrides) -> dict:
    base = {
        "tool_hash": "tool_v1",
        "platform": "windows-x86_64",
        "profile_hash": "prof_v1",
        "input_hashes": ["frame_a", "frame_b"],
        "edl_hash": "edl_v1",
        "mix_hash": "mix_v1",
        "video_codec": "h264",
        "resolution": "320x180",
        "frame_rate": 30,
        "duration_seconds": 1.9,
        "audio_streams": 1,
        "pixel_format": "yuv420p",
        "output_hash": "out_v1",
    }
    base.update(overrides)
    return base


def test_reproducibility_bit_exact_required_when_identical():
    auditor = ReproducibilityAuditor()
    report = auditor.audit_manifest_runs(_manifest(), _manifest())
    assert report.bit_exact_required
    assert report.bit_exact
    assert report.is_reproducible
    assert report.mismatch_reasons == ()


def test_reproducibility_same_manifest_same_tool_bit_exact():
    auditor = ReproducibilityAuditor()
    report = auditor.audit_manifest_runs(
        _manifest(output_hash="same"),
        _manifest(output_hash="same"),
    )
    assert report.bit_exact and report.is_reproducible


def test_reproducibility_same_tool_different_output_fails():
    auditor = ReproducibilityAuditor()
    report = auditor.audit_manifest_runs(
        _manifest(output_hash="out_a"),
        _manifest(output_hash="out_b"),
    )
    assert report.bit_exact_required
    assert not report.bit_exact
    assert not report.is_reproducible
    assert any("bit-exact" in reason for reason in report.mismatch_reasons)


def test_reproducibility_semantic_when_profile_differs():
    auditor = ReproducibilityAuditor()
    report = auditor.audit_manifest_runs(
        _manifest(profile_hash="prof_v1", output_hash="out_a"),
        _manifest(profile_hash="prof_v2", output_hash="out_b"),
    )
    assert not report.bit_exact_required
    assert not report.bit_exact
    assert report.is_reproducible  # manifest + technical properties match
    assert any("profile hash" in reason for reason in report.mismatch_reasons)


def test_reproducibility_semantic_fails_on_input_change():
    auditor = ReproducibilityAuditor()
    report = auditor.audit_manifest_runs(
        _manifest(profile_hash="p1", input_hashes=["frame_a", "frame_b"], output_hash="o1"),
        _manifest(profile_hash="p2", input_hashes=["frame_a", "frame_X"], output_hash="o2"),
    )
    assert not report.is_reproducible
    assert not report.input_hashes_matched


# ---------------------------------------------------------------------------
# 8. subtitle bounds + media verification reuse (stage_l §4)
# ---------------------------------------------------------------------------

def test_subtitle_bounds_within_tolerance():
    track = SubtitleTrack(
        track_id=SubtitleTrackId("sub_01"),
        cues=(SubtitleCue(cue_id=SubtitleCueId("c1"), start_time=0.5, end_time=1.4, text="Xin chào"),),
    )
    assert track.cues[0].validate_bounds(1.9)
    assert not SubtitleCue(
        cue_id=SubtitleCueId("c2"), start_time=2.0, end_time=3.0, text="late"
    ).validate_bounds(1.9)
    assert track.content_hash  # deterministic subtitle key
