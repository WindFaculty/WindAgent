"""
VP3D Phase 26 — Multi-Scene Episode unit tests (Stage M, gate
VP3D_P26_MULTI_SCENE_EPISODE_VERIFIED).

Fail-closed matrix (stage_m.md §4 backlog):
- asset cache: HIT / MISS / INVALIDATED / REJECTED_REUSE decisions,
  persistence across instances, usage counting;
- resume planner: node-level SKIP only on COMPLETED + identical hashes;
  chunk-level SKIP enables PARTIAL rerender after a kill (only missing
  chunks re-run);
- invalidation: replacing one shot/camera/audio cue invalidates ONLY the
  correct downstream artifacts; unrelated artifacts are preserved;
- branch scheduler: parallel asset/audio branches, critical path + idle
  time measured, cycles fail closed;
- episode ordering: stable, deterministic from the fixture;
- verdict policy: any failed/cancelled node or chunk, ordering mismatch,
  identity/verification failure or unrepaired blocking finding REJECTS;
- fixture validation fails closed on broken structure.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from windagent_core.domain.video_production.enums import (
    EpisodeArtifactKind,
    EpisodeBranchKind,
    EpisodeCacheDecision,
    EpisodeChunkStatus,
    EpisodeVerdict,
    GoldenSceneNodeStatus,
)
from windagent_core.domain.video_production.episode import (
    EpisodeBranchScheduler,
    EpisodeBranchSpec,
    EpisodeChunkReceipt,
    EpisodeChunkSpec,
    EpisodeCheckpoint,
    EpisodeDependencyCycleError,
    EpisodeDependencyGraph,
    EpisodeFixture,
    EpisodeInvalidationPlanner,
    EpisodeNodeReceipt,
    EpisodeOrderingReceipt,
    EpisodeResumePlanner,
    EpisodeRunManifest,
    EpisodeVerdictPolicy,
    build_episode_branch_specs,
)
from windagent_core.domain.video_production.errors import (
    EpisodeValidationError,
)
from windagent_core.domain.video_production.golden_scene import (
    GoldenSceneNodeKind,
    IdentityContinuityReceipt,
    TechnicalVerificationReceipt,
)
from windagent_core.domain.video_production.ids import (
    EpisodeChunkId,
    EpisodeRunId,
    VideoProjectId,
)
from windagent_intelligence.video.episode import (
    EpisodeAssetCache,
    asset_expected_hash,
)


def _episode_fixture(**overrides) -> EpisodeFixture:
    characters = [
        {
            "master_id": "cm_alice",
            "name": "Alice",
            "approved_revision_id": "cmr_alice_1",
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
            "approved_revision_id": "cmr_bob_1",
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
        {
            "master_id": "cm_carol",
            "name": "Carol",
            "approved_revision_id": "cmr_carol_1",
            "revisions": [
                {
                    "revision_id": "cmr_carol_1",
                    "master_id": "cm_carol",
                    "state": "APPROVED",
                    "approval_verdict": "APPROVED",
                    "approval_actor": "producer",
                }
            ],
            "active_revision_id": "cmr_carol_1",
        },
    ]
    environments = [
        {"id": "env_park", "name": "Park", "revision_id": "envr_1"},
        {"id": "env_city", "name": "City", "revision_id": "envr_1"},
    ]
    data = {
        "fixture_id": "ep_fixture_01",
        "title": "Multi-Scene Episode",
        "planned_duration_seconds": 150.0,
        "fps": 24,
        "screenplay_text": (
            "Title: EPISODE\n\n"
            "INT. PARK - DAY\n"
            "ALICE walks toward BOB.\n"
            "BOB (warm)\nHello, Alice!\n"
            "ALICE\nHi, Bob!\n"
            "INT. CITY - NIGHT\n"
            "BOB and CAROL talk.\n"
            "INT. PARK - DAY\n"
            "ALICE and CAROL meet.\n"
        ),
        "scenes": [
            {
                "scene_id": "scn_1",
                "order_index": 0,
                "environment_ref": "env_park",
                "character_ids": ["cm_alice", "cm_bob"],
                "shot_ids": ["sh_1", "sh_2"],
                "frame_start": 1,
                "frame_end": 48,
            },
            {
                "scene_id": "scn_2",
                "order_index": 1,
                "environment_ref": "env_city",
                "character_ids": ["cm_bob", "cm_carol"],
                "shot_ids": ["sh_3", "sh_4"],
                "frame_start": 49,
                "frame_end": 96,
            },
            {
                "scene_id": "scn_3",
                "order_index": 2,
                "environment_ref": "env_park",
                "character_ids": ["cm_alice", "cm_carol"],
                "shot_ids": ["sh_5"],
                "frame_start": 97,
                "frame_end": 120,
            },
        ],
        "shots": [
            {
                "shot_id": "sh_1",
                "scene_id": "scn_1",
                "order_index": 0,
                "character_ids": ["cm_alice"],
                "camera_intent_ref": "cam_1",
                "audio_cue_refs": ["cue_alice"],
                "animation_intent_refs": ["ani_walk_alice"],
                "frame_start": 1,
                "frame_end": 24,
            },
            {
                "shot_id": "sh_2",
                "scene_id": "scn_1",
                "order_index": 1,
                "character_ids": ["cm_bob"],
                "camera_intent_ref": "cam_2",
                "audio_cue_refs": ["cue_bob"],
                "animation_intent_refs": ["ani_walk_bob"],
                "frame_start": 25,
                "frame_end": 48,
            },
            {
                "shot_id": "sh_3",
                "scene_id": "scn_2",
                "order_index": 0,
                "character_ids": ["cm_bob"],
                "camera_intent_ref": "cam_3",
                "audio_cue_refs": ["cue_bob"],
                "animation_intent_refs": [],
                "frame_start": 49,
                "frame_end": 72,
            },
            {
                "shot_id": "sh_4",
                "scene_id": "scn_2",
                "order_index": 1,
                "character_ids": ["cm_carol"],
                "camera_intent_ref": "cam_4",
                "audio_cue_refs": ["cue_carol"],
                "animation_intent_refs": [],
                "frame_start": 73,
                "frame_end": 96,
            },
            {
                "shot_id": "sh_5",
                "scene_id": "scn_3",
                "order_index": 0,
                "character_ids": ["cm_alice", "cm_carol"],
                "camera_intent_ref": "cam_5",
                "audio_cue_refs": ["cue_bgm"],
                "animation_intent_refs": ["ani_walk_alice"],
                "frame_start": 97,
                "frame_end": 120,
            },
        ],
        "characters": characters,
        "environments": environments,
        "dialogue_lines": [
            {
                "dialogue_id": "dlg_1",
                "scene_id": "scn_1",
                "character_id": "cm_bob",
                "text": "Hello, Alice!",
                "shot_id": "sh_1",
            },
            {
                "dialogue_id": "dlg_2",
                "scene_id": "scn_1",
                "character_id": "cm_alice",
                "text": "Hi, Bob!",
                "shot_id": "sh_2",
            },
            {
                "dialogue_id": "dlg_3",
                "scene_id": "scn_2",
                "character_id": "cm_carol",
                "text": "Long time!",
                "shot_id": "sh_4",
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
            },
            {
                "intent_id": "ani_walk_bob",
                "actor_id": "cm_bob",
                "action": "WALK",
                "emotion": "NEUTRAL",
                "fps": 24,
                "skeleton_profile_id": "skel_default",
            },
        ],
        "camera_intents": [
            {
                "intent_id": f"cam_{i}",
                "shot_id": f"sh_{i}",
                "scene_id": scene_id,
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
                "duration_seconds": 1.0,
                "fps": 24,
                "dialogue_timing": [],
            }
            for i, scene_id in zip(range(1, 6), ["scn_1", "scn_1", "scn_2", "scn_2", "scn_3"])
        ],
        "lighting_intents": [
            {
                "intent_id": f"lit_{i}",
                "shot_id": f"sh_{i}",
                "scene_id": scene_id,
                "mood": "HAPPY",
                "time_of_day": "DAY",
                "style": "CARTOON",
                "emphasis": "SUBJECT",
                "continuity_key": f"ep_scene_{scene_id}",
            }
            for i, scene_id in zip(range(1, 6), ["scn_1", "scn_1", "scn_2", "scn_2", "scn_3"])
        ],
        "audio_cues": [
            {
                "cue_id": "cue_alice",
                "kind": "DIALOGUE",
                "path": "dialogue_alice.wav",
                "source_hash": "a" * 64,
                "sample_rate": 48000,
                "channels": 2,
                "label": "cue_alice",
            },
            {
                "cue_id": "cue_bob",
                "kind": "DIALOGUE",
                "path": "dialogue_bob.wav",
                "source_hash": "b" * 64,
                "sample_rate": 48000,
                "channels": 2,
                "label": "cue_bob",
            },
            {
                "cue_id": "cue_carol",
                "kind": "DIALOGUE",
                "path": "dialogue_carol.wav",
                "source_hash": "c" * 64,
                "sample_rate": 48000,
                "channels": 2,
                "label": "cue_carol",
            },
            {
                "cue_id": "cue_bgm",
                "kind": "BGM",
                "path": "bgm.wav",
                "source_hash": "d" * 64,
                "sample_rate": 48000,
                "channels": 2,
                "label": "cue_bgm",
            },
        ],
        "render_profile": {
            "engine": "CYCLES",
            "quality": "DRAFT",
            "chunk_frames": 12,
        },
        "approvals": [],
        "metadata": {"voice_profiles": {}},
    }
    data.update(overrides)
    return EpisodeFixture.model_validate(data)


def _manifest(fixture: EpisodeFixture, run_id: str = "ep_run_1") -> EpisodeRunManifest:
    return EpisodeRunManifest(
        run_id=EpisodeRunId(run_id),
        project_id=VideoProjectId("vp_episode"),
        revision_id="rev_ep_1",
        fixture_hash=fixture.content_hash(),
        candidate_sha="candidate",
        hardware_baseline={"gpu": "RTX 5060"},
        tool_versions={"blender": "4.5"},
        budgets={"wall_clock_seconds": 3600.0},
        pinned_seeds={"render": 7},
    )


def _cache(tmp_path: Path) -> EpisodeAssetCache:
    return EpisodeAssetCache(tmp_path / "cache")


# ---------------------------------------------------------------------------
# Asset cache (backlog 1 + 6)
# ---------------------------------------------------------------------------
class TestEpisodeAssetCache:
    def test_miss_then_hit_reuse_no_regenerate(self, tmp_path):
        cache = _cache(tmp_path)
        expected = asset_expected_hash(
            EpisodeArtifactKind.CHARACTER_ASSET, "cm_alice", "cmr_alice_1"
        )
        decision, entry = cache.resolve("character:cm_alice", expected)
        assert decision == EpisodeCacheDecision.MISS.value
        assert entry is None
        cache.record_generated(
            "character:cm_alice",
            EpisodeArtifactKind.CHARACTER_ASSET,
            "cmr_alice_1",
            expected,
        )
        decision, entry = cache.resolve("character:cm_alice", expected)
        assert decision == EpisodeCacheDecision.HIT.value
        assert entry is not None
        assert entry.usage_count == 0
        cache.record_reuse("character:cm_alice")
        assert cache.entry("character:cm_alice").usage_count == 1

    def test_invalidated_on_stale_revision(self, tmp_path):
        cache = _cache(tmp_path)
        old = asset_expected_hash(
            EpisodeArtifactKind.CHARACTER_ASSET, "cm_bob", "cmr_bob_0"
        )
        new = asset_expected_hash(
            EpisodeArtifactKind.CHARACTER_ASSET, "cm_bob", "cmr_bob_1"
        )
        cache.record_generated(
            "character:cm_bob", EpisodeArtifactKind.CHARACTER_ASSET, "cmr_bob_0", old
        )
        decision, entry = cache.resolve("character:cm_bob", new)
        assert decision == EpisodeCacheDecision.INVALIDATED.value
        assert entry is None
        # regenerating replaces the stale entry
        cache.record_generated(
            "character:cm_bob", EpisodeArtifactKind.CHARACTER_ASSET, "cmr_bob_1", new
        )
        decision, _ = cache.resolve("character:cm_bob", new)
        assert decision == EpisodeCacheDecision.HIT.value

    def test_rejected_reuse_when_unapproved(self, tmp_path):
        cache = _cache(tmp_path)
        expected = asset_expected_hash(
            EpisodeArtifactKind.CHARACTER_ASSET, "cm_carol", "cmr_carol_1"
        )
        cache.record_generated(
            "character:cm_carol",
            EpisodeArtifactKind.CHARACTER_ASSET,
            "cmr_carol_1",
            expected,
            approved=False,
        )
        decision, entry = cache.resolve(
            "character:cm_carol", expected, approved=True
        )
        assert decision == EpisodeCacheDecision.REJECTED_REUSE.value
        assert entry is None

    def test_report_totals_four_categories(self, tmp_path):
        cache = _cache(tmp_path)
        a = asset_expected_hash(EpisodeArtifactKind.CHARACTER_ASSET, "cm_alice", "r1")
        b = asset_expected_hash(EpisodeArtifactKind.ENVIRONMENT_ASSET, "env_park", "r1")
        c = asset_expected_hash(EpisodeArtifactKind.CHARACTER_ASSET, "cm_bob", "r1")
        d = asset_expected_hash(EpisodeArtifactKind.CHARACTER_ASSET, "cm_carol", "r1")
        cache.record_generated("character:cm_alice", EpisodeArtifactKind.CHARACTER_ASSET, "r1", a)
        cache.record_generated("environment:env_park", EpisodeArtifactKind.ENVIRONMENT_ASSET, "r1", b)
        cache.record_generated(
            "character:cm_bob",
            EpisodeArtifactKind.CHARACTER_ASSET,
            "r0",
            asset_expected_hash(EpisodeArtifactKind.CHARACTER_ASSET, "cm_bob", "r0"),
        )
        cache.record_generated(
            "character:cm_carol", EpisodeArtifactKind.CHARACTER_ASSET, "r1", d, approved=False
        )
        cache.resolve("character:cm_alice", a)  # HIT
        cache.resolve("environment:env_park", b)  # HIT
        cache.resolve("environment:env_city", b)  # MISS
        cache.resolve("character:cm_bob", c)  # INVALIDATED (recorded r0, expect r1)
        cache.resolve("character:cm_carol", d, approved=True)  # REJECTED_REUSE
        report = cache.report()
        assert report.hits == 2
        assert report.misses == 1
        assert report.invalidated == 1
        assert report.rejected == 1
        assert report.decisions["character:cm_alice"] == EpisodeCacheDecision.HIT.value
        assert (
            report.decisions["character:cm_carol"]
            == EpisodeCacheDecision.REJECTED_REUSE.value
        )

    def test_persists_across_instances(self, tmp_path):
        cache = _cache(tmp_path)
        expected = asset_expected_hash(
            EpisodeArtifactKind.CHARACTER_ASSET, "cm_alice", "cmr_alice_1"
        )
        cache.record_generated(
            "character:cm_alice",
            EpisodeArtifactKind.CHARACTER_ASSET,
            "cmr_alice_1",
            expected,
        )
        cache.save()
        reloaded = EpisodeAssetCache(tmp_path / "cache")
        decision, _ = reloaded.resolve("character:cm_alice", expected)
        assert decision == EpisodeCacheDecision.HIT.value

    def test_record_reuse_unknown_key_raises(self, tmp_path):
        cache = _cache(tmp_path)
        with pytest.raises(Exception):
            cache.record_reuse("character:ghost")


# ---------------------------------------------------------------------------
# Resume planner: node + chunk level (backlog 4)
# ---------------------------------------------------------------------------
class TestEpisodeResumePlanner:
    def _node(self, node_id: str, status, input_hashes: dict) -> EpisodeNodeReceipt:
        return EpisodeNodeReceipt(
            node_id=node_id,
            kind=GoldenSceneNodeKind.SCENE,
            scene_id="scn_1",
            status=status,
            input_hashes=input_hashes,
            output_hashes={"x": "h"},
        )

    def test_node_skip_only_completed_with_identical_hashes(self):
        planner = EpisodeResumePlanner()
        inputs = {"scn_1::SCENE": {"fixture": "f1", "manifest": "m1"}}
        checkpoint = EpisodeCheckpoint(
            run_id=EpisodeRunId("r1"),
            receipts=[self._node("scn_1::SCENE", GoldenSceneNodeStatus.COMPLETED, inputs["scn_1::SCENE"])],
        )
        assert planner.plan(checkpoint, inputs)["scn_1::SCENE"] == "SKIP"
        # changed input -> RUN
        changed = {"scn_1::SCENE": {"fixture": "f2", "manifest": "m1"}}
        assert planner.plan(checkpoint, changed)["scn_1::SCENE"] == "RUN"
        # failed node -> RUN
        failed_cp = EpisodeCheckpoint(
            run_id=EpisodeRunId("r1"),
            receipts=[self._node("scn_1::SCENE", GoldenSceneNodeStatus.FAILED, inputs["scn_1::SCENE"])],
        )
        assert planner.plan(failed_cp, inputs)["scn_1::SCENE"] == "RUN"
        # cancelled node -> RUN
        cancelled_cp = EpisodeCheckpoint(
            run_id=EpisodeRunId("r1"),
            receipts=[self._node("scn_1::SCENE", GoldenSceneNodeStatus.CANCELLED, inputs["scn_1::SCENE"])],
        )
        assert planner.plan(cancelled_cp, inputs)["scn_1::SCENE"] == "RUN"

    def _chunk(self, chunk_id: str, status, input_hash: str) -> EpisodeChunkReceipt:
        return EpisodeChunkReceipt(
            chunk_id=EpisodeChunkId(chunk_id),
            shot_id="sh_1",
            scene_id="scn_1",
            status=status,
            input_hash=input_hash,
            output_hash="out",
        )

    def test_chunk_skip_enables_partial_rerender(self):
        planner = EpisodeResumePlanner()
        specs = [
            EpisodeChunkSpec(
                chunk_id=EpisodeChunkId("sh_1:chunk:0"),
                shot_id="sh_1", scene_id="scn_1",
                frame_start=1, frame_end=12, input_hash="h0",
            ),
            EpisodeChunkSpec(
                chunk_id=EpisodeChunkId("sh_1:chunk:1"),
                shot_id="sh_1", scene_id="scn_1",
                frame_start=13, frame_end=24, input_hash="h1",
            ),
            EpisodeChunkSpec(
                chunk_id=EpisodeChunkId("sh_1:chunk:2"),
                shot_id="sh_1", scene_id="scn_1",
                frame_start=25, frame_end=36, input_hash="h2",
            ),
        ]
        # Kill happened after chunk 0: chunk 0 COMPLETED, 1-2 CANCELLED.
        checkpoint = EpisodeCheckpoint(
            run_id=EpisodeRunId("r1"),
            chunks=[
                self._chunk("sh_1:chunk:0", EpisodeChunkStatus.COMPLETED, "h0"),
                self._chunk("sh_1:chunk:1", EpisodeChunkStatus.CANCELLED, "h1"),
                self._chunk("sh_1:chunk:2", EpisodeChunkStatus.CANCELLED, "h2"),
            ],
        )
        decisions = planner.plan_chunks(checkpoint, specs)
        assert decisions["sh_1:chunk:0"] == "SKIP"
        assert decisions["sh_1:chunk:1"] == "RUN"
        assert decisions["sh_1:chunk:2"] == "RUN"
        # changed chunk input hash -> re-run (never reuse stale frames)
        stale = EpisodeCheckpoint(
            run_id=EpisodeRunId("r1"),
            chunks=[self._chunk("sh_1:chunk:0", EpisodeChunkStatus.COMPLETED, "h0_old")],
        )
        assert planner.plan_chunks(stale, specs)["sh_1:chunk:0"] == "RUN"
        # no checkpoint -> everything RUNs
        assert all(
            d == "RUN" for d in planner.plan_chunks(None, specs).values()
        )


# ---------------------------------------------------------------------------
# Targeted invalidation (backlog 5)
# ---------------------------------------------------------------------------
class TestEpisodeInvalidation:
    def test_replace_shot_invalidates_only_its_downstream(self):
        fixture = _episode_fixture()
        graph = EpisodeDependencyGraph.build_from_fixture(fixture)
        known = [
            "shot:sh_1", "shot:sh_2", "shot:sh_3", "shot:sh_4", "shot:sh_5",
            "render:sh_1", "render:sh_2", "render:sh_3", "render:sh_4", "render:sh_5",
            "media:scn_1", "media:scn_2", "media:scn_3",
            "final:episode",
            "character:cm_alice", "character:cm_bob", "character:cm_carol",
            "environment:env_park", "environment:env_city",
            "camera:cam_1", "camera:cam_2",
            "audio_cue:cue_alice", "audio_cue:cue_bgm",
            "animation:ani_walk_alice",
            "scene:scn_1", "scene:scn_2", "scene:scn_3",
        ]
        plan = EpisodeInvalidationPlanner().plan(graph, ["shot:sh_1"], known)
        assert set(plan.invalidated) == {
            "render:sh_1", "media:scn_1", "final:episode",
        }
        # unrelated shots/scenes/media preserved
        assert "render:sh_2" in plan.preserved
        assert "media:scn_2" in plan.preserved
        assert "shot:sh_2" in plan.preserved

    def test_replace_camera_invalidates_shots_using_it_only(self):
        fixture = _episode_fixture()
        graph = EpisodeDependencyGraph.build_from_fixture(fixture)
        known = [
            "shot:sh_1", "shot:sh_2", "render:sh_1", "render:sh_2",
            "media:scn_1", "final:episode",
            "camera:cam_1", "camera:cam_2",
        ]
        plan = EpisodeInvalidationPlanner().plan(graph, ["camera:cam_1"], known)
        # cam_1 is used by sh_1 only -> sh_1 + render + media + final
        assert set(plan.invalidated) == {
            "shot:sh_1", "render:sh_1", "media:scn_1", "final:episode",
        }
        assert "shot:sh_2" in plan.preserved
        assert "render:sh_2" in plan.preserved

    def test_replace_audio_cue_invalidates_media_not_unrelated_renders(self):
        fixture = _episode_fixture()
        graph = EpisodeDependencyGraph.build_from_fixture(fixture)
        known = [
            "shot:sh_1", "shot:sh_2", "render:sh_1", "render:sh_2",
            "media:scn_1", "final:episode", "audio_cue:cue_alice",
        ]
        plan = EpisodeInvalidationPlanner().plan(graph, ["audio_cue:cue_alice"], known)
        # cue_alice feeds sh_1 (audio) + media:scn_1 (mix) + final
        assert set(plan.invalidated) == {
            "shot:sh_1", "render:sh_1", "media:scn_1", "final:episode",
        }
        assert "render:sh_2" in plan.preserved

    def test_replace_environment_invalidates_its_scenes_only(self):
        fixture = _episode_fixture()
        graph = EpisodeDependencyGraph.build_from_fixture(fixture)
        known = [
            "scene:scn_1", "scene:scn_2", "scene:scn_3",
            "shot:sh_1", "shot:sh_3", "shot:sh_5",
            "render:sh_1", "render:sh_3", "render:sh_5",
            "media:scn_1", "media:scn_2", "media:scn_3",
            "final:episode", "environment:env_park",
        ]
        plan = EpisodeInvalidationPlanner().plan(graph, ["environment:env_park"], known)
        # env_park feeds scn_1 + scn_3 (not scn_2)
        assert "scene:scn_2" in plan.preserved
        assert "shot:sh_3" in plan.preserved
        assert "render:sh_3" in plan.preserved
        assert "media:scn_2" in plan.preserved
        assert "scene:scn_1" in plan.invalidated
        assert "scene:scn_3" in plan.invalidated

    def test_replace_character_invalidates_all_shots_using_it(self):
        fixture = _episode_fixture()
        graph = EpisodeDependencyGraph.build_from_fixture(fixture)
        known = [
            "shot:sh_1", "shot:sh_2", "shot:sh_3", "shot:sh_4", "shot:sh_5",
            "render:sh_1", "render:sh_5",
            "media:scn_1", "media:scn_3", "final:episode",
            "character:cm_alice",
        ]
        plan = EpisodeInvalidationPlanner().plan(graph, ["character:cm_alice"], known)
        # cm_alice appears in sh_1, sh_2(no), sh_5 -> sh_1 + sh_5 chains
        assert "shot:sh_1" in plan.invalidated
        assert "shot:sh_5" in plan.invalidated
        assert "render:sh_1" in plan.invalidated
        assert "render:sh_5" in plan.invalidated
        assert "shot:sh_3" in plan.preserved
        assert "shot:sh_4" in plan.preserved


# ---------------------------------------------------------------------------
# Branch scheduler: critical path + idle (backlog 3)
# ---------------------------------------------------------------------------
class TestEpisodeBranchScheduler:
    def test_parallel_branches_critical_path_and_idle(self):
        fixture = _episode_fixture()
        specs = build_episode_branch_specs(fixture)
        durations = {
            "asset_prep": 30.0,
            "audio_prep": 10.0,
            "compile:scn_1": 5.0,
            "render:scn_1": 20.0,
            "review:scn_1": 3.0,
            "compile:scn_2": 5.0,
            "render:scn_2": 20.0,
            "review:scn_2": 3.0,
            "compile:scn_3": 5.0,
            "render:scn_3": 20.0,
            "review:scn_3": 3.0,
            "post": 10.0,
        }
        receipt = EpisodeBranchScheduler().schedule(specs, durations)
        # asset_prep is the slowest root: critical path =
        #   30 (asset) + 5 + 20 + 3 (scn_1 chain) + 10 (post) = 68
        assert receipt.critical_path_seconds == pytest.approx(68.0)
        assert receipt.parallel_span_seconds == pytest.approx(68.0)
        # audio_prep finishes at 10, compile starts at 30 -> idle 20
        audio = receipt.timing("audio_prep")
        assert audio.idle_seconds == pytest.approx(20.0)
        compile_1 = receipt.timing("compile:scn_1")
        assert compile_1.start_seconds == pytest.approx(30.0)
        assert compile_1.idle_seconds == pytest.approx(0.0)
        assert receipt.idle_total_seconds == pytest.approx(20.0)
        # critical path trace: asset_prep, compile, render, review, post
        critical_ids = {t.branch_id for t in receipt.branches if t.critical}
        assert "asset_prep" in critical_ids
        assert "audio_prep" not in critical_ids
        assert "post" in critical_ids

    def test_slow_audio_branch_becomes_critical(self):
        fixture = _episode_fixture()
        specs = build_episode_branch_specs(fixture)
        durations = {
            "asset_prep": 5.0,
            "audio_prep": 100.0,
            "compile:scn_1": 1.0,
            "render:scn_1": 1.0,
            "review:scn_1": 1.0,
            "compile:scn_2": 1.0,
            "render:scn_2": 1.0,
            "review:scn_2": 1.0,
            "compile:scn_3": 1.0,
            "render:scn_3": 1.0,
            "review:scn_3": 1.0,
            "post": 1.0,
        }
        receipt = EpisodeBranchScheduler().schedule(specs, durations)
        assert receipt.critical_path_seconds == pytest.approx(104.0)
        critical_ids = {t.branch_id for t in receipt.branches if t.critical}
        assert "audio_prep" in critical_ids
        assert "asset_prep" not in critical_ids

    def test_cycle_fails_closed(self):
        specs = [
            EpisodeBranchSpec(branch_id="a", kind=EpisodeBranchKind.ASSET_PREP, depends_on=["b"]),
            EpisodeBranchSpec(branch_id="b", kind=EpisodeBranchKind.AUDIO_PREP, depends_on=["a"]),
        ]
        with pytest.raises(EpisodeDependencyCycleError):
            EpisodeBranchScheduler().schedule(specs, {"a": 1.0, "b": 1.0})

    def test_unknown_dependency_fails_closed(self):
        specs = [
            EpisodeBranchSpec(
                branch_id="a", kind=EpisodeBranchKind.ASSET_PREP, depends_on=["ghost"]
            )
        ]
        with pytest.raises(EpisodeDependencyCycleError):
            EpisodeBranchScheduler().schedule(specs, {"a": 1.0})


# ---------------------------------------------------------------------------
# Episode ordering (backlog 2)
# ---------------------------------------------------------------------------
class TestEpisodeOrdering:
    def test_ordering_stable_and_deterministic(self):
        fixture = _episode_fixture()
        ordering_a = EpisodeOrderingReceipt.from_fixture(fixture)
        ordering_b = EpisodeOrderingReceipt.from_fixture(fixture)
        assert ordering_a.ordering_hash() == ordering_b.ordering_hash()
        assert ordering_a.scene_order == ["scn_1", "scn_2", "scn_3"]
        assert ordering_a.shot_order == [
            "sh_1", "sh_2", "sh_3", "sh_4", "sh_5",
        ]
        assert ordering_a.matches(ordering_a.ordering_hash())

    def test_ordering_changes_when_scene_order_changes(self):
        a = _episode_fixture()
        b = _episode_fixture(
            scenes=[
                s.model_copy(update={"order_index": 2 - s.order_index})
                for s in _episode_fixture().scenes
            ]
        )
        ordering_a = EpisodeOrderingReceipt.from_fixture(a)
        ordering_b = EpisodeOrderingReceipt.from_fixture(b)
        assert ordering_a.ordering_hash() != ordering_b.ordering_hash()
        assert ordering_b.scene_order == ["scn_3", "scn_2", "scn_1"]


# ---------------------------------------------------------------------------
# Fixture validation
# ---------------------------------------------------------------------------
class TestEpisodeFixtureValidation:
    def test_empty_scenes_rejected(self):
        fixture = _episode_fixture(scenes=[])
        with pytest.raises(EpisodeValidationError):
            fixture.validate_fixture()

    def test_shot_unknown_scene_rejected(self):
        fixture = _episode_fixture(
            shots=[
                s.model_copy(update={"scene_id": "scn_ghost"})
                if str(s.shot_id) == "sh_1"
                else s
                for s in _episode_fixture().shots
            ]
        )
        with pytest.raises(EpisodeValidationError):
            fixture.validate_fixture()

    def test_scene_unknown_shot_rejected(self):
        fixture = _episode_fixture(
            scenes=[
                s.model_copy(update={"shot_ids": ["sh_ghost"]})
                if str(s.scene_id) == "scn_1"
                else s
                for s in _episode_fixture().scenes
            ]
        )
        with pytest.raises(EpisodeValidationError):
            fixture.validate_fixture()

    def test_duplicate_scene_order_rejected(self):
        fixture = _episode_fixture(
            scenes=[
                s.model_copy(update={"order_index": 0})
                for s in _episode_fixture().scenes
            ]
        )
        with pytest.raises(EpisodeValidationError):
            fixture.validate_fixture()

    def test_inverted_shot_frame_range_rejected(self):
        fixture = _episode_fixture(
            shots=[
                s.model_copy(update={"frame_start": 24, "frame_end": 1})
                if str(s.shot_id) == "sh_1"
                else s
                for s in _episode_fixture().shots
            ]
        )
        with pytest.raises(EpisodeValidationError):
            fixture.validate_fixture()

    def test_fixture_content_hash_deterministic(self):
        a = _episode_fixture()
        b = _episode_fixture()
        assert a.content_hash() == b.content_hash()
        changed = _episode_fixture(title="Other Episode")
        assert a.content_hash() != changed.content_hash()


# ---------------------------------------------------------------------------
# Verdict policy (fail-closed)
# ---------------------------------------------------------------------------
class TestEpisodeVerdictPolicy:
    def _ok_receipt(self, node_id: str = "scn_1::SCENE") -> EpisodeNodeReceipt:
        return EpisodeNodeReceipt(
            node_id=node_id,
            kind=GoldenSceneNodeKind.SCENE,
            scene_id="scn_1",
            status=GoldenSceneNodeStatus.COMPLETED,
            input_hashes={},
            output_hashes={"x": "h"},
        )

    def _ok_chunk(self) -> EpisodeChunkReceipt:
        return EpisodeChunkReceipt(
            chunk_id=EpisodeChunkId("sh_1:chunk:0"),
            shot_id="sh_1",
            scene_id="scn_1",
            status=EpisodeChunkStatus.COMPLETED,
            input_hash="h",
        )

    def _identity_ok(self) -> IdentityContinuityReceipt:
        return IdentityContinuityReceipt(
            character_identity_ok=True,
            voice_identity_ok=True,
            continuity_ok=True,
        )

    def _verification_ok(self) -> TechnicalVerificationReceipt:
        return TechnicalVerificationReceipt(
            frames_ok=True, audio_ok=True, final_mp4_ok=True
        )

    def test_pass_when_everything_ok(self):
        policy = EpisodeVerdictPolicy()
        verdict = policy.decide(
            [self._ok_receipt()],
            [self._ok_chunk()],
            True,
            self._identity_ok(),
            self._verification_ok(),
        )
        assert verdict == EpisodeVerdict.PASS

    def test_failed_node_rejects(self):
        policy = EpisodeVerdictPolicy()
        verdict = policy.decide(
            [self._ok_receipt().model_copy(
                update={"status": GoldenSceneNodeStatus.FAILED}
            )],
            [self._ok_chunk()],
            True,
            self._identity_ok(),
            self._verification_ok(),
        )
        assert verdict == EpisodeVerdict.REJECT

    def test_cancelled_chunk_rejects(self):
        policy = EpisodeVerdictPolicy()
        verdict = policy.decide(
            [self._ok_receipt()],
            [self._ok_chunk().model_copy(update={"status": EpisodeChunkStatus.CANCELLED})],
            True,
            self._identity_ok(),
            self._verification_ok(),
        )
        assert verdict == EpisodeVerdict.REJECT

    def test_ordering_mismatch_rejects(self):
        policy = EpisodeVerdictPolicy()
        verdict = policy.decide(
            [self._ok_receipt()],
            [self._ok_chunk()],
            False,
            self._identity_ok(),
            self._verification_ok(),
        )
        assert verdict == EpisodeVerdict.REJECT

    def test_identity_failure_rejects(self):
        policy = EpisodeVerdictPolicy()
        verdict = policy.decide(
            [self._ok_receipt()],
            [self._ok_chunk()],
            True,
            IdentityContinuityReceipt(
                character_identity_ok=False,
                voice_identity_ok=False,
                continuity_ok=False,
                blocking_issues=["unapproved master"],
            ),
            self._verification_ok(),
        )
        assert verdict == EpisodeVerdict.REJECT

    def test_verification_failure_rejects(self):
        policy = EpisodeVerdictPolicy()
        verdict = policy.decide(
            [self._ok_receipt()],
            [self._ok_chunk()],
            True,
            self._identity_ok(),
            TechnicalVerificationReceipt(frames_ok=False, audio_ok=False, final_mp4_ok=False),
        )
        assert verdict == EpisodeVerdict.REJECT

    def test_unrepaired_blocking_finding_rejects(self):
        policy = EpisodeVerdictPolicy()
        receipt = self._ok_receipt().model_copy(
            update={
                "findings": [{"code": "CAMERA_BLOCKING", "blocking": True}],
            }
        )
        verdict = policy.decide(
            [receipt],
            [self._ok_chunk()],
            True,
            self._identity_ok(),
            self._verification_ok(),
        )
        assert verdict == EpisodeVerdict.REJECT

    def test_repaired_blocking_finding_passes(self):
        from windagent_core.domain.video_production.golden_scene import RepairEntry

        policy = EpisodeVerdictPolicy()
        receipt = self._ok_receipt().model_copy(
            update={
                "findings": [{"code": "CAMERA_BLOCKING", "blocking": True}],
                "repairs": [
                    RepairEntry(
                        repair_id="rp_1",
                        node_kind=GoldenSceneNodeKind.SCENE,
                        finding_code="CAMERA_BLOCKING",
                        outcome="REPAIRED",
                    )
                ],
            }
        )
        verdict = policy.decide(
            [receipt],
            [self._ok_chunk()],
            True,
            self._identity_ok(),
            self._verification_ok(),
        )
        assert verdict == EpisodeVerdict.PASS
