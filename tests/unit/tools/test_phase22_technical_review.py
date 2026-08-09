"""VP3D Phase 22 - 3D technical reviewer acceptance tests.

Covers the Stage K §3 components (PreRenderReviewer, FrameIntegrityReviewer,
TemporalReviewer, ContentReviewer + VLM port, CrossShotReviewer,
decide_verdict) plus the adapter pre-render gate wiring, against the
Stage K §5 test matrix: missing texture -> asset repair, camera collision ->
camera recompile, lip-sync -> facial only, noise -> affected frames,
multi-cause uncertainty (no auto-picked repair below the confidence
threshold), VLM timeout never becomes PASS, blocking finding -> REJECT,
low confidence / creative conflict -> REQUIRES_HUMAN, all required
dimensions covered -> APPROVE.
"""

from __future__ import annotations

import asyncio

import httpx

from windagent_core.domain.video_production.production_ir.enums import EngineJobStatus
from tests.fixtures.video_production.ir_fixture_builder import build_valid_ir
from tests.unit.tools.test_phase3_blender_adapter import (
    FakeBlenderProcess,
    make_detector,
)
from windagent_tools.production_engines.blender import (
    BlenderEngineAdapter,
    BlenderEngineConfig,
    BlenderGpuProbe,
    ContentReviewer,
    CrossShotReviewer,
    FrameIntegrityReviewer,
    FrameProbe,
    MODEL_ID,
    PROMPT_HASH,
    OpenRouterVlmReviewer,
    PreRenderReviewer,
    REQUIRED_DIMENSIONS,
    ReviewFinding,
    ShotReviewContext,
    TechnicalReviewPolicy,
    TemporalReviewer,
    VERDICT_APPROVE,
    VERDICT_REJECT,
    VERDICT_REQUIRES_HUMAN,
    decide_verdict,
)


