"""
VP3D Phase 25 — Golden Scene E2E unit tests (Stage M, gate
VP3D_P25_GOLDEN_SCENE_E2E_PASSED).

Fail-closed matrix (stage_m.md §3 acceptance):
- cancel/restart at a node resumes WITHOUT duplication (SKIPPED nodes never
  re-execute; outputs reused);
- blocking-defect fixtures are REJECTED — never a false PASS;
- identity/continuity and technical verification failures REJECT;
- fixture/manifest mismatch and resume-input mismatch fail closed;
- every node receipt records ID, revision (attempt), provenance and content
  hashes;
- the production report lists every repair and every human approval;
- determinism: same fixture + manifest => same content hashes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from windagent_core.domain.video_production.enums import (
    GoldenSceneNodeKind,
    GoldenSceneNodeStatus,
    GoldenSceneVerdict,
)
from windagent_core.domain.video_production.golden_scene import (
    GoldenSceneCheckpoint,
    GoldenSceneFixture,
    GoldenSceneNodeReceipt,
    GoldenSceneResumeMismatchError,
    GoldenSceneResumePlanner,
    GoldenSceneRunManifest,
    GoldenSceneVerdictPolicy,
    IdentityContinuityReceipt,
    RepairEntry,
    TechnicalVerificationReceipt,
    compute_content_hash,
)
from windagent_core.domain.video_production.ids import (
    GoldenSceneNodeId,
    GoldenSceneRunId,
    VideoProjectId,
)
from windagent_intelligence.video.golden_scene import (
    GoldenSceneOrchestrator,
    build_default_steps,
    default_identity_checker,
)


def _fixture(**overrides) -> GoldenSceneFixture:
    data = {
        "fixture_id": "gs_fixture_01",
        "title": "Golden Scene 01",
        "planned_duration_seconds": 35.0,
        "fps": 24,
        "screenplay_text": (
            "Title: GOLDEN SCENE\n\n"
            "INT. PARK - DAY\n"
            "ALICE walks toward the fountain.\n"
            "BOB (warm)\nHello, Alice!\n"
            "ALICE\nHi, Bob!\n"
        ),
        "characters": [
            {
                "master_id": "cm_alice",
                "name": "Alice",
                "revisions": [
                    {
                        "revision_id": "cmr_alice_1",
                        "master_id": "cm_alice",
                        "state": "APPROVED",
                        "approval_verdict": "APPROVED",
                        "approval_actor": "producer",
                    }
                ],
                "active_revision_id": "cmr_alice_1",
            },
            {
                "master_id": "cm_bob",
                "name": "Bob",
                "revisions": [
                    {
                        "revision_id": "cmr_bob_1",
                        "master_id": "cm_bob",
                        "state": "APPROVED",
                        "approval_verdict": "APPROVED",
                        "approval_actor": "producer",
                    }
                ],
                "active_revision_id": "cmr_bob_1",
            },
        ],
        "environment": {"environment_id": "env_park", "name": "Park"},
        "dialogue_lines": [
            {
                "dialogue_id": "dlg_1",
                "character_id": "cm_bob",
                "text": "Hello, Alice!",
                "shot_id": "shot_1",
            },
            {
                "dialogue_id": "dlg_2",
                "character_id": "cm_alice",
                "text": "Hi, Bob!",
                "shot_id": "shot_2",
            },
        ],
        "animation_intents": [
            {
                "intent_id": "ani_walk_alice",
                "actor_id": "cm_alice",
                "action": "WALK",
                "emotion": "NEUTRAL",
                "fps": 24,
                "skeleton_profile_id": "skel_default",
            }
        ],
        "camera_intents": [
            {
                "intent_id": "cam_1",
                "shot_id": "shot_1",
                "scene_id": "scn_1",
                "movement": "DOLLY",
                "angle": "EYE_LEVEL",
                "side": "NEUTRAL",
                "screen_direction": "NEUTRAL",
                "lens": {
                    "focal_mm": 35.0,
                    "sensor_width_mm": 36.0,
                    "aspect_ratio": 1.7778,
                    "aperture_fstop": 2.8,
                },
                "focus": {
                    "focus_target": "cm_alice",
                    "focus_distance_m": 3.0,
                    "dof_near_m": 2.5,
                    "dof_far_m": 3.5,
                },
                "framing": {},
                "path": {},
                "duration_seconds": 2.0,
                "fps": 24,
                "dialogue_timing": [],
            }
        ],
        "lighting_intents": [
            {
                "intent_id": "lit_1",
                "shot_id": "shot_1",
                "scene_id": "scn_1",
                "mood": "HAPPY",
                "time_of_day": "DAY",
                "style": "CARTOON",
                "emphasis": "SUBJECT",
                "continuity_key": "gs_scene_1",
            }
        ],
        "audio_cues": [
            {
                "kind": "DIALOGUE",
                "path": "dialogue_alice.wav",
                "source_hash": "a" * 64,
                "sample_rate": 48000,
                "channels": 2,
                "label": "alice",
            }
        ],
        "render_profile": {"engine": "CYCLES", "quality": "DRAFT"},
        "approvals": [
            {
                "approval_id": "ap_1",
                "node_kind": "FINAL",
                "actor": "producer",
                "decision": "APPROVED",
                "reason": "golden scene cut approved",
            }
        ],
        "metadata": {"voice_profiles": {}},
    }
    if "ir_document" not in data["metadata"]:
        from tests.fixtures.video_production.ir_fixture_builder import (
            build_valid_ir_dict,
        )

        data["metadata"]["ir_document"] = build_valid_ir_dict()
    data.update(overrides)
    return GoldenSceneFixture.model_validate(data)


def _manifest(fixture: GoldenSceneFixture, run_id: str = "gs_run_1") -> GoldenSceneRunManifest:
    return GoldenSceneRunManifest(
        run_id=GoldenSceneRunId(run_id),
        project_id=VideoProjectId("vp_golden"),
        revision_id="rev_golden_1",
        fixture_hash=fixture.content_hash(),
        candidate_sha="candidate_phase25",
        hardware_baseline={"gpu": "RTX 5060 Laptop 8GB", "ram_gb": "32"},
        tool_versions={"blender": "4.5.12 LTS", "ffmpeg": "8.1.2"},
        budgets={"wall_clock_seconds": 3600.0, "repairs": 3.0},
        pinned_seeds={"facial": 42, "render": 7},
    )


# ---------------------------------------------------------------------------
# Deterministic legs
# ---------------------------------------------------------------------------
class _RecordingRenderLeg:
    """Render leg that records every invocation (duplication detector)."""

    def __init__(self) -> None:
        self.calls = 0

    async def render(self, *, node, fixture, workspace) -> dict:
        self.calls += 1
        frame_dir = workspace / "render"
        frame_dir.mkdir(parents=True, exist_ok=True)
        (frame_dir / "frame_0001.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
        (frame_dir / "frame_0002.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"y" * 64)
        return {
            "output_hashes": {
                "frames": compute_content_hash(
                    {"count": 2, "files": ["frame_0001.png", "frame_0002.png"]}
                ),
            },
            "metadata": {"frame_count": 2},
        }


class _PassingReviewRepairLeg:
    def __init__(self, findings=None, repairs=None) -> None:
        self.findings = findings or []
        self.repairs = repairs or []

    async def review_and_repair(self, *, node, fixture, workspace) -> dict:
        return {
            "output_hashes": {"review": compute_content_hash({"findings": self.findings})},
            "findings": self.findings,
            "repairs": [r.model_dump() for r in self.repairs],
            "metadata": {"repair_count": len(self.repairs)},
        }


class _PassingFfmpegLeg:
    def __init__(self) -> None:
        self.calls = 0

    async def assemble(self, *, node, fixture, workspace) -> dict:
        self.calls += 1
        mp4 = workspace / "final_golden.mp4"
        mp4.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32)
        (workspace / "dialogue_alice.wav").write_bytes(b"RIFF" + b"\x00" * 40)
        return {
            "output_hashes": {"final_mp4": compute_content_hash({"size": mp4.stat().st_size})},
            "metadata": {"final_mp4": str(mp4)},
        }


def _passing_identity(fixture, receipts) -> IdentityContinuityReceipt:
    return IdentityContinuityReceipt(
        character_identity_ok=True,
        voice_identity_ok=True,
        continuity_ok=True,
    )


def _passing_verification(fixture, receipts, workspace) -> TechnicalVerificationReceipt:
    return TechnicalVerificationReceipt(
        frames_ok=True,
        audio_ok=True,
        final_mp4_ok=True,
        checks={"frames": {"count": 2}, "audio": {"count": 1}, "final_mp4": {"exists": True}},
    )


def _orchestrator(tmp_path: Path, fixture=None, manifest=None, **kwargs):
    fixture = fixture or _fixture()
    manifest = manifest or _manifest(fixture)
    steps = build_default_steps()
    render_leg = kwargs.pop("render_leg", None) or _RecordingRenderLeg()
    review_leg = kwargs.pop("review_leg", None) or _PassingReviewRepairLeg()
    ffmpeg_leg = kwargs.pop("ffmpeg_leg", None) or _PassingFfmpegLeg()
    return GoldenSceneOrchestrator(
        fixture=fixture,
        manifest=manifest,
        checkpoint_dir=tmp_path / "checkpoints",
        steps=steps,
        render_leg=render_leg,
        review_repair_leg=review_leg,
        ffmpeg_leg=ffmpeg_leg,
        identity_checker=kwargs.pop("identity_checker", _passing_identity),
        verification_checker=kwargs.pop(
            "verification_checker", _passing_verification
        ),
    ), render_leg, review_leg, ffmpeg_leg


def _run(orch: GoldenSceneOrchestrator, **kw):
    return asyncio.run(orch.run(**kw))


# ---------------------------------------------------------------------------
# Core domain: resume planner + verdict policy
# ---------------------------------------------------------------------------
class TestResumePlanner:
    def test_completed_same_inputs_skips(self):
        planner = GoldenSceneResumePlanner()
        checkpoint = GoldenSceneCheckpoint(
            run_id=GoldenSceneRunId("r1"),
            receipts=[
                GoldenSceneNodeReceipt(
                    node_id=GoldenSceneNodeId("n1"),
                    kind=GoldenSceneNodeKind.SCRIPT,
                    status=GoldenSceneNodeStatus.COMPLETED,
                    input_hashes={"fixture": "abc"},
                    output_hashes={"screenplay": "x"},
                )
            ],
        )
        decisions = planner.plan(checkpoint, {GoldenSceneNodeKind.SCRIPT: {"fixture": "abc"}})
        assert decisions[GoldenSceneNodeKind.SCRIPT] == "SKIP"

    def test_changed_inputs_rerun(self):
        planner = GoldenSceneResumePlanner()
        checkpoint = GoldenSceneCheckpoint(
            run_id=GoldenSceneRunId("r1"),
            receipts=[
                GoldenSceneNodeReceipt(
                    node_id=GoldenSceneNodeId("n1"),
                    kind=GoldenSceneNodeKind.SCRIPT,
                    status=GoldenSceneNodeStatus.COMPLETED,
                    input_hashes={"fixture": "abc"},
                )
            ],
        )
        decisions = planner.plan(checkpoint, {GoldenSceneNodeKind.SCRIPT: {"fixture": "zzz"}})
        assert decisions[GoldenSceneNodeKind.SCRIPT] == "RUN"

    def test_failed_or_cancelled_never_skips(self):
        planner = GoldenSceneResumePlanner()
        for status in (GoldenSceneNodeStatus.FAILED, GoldenSceneNodeStatus.CANCELLED):
            checkpoint = GoldenSceneCheckpoint(
                run_id=GoldenSceneRunId("r1"),
                receipts=[
                    GoldenSceneNodeReceipt(
                        node_id=GoldenSceneNodeId("n1"),
                        kind=GoldenSceneNodeKind.SCRIPT,
                        status=status,
                        input_hashes={"fixture": "abc"},
                    )
                ],
            )
            decisions = planner.plan(
                checkpoint, {GoldenSceneNodeKind.SCRIPT: {"fixture": "abc"}}
            )
            assert decisions[GoldenSceneNodeKind.SCRIPT] == "RUN"

    def test_no_checkpoint_runs_everything(self):
        decisions = GoldenSceneResumePlanner().plan(None, {})
        assert all(v == "RUN" for v in decisions.values())


class TestVerdictPolicy:
    def _receipts(self, **statuses) -> list:
        receipts = []
        for kind in GoldenSceneNodeKind:
            status = statuses.get(kind, GoldenSceneNodeStatus.COMPLETED)
            receipts.append(
                GoldenSceneNodeReceipt(
                    node_id=GoldenSceneNodeId(f"n_{kind.value}"),
                    kind=kind,
                    status=status,
                    output_hashes={"out": "x"},
                )
            )
        return receipts

    def test_all_pass_is_pass(self):
        policy = GoldenSceneVerdictPolicy()
        assert (
            policy.decide(
                self._receipts(),
                _passing_identity(None, {}),
                _passing_verification(None, {}, Path(".")),
            )
            == GoldenSceneVerdict.PASS
        )

    def test_missing_node_rejects(self):
        policy = GoldenSceneVerdictPolicy()
        receipts = self._receipts()
        receipts = [r for r in receipts if r.kind != GoldenSceneNodeKind.FINAL]
        assert (
            policy.decide(
                receipts,
                _passing_identity(None, {}),
                _passing_verification(None, {}, Path(".")),
            )
            == GoldenSceneVerdict.REJECT
        )

    def test_failed_node_rejects(self):
        policy = GoldenSceneVerdictPolicy()
        receipts = self._receipts(RENDER=GoldenSceneNodeStatus.FAILED)
        assert (
            policy.decide(
                receipts,
                _passing_identity(None, {}),
                _passing_verification(None, {}, Path(".")),
            )
            == GoldenSceneVerdict.REJECT
        )

    def test_identity_fail_rejects(self):
        policy = GoldenSceneVerdictPolicy()
        identity = IdentityContinuityReceipt(
            character_identity_ok=False,
            voice_identity_ok=True,
            continuity_ok=True,
            blocking_issues=["master cm_alice has no approved revision"],
        )
        assert (
            policy.decide(
                self._receipts(),
                identity,
                _passing_verification(None, {}, Path(".")),
            )
            == GoldenSceneVerdict.REJECT
        )

    def test_verification_fail_rejects(self):
        policy = GoldenSceneVerdictPolicy()
        verification = TechnicalVerificationReceipt(
            frames_ok=True, audio_ok=False, final_mp4_ok=False
        )
        assert (
            policy.decide(self._receipts(), _passing_identity(None, {}), verification)
            == GoldenSceneVerdict.REJECT
        )

    def test_blocking_review_finding_unrepaired_rejects(self):
        policy = GoldenSceneVerdictPolicy()
        receipts = self._receipts()
        receipts = [
            r.model_copy(
                update={
                    "findings": (
                        [{"code": "FINDING_BLOCKING", "blocking": True}]
                        if r.kind == GoldenSceneNodeKind.REVIEW_REPAIR
                        else r.findings
                    )
                }
            )
            if r.kind == GoldenSceneNodeKind.REVIEW_REPAIR
            else r
            for r in receipts
        ]
        assert (
            policy.decide(
                receipts,
                _passing_identity(None, {}),
                _passing_verification(None, {}, Path(".")),
            )
            == GoldenSceneVerdict.REJECT
        )

    def test_blocking_finding_repaired_passes(self):
        policy = GoldenSceneVerdictPolicy()
        receipts = self._receipts()
        receipts = [
            r.model_copy(
                update={
                    "findings": [{"code": "FINDING_BLOCKING", "blocking": True}],
                    "repairs": [
                        RepairEntry(
                            repair_id="rp_1",
                            node_kind=GoldenSceneNodeKind.REVIEW_REPAIR,
                            finding_code="FINDING_BLOCKING",
                            outcome="REPAIRED",
                        )
                    ],
                }
            )
            if r.kind == GoldenSceneNodeKind.REVIEW_REPAIR
            else r
            for r in receipts
        ]
        assert (
            policy.decide(
                receipts,
                _passing_identity(None, {}),
                _passing_verification(None, {}, Path(".")),
            )
            == GoldenSceneVerdict.PASS
        )


# ---------------------------------------------------------------------------
# Orchestrator: happy path + acceptance matrix
# ---------------------------------------------------------------------------
class TestOrchestratorHappyPath:
    def test_full_run_passes_and_records_hashes(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)
        orch, render_leg, _, _ = _orchestrator(tmp_path, fixture, manifest)
        report = _run(orch)
        assert report.verdict == GoldenSceneVerdict.PASS
        assert len(report.receipts) == 10
        assert all(r.output_hashes for r in report.receipts)
        assert all(r.provenance is not None for r in report.receipts)
        assert render_leg.calls == 1
        # every human approval appears in the report
        assert [a.approval_id for a in report.human_approvals] == ["ap_1"]

    def test_report_is_immutable_and_deterministic(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)
        orch, _, _, _ = _orchestrator(tmp_path, fixture, manifest)
        report = _run(orch)
        assert report.verdict == GoldenSceneVerdict.PASS
        # hash stability: same fixture + manifest => same report hash
        orch2, _, _, _ = _orchestrator(tmp_path / "b", fixture, manifest)
        report2 = _run(orch2)
        assert report.content_hash() == report2.content_hash()
        with pytest.raises(ValueError):
            report.summary = "mutated"  # frozen model

    def test_fixture_manifest_hash_mismatch_fails_closed(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(_fixture(fixture_id="other"))
        with pytest.raises(Exception) as exc:
            _orchestrator(tmp_path, fixture, manifest)
        assert "Fixture hash does not match" in str(exc.value)


class TestCancelRestartResume:
    def test_cancel_mid_run_resumes_without_duplication(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)
        orch, render_leg, _, _ = _orchestrator(tmp_path, fixture, manifest)

        # Cancel after the RENDER node (i.e. when REVIEW_REPAIR is next).
        cancelled_nodes: list = []
        state = {"stopped": False}

        async def cancel_after_render():
            nonlocal cancelled_nodes
            cancelled_nodes = []
            report = await orch.run(
                cancel_token=lambda: state["stopped"],
            )
            # simulate: user cancels when REVIEW_REPAIR about to run — emulate
            # by cancelling right after RENDER completes via monkey state.
            return report

        # Phase A: run with a token that flips True once RENDER completed.

        def token():
            # flip cancel AFTER render leg executed
            if render_leg.calls >= 1 and not state["stopped"]:
                state["stopped"] = True
            return state["stopped"]

        report_a = asyncio.run(orch.run(cancel_token=token))
        statuses = {r.kind: r.status for r in report_a.receipts}
        assert statuses[GoldenSceneNodeKind.RENDER] == GoldenSceneNodeStatus.COMPLETED
        # REVIEW_REPAIR got cancelled (token flips right after RENDER)
        assert statuses[GoldenSceneNodeKind.REVIEW_REPAIR] == GoldenSceneNodeStatus.CANCELLED
        assert report_a.verdict == GoldenSceneVerdict.REJECT  # unfinished run

        render_calls_after_cancel = render_leg.calls

        # Phase B: restart same run_id — completed nodes SKIPPED, no re-render.
        orch_b, render_leg_b, _, _ = _orchestrator(
            tmp_path, fixture, manifest, render_leg=render_leg
        )
        state["stopped"] = False
        report_b = asyncio.run(orch_b.run())
        assert report_b.verdict == GoldenSceneVerdict.PASS
        skipped = {r.kind for r in report_b.receipts if r.status == GoldenSceneNodeStatus.SKIPPED}
        assert GoldenSceneNodeKind.SCRIPT in skipped
        assert GoldenSceneNodeKind.RENDER in skipped
        # THE key acceptance: render leg NOT re-executed on restart.
        assert render_leg.calls == render_calls_after_cancel
        # FINAL ran to completion after resume.
        final = next(r for r in report_b.receipts if r.kind == GoldenSceneNodeKind.FINAL)
        assert final.status == GoldenSceneNodeStatus.COMPLETED

    def test_resume_with_different_fixture_never_skips(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)
        orch, _, _, _ = _orchestrator(tmp_path, fixture, manifest)
        report_a = _run(orch)
        assert report_a.verdict == GoldenSceneVerdict.PASS

        # Same run_id but a DIFFERENT fixture: the resume planner must see the
        # input-hash mismatch and re-run every node — never SKIP stale output.
        other = _fixture(fixture_id="other_fixture")
        other_manifest = GoldenSceneRunManifest(
            run_id=GoldenSceneRunId("gs_run_1"),
            project_id=VideoProjectId("vp_golden"),
            revision_id="rev_golden_1",
            fixture_hash=other.content_hash(),
            candidate_sha="candidate_phase25",
        )
        orch2, render_leg_b, _, _ = _orchestrator(
            tmp_path, other, other_manifest, render_leg=_RecordingRenderLeg()
        )
        report_b = asyncio.run(orch2.run())
        assert report_b.verdict == GoldenSceneVerdict.PASS
        assert not any(
            r.status == GoldenSceneNodeStatus.SKIPPED for r in report_b.receipts
        )

    def test_checkpoint_run_id_mismatch_raises(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)
        orch, _, _, _ = _orchestrator(tmp_path, fixture, manifest)
        _run(orch)
        # Corrupt the checkpoint run id.
        path = tmp_path / "checkpoints" / "gs_run_1.checkpoint.json"
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        data["run_id"] = "other_run"
        path.write_text(json.dumps(data), encoding="utf-8")
        orch2, _, _, _ = _orchestrator(tmp_path, fixture, manifest)
        with pytest.raises(GoldenSceneResumeMismatchError):
            asyncio.run(orch2.run())


class TestBlockingDefect:
    def test_render_leg_failure_rejects_no_false_pass(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)

        class _FailingRenderLeg:
            async def render(self, *, node, fixture, workspace) -> dict:
                raise RuntimeError("render device lost")

        orch, _, _, _ = _orchestrator(
            tmp_path, fixture, manifest, render_leg=_FailingRenderLeg()
        )
        report = _run(orch)
        assert report.verdict == GoldenSceneVerdict.REJECT
        render = next(
            r for r in report.receipts if r.kind == GoldenSceneNodeKind.RENDER
        )
        assert render.status == GoldenSceneNodeStatus.FAILED
        assert "render device lost" in render.error
        # no false PASS anywhere
        assert all(
            r.status != GoldenSceneNodeStatus.COMPLETED
            or r.kind in (GoldenSceneNodeKind.SCRIPT, GoldenSceneNodeKind.IR,
                          GoldenSceneNodeKind.ASSETS, GoldenSceneNodeKind.SCENE,
                          GoldenSceneNodeKind.ANIMATION_AUDIO, GoldenSceneNodeKind.FACIAL)
            for r in report.receipts
        )

    def test_blocking_review_finding_rejects(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)
        review = _PassingReviewRepairLeg(
            findings=[
                {
                    "code": "REVIEW_BLOCKING",
                    "blocking": True,
                    "message": "unskinned mesh detected",
                }
            ]
        )
        orch, _, _, _ = _orchestrator(
            tmp_path, fixture, manifest, review_leg=review
        )
        report = _run(orch)
        assert report.verdict == GoldenSceneVerdict.REJECT
        review_receipt = next(
            r for r in report.receipts if r.kind == GoldenSceneNodeKind.REVIEW_REPAIR
        )
        assert review_receipt.findings[0]["blocking"] is True

    def test_step_runner_missing_rejects(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)
        steps = build_default_steps()
        del steps[GoldenSceneNodeKind.SCRIPT]  # no leg fallback for SCRIPT
        orch = GoldenSceneOrchestrator(
            fixture=fixture,
            manifest=manifest,
            checkpoint_dir=tmp_path / "checkpoints",
            steps=steps,
            render_leg=_RecordingRenderLeg(),
            review_repair_leg=_PassingReviewRepairLeg(),
            ffmpeg_leg=_PassingFfmpegLeg(),
            identity_checker=_passing_identity,
            verification_checker=_passing_verification,
        )
        report = _run(orch)
        assert report.verdict == GoldenSceneVerdict.REJECT

    def test_fixture_with_unapproved_asset_rejects(self, tmp_path):
        fixture = _fixture()
        fixture = fixture.model_copy(
            update={
                "characters": [
                    {
                        "master_id": "cm_evil",
                        "name": "Evil",
                        "revisions": [],
                        "active_revision_id": None,
                    }
                ]
            }
        )
        manifest = _manifest(fixture)
        orch, _, _, _ = _orchestrator(tmp_path, fixture, manifest)
        report = _run(orch)
        assets = next(
            r for r in report.receipts if r.kind == GoldenSceneNodeKind.ASSETS
        )
        assert assets.findings[0]["blocking"] is True
        assert report.verdict == GoldenSceneVerdict.REJECT


class TestIdentityVerificationGates:
    def test_identity_fail_rejects(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)

        def bad_identity(fixture, receipts):
            return IdentityContinuityReceipt(
                character_identity_ok=False,
                voice_identity_ok=True,
                continuity_ok=True,
                blocking_issues=["character identity mismatch"],
            )

        orch, _, _, _ = _orchestrator(
            tmp_path, fixture, manifest, identity_checker=bad_identity
        )
        report = _run(orch)
        assert report.verdict == GoldenSceneVerdict.REJECT

    def test_verification_fail_rejects(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)

        def bad_verification(fixture, receipts, workspace):
            return TechnicalVerificationReceipt(
                frames_ok=True, audio_ok=False, final_mp4_ok=False,
                checks={"final_mp4": {"exists": False}},
            )

        orch, _, _, _ = _orchestrator(
            tmp_path, fixture, manifest, verification_checker=bad_verification
        )
        report = _run(orch)
        assert report.verdict == GoldenSceneVerdict.REJECT


class TestReportContent:
    def test_report_lists_repairs_and_approvals(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)
        review = _PassingReviewRepairLeg(
            findings=[{"code": "LOW_QUALITY", "blocking": False, "message": "denoise"}],
            repairs=[
                RepairEntry(
                    repair_id="rp_1",
                    node_kind=GoldenSceneNodeKind.REVIEW_REPAIR,
                    finding_code="LOW_QUALITY",
                    outcome="REPAIRED",
                )
            ],
        )
        orch, _, _, _ = _orchestrator(
            tmp_path, fixture, manifest, review_leg=review
        )
        report = _run(orch)
        assert report.verdict == GoldenSceneVerdict.PASS
        assert report.repair_count == 1
        assert report.repair_entries[0].finding_code == "LOW_QUALITY"
        assert [a.approval_id for a in report.human_approvals] == ["ap_1"]

    def test_summary_names_verdict_and_gates(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)
        orch, _, _, _ = _orchestrator(tmp_path, fixture, manifest)
        report = _run(orch)
        assert "PASS" in report.summary
        assert "identity_continuity=PASS" in report.summary


class TestRealKernelSteps:
    def test_script_step_parses_real_screenplay(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)
        steps = build_default_steps()
        node = GoldenSceneNodeReceipt(
            node_id=GoldenSceneNodeId("n_script"),
            kind=GoldenSceneNodeKind.SCRIPT,
            status=GoldenSceneNodeStatus.RUNNING,
        )
        outcome = asyncio.run(
            steps[GoldenSceneNodeKind.SCRIPT].run(
                node=node,
                fixture=fixture,
                manifest=manifest,
                workspace=tmp_path,
                prior={},
            )
        )
        assert outcome["output_hashes"]["screenplay"]
        assert outcome["findings"][0]["blocking"] is False

    def test_assets_step_approved_masters_pass(self, tmp_path):
        fixture = _fixture()
        manifest = _manifest(fixture)
        steps = build_default_steps()
        node = GoldenSceneNodeReceipt(
            node_id=GoldenSceneNodeId("n_assets"),
            kind=GoldenSceneNodeKind.ASSETS,
            status=GoldenSceneNodeStatus.RUNNING,
        )
        outcome = asyncio.run(
            steps[GoldenSceneNodeKind.ASSETS].run(
                node=node, fixture=fixture, manifest=manifest,
                workspace=tmp_path, prior={},
            )
        )
        assert outcome["findings"][0]["blocking"] is False

    def test_default_identity_checker_fails_closed_without_package(self, tmp_path):
        # No package/graph in fixture metadata => continuity cannot verify.
        fixture = _fixture()
        receipt = default_identity_checker(fixture, {})
        assert receipt.passed is False
        assert any("continuity" in i for i in receipt.blocking_issues)
