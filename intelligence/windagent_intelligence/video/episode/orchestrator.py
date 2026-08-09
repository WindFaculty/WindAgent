"""
Multi-Scene Episode Orchestrator (VP3D Phase 26, Stage M).

Runs the 2-3 minute episode production (stage_m.md §4): three+ scenes, five+
shots, two to four characters, multiple environments, on top of the Phase 25
golden-scene step kernels.

Backlog guarantees:

1. asset reuse — the ASSETS branch resolves every character/environment
   through the EpisodeAssetCache (HIT -> reuse, MISS/INVALIDATED/REJECTED ->
   generate) — nothing is regenerated that the cache already holds;
2. continuity + stable ordering — scenes run in fixture order, the FINAL
   node writes the episode media manifest in scene order and a mismatch is a
   blocking ORDERING_MISMATCH finding (verdict REJECT);
3. parallel branches — ASSET_PREP and AUDIO_PREP run concurrently; real
   branch durations feed the EpisodeBranchScheduler which reports critical
   path and idle time;
4. kill/resume at chunk granularity — the RENDER node renders frame chunks;
   after a kill, completed chunks with identical input hashes are SKIPPED
   and only missing/failed chunks re-render (partial rerender, no
   duplicate);
5. targeted invalidation — invalidation_requests (changed shot/camera/audio
   cue refs) are planned through the EpisodeDependencyGraph so only the
   correct downstream artifacts are invalidated;
6. cache report — hits/misses/invalidated/rejected totals on the report.

Architecture: this module is intelligence-side and NEVER imports
tools/providers. The render / review / ffmpeg / audio-synthesis /
asset-generation legs are injected via protocols — the composition root
(evidence producer) wires the real Blender adapter + technical review +
ffmpeg machinery, tests wire deterministic fakes.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from windagent_core.domain.video_production.episode import (
    EpisodeArtifactKind,
    EpisodeArtifactRecord,
    EpisodeBranchScheduler,
    EpisodeCheckpoint,
    EpisodeChunkReceipt,
    EpisodeChunkSpec,
    EpisodeChunkStatus,
    EpisodeDependencyGraph,
    EpisodeFixture,
    EpisodeInvalidationPlanner,
    EpisodeNodeReceipt,
    EpisodeOrderingReceipt,
    EpisodeProductionReport,
    EpisodeResumePlanner,
    EpisodeRunManifest,
    EpisodeSceneSpec,
    EpisodeVerdict,
    EpisodeVerdictPolicy,
    build_episode_branch_specs,
)
from windagent_core.domain.video_production.enums import (
    GoldenSceneNodeKind,
    GoldenSceneNodeStatus,
)
from windagent_core.domain.video_production.errors import (
    EpisodeResumeMismatchError,
    EpisodeValidationError,
)
from windagent_core.domain.video_production.golden_scene import (
    GoldenSceneFixture,
    GoldenSceneRunManifest,
    RepairEntry,
    compute_content_hash,
)
from windagent_core.domain.video_production.ids import (
    EpisodeArtifactId,
    EpisodeChunkId,
    EpisodeRunId,
)
from windagent_intelligence.video.episode.cache import (
    EpisodeAssetCache,
    asset_expected_hash,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Leg protocols (composition root injects real tools implementations)
# ---------------------------------------------------------------------------
@runtime_checkable
class EpisodeRenderLeg(Protocol):
    """Render leg: renders ONE frame chunk of one scene."""

    async def render_chunk(
        self,
        *,
        chunk: EpisodeChunkSpec,
        scene_fixture: GoldenSceneFixture,
        workspace: Path,
    ) -> Dict[str, Any]:
        """Render the chunk's frames; return output_hashes + metadata."""
        ...


@runtime_checkable
class EpisodeReviewRepairLeg(Protocol):
    """Review/repair leg: deterministic review of one rendered scene."""

    async def review_scene(
        self,
        *,
        scene: EpisodeSceneSpec,
        scene_fixture: GoldenSceneFixture,
        workspace: Path,
    ) -> Dict[str, Any]:
        """Review the scene artifacts; return findings + repairs."""
        ...


@runtime_checkable
class EpisodeFfmpegLeg(Protocol):
    """FFmpeg leg: assemble one scene's frames + audio into a scene MP4."""

    async def assemble_scene(
        self,
        *,
        scene: EpisodeSceneSpec,
        scene_fixture: GoldenSceneFixture,
        workspace: Path,
    ) -> Dict[str, Any]:
        """Assemble the scene MP4; return scene_media_path + ffprobe."""
        ...


@runtime_checkable
class EpisodeAudioSynthesisLeg(Protocol):
    """Audio leg: synthesize one scene's dialogue assets (parallel branch)."""

    async def synthesize(
        self,
        *,
        scene: EpisodeSceneSpec,
        scene_fixture: GoldenSceneFixture,
        workspace: Path,
    ) -> Dict[str, Any]:
        """Synthesize the scene's audio; return output_hashes + metadata."""
        ...


@runtime_checkable
class EpisodeAssetGeneratorLeg(Protocol):
    """Asset generator: generate ONE asset that the cache did not hold."""

    async def generate(
        self,
        *,
        cache_key: str,
        kind: EpisodeArtifactKind,
        revision: str,
        scene_fixture: GoldenSceneFixture,
        workspace: Path,
    ) -> Dict[str, Any]:
        """Generate the asset; return {'content_hash': ..., 'metadata': {...}}."""
        ...


# ---------------------------------------------------------------------------
# Step adapters + runners
# ---------------------------------------------------------------------------
class _LegStepAdapter:
    """Adapts a leg callable to the generic node-runner signature."""

    def __init__(self, leg: Callable[..., Any], **kwargs: Any) -> None:
        self._leg = leg
        self._kwargs = kwargs

    async def run(
        self,
        *,
        node: EpisodeNodeReceipt,
        fixture: EpisodeFixture,
        manifest: EpisodeRunManifest,
        workspace: Path,
        prior: Dict[str, EpisodeNodeReceipt],
        **extra: Any,
    ) -> Dict[str, Any]:
        return await self._leg(
            workspace=workspace, **self._kwargs, **extra
        )