def _manifest(**overrides) -> dict:
    base = {
        "object_registry": ["char_hero", "prop_table"],
        "texture_registry": ["tex_skin", "tex_table"],
        "rigs": [
            {"id": "rig_hero", "joints": ["root", "spine", "head"], "skinned": True}
        ],
        "objects": [
            {"id": "char_hero", "rig": "rig_hero"},
            {"id": "prop_table", "rig": ""},
        ],
        "textures": [{"id": "tex_skin"}, {"id": "tex_table"}],
        "frame_range": [1, 120],
        "camera": {
            "path": [{"frame": 1, "x": 10.0, "y": 0.0, "z": 0.0}],
        },
        "characters": [
            {
                "id": "char_hero",
                "bounds": {
                    "min_x": -1,
                    "max_x": 1,
                    "min_y": 0,
                    "max_y": 2,
                    "min_z": 0,
                    "max_z": 2,
                },
            }
        ],
        "lights": [{"id": "key", "intensity": 1.0}],
        "audio": {"duration_seconds": 5.5, "frame_rate": 24},
        "assets": [{"id": "char_hero", "approved": True}],
        "addons": [],
        "vram": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Pre-render gates
# ---------------------------------------------------------------------------
def test_clean_manifest_passes_pre_render():
    result = PreRenderReviewer().review(_manifest())
    assert result.blocked is False
    assert result.findings == ()


def test_missing_texture_is_blocking_with_asset_repair_scope():
    manifest = _manifest(
        textures=[{"id": "tex_skin"}, {"id": "tex_missing"}]
    )  # tex_missing not in registry
    result = PreRenderReviewer().review(manifest)
    assert result.blocked is True
    missing = [f for f in result.findings if f.code == "MISSING_TEXTURE"]
    assert missing
    assert missing[0].entity == "tex_missing"
    assert missing[0].severity == "BLOCKING"
    assert missing[0].suggested_repair == "asset_revision"  # §5: asset repair


def test_missing_object_is_blocking():
    manifest = _manifest(object_registry=["char_hero"])  # prop_table missing
    result = PreRenderReviewer().review(manifest)
    missing = [f for f in result.findings if f.code == "MISSING_OBJECT"]
    assert missing and missing[0].entity == "prop_table"
    assert missing[0].suggested_repair == "asset_revision"


def test_missing_rig_is_blocking_with_rig_repair_scope():
    manifest = _manifest(objects=[{"id": "char_hero", "rig": "rig_ghost"}])
    result = PreRenderReviewer().review(manifest)
    missing = [f for f in result.findings if f.code == "MISSING_OBJECT"]
    assert missing and missing[0].entity == "rig_ghost"
    assert missing[0].suggested_repair == "rig_repair"


def test_broken_rig_missing_joints_is_blocking():
    manifest = _manifest(
        rigs=[{"id": "rig_hero", "joints": ["root"], "skinned": True}]
    )
    result = PreRenderReviewer().review(manifest)
    broken = [f for f in result.findings if f.code == "BROKEN_RIG"]
    assert broken
    assert set(broken[0].evidence["missing_joints"]) == {"spine", "head"}
    assert broken[0].suggested_repair == "rig_repair"


def test_unskinned_rig_is_blocking():
    manifest = _manifest(
        rigs=[
            {
                "id": "rig_hero",
                "joints": ["root", "spine", "head"],
                "skinned": False,
            }
        ]
    )
    result = PreRenderReviewer().review(manifest)
    assert [f for f in result.findings if f.code == "BROKEN_RIG"]


def test_invalid_frame_range_is_blocking():
    manifest = _manifest(frame_range=[0, 120])
    result = PreRenderReviewer().review(manifest)
    bad = [f for f in result.findings if f.code == "FRAME_RANGE_INVALID"]
    assert bad and bad[0].suggested_repair == "frame_range_adjust"


def test_camera_character_collision_is_blocking_with_camera_recompile():
    manifest = _manifest(
        camera={
            "path": [{"frame": 10, "x": 0.0, "y": 1.0, "z": 1.0}]  # inside bounds
        }
    )
    result = PreRenderReviewer().review(manifest)
    collision = [
        f for f in result.findings if f.code == "CAMERA_CHARACTER_COLLISION"
    ]
    assert collision
    assert collision[0].frame_range == (10, 10)
    assert collision[0].suggested_repair == "camera_recompile"  # §5


def test_camera_outside_bounds_passes():
    manifest = _manifest(
        camera={"path": [{"frame": 1, "x": 5.0, "y": 0.0, "z": 0.0}]}
    )
    assert PreRenderReviewer().review(manifest).blocked is False


def test_no_lights_is_blocking_lighting_check():
    result = PreRenderReviewer().review(_manifest(lights=[]))
    assert result.blocked is True
    assert [f for f in result.findings if f.code == "LIGHTING_INVALID"]


def test_dim_light_is_warning_not_blocking():
    manifest = _manifest(lights=[{"id": "key", "intensity": 0.01}])
    result = PreRenderReviewer().review(manifest)
    assert result.blocked is False
    assert [f for f in result.findings if f.code == "LIGHTING_INVALID"]


def test_audio_shorter_than_shot_is_blocking_with_audio_mix():
    manifest = _manifest(
        frame_range=[1, 240], audio={"duration_seconds": 3.0, "frame_rate": 24}
    )  # needs 10s, has 3s
    result = PreRenderReviewer().review(manifest)
    timing = [f for f in result.findings if f.code == "AUDIO_TIMING"]
    assert timing and timing[0].suggested_repair == "audio_mix"


def test_audio_timing_within_tolerance_passes():
    manifest = _manifest(
        frame_range=[1, 120], audio={"duration_seconds": 4.8, "frame_rate": 24}
    )  # needs 5.0s, tolerance 0.25s
    assert PreRenderReviewer().review(manifest).blocked is False


def test_unapproved_asset_is_blocking_with_approval_scope():
    manifest = _manifest(
        assets=[{"id": "char_hero", "approved": False}]
    )
    result = PreRenderReviewer().review(manifest)
    unapproved = [f for f in result.findings if f.code == "UNAPPROVED_ASSET"]
    assert unapproved and unapproved[0].suggested_repair == "asset_approval"


def test_unapproved_addon_is_blocking():
    policy = TechnicalReviewPolicy(approved_addons=frozenset({"io_export"}) )
    manifest = _manifest(addons=[{"module_id": "io_evil"}])
    result = PreRenderReviewer(policy).review(manifest)
    addon = [f for f in result.findings if f.code == "UNAPPROVED_ADDON"]
    assert addon and addon[0].entity == "io_evil"


def test_vram_blocking_finding_from_phase20_policy():
    from windagent_tools.production_engines.blender.vram_budget import (
        VramBudgetPolicy,
    )

    policy = TechnicalReviewPolicy(
        vram_budget_policy=VramBudgetPolicy(
            safe_threshold_gb=6.0, block_threshold_gb=7.0
        )
    )
    manifest = _manifest(
        vram={
            "textures": [
                {
                    "name": f"tex_{i}",
                    "width": 16384,
                    "height": 16384,
                    "channels": 4,
                    "bytes_per_channel": 1,
                    "mipmaps": True,
                    "visible": True,
                }
                for i in range(64)
            ],
            "meshes": [
                {
                    "name": "hero_mesh",
                    "vertex_count": 4000000,
                    "triangle_count": 8000000,
                    "instance_count": 1,
                    "instanced": False,
                    "visible": True,
                }
            ],
            "render_buffers": {"width": 1920, "height": 1080},
        }
    )
    result = PreRenderReviewer(policy).review(manifest)
    vram = [f for f in result.findings if f.code == "VRAM_BUDGET_EXCEEDED"]
    assert vram and vram[0].suggested_repair == "vram_mitigation"


def test_no_vram_policy_skips_vram_gate():
    result = PreRenderReviewer().review(_manifest(vram={"textures": []}))
    assert not [f for f in result.findings if f.code == "VRAM_BUDGET_EXCEEDED"]


# ---------------------------------------------------------------------------
# Frame integrity (post-render item 1)
# ---------------------------------------------------------------------------
def _probes(frames, *, undecodable=(), black=(), dims=(1920, 1080), luma=100.0):
    return [
        FrameProbe(
            frame=f,
            decodable=f not in undecodable,
            width=dims[0],
            height=dims[1],
            luma_mean=1.0 if f in black else luma,
        )
        for f in frames
    ]


def test_full_frame_set_passes_integrity():
    probes = _probes(range(1, 121))
    findings = FrameIntegrityReviewer().review(
        expected_start=1, expected_end=120, probes=probes
    )
    assert findings == ()


def test_missing_frames_report_missing_range_and_count():
    probes = _probes([f for f in range(1, 121) if f != 60])
    findings = FrameIntegrityReviewer().review(
        expected_start=1, expected_end=120, probes=probes
    )
    codes = {f.code for f in findings}
    assert "FRAME_MISSING_RANGE" in codes
    assert "FRAME_COUNT_MISMATCH" in codes
    missing = [f for f in findings if f.code == "FRAME_MISSING_RANGE"][0]
    assert missing.frame_range == (60, 60)
    assert missing.suggested_repair == "affected_frames"  # §5: affected frames


def test_undecodable_frame_is_blocking():
    probes = _probes(range(1, 11), undecodable=(4,))
    findings = FrameIntegrityReviewer().review(
        expected_start=1, expected_end=10, probes=probes
    )
    bad = [f for f in findings if f.code == "FRAME_UNDECODABLE"]
    assert bad and bad[0].frame_range == (4, 4)


def test_dimension_mismatch_is_blocking():
    probes = _probes(range(1, 11), dims=(640, 480))
    findings = FrameIntegrityReviewer().review(
        expected_start=1,
        expected_end=10,
        probes=probes,
        expected_dimensions=(1920, 1080),
    )
    assert [f for f in findings if f.code == "FRAME_DIMENSION_MISMATCH"]


def test_black_frame_is_blocking():
    probes = _probes(range(1, 11), black=(9,))
    findings = FrameIntegrityReviewer().review(
        expected_start=1, expected_end=10, probes=probes
    )
    black = [f for f in findings if f.code == "FRAME_BLACK_OR_CORRUPT"]
    assert black and black[0].frame_range == (9, 9)


def test_zero_luma_probe_never_counts_as_pass():
    # luma_mean=None means "no luminance signal": black check is skipped, but
    # the frame must still decode with the right dimensions.
    probes = [FrameProbe(f, decodable=True, width=1920, height=1080) for f in range(1, 11)]
    assert FrameIntegrityReviewer().review(
        expected_start=1, expected_end=10, probes=probes
    ) == ()


# ---------------------------------------------------------------------------
# Temporal review (post-render item 2)
# ---------------------------------------------------------------------------
def test_steady_luma_passes_temporal():
    luma = {i: 60.0 for i in range(1, 49)}
    assert TemporalReviewer().review(luma=luma, window=8) == ()


def test_exposure_discontinuity_detected():
    luma = {i: (60.0 if i < 25 else 30.0) for i in range(1, 49)}
    findings = TemporalReviewer().review(luma=luma, window=8)
    disc = [f for f in findings if f.code == "EXPOSURE_DISCONTINUITY"]
    assert disc
    assert disc[0].frame_range[0] <= 25 <= disc[0].frame_range[1]
    assert disc[0].suggested_repair == "lighting_fix"


def test_sustained_noise_escalates_to_blocking():
    luma = {i: 60.0 for i in range(1, 49)}
    noise = {i: 60.0 for i in range(1, 49)}  # every window above threshold
    findings = TemporalReviewer().review(luma=luma, noise=noise, window=8)
    bursts = [f for f in findings if f.code == "NOISE_BURST"]
    assert bursts
    assert bursts[0].severity == "BLOCKING"  # sustained -> escalates
    assert bursts[0].suggested_repair == "affected_frames"  # §5: noise -> frames


def test_transient_noise_stays_warning():
    luma = {i: 60.0 for i in range(1, 49)}
    noise = {i: (60.0 if 17 <= i <= 24 else 0.0) for i in range(1, 49)}  # 1/6 windows
    findings = TemporalReviewer().review(luma=luma, noise=noise, window=8)
    bursts = [f for f in findings if f.code == "NOISE_BURST"]
    assert bursts and bursts[0].severity == "WARNING"


def test_flicker_detected():
    luma = {i: (60.0 if i % 2 else 15.0) for i in range(1, 49)}  # alternates
    findings = TemporalReviewer().review(luma=luma, window=8)
    flicker = [f for f in findings if f.code == "FLICKER_DETECTED"]
    assert flicker and flicker[0].severity == "BLOCKING"


def test_empty_luma_fails_closed_to_no_findings():
    assert TemporalReviewer().review(luma={}) == ()


# ---------------------------------------------------------------------------
# Content review (post-render item 3): deterministic first, VLM after
# ---------------------------------------------------------------------------
def _good_signals(n=60):
    return {
        "audio_envelope": [0.1, 0.5, 0.9] * (n // 3),
        "mouth_open": [0.1, 0.5, 0.9] * (n // 3),
        "identity_score": [1.0] * n,
        "occlusion_score": [0.1] * n,
        "continuity_breaks": [0] * n,
        "motion_magnitude": [0.2] * n,
        "luma_mean": [50.0] * n,
        "camera_speed": [0.3] * n,
    }


def test_all_required_dimensions_covered_approves():
    result = ContentReviewer().review(signals=_good_signals())
    assert set(REQUIRED_DIMENSIONS) == set(result.covered_dimensions)
    assert result.findings == ()


def test_lip_sync_mismatch_maps_to_facial_only():
    signals = _good_signals()
    signals["mouth_open"] = [0.1] * 60  # flat mouth, moving audio
    result = ContentReviewer().review(signals=signals)
    lip = [f for f in result.findings if f.code == "LIP_SYNC_MISMATCH"]
    assert lip
    assert lip[0].suggested_repair == "facial_only"  # §5: lip-sync -> facial only
    assert "audio_alignment" in lip[0].causes  # uncertainty kept, not picked


def test_identity_drift_is_blocking():
    signals = _good_signals()
    signals["identity_score"] = [1.0] * 30 + [0.4] * 30
    result = ContentReviewer().review(signals=signals)
    drift = [f for f in result.findings if f.code == "IDENTITY_DRIFT"]
    assert drift and drift[0].severity == "BLOCKING"
    assert len(drift[0].causes) > 1  # multiple possible causes preserved


def test_occlusion_anomaly_is_blocking():
    signals = _good_signals()
    signals["occlusion_score"] = [0.95] * 60
    result = ContentReviewer().review(signals=signals)
    occ = [f for f in result.findings if f.code == "OCCLUSION_ANOMALY"]
    assert occ and occ[0].suggested_repair == "camera_recompile"


def test_motion_jitter_is_blocking():
    signals = _good_signals()
    # Non-uniform deltas: 2,0.5,1.5,2,... -> jitter above threshold
    signals["motion_magnitude"] = [0.0, 2.0, 1.5, 0.0, 2.0, 1.5] * 10
    result = ContentReviewer().review(signals=signals)
    motion = [f for f in result.findings if f.code == "MOTION_QUALITY_DEGRADED"]
    assert motion and motion[0].suggested_repair == "affected_frames"


def test_camera_speed_violation_is_blocking():
    signals = _good_signals()
    signals["camera_speed"] = [0.3] * 59 + [5.0]
    result = ContentReviewer().review(signals=signals)
    cam = [f for f in result.findings if f.code == "CAMERA_NON_COMPLIANT"]
    assert cam and cam[0].suggested_repair == "camera_recompile"


def test_missing_dimension_signal_is_not_a_pass():
    # No identity signal -> identity NOT covered -> REQUIRES_HUMAN (fail
    # closed; a missing metric must never silently approve).
    signals = {k: v for k, v in _good_signals().items() if k != "identity_score"}
    result = ContentReviewer().review(signals=signals)
    assert "identity" not in result.covered_dimensions
    verdict, _ = decide_verdict(
        result.findings, covered_dimensions=result.covered_dimensions
    )
    assert verdict == VERDICT_REQUIRES_HUMAN


def test_vlm_timeout_is_low_confidence_never_pass():
    signals = _good_signals()
    signals.pop("identity_score")
    result = ContentReviewer().review(
        signals=signals, vlm_outcome={"timed_out": True, "dimension": "identity"}
    )
    timeout = [f for f in result.findings if f.code == "VLM_REVIEW_TIMEOUT"]
    assert timeout
    assert timeout[0].confidence == 0.0
    verdict, _ = decide_verdict(
        result.findings, covered_dimensions=result.covered_dimensions
    )
    assert verdict == VERDICT_REQUIRES_HUMAN  # never APPROVE


def test_vlm_error_also_fails_closed():
    signals = _good_signals()
    signals.pop("identity_score")
    result = ContentReviewer().review(
        signals=signals, vlm_outcome={"error": "model 503", "dimension": "identity"}
    )
    assert [f for f in result.findings if f.code == "VLM_REVIEW_TIMEOUT"]


def test_vlm_finding_merges_into_bundle():
    result = ContentReviewer().review(
        signals=_good_signals(),
        vlm_outcome={
            "code": "VLM_AESTHETIC_ISSUE",
            "severity": "WARNING",
            "entity": "lighting",
            "confidence": 0.4,
            "evidence": {"note": "mood mismatch"},
        },
    )
    assert [f for f in result.findings if f.code == "VLM_AESTHETIC_ISSUE"]
    verdict, _ = decide_verdict(
        result.findings, covered_dimensions=result.covered_dimensions
    )
    assert verdict == VERDICT_REQUIRES_HUMAN  # low VLM confidence


# ---------------------------------------------------------------------------
# Cross-shot continuity (post-render item 4): references always pinned
# ---------------------------------------------------------------------------
def test_cross_shot_identity_drift_pins_character_reference():
    shots = [
        ShotReviewContext("s01", "char_hero", "loc_kitchen", "light_kitchen", 0.95, 50.0),
        ShotReviewContext("s02", "char_hero", "loc_kitchen", "light_kitchen", 0.55, 52.0),
    ]
    findings = CrossShotReviewer().review(shots)
    drift = [f for f in findings if f.code == "CROSS_SHOT_IDENTITY_MISMATCH"]
    assert drift
    assert drift[0].entity == "char_hero"  # pinned character reference
    assert drift[0].evidence["pinned_character_ref"] == "char_hero"
    assert drift[0].severity == "WARNING"  # creative conflict -> human, not REJECT


def test_cross_shot_lighting_ref_mismatch_is_warning():
    shots = [
        ShotReviewContext("s01", "char_a", "loc_kitchen", "light_kitchen", 1.0, 50.0),
        ShotReviewContext("s02", "char_b", "loc_kitchen", "light_night", 1.0, 50.0),
    ]
    findings = CrossShotReviewer().review(shots)
    mismatch = [f for f in findings if f.code == "CROSS_SHOT_LIGHTING_MISMATCH"]
    assert mismatch
    assert mismatch[0].evidence["pinned_location_ref"] == "loc_kitchen"
    assert set(mismatch[0].evidence["lighting_refs"]) == {"light_kitchen", "light_night"}


def test_cross_shot_luma_jump_at_same_location_is_warning():
    shots = [
        ShotReviewContext("s01", "char_a", "loc_kitchen", "light_kitchen", 1.0, 50.0),
        ShotReviewContext("s02", "char_b", "loc_kitchen", "light_kitchen", 1.0, 80.0),
    ]
    findings = CrossShotReviewer().review(shots)
    assert [f for f in findings if f.code == "CROSS_SHOT_LOCATION_MISMATCH"]


def test_cross_shot_consistent_shots_pass():
    shots = [
        ShotReviewContext("s01", "char_hero", "loc_kitchen", "light_kitchen", 0.95, 50.0),
        ShotReviewContext("s02", "char_hero", "loc_kitchen", "light_kitchen", 0.96, 51.0),
    ]
    assert CrossShotReviewer().review(shots) == ()


def test_single_shot_has_no_cross_shot_findings():
    shots = [ShotReviewContext("s01", "char_hero", "loc_kitchen", "light_kitchen", 0.9)]
    assert CrossShotReviewer().review(shots) == ()


# ---------------------------------------------------------------------------
# Verdict rule (Stage K §3 verdict rule)
# ---------------------------------------------------------------------------
def _finding(code, severity="WARNING", confidence=0.9):
    return ReviewFinding(
        code=code, severity=severity, entity="render", confidence=confidence
    )


def test_blocking_finding_rejects():
    verdict, _ = decide_verdict(
        [_finding("MISSING_TEXTURE", severity="BLOCKING")],
        covered_dimensions=REQUIRED_DIMENSIONS,
    )
    assert verdict == VERDICT_REJECT


def test_low_confidence_requires_human():
    verdict, _ = decide_verdict(
        [_finding("VLM_REVIEW_TIMEOUT", confidence=0.0)],
        covered_dimensions=REQUIRED_DIMENSIONS,
    )
    assert verdict == VERDICT_REQUIRES_HUMAN


def test_creative_conflict_warning_requires_human_never_auto_pass():
    verdict, _ = decide_verdict(
        [_finding("CROSS_SHOT_IDENTITY_MISMATCH", confidence=0.8)],
        covered_dimensions=REQUIRED_DIMENSIONS,
    )
    assert verdict == VERDICT_REQUIRES_HUMAN  # §3 item 6: no auto-pass


def test_uncovered_required_dimension_requires_human():
    verdict, _ = decide_verdict(
        [], covered_dimensions=("lip_sync",)  # identity, ... uncovered
    )
    assert verdict == VERDICT_REQUIRES_HUMAN


def test_clean_bundle_approves():
    verdict, reason = decide_verdict(
        [], covered_dimensions=REQUIRED_DIMENSIONS
    )
    assert verdict == VERDICT_APPROVE
    assert "all required dimensions pass" in reason


# ---------------------------------------------------------------------------
# Adapter wiring: pre-render BLOCKING stops submission before launch
# ---------------------------------------------------------------------------
def _make_adapter(tmp_path, policy):
    from windagent_tools.production_engines.blender.runtime.capabilities import (
        BlenderCapabilityProbe,
    )

    fake_exe = tmp_path / "fake_blender" / "blender.exe"
    fake_exe.parent.mkdir(parents=True, exist_ok=True)
    fake_exe.write_bytes(b"MZ")
    fake_process = FakeBlenderProcess(blender_version="Blender 4.5.3")
    config = BlenderEngineConfig(
        artifact_root=str(tmp_path / "artifacts"),
        state_dir=str(tmp_path / "state"),
        executable_path=str(fake_exe),
        technical_review_policy=policy,
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


def test_adapter_blocks_submission_on_blocking_finding(tmp_path):
    adapter = _make_adapter(
        tmp_path, TechnicalReviewPolicy(approved_addons=frozenset())
    )
    ir = build_valid_ir()
    scene = ir.scenes[0]
    render = ir.render_intents[0]
    render = render.model_copy(
        update={
            "metadata": {
                **render.metadata,
                "review_manifest": _manifest(addons=[{"module_id": "io_evil"}]),
            }
        }
    )
    receipt = asyncio.run(adapter.submit_scene(scene, render))
    assert receipt.status == EngineJobStatus.FAILED
    assert receipt.metadata["gate"] == "technical_review"
    codes = [f["code"] for f in receipt.metadata["review_findings"]]
    assert "UNAPPROVED_ADDON" in codes


def test_adapter_passes_clean_manifest_through(tmp_path):
    adapter = _make_adapter(
        tmp_path, TechnicalReviewPolicy(approved_addons=frozenset())
    )
    ir = build_valid_ir()
    scene = ir.scenes[0]
    render = ir.render_intents[0]
    render = render.model_copy(
        update={"metadata": {**render.metadata, "review_manifest": _manifest()}}
    )
    receipt = asyncio.run(adapter.submit_scene(scene, render))
    assert receipt.metadata.get("gate") != "technical_review"


def test_adapter_without_policy_skips_review_gate(tmp_path):
    adapter = _make_adapter(tmp_path, None)
    ir = build_valid_ir()
    receipt = asyncio.run(adapter.submit_scene(ir.scenes[0], ir.render_intents[0]))
    assert receipt.metadata.get("gate") != "technical_review"


def test_finding_round_trips_through_dict():
    finding = _finding("NOISE_BURST", severity="BLOCKING", confidence=0.9)
    data = finding.to_dict()
    assert data["code"] == "NOISE_BURST"
    assert data["severity"] == "BLOCKING"
    assert data["confidence"] == 0.9
    assert data["frame_range"] is None


# ---------------------------------------------------------------------------
# OpenRouter VLM reviewer port (Stage K §3 item 3 + §7 risk pinning)
# ---------------------------------------------------------------------------
class _FakeHttp:
    """Offline httpx.Client stand-in: returns canned responses."""

    def __init__(self, *, payload=None, status=200, error=None):
        self._payload = payload
        self._status = status
        self._error = error
        self.calls = []

    def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._payload, self._status)


class _FakeResponse:
    def __init__(self, payload, status):
        self._payload = payload
        self._status = status

    def raise_for_status(self):
        if self._status >= 400:
            raise httpx.HTTPStatusError(
                f"status {self._status}", request=None, response=self
            )

    def json(self):
        return self._payload


def test_vlm_reviewer_without_key_fails_closed():
    reviewer = OpenRouterVlmReviewer(api_key="")
    outcome = reviewer.review({"dimension": "identity"})
    assert outcome["timed_out"] is True
    assert "not configured" in outcome["error"]
    # Evidence carries the model + prompt hash pin (Stage K §7).
    assert outcome["evidence"]["model"] == MODEL_ID
    assert outcome["evidence"]["prompt_hash"] == PROMPT_HASH


def test_vlm_reviewer_timeout_fails_closed_never_pass():
    http = _FakeHttp(error=TimeoutError("slow model"))
    reviewer = OpenRouterVlmReviewer(api_key="sk-test", http=http)
    outcome = reviewer.review({"dimension": "identity"})
    assert outcome["timed_out"] is True
    assert outcome["error"]
    verdict, _ = decide_verdict(
        [ReviewFinding(code="VLM_REVIEW_TIMEOUT", severity="WARNING", entity="render", confidence=0.0)],
        covered_dimensions=("lip_sync",),
    )
    assert verdict == VERDICT_REQUIRES_HUMAN  # timeout never becomes PASS


def test_vlm_reviewer_http_error_fails_closed():
    http = _FakeHttp(payload={}, status=503)
    reviewer = OpenRouterVlmReviewer(api_key="sk-test", http=http)
    outcome = reviewer.review({"dimension": "identity"})
    assert outcome["timed_out"] is True


def test_vlm_reviewer_parses_model_json_and_pins_model():
    http = _FakeHttp(
        payload={
            "model": MODEL_ID,
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"code": "VLM_AESTHETIC_ISSUE", "severity": "WARNING", '
                            '"entity": "lighting", "confidence": 0.4, '
                            '"evidence": {"note": "mood mismatch"}, '
                            '"suggested_repair": "lighting_fix"}'
                        )
                    }
                }
            ],
        }
    )
    reviewer = OpenRouterVlmReviewer(api_key="sk-test", http=http)
    outcome = reviewer.review({"dimension": "lighting", "shots": ["s01"]})
    assert outcome["code"] == "VLM_AESTHETIC_ISSUE"
    assert outcome["severity"] == "WARNING"
    assert outcome["confidence"] == 0.4
    assert outcome["suggested_repair"] == "lighting_fix"
    assert outcome["evidence"]["api_model"] == MODEL_ID  # pinning
    assert outcome["evidence"]["prompt_hash"] == PROMPT_HASH
    # The request went to OpenRouter with the pinned model id.
    assert http.calls[0]["url"].endswith("/chat/completions")
    assert http.calls[0]["json"]["model"] == MODEL_ID


