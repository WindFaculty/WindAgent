"""
VP3D Phase 26 — Multi-Scene Episode integration flow (Stage M).

Runs the REAL EpisodeOrchestrator with the REAL golden-scene kernel steps
(screenplay parse, IR, camera/lighting scene compile, animation + audio mix
plan, facial) and REAL ffmpeg assembly, with deterministic injected legs for
the render / review / audio / asset-generation ports. Proves the full
multi-scene episode contract end to end (stage_m.md §4):

- three scenes, five shots, three characters, two environments;
- asset reuse: a SECOND run with a fresh run id reuses every cached asset
  (no regeneration) and the cache report counts HIT vs MISS;
- kill/resume: cancel after the first render chunk, restart -> completed
  chunks SKIPPED, only missing chunks re-render (partial rerender, render
  leg call count frozen for the completed chunk);
- targeted invalidation: replacing one shot invalidates only its
  downstream artifacts;
- continuity + stable episode ordering; missing media manifest fails
  closed (REJECT, never a false PASS);
- real ffmpeg: per-scene MP4s + episode media manifest.
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from windagent_core.domain.video_production.enums import (
    EpisodeChunkStatus,
    EpisodeVerdict,
    GoldenSceneNodeStatus,
)
from windagent_core.domain.video_production.episode import (
    EpisodeChunkSpec,
    EpisodeFixture,
    EpisodeRunManifest,
)
from windagent_core.domain.video_production.golden_scene import (
    GoldenSceneFixture,
)
from windagent_core.domain.video_production.ids import (
    EpisodeRunId,
    VideoProjectId,
)
from windagent_intelligence.video.episode import (
    EpisodeAssetCache,
    EpisodeOrchestrator,
    episode_identity_checker,
    episode_verification_checker,
)
from windagent_intelligence.video.golden_scene import build_default_steps

from tests.unit.intelligence.test_phase26_episode import _episode_fixture

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _one_px_png() -> bytes:
    """A REAL 2x2 RGB PNG, built programmatically (ffmpeg must be able to
    decode the frames to mux the MP4; h264 needs even dimensions)."""
    import struct
    import zlib

    def _chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    row = b"\xff\x00\x00" * 2  # 2 red pixels
    raw = b"\x00" + row + b"\x00" + row  # 2 scanlines, filter 0 each
    return (
        PNG_MAGIC
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


ONE_PX_PNG = _one_px_png()


def _episode_fixture_with_evidence() -> EpisodeFixture:
    """Episode fixture + REAL continuity evidence (package + shot graph +
    voice profiles) like the Phase 25 golden-scene fixture."""
    import asyncio as _asyncio

    from tests.fixtures.video_production.director_fixtures import (
        DeterministicDirectorModel,
        build_pinned_planner_output,
        build_two_character_dialogue_package,
    )
    from tests.fixtures.video_production.ir_fixture_builder import (
        build_valid_ir_dict,
    )
    from windagent_intelligence.video import VideoDirectorService
    from windagent_intelligence.video.shot_planner import ShotGraphPlannerService

    async def _graph():
        pkg = build_two_character_dialogue_package()
        plan_json = build_pinned_planner_output(pkg)
        director = VideoDirectorService(DeterministicDirectorModel(plan_json))
        receipt = await director.create_cinematic_plan_receipt(pkg)
        locked = await director.lock_shot_plan(receipt.plan)
        return pkg, ShotGraphPlannerService().plan(pkg, locked)

    pkg, graph = _asyncio.run(_graph())
    fixture = _episode_fixture()
    metadata = dict(fixture.metadata)
    metadata["ir_document"] = build_valid_ir_dict()
    metadata["package"] = pkg.model_dump()
    metadata["graph_receipt"] = graph.to_dict()
    metadata["voice_profiles"] = {
        "cm_alice": {"approved": True, "voice_profile_id": "vp_alice"},
        "cm_bob": {"approved": True, "voice_profile_id": "vp_bob"},
        "cm_carol": {"approved": True, "voice_profile_id": "vp_carol"},
    }
    return fixture.model_copy(update={"metadata": metadata})


def _manifest(
    fixture: EpisodeFixture, run_id: str = "ep_flow_run"
) -> EpisodeRunManifest:
    return EpisodeRunManifest(
        run_id=EpisodeRunId(run_id),
        project_id=VideoProjectId("vp_episode_flow"),
        revision_id="rev_ep_flow_1",
        fixture_hash=fixture.content_hash(),
        candidate_sha="candidate_flow",
        hardware_baseline={"gpu": "RTX 5060"},
        tool_versions={"blender": "4.5", "ffmpeg": "8.x"},
        budgets={"wall_clock_seconds": 3600.0},
        pinned_seeds={"render": 7},
    )


# ---------------------------------------------------------------------------
# Deterministic legs
# ---------------------------------------------------------------------------
class _FakeRenderLeg:
    """Writes real PNG-magic frame files per chunk; counts calls per chunk."""

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    async def render_chunk(
        self,
        *,
        chunk: EpisodeChunkSpec,
        scene_fixture: GoldenSceneFixture,
        workspace: Path,
    ) -> dict:
        chunk_id = str(chunk.chunk_id)
        self.calls[chunk_id] = self.calls.get(chunk_id, 0) + 1
        scene_dir = Path(workspace) / chunk.scene_id
        scene_dir.mkdir(parents=True, exist_ok=True)
        names = []
        for frame in range(chunk.frame_start, chunk.frame_end + 1):
            # scene-relative numbering (stable across resume: the SAME file
            # names are rewritten for re-rendered chunks)
            scene_frame = chunk.scene_frame_start + (frame - chunk.frame_start)
            name = f"frame_{scene_frame:04d}.png"
            (scene_dir / name).write_bytes(ONE_PX_PNG)
            names.append(name)
        return {
            "output_hashes": {
                "frames": hashlib.sha256(
                    "\n".join(names).encode()
                ).hexdigest()
            },
            "metadata": {"frames": len(names), "chunk": chunk_id},
        }


class _CleanReviewLeg:
    async def review_scene(
        self, *, scene, scene_fixture, workspace
    ) -> dict:
        return {
            "output_hashes": {"review": hashlib.sha256(b"clean").hexdigest()},
            "findings": [],
            "metadata": {"reviewed_scene": str(scene.scene_id)},
        }


class _BlockingReviewLeg:
    async def review_scene(
        self, *, scene, scene_fixture, workspace
    ) -> dict:
        return {
            "output_hashes": {"review": hashlib.sha256(b"defect").hexdigest()},
            "findings": [
                {
                    "code": "FRAME_MISSING",
                    "blocking": True,
                    "message": "planted blocking defect",
                }
            ],
            "metadata": {"reviewed_scene": str(scene.scene_id)},
        }


class _RealFfmpegLeg:
    """REAL ffmpeg: scene frames + real sine WAV -> scene_<id>.mp4."""

    async def assemble_scene(
        self, *, scene, scene_fixture, workspace
    ) -> dict:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg not available")
        scene_dir = Path(workspace) / str(scene.scene_id)
        scene_dir.mkdir(parents=True, exist_ok=True)
        pngs = sorted(scene_dir.glob("frame_*.png"))
        if not pngs:
            raise RuntimeError(f"no frames for scene {scene.scene_id}")
        wav = scene_dir / "dialogue.wav"
        subprocess.run(
            [
                ffmpeg, "-y",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
                "-ar", "48000", "-ac", "2", str(wav),
            ],
            capture_output=True, text=True, timeout=120,
        )
        mp4 = scene_dir / f"scene_{scene.scene_id}.mp4"
        argv = [
            ffmpeg, "-y",
            "-framerate", "24",
            "-i", str(scene_dir / "frame_%04d.png"),
            "-i", str(wav),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(mp4),
        ]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg assemble failed: {proc.stderr[-300:]}")
        return {
            "output_hashes": {
                "scene_media": hashlib.sha256(mp4.read_bytes()).hexdigest()
            },
            "metadata": {
                "scene_media_path": str(mp4),
                "scene_media_sha256": hashlib.sha256(mp4.read_bytes()).hexdigest(),
                "frames_used": len(pngs),
            },
        }


class _FakeAudioLeg:
    async def synthesize(self, *, scene, scene_fixture, workspace) -> dict:
        scene_dir = Path(workspace) / str(scene.scene_id)
        scene_dir.mkdir(parents=True, exist_ok=True)
        return {
            "output_hashes": {
                "audio": hashlib.sha256(str(scene.scene_id).encode()).hexdigest()
            },
            "metadata": {"scene": str(scene.scene_id)},
        }


class _FakeAssetGenerator:
    """Deterministic generation; counts calls per cache key."""

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    async def generate(
        self, *, cache_key, kind, revision, scene_fixture, workspace
    ) -> dict:
        self.calls[cache_key] = self.calls.get(cache_key, 0) + 1
        content_hash = hashlib.sha256(
            f"{cache_key}:{revision}".encode()
        ).hexdigest()
        return {"content_hash": content_hash, "metadata": {"generated": True}}


class _PassingIdentity:
    def __call__(self, fixture, receipts):
        from windagent_core.domain.video_production.golden_scene import (
            IdentityContinuityReceipt,
        )

        return IdentityContinuityReceipt(
            character_identity_ok=True,
            voice_identity_ok=True,
            continuity_ok=True,
        )


class _PassingVerification:
    def __call__(self, fixture, receipts, workspace):
        from windagent_core.domain.video_production.golden_scene import (
            TechnicalVerificationReceipt,
        )

        return TechnicalVerificationReceipt(
            frames_ok=True, audio_ok=True, final_mp4_ok=True
        )


def _make_orchestrator(
    tmp_path: Path,
    fixture: EpisodeFixture,
    manifest: EpisodeRunManifest,
    *,
    render_leg,
    review_leg,
    cache_dir: str = "cache",
    run_dir: str = "checkpoints",
    identity=None,
    verification=None,
    steps=None,
    generator=None,
) -> EpisodeOrchestrator:
    root = Path(tmp_path)
    cache = EpisodeAssetCache(root / cache_dir)
    return EpisodeOrchestrator(
        fixture=fixture,
        manifest=manifest,
        checkpoint_dir=root / run_dir,
        cache=cache,
        steps=steps or build_default_steps(),
        render_leg=render_leg,
        review_repair_leg=review_leg,
        ffmpeg_leg=_RealFfmpegLeg(),
        audio_leg=_FakeAudioLeg(),
        asset_generator=generator or _FakeAssetGenerator(),
        identity_checker=identity or _PassingIdentity(),
        verification_checker=verification or _PassingVerification(),
        artifact_dir=root / "workspace",
    )


class TestEpisodeFlow:
    @pytest.fixture(autouse=True)
    def _require_ffmpeg(self):
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not available")

    def test_full_episode_pipeline_to_real_mp4(self, tmp_path):
        fixture = _episode_fixture_with_evidence()
        manifest = _manifest(fixture)
        render_leg = _FakeRenderLeg()
        orch = _make_orchestrator(
            tmp_path, fixture, manifest,
            render_leg=render_leg,
            review_leg=_CleanReviewLeg(),
            identity=episode_identity_checker,
            verification=episode_verification_checker,
        )
        report = asyncio.run(orch.run())
        assert report.verdict == EpisodeVerdict.PASS
        # node plan: 2 episode + 2 branches + 6*3 scenes + 1 final = 23
        assert len(report.receipts) == 23
        statuses = {r.node_id: r.status.value for r in report.receipts}
        assert all(
            s in ("COMPLETED", "SKIPPED") for s in statuses.values()
        ), statuses
        # chunk_frames=12 -> each 24-frame shot = 2 chunks -> 10 total
        assert len(report.chunks) == 10
        assert all(c.status == EpisodeChunkStatus.COMPLETED for c in report.chunks)
        # episode media manifest in scene order
        final_receipt = next(r for r in report.receipts if r.node_id == "episode::FINAL")
        assert final_receipt.metadata["media_scene_order"] == ["scn_1", "scn_2", "scn_3"]
        # real mp4s exist
        workspace = Path(tmp_path) / "workspace"
        for scene_id in ("scn_1", "scn_2", "scn_3"):
            mp4 = workspace / scene_id / f"scene_{scene_id}.mp4"
            assert mp4.is_file() and mp4.stat().st_size > 0
        # identity + continuity + technical verification pass
        assert report.identity_continuity.passed
        assert report.technical_verification.passed
        # real ffprobe verified h264+aac streams (when ffprobe available)
        if shutil.which("ffprobe"):
            mp4 = workspace / "scn_1" / "scene_scn_1.mp4"
            probe = subprocess.run(
                [
                    shutil.which("ffprobe"), "-v", "error",
                    "-show_entries", "stream=codec_type",
                    "-of", "json", str(mp4),
                ],
                capture_output=True, text=True, timeout=60,
            )
            import json

            streams = json.loads(probe.stdout).get("streams", [])
            assert {s.get("codec_type") for s in streams} == {"video", "audio"}

    def test_second_run_reuses_assets_no_regeneration(self, tmp_path):
        """Backlog 1: a new run over the same cache REUSES every asset."""
        fixture = _episode_fixture_with_evidence()
        generator = _FakeAssetGenerator()
        render_leg = _FakeRenderLeg()

        # Run 1: fresh cache -> everything MISS -> generated.
        manifest_1 = _manifest(fixture, "ep_flow_run_1")
        orch_1 = _make_orchestrator(
            tmp_path, fixture, manifest_1,
            render_leg=render_leg, review_leg=_CleanReviewLeg(),
            generator=generator, run_dir="ckpt_a",
        )
        report_1 = asyncio.run(orch_1.run())
        assert report_1.verdict == EpisodeVerdict.PASS
        generated_once = dict(generator.calls)
        # 3 characters + 2 environments generated exactly once
        assert set(generated_once) == {
            "character:cm_alice", "character:cm_bob", "character:cm_carol",
            "environment:env_park", "environment:env_city",
        }
        assert all(v == 1 for v in generated_once.values())
        assert report_1.cache_report.misses == 5
        assert report_1.cache_report.hits == 0

        # Run 2: NEW run id, SAME cache dir -> every asset HIT, no generate.
        manifest_2 = _manifest(fixture, "ep_flow_run_2")
        orch_2 = _make_orchestrator(
            tmp_path, fixture, manifest_2,
            render_leg=_FakeRenderLeg(), review_leg=_CleanReviewLeg(),
            generator=generator, run_dir="ckpt_b",
        )
        report_2 = asyncio.run(orch_2.run())
        assert report_2.verdict == EpisodeVerdict.PASS
        assert generator.calls == generated_once  # nothing regenerated
        assert report_2.cache_report.hits == 5
        assert report_2.cache_report.misses == 0
        # usage counts track REUSES across runs (run 1 generated, run 2 reused)
        assert (
            report_2.cache_report.entries["character:cm_alice"].usage_count == 1
        )
        assert (
            report_2.cache_report.entries["environment:env_park"].usage_count == 1
        )

    def test_replace_shot_invalidates_only_downstream(self, tmp_path):
        """Backlog 5: shot/camera/audio change invalidates correct scope."""
        fixture = _episode_fixture_with_evidence()
        manifest = _manifest(fixture, "ep_flow_run_inv")
        orch = _make_orchestrator(
            tmp_path, fixture, manifest,
            render_leg=_FakeRenderLeg(), review_leg=_CleanReviewLeg(),
        )
        report = asyncio.run(
            orch.run(
                invalidation_requests=[
                    ["shot:sh_1"],
                    ["audio_cue:cue_bgm"],
                    ["camera:cam_3"],
                ]
            )
        )
        assert report.verdict == EpisodeVerdict.PASS
        plans = {tuple(p.changed_refs): p for p in report.invalidation_plans}
        shot_plan = plans[("shot:sh_1",)]
        assert set(shot_plan.invalidated) == {
            "render:sh_1", "media:scn_1", "final:episode",
        }
        assert "render:sh_2" in shot_plan.preserved
        assert "media:scn_2" in shot_plan.preserved
        cue_plan = plans[("audio_cue:cue_bgm",)]
        # cue_bgm feeds sh_5 (scene 3) + media:scn_3 + final
        assert set(cue_plan.invalidated) == {
            "shot:sh_5", "render:sh_5", "media:scn_3", "final:episode",
        }
        camera_plan = plans[("camera:cam_3",)]
        assert set(camera_plan.invalidated) == {
            "shot:sh_3", "render:sh_3", "media:scn_2", "final:episode",
        }
        assert "render:sh_4" in camera_plan.preserved

    def test_kill_mid_render_resumes_partial_rerender(self, tmp_path):
        """Backlog 4: kill after chunk 1; restart renders only missing chunks."""
        fixture = _episode_fixture_with_evidence()
        manifest = _manifest(fixture, "ep_flow_run_kill")
        render_leg = _FakeRenderLeg()
        orch = _make_orchestrator(
            tmp_path, fixture, manifest,
            render_leg=render_leg, review_leg=_CleanReviewLeg(),
            identity=episode_identity_checker,
            verification=episode_verification_checker,
        )
        state = {"stop": False}

        def token():
            if sum(render_leg.calls.values()) >= 1:
                state["stop"] = True
            return state["stop"]

        report_a = asyncio.run(orch.run(cancel_token=token))
        # first chunk done, rest cancelled -> REJECT (never a false PASS)
        assert report_a.verdict == EpisodeVerdict.REJECT
        render_node_a = next(
            r for r in report_a.receipts if r.node_id == "scn_1::RENDER"
        )
        assert render_node_a.status == GoldenSceneNodeStatus.CANCELLED
        calls_after_cancel = dict(render_leg.calls)
        chunk_ids_after_cancel = set(calls_after_cancel)
        assert len(chunk_ids_after_cancel) >= 1

        # Restart: same run id + fixture -> completed chunks SKIPPED.
        state["stop"] = False
        report_b = asyncio.run(orch.run())
        assert report_b.verdict == EpisodeVerdict.PASS
        # completed chunks were NEVER re-rendered (call count frozen)
        for chunk_id in chunk_ids_after_cancel:
            assert render_leg.calls[chunk_id] == calls_after_cancel[chunk_id]
        # new chunks got rendered (partial rerender, no duplicate)
        assert len(render_leg.calls) == len(chunk_ids_after_cancel) + 9
        # chunk receipts: completed chunks SKIPPED in run B, rest COMPLETED
        chunk_statuses = {str(c.chunk_id): c.status for c in report_b.chunks}
        for chunk_id in chunk_ids_after_cancel:
            assert chunk_statuses[chunk_id] == EpisodeChunkStatus.SKIPPED
        assert all(
            s == EpisodeChunkStatus.COMPLETED
            for cid, s in chunk_statuses.items()
            if cid not in chunk_ids_after_cancel
        )

    def test_blocking_review_defect_rejects(self, tmp_path):
        """No false PASS: planted blocking finding -> REJECT."""
        fixture = _episode_fixture_with_evidence()
        manifest = _manifest(fixture, "ep_flow_run_defect")
        orch = _make_orchestrator(
            tmp_path, fixture, manifest,
            render_leg=_FakeRenderLeg(),
            review_leg=_BlockingReviewLeg(),
            identity=episode_identity_checker,
            verification=episode_verification_checker,
        )
        report = asyncio.run(orch.run())
        assert report.verdict == EpisodeVerdict.REJECT
        blocking = [
            f for r in report.receipts for f in r.findings if f.get("blocking")
        ]
        assert any(f["code"] == "FRAME_MISSING" for f in blocking)

    def test_unfinished_run_missing_media_manifest_fails_closed(self, tmp_path):
        """No FINAL node -> no media manifest -> verification fails -> REJECT."""
        fixture = _episode_fixture_with_evidence()
        manifest = _manifest(fixture, "ep_flow_run_nomanifest")
        orch = _make_orchestrator(
            tmp_path, fixture, manifest,
            render_leg=_FakeRenderLeg(),
            review_leg=_CleanReviewLeg(),
            verification=episode_verification_checker,
        )
        # Cancel right before FINAL: 22 nodes = 4 episode-level + 6*3 scenes.
        report = asyncio.run(
            orch.run(cancel_token=lambda: len(orch._receipts) >= 22)
        )
        assert report.verdict == EpisodeVerdict.REJECT
        final_receipt = next(
            (r for r in report.receipts if r.node_id == "episode::FINAL"), None
        )
        assert final_receipt is not None
        assert final_receipt.status == GoldenSceneNodeStatus.CANCELLED
        assert report.technical_verification.checks["episode_ordering"]["ok"] is False

    def test_identity_checker_requires_continuity_evidence(self, tmp_path):
        """Episode identity gate fails closed without package/graph."""
        fixture = _episode_fixture()  # no package/graph evidence
        manifest = _manifest(fixture, "ep_flow_run_noid")
        orch = _make_orchestrator(
            tmp_path, fixture, manifest,
            render_leg=_FakeRenderLeg(),
            review_leg=_CleanReviewLeg(),
            identity=episode_identity_checker,
            verification=episode_verification_checker,
        )
        report = asyncio.run(orch.run())
        assert report.verdict == EpisodeVerdict.REJECT
        assert not report.identity_continuity.passed