class _CachedAssetsStep:
    """ASSETS branch: cache-first asset resolution (backlog 1 + 6).

    Every character/environment asset is resolved through the cache. HIT
    reuses the recorded entry (no regeneration); MISS / INVALIDATED /
    REJECTED_REUSE generate through the injected generator leg and the
    result is recorded back. The cache report therefore distinguishes the
    four decisions per asset.
    """

    def __init__(
        self,
        cache: EpisodeAssetCache,
        generator: EpisodeAssetGeneratorLeg,
    ) -> None:
        self._cache = cache
        self._generator = generator

    async def run(
        self,
        *,
        node: EpisodeNodeReceipt,
        fixture: EpisodeFixture,
        manifest: EpisodeRunManifest,
        workspace: Path,
        prior: Dict[str, EpisodeNodeReceipt],
        **extra: Any,
    ) -> Dict[str, Any]:
        artifacts: List[Dict[str, Any]] = []

        async def _resolve(
            kind: EpisodeArtifactKind,
            ref_key: str,
            asset_id: str,
            revision: str,
            approved: bool,
        ) -> Dict[str, Any]:
            expected = asset_expected_hash(kind, asset_id, revision)
            decision, _ = self._cache.resolve(
                ref_key, expected, approved=approved
            )
            if decision == "HIT":
                self._cache.record_reuse(ref_key)
                return {
                    "ref_key": ref_key,
                    "kind": kind.value,
                    "revision": revision,
                    "content_hash": expected,
                    "source": "REUSED",
                }
            # The generator does the real work; the cache entry pins the
            # REVISION contract (the expected deterministic hash), so a later
            # run resolves HIT for the same revision — never INVALIDATED
            # against itself.
            await self._generator.generate(
                cache_key=ref_key,
                kind=kind,
                revision=revision,
                scene_fixture=None,
                workspace=workspace,
            )
            self._cache.record_generated(
                ref_key, kind, revision, expected, approved=approved
            )
            return {
                "ref_key": ref_key,
                "kind": kind.value,
                "revision": revision,
                "content_hash": expected,
                "source": "GENERATED",
            }

        for entry in fixture.characters:
            master_id = str(entry.get("master_id") or entry.get("id") or "")
            revision = str(
                entry.get("approved_revision_id")
                or entry.get("revision_id")
                or "rev_1"
            )
            if not master_id:
                continue
            artifacts.append(
                await _resolve(
                    EpisodeArtifactKind.CHARACTER_ASSET,
                    f"character:{master_id}",
                    master_id,
                    revision,
                    bool(entry.get("approved", True)),
                )
            )
        for entry in fixture.environments:
            env_id = str(entry.get("id") or entry.get("environment_id") or "")
            revision = str(entry.get("revision_id") or "rev_1")
            if not env_id:
                continue
            artifacts.append(
                await _resolve(
                    EpisodeArtifactKind.ENVIRONMENT_ASSET,
                    f"environment:{env_id}",
                    env_id,
                    revision,
                    bool(entry.get("approved", True)),
                )
            )

        manifest_hash = compute_content_hash({"artifacts": artifacts})
        out = workspace / "assets"
        out.mkdir(parents=True, exist_ok=True)
        (out / "asset_resolution.json").write_text(
            json.dumps(
                {"artifacts": artifacts, "decisions": self._cache.report().decisions},
                ensure_ascii=False, indent=2, sort_keys=True,
            ),
            encoding="utf-8",
        )
        return {
            "output_hashes": {
                "assets": manifest_hash,
                "asset_resolution_file": _sha256_bytes(
                    (out / "asset_resolution.json").read_bytes()
                ),
            },
            "metadata": {
                "decisions": dict(self._cache.report().decisions),
                "artifact_count": len(artifacts),
            },
            "artifacts": artifacts,
        }


class _AudioPrepRunner:
    """AUDIO_PREP branch: per-scene audio synthesis (parallel with assets)."""

    def __init__(self, leg: EpisodeAudioSynthesisLeg) -> None:
        self._leg = leg

    async def run(
        self,
        *,
        node: EpisodeNodeReceipt,
        fixture: EpisodeFixture,
        manifest: EpisodeRunManifest,
        workspace: Path,
        prior: Dict[str, EpisodeNodeReceipt],
        **extra: Any,
    ) -> Dict[str, Any]:
        scenes = fixture.ordered_scenes()
        outcomes: List[Dict[str, Any]] = []
        for scene in scenes:
            scene_fixture = _scene_fixture(fixture, scene)
            outcome = await self._leg.synthesize(
                scene=scene, scene_fixture=scene_fixture, workspace=workspace
            )
            outcomes.append(outcome)
        payload = {"scenes": [str(s.scene_id) for s in scenes], "count": len(outcomes)}
        return {
            "output_hashes": {"audio_prep": compute_content_hash(payload)},
            "metadata": {"scene_count": len(scenes)},
        }