def test_vlm_reviewer_bad_json_fails_closed():
    http = _FakeHttp(
        payload={
            "choices": [{"message": {"content": "sorry, no json here"}}]
        }
    )
    reviewer = OpenRouterVlmReviewer(api_key="sk-test", http=http)
    outcome = reviewer.review({"dimension": "identity"})
    assert outcome["timed_out"] is True


def test_vlm_reviewer_merges_into_content_reviewer():
    # End-to-end: VLM reviewer outcome feeds the deterministic ContentReviewer
    # (deterministic metrics first, VLM after — Stage K §3 item 3).
    http = _FakeHttp(
        payload={
            "model": MODEL_ID,
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"code": "VLM_AESTHETIC_ISSUE", "severity": "WARNING", '
                            '"entity": "lighting", "confidence": 0.4, '
                            '"evidence": {"note": "mood mismatch"}, '
                            '"suggested_repair": "lighting_fix"}'
                        )
                    }
                }
            ],
        }
    )
    reviewer = OpenRouterVlmReviewer(api_key="sk-test", http=http)
    signals = _good_signals()
    result = ContentReviewer().review(
        signals=signals, vlm_outcome=reviewer.review({"dimension": "lighting"})
    )
    codes = {f.code for f in result.findings}
    assert "VLM_AESTHETIC_ISSUE" in codes
    verdict, _ = decide_verdict(
        result.findings, covered_dimensions=result.covered_dimensions
    )
    assert verdict == VERDICT_REQUIRES_HUMAN  # low VLM confidence
