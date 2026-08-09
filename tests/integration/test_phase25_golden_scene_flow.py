"""
VP3D Phase 25 — Golden Scene E2E integration flow (Stage M).

Runs the REAL orchestrator with the REAL intelligence kernels (screenplay
parse, IR build, character-master gate, camera/lighting scene compile,
animation + audio mix plan, facial lip-sync) and REAL ffmpeg assembly, with
deterministic injected legs for the render / review-repair ports. Proves the
full pipeline contract end to end:

    Script -> IR -> Assets -> Scene -> Animation + Audio -> Facial
    -> Render -> Review/Repair -> FFmpeg -> Final MP4

plus the gate scenario: cancel/restart at the RENDER node resumes WITHOUT
duplication, and a blocking-defect fixture is REJECTED (no false PASS).
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest
from windagent_core.domain.video_production.enums import (
    GoldenSceneNodeKind,
    GoldenSceneNodeStatus,
    GoldenSceneVerdict,
)
from windagent_core.domain.video_production.golden_scene import (
    GoldenSceneFixture,
    GoldenSceneRunManifest,
    compute_content_hash,
)
from windagent_core.domain.video_production.ids import (
    GoldenSceneRunId,
    VideoProjectId,
)
from windagent_intelligence.video.golden_scene import (
    GoldenSceneOrchestrator,
    build_default_steps,
    default_identity_checker,
    default_verification_checker,
)

HAVE_FFMPEG = shutil.which("ffmpeg") is not None


def _fixture() -> GoldenSceneFixture:
    from tests.unit.intelligence.test_phase25_golden_scene import _fixture as _base_fixture

    fixture = _base_fixture()
    # Wire REAL continuity evidence: director-planned package + shot graph
    # from the Phase 8 golden fixture, plus approved voice profiles for both
    # dialogue characters (identity gate needs them).
    import asyncio

    from tests.fixtures.video_production.director_fixtures import (
        DeterministicDirectorModel,
        build_pinned_planner_output,
        build_two_character_dialogue_package,
    )
    from windagent_intelligence.video import VideoDirectorService
    from windagent_intelligence.video.shot_planner import ShotGraphPlannerService

    async def _graph_receipt():
        pkg = build_two_character_dialogue_package()
        plan_json = build_pinned_planner_output(pkg)
        director = VideoDirectorService(DeterministicDirectorModel(plan_json))
        receipt = await director.create_cinematic_plan_receipt(pkg)
        locked = await director.lock_shot_plan(receipt.plan)
        return pkg, ShotGraphPlannerService().plan(pkg, locked)

    pkg, graph = asyncio.run(_graph_receipt())
    metadata = dict(fixture.metadata)
    metadata["package"] = pkg.model_dump()
    metadata["graph_receipt"] = graph.to_dict()
    metadata["voice_profiles"] = {
        "cm_bob": {"approved": True, "voice_profile_id": "vp_bob"},
        "cm_alice": {"approved": True, "voice_profile_id": "vp_alice"},
    }
    return fixture.model_copy(update={"metadata": metadata})


class _RealFfmpegLeg:
    """REAL ffmpeg: frames + audio -> final MP4, ffprobe-verified."""

    async def assemble(self, *, node, fixture, workspace) -> dict:
        frame_dir = workspace / "render"
        pngs = sorted(frame_dir.glob("frame_*.png"))
        if len(pngs) < 2:
            raise RuntimeError("render leg produced no frames")
        mp4 = workspace / "final_golden.mp4"
        audio_in = ""
        wav = workspace / "dialogue_alice.wav"
        if wav.is_file():
            audio_in = str(wav)
        argv = [
            shutil.which("ffmpeg"),
            "-y",
            "-framerate", "24",
            "-i", str(frame_dir / "frame_%04d.png"),
        ]
        if audio_in:
            argv += ["-i", audio_in, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                     "-c:a", "aac", "-shortest"]
        else:
            argv += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        argv += [str(mp4)]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {proc.stderr[-400:]}")
        assert mp4.is_file() and mp4.stat().st_size > 0
        return {
            "output_hashes": {
                "final_mp4": compute_content_hash(
                    {"size": mp4.stat().st_size, "path": mp4.name}
                )
            },
            "metadata": {"final_mp4": str(mp4)},
        }


class _RealFfmpegRenderLeg:
    """Render leg that synthesizes REAL PNG frames (testsrc via ffmpeg)."""

    def __init__(self) -> None:
        self.calls = 0

    async def render(self, *, node, fixture, workspace) -> dict:
        self.calls += 1
        frame_dir = workspace / "render"
        frame_dir.mkdir(parents=True, exist_ok=True)
        # 8 real PNG frames @ 24fps, testsrc pattern.
        argv = [
            shutil.which("ffmpeg"), "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=0.35",
            "-frames:v", "8",
            str(frame_dir / "frame_%04d.png"),
        ]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg frame gen failed: {proc.stderr[-300:]}")
        pngs = sorted(frame_dir.glob("frame_*.png"))
        if len(pngs) != 8:
            raise RuntimeError(f"expected 8 frames, got {len(pngs)}")
        # Real dialogue WAV for the audio leg.
        wav = workspace / "dialogue_alice.wav"
        subprocess.run(
            [
                shutil.which("ffmpeg"), "-y",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=0.35",
                "-ar", "48000", "-ac", "2", str(wav),
            ],
            capture_output=True, text=True, timeout=120,
        )
        return {
            "output_hashes": {
                "frames": compute_content_hash(
                    {"count": len(pngs), "files": [p.name for p in pngs]}
                ),
            },
            "metadata": {"frame_count": len(pngs)},
        }


class _CleanReviewRepairLeg:
    async def review_and_repair(self, *, node, fixture, workspace) -> dict:
        return {
            "output_hashes": {"review": compute_content_hash({"findings": []})},
            "findings": [],
            "repairs": [],
            "metadata": {"repair_count": 0},
        }


class _BlockingReviewRepairLeg:
    async def review_and_repair(self, *, node, fixture, workspace) -> dict:
        return {
            "output_hashes": {"review": compute_content_hash({"findings": ["block"]})},
            "findings": [
                {
                    "code": "REVIEW_BLOCKING",
                    "blocking": True,
                    "message": "unskinned mesh detected (planted defect)",
                }
            ],
            "repairs": [],
            "metadata": {"repair_count": 0},
        }


@pytest.mark.skipif(not HAVE_FFMPEG, reason="real ffmpeg not on PATH")
class TestGoldenSceneFlowRealFfmpeg:
    def _run(
        self,
        tmp_path: Path,
        *,
        review_leg=None,
        render_leg=None,
        fixture=None,
        run_id: str = "gs_flow_run",
    ) -> GoldenSceneOrchestrator:
        fixture = fixture or _fixture()
        manifest = GoldenSceneRunManifest(
            run_id=GoldenSceneRunId(run_id),
            project_id=VideoProjectId("vp_golden"),
            revision_id="rev_golden_1",
            fixture_hash=fixture.content_hash(),
            candidate_sha="candidate_phase25",
            tool_versions={"ffmpeg": "8.x"},
            budgets={"wall_clock_seconds": 600.0},
            pinned_seeds={"facial": 42, "render": 7},
        )
        return GoldenSceneOrchestrator(
            fixture=fixture,
            manifest=manifest,
            checkpoint_dir=tmp_path / "checkpoints",
            steps=build_default_steps(),
            render_leg=render_leg or _RealFfmpegRenderLeg(),
            review_repair_leg=review_leg or _CleanReviewRepairLeg(),
            ffmpeg_leg=_RealFfmpegLeg(),
            identity_checker=default_identity_checker,
            verification_checker=default_verification_checker,
        )

    def test_full_pipeline_to_real_mp4(self, tmp_path):
        """Golden scene runs end to end; real MP4 passes verification."""
        orch = self._run(tmp_path)
        report = asyncio.run(orch.run())
        assert report.verdict == GoldenSceneVerdict.PASS
        assert len(report.receipts) == 10
        assert all(r.output_hashes for r in report.receipts)
        # Real technical verification passed: frames + audio + MP4 all real.
        assert report.technical_verification.frames_ok
        assert report.technical_verification.audio_ok
        assert report.technical_verification.final_mp4_ok
        # Every node receipt carries provenance chain.
        assert report.receipts[-1].provenance  # FINAL references prior nodes

    def test_cancel_after_render_resumes_without_duplicate(self, tmp_path):
        """Cancel at RENDER boundary; restart must not re-render."""
        render_leg = _RealFfmpegRenderLeg()
        orch = self._run(tmp_path, render_leg=render_leg)

        state = {"stop": False}

        def token():
            if render_leg.calls >= 1:
                state["stop"] = True
            return state["stop"]

        report_a = asyncio.run(orch.run(cancel_token=token))
        statuses = {r.kind: r.status for r in report_a.receipts}
        assert statuses[GoldenSceneNodeKind.RENDER] == GoldenSceneNodeStatus.COMPLETED
        assert statuses[GoldenSceneNodeKind.REVIEW_REPAIR] == GoldenSceneNodeStatus.CANCELLED
        assert report_a.verdict == GoldenSceneVerdict.REJECT
        calls_after_cancel = render_leg.calls

        state["stop"] = False
        report_b = asyncio.run(orch.run())
        assert report_b.verdict == GoldenSceneVerdict.PASS
        skipped = {
            r.kind for r in report_b.receipts if r.status == GoldenSceneNodeStatus.SKIPPED
        }
        assert GoldenSceneNodeKind.RENDER in skipped
        assert GoldenSceneNodeKind.SCRIPT in skipped
        # No duplicate render: the leg was not invoked again.
        assert render_leg.calls == calls_after_cancel
        # Output hashes identical on resume (reused, not regenerated).
        render_a = next(r for r in report_a.receipts if r.kind == GoldenSceneNodeKind.RENDER)
        render_b = next(r for r in report_b.receipts if r.kind == GoldenSceneNodeKind.RENDER)
        assert render_a.output_hashes == render_b.output_hashes

    def test_blocking_defect_rejected_no_false_pass(self, tmp_path):
        """Planted blocking review finding -> REJECT, never PASS."""
        orch = self._run(tmp_path, review_leg=_BlockingReviewRepairLeg())
        report = asyncio.run(orch.run())
        assert report.verdict == GoldenSceneVerdict.REJECT
        review = next(
            r for r in report.receipts if r.kind == GoldenSceneNodeKind.REVIEW_REPAIR
        )
        assert review.findings[0]["blocking"] is True
        # The run manifest stays reproducible: same fixture -> same hash.
        assert report.manifest_hash == orch._manifest.content_hash()


class TestDefaultGatesFailClosed:
    def test_identity_checker_requires_continuity_evidence(self):
        """No package/graph in fixture => continuity cannot pass."""
        from tests.unit.intelligence.test_phase25_golden_scene import (
            _fixture as _base_fixture,
        )

        fixture = _base_fixture()  # no package/graph/voice metadata
        receipt = default_identity_checker(fixture, {})
        assert receipt.passed is False
        assert any("continuity" in i for i in receipt.blocking_issues)

    def test_verification_checker_rejects_empty_workspace(self, tmp_path):
        receipt = default_verification_checker(_fixture(), {}, tmp_path)
        assert receipt.passed is False
        assert receipt.frames_ok is False
        assert receipt.final_mp4_ok is False