class _ChunkedRenderRunner:
    """RENDER node: chunked rendering with kill/resume (backlog 4).

    Chunks are the resume unit: a COMPLETED chunk with an identical input
    hash is SKIPPED on restart; CANCELLED/FAILED chunks re-render. Chunk
    receipts are pushed into the orchestrator state (and checkpoint) after
    EVERY chunk so a kill mid-render never loses completed work.
    """

    def __init__(
        self,
        leg: EpisodeRenderLeg,
        fixture: EpisodeFixture,
        scene: EpisodeSceneSpec,
        scene_fixture: GoldenSceneFixture,
        planner: EpisodeResumePlanner,
        record_chunks: Callable[[List[EpisodeChunkReceipt]], None],
        current_chunks: Callable[[], Dict[str, EpisodeChunkReceipt]],
    ) -> None:
        self._leg = leg
        self._fixture = fixture
        self._scene = scene
        self._scene_fixture = scene_fixture
        self._planner = planner
        self._record_chunks = record_chunks
        self._current_chunks = current_chunks

    def chunk_specs(self) -> List[EpisodeChunkSpec]:
        chunk_size = int(self._fixture.render_profile.get("chunk_frames", 8))
        specs: List[EpisodeChunkSpec] = []
        scene_start = self._scene.frame_start
        for shot in self._fixture.shots:
            if str(shot.scene_id) != str(self._scene.scene_id):
                continue
            frame = shot.frame_start
            index = 0
            while frame <= shot.frame_end:
                end = min(frame + chunk_size - 1, shot.frame_end)
                chunk_id = EpisodeChunkId(f"{shot.shot_id}:chunk:{index}")
                scene_frame_start = (
                    shot.frame_start - scene_start + 1 + (frame - shot.frame_start)
                )
                input_hash = compute_content_hash(
                    {
                        "scene_fixture": self._scene_fixture.content_hash(),
                        "shot": str(shot.shot_id),
                        "frame_start": frame,
                        "frame_end": end,
                        "render_profile": self._fixture.render_profile,
                    }
                )
                specs.append(
                    EpisodeChunkSpec(
                        chunk_id=chunk_id,
                        shot_id=str(shot.shot_id),
                        scene_id=str(self._scene.scene_id),
                        frame_start=frame,
                        frame_end=end,
                        scene_frame_start=scene_frame_start,
                        input_hash=input_hash,
                    )
                )
                frame = end + 1
                index += 1
        return specs

    async def run(
        self,
        *,
        node: EpisodeNodeReceipt,
        fixture: EpisodeFixture,
        manifest: EpisodeRunManifest,
        workspace: Path,
        prior: Dict[str, EpisodeNodeReceipt],
        cancel_token: Callable[[], bool],
    ) -> Dict[str, Any]:
        specs = self.chunk_specs()
        current = self._current_chunks()
        decisions = self._planner.plan_chunks(
            EpisodeCheckpoint(run_id=EpisodeRunId("resume"), chunks=list(current.values()))
            if current
            else None,
            specs,
        )
        chunk_receipts: List[EpisodeChunkReceipt] = []
        cancelled = False
        failed = False
        for spec in specs:
            chunk_id = str(spec.chunk_id)
            if cancel_token():
                cancelled = True
                chunk_receipts.append(
                    EpisodeChunkReceipt(
                        chunk_id=spec.chunk_id,
                        shot_id=spec.shot_id,
                        scene_id=spec.scene_id,
                        status=EpisodeChunkStatus.CANCELLED,
                        attempt=1,
                        input_hash=spec.input_hash,
                        started_at=utc_now_iso(),
                        finished_at=utc_now_iso(),
                    )
                )
                continue
            if decisions.get(chunk_id) == "SKIP":
                prior_chunk = self._current_chunks().get(chunk_id)
                chunk_receipts.append(
                    prior_chunk.model_copy(
                        update={"status": EpisodeChunkStatus.SKIPPED}
                    )
                    if prior_chunk is not None
                    else EpisodeChunkReceipt(
                        chunk_id=spec.chunk_id,
                        shot_id=spec.shot_id,
                        scene_id=spec.scene_id,
                        status=EpisodeChunkStatus.SKIPPED,
                        attempt=1,
                        input_hash=spec.input_hash,
                    )
                )
                self._record_chunks(chunk_receipts)
                continue
            try:
                outcome = await self._leg.render_chunk(
                    chunk=spec, scene_fixture=self._scene_fixture, workspace=workspace
                )
                output_hash = next(iter(outcome.get("output_hashes", {}).values()), "")
                chunk_receipts.append(
                    EpisodeChunkReceipt(
                        chunk_id=spec.chunk_id,
                        shot_id=spec.shot_id,
                        scene_id=spec.scene_id,
                        status=EpisodeChunkStatus.COMPLETED,
                        attempt=1,
                        input_hash=spec.input_hash,
                        output_hash=output_hash,
                        started_at=utc_now_iso(),
                        finished_at=utc_now_iso(),
                    )
                )
            except Exception:
                failed = True
                chunk_receipts.append(
                    EpisodeChunkReceipt(
                        chunk_id=spec.chunk_id,
                        shot_id=spec.shot_id,
                        scene_id=spec.scene_id,
                        status=EpisodeChunkStatus.FAILED,
                        attempt=1,
                        input_hash=spec.input_hash,
                        started_at=utc_now_iso(),
                        finished_at=utc_now_iso(),
                    )
                )
                break
            # Persist after EVERY chunk: a kill mid-render never loses work.
            self._record_chunks(chunk_receipts)

        if failed:
            status = GoldenSceneNodeStatus.FAILED
            error = "render chunk failed"
        elif cancelled:
            status = GoldenSceneNodeStatus.CANCELLED
            error = "cancelled between render chunks"
        else:
            status = GoldenSceneNodeStatus.COMPLETED
            error = ""
        rendered = [c for c in chunk_receipts if c.status == EpisodeChunkStatus.COMPLETED]
        skipped = [c for c in chunk_receipts if c.status == EpisodeChunkStatus.SKIPPED]
        return {
            "output_hashes": {
                "chunks": compute_content_hash(
                    {"chunk_ids": [str(c.chunk_id) for c in chunk_receipts]}
                )
            },
            "status": status,
            "error": error,
            "metadata": {
                "chunk_count": len(chunk_receipts),
                "chunk_ids": [str(c.chunk_id) for c in chunk_receipts],
                "rendered_chunk_ids": [str(c.chunk_id) for c in rendered],
                "skipped_chunk_ids": [str(c.chunk_id) for c in skipped],
            },
        }


class _EpisodeFinalRunner:
    """FINAL node: episode media manifest in scene order (backlog 2)."""

    async def run(
        self,
        *,
        node: EpisodeNodeReceipt,
        fixture: EpisodeFixture,
        manifest: EpisodeRunManifest,
        workspace: Path,
        prior: Dict[str, EpisodeNodeReceipt],
        **extra: Any,
    ) -> Dict[str, Any]:
        scenes = fixture.ordered_scenes()
        media: List[Dict[str, Any]] = []
        findings: List[Dict[str, Any]] = []
        for scene in scenes:
            ffmpeg_receipt = prior.get(f"{scene.scene_id}::FFMPEG")
            path = ""
            sha = ""
            if ffmpeg_receipt is not None:
                path = str(ffmpeg_receipt.metadata.get("scene_media_path", ""))
                sha = str(ffmpeg_receipt.metadata.get("scene_media_sha256", ""))
            media.append(
                {
                    "scene_id": str(scene.scene_id),
                    "media_path": path,
                    "sha256": sha,
                }
            )
        media_order = [m["scene_id"] for m in media]
        expected_order = [str(s.scene_id) for s in scenes]
        ordered = media_order == expected_order
        if not ordered:
            findings.append(
                {
                    "code": "ORDERING_MISMATCH",
                    "blocking": True,
                    "message": (
                        f"episode media order {media_order} != fixture order "
                        f"{expected_order}"
                    ),
                }
            )
        payload = {
            "episode_media": media,
            "ordered": ordered,
            "scene_order": expected_order,
        }
        out = workspace / "final"
        out.mkdir(parents=True, exist_ok=True)
        (out / "episode_media_manifest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return {
            "output_hashes": {
                "episode_media": compute_content_hash(payload),
                "episode_media_manifest_file": _sha256_bytes(
                    (out / "episode_media_manifest.json").read_bytes()
                ),
            },
            "findings": findings,
            "metadata": {"media_scene_order": media_order, "ordered": ordered},
        }


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
def _scene_fixture(fixture: EpisodeFixture, scene: EpisodeSceneSpec) -> GoldenSceneFixture:
    """Build the per-scene golden-scene fixture (REUSES episode assets)."""
    characters = [
        c
        for c in fixture.characters
        if str(c.get("master_id") or c.get("id") or "") in scene.character_ids
    ]
    environment = {}
    for env in fixture.environments:
        if str(env.get("id") or env.get("environment_id") or "") == scene.environment_ref:
            environment = env
            break
    shot_ids = {str(s) for s in scene.shot_ids}
    camera_refs = {
        str(shot.camera_intent_ref)
        for shot in fixture.shots
        if str(shot.shot_id) in shot_ids and shot.camera_intent_ref
    }
    anim_refs = {
        str(ref)
        for shot in fixture.shots
        if str(shot.shot_id) in shot_ids
        for ref in shot.animation_intent_refs
    }
    cue_refs = {
        str(ref)
        for shot in fixture.shots
        if str(shot.shot_id) in shot_ids
        for ref in shot.audio_cue_refs
    }
    dialogue_lines = [
        line
        for line in fixture.dialogue_lines
        if str(line.get("scene_id", "")) == str(scene.scene_id)
        or str(line.get("character_id", "")) in scene.character_ids
    ]
    metadata = dict(fixture.metadata)
    ir_documents = metadata.get("ir_documents")
    if isinstance(ir_documents, dict) and str(scene.scene_id) in ir_documents:
        metadata["ir_document"] = ir_documents[str(scene.scene_id)]
    return GoldenSceneFixture(
        fixture_id=f"{fixture.fixture_id}:{scene.scene_id}",
        title=fixture.title,
        # The facial alignment window is the EPISODE timeline (2-3 minutes),
        # not the DRAFT render window: dialogue phonemes must fit the
        # episode's planned duration, while rendering stays chunk-bounded.
        planned_duration_seconds=fixture.planned_duration_seconds,
        fps=fixture.fps,
        screenplay_text=fixture.screenplay_text,
        characters=characters,
        environment=environment,
        dialogue_lines=dialogue_lines,
        animation_intents=[
            intent
            for intent in fixture.animation_intents
            if str(intent.get("intent_id", "")) in anim_refs
            or str(intent.get("animation_intent_id", "")) in anim_refs
        ],
        camera_intents=[
            intent
            for intent in fixture.camera_intents
            if str(intent.get("intent_id", "")) in camera_refs
            or str(intent.get("camera_intent_id", "")) in camera_refs
        ],
        lighting_intents=[
            intent
            for intent in fixture.lighting_intents
            if str(intent.get("scene_id", "")) == str(scene.scene_id)
        ],
        audio_cues=[
            cue
            for cue in fixture.audio_cues
            if str(cue.get("cue_id", "")) in cue_refs
            or str(cue.get("label", "")) in cue_refs
        ],
        render_profile=dict(fixture.render_profile),
        approvals=list(fixture.approvals),
        metadata=metadata,
    )


def _scene_manifest(
    manifest: EpisodeRunManifest, scene_fixture: GoldenSceneFixture
) -> GoldenSceneRunManifest:
    from windagent_core.domain.video_production.ids import GoldenSceneRunId

    return GoldenSceneRunManifest(
        run_id=GoldenSceneRunId(str(manifest.run_id)),
        project_id=manifest.project_id,
        revision_id=manifest.revision_id,
        fixture_hash=scene_fixture.content_hash(),
        candidate_sha=manifest.candidate_sha,
        hardware_baseline=manifest.hardware_baseline,
        tool_versions=manifest.tool_versions,
        budgets=manifest.budgets,
        pinned_seeds=manifest.pinned_seeds,
    )


def _dummy_node(node_id: str, kind: GoldenSceneNodeKind, scene_id: str) -> EpisodeNodeReceipt:
    return EpisodeNodeReceipt(
        node_id=node_id,
        kind=kind,
        scene_id=scene_id,
        status=GoldenSceneNodeStatus.RUNNING,
        attempt=1,
        input_hashes={},
    )


def _chunk_input_signature(fixture: EpisodeFixture, scene: EpisodeSceneSpec) -> str:
    chunk_size = int(fixture.render_profile.get("chunk_frames", 8))
    parts = []
    for shot in fixture.shots:
        if str(shot.scene_id) != str(scene.scene_id):
            continue
        frame = shot.frame_start
        while frame <= shot.frame_end:
            end = min(frame + chunk_size - 1, shot.frame_end)
            parts.append(f"{shot.shot_id}:{frame}-{end}")
            frame = end + 1
    return compute_content_hash(
        {
            "scene_fixture": _scene_fixture(fixture, scene).content_hash(),
            "chunks": parts,
            "render_profile": fixture.render_profile,
        }
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class EpisodeOrchestrator:
    """Production orchestrator for one multi-scene episode run.

    Usage (composition root):

        orch = EpisodeOrchestrator(
            fixture=fixture, manifest=manifest,
            checkpoint_dir=..., cache=EpisodeAssetCache(cache_dir),
            steps={...golden-scene kernels...},
            render_leg=..., review_repair_leg=..., ffmpeg_leg=...,
            audio_leg=..., asset_generator=...,
            identity_checker=..., verification_checker=...,
        )
        report = await orch.run(cancel_token=..., invalidation_requests=[...])

    Resume: pass the SAME run_id + fixture + manifest on restart; completed
    nodes with identical input hashes are SKIPPED and completed render
    chunks are reused — a killed render resumes with a PARTIAL rerender.
    """

    def __init__(
        self,
        *,
        fixture: EpisodeFixture,
        manifest: EpisodeRunManifest,
        checkpoint_dir: Path,
        cache: EpisodeAssetCache,
        steps: Dict[str, Callable[..., Any]],
        render_leg: EpisodeRenderLeg,
        review_repair_leg: EpisodeReviewRepairLeg,
        ffmpeg_leg: EpisodeFfmpegLeg,
        audio_leg: EpisodeAudioSynthesisLeg,
        asset_generator: EpisodeAssetGeneratorLeg,
        identity_checker: Callable[[EpisodeFixture, Dict[str, EpisodeNodeReceipt]], Any],
        verification_checker: Callable[
            [EpisodeFixture, Dict[str, EpisodeNodeReceipt], Path], Any
        ],
        verdict_policy: Optional[EpisodeVerdictPolicy] = None,
        resume_planner: Optional[EpisodeResumePlanner] = None,
        artifact_dir: Optional[Path] = None,
    ) -> None:
        fixture.validate_fixture()
        if fixture.content_hash() != manifest.fixture_hash:
            raise EpisodeValidationError(
                "Fixture hash does not match the run manifest.",
                details={
                    "fixture_hash": fixture.content_hash(),
                    "manifest_fixture_hash": manifest.fixture_hash,
                },
            )
        self._fixture = fixture
        self._manifest = manifest
        self._checkpoint_dir = Path(checkpoint_dir)
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._cache = cache
        self._steps = dict(steps)
        self._render_leg = render_leg
        self._review_repair_leg = review_repair_leg
        self._ffmpeg_leg = ffmpeg_leg
        self._audio_leg = audio_leg
        self._asset_generator = asset_generator
        self._identity_checker = identity_checker
        self._verification_checker = verification_checker
        self._verdict_policy = verdict_policy or EpisodeVerdictPolicy()
        self._resume_planner = resume_planner or EpisodeResumePlanner()
        self._artifact_dir = (
            Path(artifact_dir) if artifact_dir else self._checkpoint_dir / "artifacts"
        )
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        self._receipts: Dict[str, EpisodeNodeReceipt] = {}
        self._chunks: Dict[str, EpisodeChunkReceipt] = {}
        self._artifacts: List[EpisodeArtifactRecord] = []

    # ------------------------------------------------------------------
    # Checkpoint persistence
    # ------------------------------------------------------------------
    def _checkpoint_path(self) -> Path:
        return self._checkpoint_dir / f"{self._manifest.run_id}.checkpoint.json"

    def _load_checkpoint(self) -> Optional[EpisodeCheckpoint]:
        path = self._checkpoint_path()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if data.get("run_id") != str(self._manifest.run_id):
            raise EpisodeResumeMismatchError(
                "Checkpoint run_id does not match the run manifest.",
                details={
                    "checkpoint_run": data.get("run_id"),
                    "run": str(self._manifest.run_id),
                },
            )
        return EpisodeCheckpoint.model_validate(data)

    def _save_checkpoint(self) -> None:
        checkpoint = EpisodeCheckpoint(
            run_id=self._manifest.run_id,
            receipts=list(self._receipts.values()),
            chunks=list(self._chunks.values()),
            artifacts=self._artifacts,
        )
        tmp = self._checkpoint_path().with_suffix(".tmp")
        tmp.write_text(
            json.dumps(checkpoint.model_dump(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(self._checkpoint_path())
        # The asset cache is part of the durable run state: a kill between
        # ASSETS and the next node must not lose generated entries (reuse
        # across runs depends on it).
        self._cache.save()

    def _record_chunks(self, chunk_receipts: List[EpisodeChunkReceipt]) -> None:
        for receipt in chunk_receipts:
            self._chunks[str(receipt.chunk_id)] = receipt
        self._save_checkpoint()

    # ------------------------------------------------------------------
    # Node plan + inputs
    # ------------------------------------------------------------------
    def _node_plan(self) -> List[tuple[str, GoldenSceneNodeKind, str]]:
        plan: List[tuple[str, GoldenSceneNodeKind, str]] = [
            ("episode::SCRIPT", GoldenSceneNodeKind.SCRIPT, ""),
            ("episode::IR", GoldenSceneNodeKind.IR, ""),
            ("episode::ASSETS", GoldenSceneNodeKind.ASSETS, ""),
            ("episode::AUDIO_PREP", GoldenSceneNodeKind.ANIMATION_AUDIO, ""),
        ]
        for scene in self._fixture.ordered_scenes():
            scene_id = str(scene.scene_id)
            plan.append((f"{scene_id}::SCENE", GoldenSceneNodeKind.SCENE, scene_id))
            plan.append(
                (f"{scene_id}::ANIMATION_AUDIO", GoldenSceneNodeKind.ANIMATION_AUDIO, scene_id)
            )
            plan.append((f"{scene_id}::FACIAL", GoldenSceneNodeKind.FACIAL, scene_id))
            plan.append((f"{scene_id}::RENDER", GoldenSceneNodeKind.RENDER, scene_id))
            plan.append(
                (f"{scene_id}::REVIEW_REPAIR", GoldenSceneNodeKind.REVIEW_REPAIR, scene_id)
            )
            plan.append((f"{scene_id}::FFMPEG", GoldenSceneNodeKind.FFMPEG, scene_id))
        plan.append(("episode::FINAL", GoldenSceneNodeKind.FINAL, ""))
        return plan

    def _current_inputs(self) -> Dict[str, Dict[str, str]]:
        inputs: Dict[str, Dict[str, str]] = {}
        fixture_hash = self._fixture.content_hash()
        manifest_hash = self._manifest.content_hash()
        base = {"fixture": fixture_hash, "manifest": manifest_hash}
        inputs["episode::SCRIPT"] = dict(base)
        inputs["episode::IR"] = dict(base)
        inputs["episode::ASSETS"] = dict(base)
        inputs["episode::AUDIO_PREP"] = dict(base)
        for scene in self._fixture.ordered_scenes():
            scene_id = str(scene.scene_id)
            scene_inputs = {
                **base,
                "scene": scene.content_hash(),
                "scene_fixture": _scene_fixture(self._fixture, scene).content_hash(),
            }
            inputs[f"{scene_id}::SCENE"] = dict(scene_inputs)
            inputs[f"{scene_id}::ANIMATION_AUDIO"] = dict(scene_inputs)
            inputs[f"{scene_id}::FACIAL"] = dict(scene_inputs)
            inputs[f"{scene_id}::RENDER"] = {
                **scene_inputs,
                "chunks": _chunk_input_signature(self._fixture, scene),
            }
            inputs[f"{scene_id}::REVIEW_REPAIR"] = dict(scene_inputs)
            inputs[f"{scene_id}::FFMPEG"] = dict(scene_inputs)
        inputs["episode::FINAL"] = {
            **base,
            "scenes": ",".join(str(s.scene_id) for s in self._fixture.ordered_scenes()),
        }
        return inputs

    # ------------------------------------------------------------------
    # Node execution
    # ------------------------------------------------------------------
    async def _execute(
        self,
        node_key: str,
        kind: GoldenSceneNodeKind,
        scene_id: str,
        runner: Callable[..., Any],
        prior: Dict[str, EpisodeNodeReceipt],
        cancel_token: Callable[[], bool],
        *,
        runner_kwargs: Optional[Dict[str, Any]] = None,
    ) -> EpisodeNodeReceipt:
        if cancel_token():
            return EpisodeNodeReceipt(
                node_id=node_key,
                kind=kind,
                scene_id=scene_id,
                status=GoldenSceneNodeStatus.CANCELLED,
                attempt=1,
                started_at=utc_now_iso(),
                finished_at=utc_now_iso(),
                error="cancelled before execution",
            )
        node = EpisodeNodeReceipt(
            node_id=node_key,
            kind=kind,
            scene_id=scene_id,
            status=GoldenSceneNodeStatus.RUNNING,
            attempt=1,
            started_at=utc_now_iso(),
            input_hashes=self._current_inputs()[node_key],
        )
        try:
            outcome = await runner.run(
                node=node,
                fixture=self._fixture,
                manifest=self._manifest,
                workspace=self._artifact_dir,
                prior=prior,
                **(runner_kwargs or {}),
            )
        except Exception as exc:
            return EpisodeNodeReceipt(
                node_id=node_key,
                kind=kind,
                scene_id=scene_id,
                status=GoldenSceneNodeStatus.FAILED,
                attempt=1,
                started_at=node.started_at,
                finished_at=utc_now_iso(),
                input_hashes=node.input_hashes,
                error=f"{type(exc).__name__}: {exc}",
                metadata={"phase_26_failure": True},
            )
        output_hashes = dict(outcome.get("output_hashes", {}))
        status_override = outcome.get("status")
        if not output_hashes and status_override not in (
            GoldenSceneNodeStatus.FAILED,
            GoldenSceneNodeStatus.CANCELLED,
        ):
            return EpisodeNodeReceipt(
                node_id=node_key,
                kind=kind,
                scene_id=scene_id,
                status=GoldenSceneNodeStatus.FAILED,
                attempt=1,
                started_at=node.started_at,
                finished_at=utc_now_iso(),
                input_hashes=node.input_hashes,
                error="step produced no output hashes",
            )
        status = (
            status_override
            if status_override
            in (GoldenSceneNodeStatus.FAILED, GoldenSceneNodeStatus.CANCELLED)
            else GoldenSceneNodeStatus.COMPLETED
        )
        artifacts = [
            EpisodeArtifactRecord(
                artifact_id=EpisodeArtifactId(f"{node_key}:{a['ref_key']}"),
                kind=EpisodeArtifactKind(a["kind"]),
                ref_key=a["ref_key"],
                revision=a["revision"],
                content_hash=a["content_hash"],
                source=a["source"],
                scene_id=scene_id,
                producer_node=node_key,
            )
            for a in outcome.get("artifacts", [])
        ]
        self._artifacts.extend(artifacts)
        return EpisodeNodeReceipt(
            node_id=node_key,
            kind=kind,
            scene_id=scene_id,
            status=status,
            attempt=1,
            started_at=node.started_at,
            finished_at=utc_now_iso(),
            input_hashes=node.input_hashes,
            output_hashes=output_hashes,
            provenance={k: r.node_id for k, r in prior.items()},
            findings=outcome.get("findings", []),
            repairs=[
                RepairEntry.model_validate(e) for e in outcome.get("repairs", [])
            ],
            error=outcome.get("error", ""),
            metadata=outcome.get("metadata", {}),
        )

    def _runner_for(self, node_key: str, kind: GoldenSceneNodeKind, scene_id: str):
        if scene_id:
            scene = self._fixture.scene(scene_id)
            scene_fixture = self._scene_fixture(scene) if scene else None
            if kind == GoldenSceneNodeKind.RENDER:
                return _ChunkedRenderRunner(
                    leg=self._render_leg,
                    fixture=self._fixture,
                    scene=scene,
                    scene_fixture=scene_fixture,
                    planner=self._resume_planner,
                    record_chunks=self._record_chunks,
                    current_chunks=lambda: self._chunks,
                )
            if kind == GoldenSceneNodeKind.REVIEW_REPAIR:
                return _LegStepAdapter(
                    self._review_repair_leg.review_scene,
                    scene=scene,
                    scene_fixture=scene_fixture,
                )
            if kind == GoldenSceneNodeKind.FFMPEG:
                return _LegStepAdapter(
                    self._ffmpeg_leg.assemble_scene,
                    scene=scene,
                    scene_fixture=scene_fixture,
                )
            kernel_steps = {
                GoldenSceneNodeKind.SCENE: "SCENE",
                GoldenSceneNodeKind.ANIMATION_AUDIO: "ANIMATION_AUDIO",
                GoldenSceneNodeKind.FACIAL: "FACIAL",
            }
            if kind in kernel_steps:
                step = self._steps[kernel_steps[kind]]

                async def _kernel(
                    scene=scene,
                    scene_fixture=scene_fixture,
                    workspace=None,
                    step=step,
                    node_key=node_key,
                    kind=kind,
                    scene_id=scene_id,
                ):
                    return await step.run(
                        node=_dummy_node(node_key, kind, scene_id),
                        fixture=scene_fixture,
                        manifest=_scene_manifest(self._manifest, scene_fixture),
                        workspace=workspace,
                        prior={},
                    )

                return _LegStepAdapter(_kernel, scene=scene, scene_fixture=scene_fixture)
        if node_key == "episode::SCRIPT":
            return _LegStepAdapter(
                lambda workspace: self._steps["SCRIPT"].run(
                    node=_dummy_node(node_key, kind, ""),
                    fixture=self._fixture,
                    manifest=self._manifest,
                    workspace=workspace,
                    prior={},
                )
            )
        if node_key == "episode::IR":
            return _LegStepAdapter(
                lambda workspace: self._steps["IR"].run(
                    node=_dummy_node(node_key, kind, ""),
                    fixture=self._fixture,
                    manifest=self._manifest,
                    workspace=workspace,
                    prior={},
                )
            )
        if node_key == "episode::ASSETS":
            return _CachedAssetsStep(self._cache, self._asset_generator)
        if node_key == "episode::AUDIO_PREP":
            return _AudioPrepRunner(self._audio_leg)
        if node_key == "episode::FINAL":
            return _EpisodeFinalRunner()
        return None

    def _scene_fixture(self, scene: EpisodeSceneSpec) -> GoldenSceneFixture:
        return _scene_fixture(self._fixture, scene)

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------
    async def run(
        self,
        *,
        cancel_token: Optional[Callable[[], bool]] = None,
        invalidation_requests: Optional[List[List[str]]] = None,
    ) -> EpisodeProductionReport:
        cancel_token = cancel_token or (lambda: False)
        checkpoint = self._load_checkpoint()
        self._receipts = {}
        self._chunks = {}
        self._artifacts = []
        if checkpoint is not None:
            self._receipts = {r.node_id: r for r in checkpoint.receipts}
            self._chunks = {str(c.chunk_id): c for c in checkpoint.chunks}
            self._artifacts = list(checkpoint.artifacts)

        decisions = self._resume_planner.plan(checkpoint, self._current_inputs())
        node_plan = self._node_plan()

        async def run_plan_entry(node_key: str, kind: GoldenSceneNodeKind, scene_id: str):
            if decisions[node_key] == "SKIP":
                prior_receipt = self._receipts[node_key]
                skipped = prior_receipt.model_copy(
                    update={
                        "status": GoldenSceneNodeStatus.SKIPPED,
                        "metadata": {
                            **prior_receipt.metadata,
                            "resumed": True,
                            "skip_reason": (
                                "completed in prior run with identical input hashes"
                            ),
                        },
                    }
                )
                self._receipts[node_key] = skipped
                self._save_checkpoint()
                return
            runner = self._runner_for(node_key, kind, scene_id)
            if runner is None:
                self._receipts[node_key] = EpisodeNodeReceipt(
                    node_id=node_key,
                    kind=kind,
                    scene_id=scene_id,
                    status=GoldenSceneNodeStatus.FAILED,
                    attempt=1,
                    started_at=utc_now_iso(),
                    finished_at=utc_now_iso(),
                    error=f"No runner registered for node {node_key}.",
                    metadata={"phase_26_failure": True},
                )
                self._save_checkpoint()
                return
            kwargs = {}
            if isinstance(runner, _ChunkedRenderRunner):
                kwargs = {"cancel_token": cancel_token}
            receipt = await self._execute(
                node_key, kind, scene_id, runner,
                prior=self._receipts, cancel_token=cancel_token,
                runner_kwargs=kwargs,
            )
            self._receipts[node_key] = receipt
            self._save_checkpoint()

        # Episode-level nodes: SCRIPT, IR sequential.
        for node_key, kind, scene_id in node_plan[:2]:
            await run_plan_entry(node_key, kind, scene_id)

        # Parallel branches: ASSET_PREP + AUDIO_PREP (backlog 3).
        branch_durations: Dict[str, float] = {}

        async def _branch(branch_key: str, node_key: str) -> None:
            entry = next((k, knd, s) for k, knd, s in node_plan if k == node_key)
            started = _time.monotonic()
            await run_plan_entry(*entry)
            branch_durations[branch_key] = _time.monotonic() - started

        await asyncio.gather(
            _branch("asset_prep", "episode::ASSETS"),
            _branch("audio_prep", "episode::AUDIO_PREP"),
        )

        # Per-scene pipeline in scene order.
        for scene in self._fixture.ordered_scenes():
            scene_id = str(scene.scene_id)
            for suffix, branch_key in (
                ("SCENE", f"compile:{scene_id}"),
                ("ANIMATION_AUDIO", None),
                ("FACIAL", None),
                ("RENDER", f"render:{scene_id}"),
                ("REVIEW_REPAIR", f"review:{scene_id}"),
                ("FFMPEG", None),
            ):
                node_key = f"{scene_id}::{suffix}"
                kind = next(knd for k, knd, _ in node_plan if k == node_key)
                started = _time.monotonic()
                await run_plan_entry(node_key, kind, scene_id)
                if branch_key is not None:
                    branch_durations[branch_key] = _time.monotonic() - started

        # FINAL node.
        final_started = _time.monotonic()
        await run_plan_entry("episode::FINAL", GoldenSceneNodeKind.FINAL, "")
        branch_durations["post"] = _time.monotonic() - final_started

        # Timing receipt: schedule the measured durations over the branch DAG.
        specs = build_episode_branch_specs(self._fixture)
        timing = EpisodeBranchScheduler().schedule(specs, branch_durations)

        # Invalidation plans (backlog 5).
        graph = EpisodeDependencyGraph.build_from_fixture(self._fixture)
        known_refs = self._known_artifact_refs()
        planner = EpisodeInvalidationPlanner()
        invalidation_plans = [
            planner.plan(graph, refs, known_refs)
            for refs in (invalidation_requests or [])
        ]

        # Ordering (backlog 2): media order must equal fixture scene order.
        ordering = EpisodeOrderingReceipt.from_fixture(self._fixture)
        final_receipt = self._receipts.get("episode::FINAL")
        media_order = []
        if final_receipt is not None:
            media_order = final_receipt.metadata.get("media_scene_order", [])
        ordering_ok = media_order == ordering.scene_order and bool(media_order)

        identity = self._identity_checker(self._fixture, self._receipts)
        verification = self._verification_checker(
            self._fixture, self._receipts, self._artifact_dir
        )
        verdict = self._verdict_policy.decide(
            list(self._receipts.values()),
            list(self._chunks.values()),
            ordering_ok,
            identity,
            verification,
        )

        repairs: List[RepairEntry] = []
        for receipt in self._receipts.values():
            repairs.extend(receipt.repairs)
        approvals = sorted(
            (a for a in self._fixture.approvals),
            key=lambda a: a.approval_id,
        )

        cache_report = self._cache.report()
        report = EpisodeProductionReport(
            run_id=self._manifest.run_id,
            verdict=verdict,
            manifest_hash=self._manifest.content_hash(),
            fixture_hash=self._fixture.content_hash(),
            ordering=ordering,
            cache_report=cache_report,
            invalidation_plans=invalidation_plans,
            receipts=list(self._receipts.values()),
            chunks=list(self._chunks.values()),
            timing=timing,
            identity_continuity=identity,
            technical_verification=verification,
            repair_entries=repairs,
            human_approvals=approvals,
            summary=self._summary(verdict, identity, verification, ordering_ok),
        )
        self._save_checkpoint()
        return report

    def _known_artifact_refs(self) -> List[str]:
        refs: List[str] = []
        for scene in self._fixture.scenes:
            refs.append(f"scene:{scene.scene_id}")
            if scene.environment_ref:
                refs.append(f"environment:{scene.environment_ref}")
        for shot in self._fixture.shots:
            refs.append(f"shot:{shot.shot_id}")
            refs.append(f"render:{shot.shot_id}")
            refs.append(f"media:{shot.scene_id}")
            for character in shot.character_ids:
                refs.append(f"character:{character}")
            if shot.camera_intent_ref:
                refs.append(f"camera:{shot.camera_intent_ref}")
            for cue in shot.audio_cue_refs:
                refs.append(f"audio_cue:{cue}")
            for anim in shot.animation_intent_refs:
                refs.append(f"animation:{anim}")
        refs.append("final:episode")
        return refs

    def _summary(
        self,
        verdict: EpisodeVerdict,
        identity: Any,
        verification: Any,
        ordering_ok: bool,
    ) -> str:
        finished = [r for r in self._receipts.values() if r.is_terminal_ok()]
        failed = [r for r in self._receipts.values() if not r.is_terminal_ok()]
        parts = [
            f"nodes completed={len(finished)} failed={len(failed)}",
            f"identity_continuity={'PASS' if identity.passed else 'FAIL'}",
            f"technical_verification={'PASS' if verification.passed else 'FAIL'}",
            f"episode_ordering={'PASS' if ordering_ok else 'FAIL'}",
        ]
        cache = self._cache.report()
        parts.append(
            f"cache hits={cache.hits} misses={cache.misses} "
            f"invalidated={cache.invalidated} rejected={cache.rejected}"
        )
        if failed:
            kinds = ",".join(r.node_id for r in failed)
            parts.append(f"blocking nodes: {kinds}")
        return (
            f"Episode run {self._manifest.run_id}: {verdict.value} | "
            + " | ".join(parts)
        )
