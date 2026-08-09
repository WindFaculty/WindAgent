"""
Multi-Scene Episode Orchestration Domain (VP3D Phase 26, Stage M).

Pure domain models + fail-closed kernels for the 2-3 minute episode run
(stage_m.md §4): at least three scenes, five shots, two to four characters
and multiple environments, built on the Phase 25 golden scene machinery.

Backlog acceptance (stage_m.md §4):

1. character/environment/animation assets are REUSED across scenes and runs
   instead of regenerated (EpisodeAssetCache decisions: HIT / MISS /
   INVALIDATED / REJECTED_REUSE);
2. continuity holds across scenes/shots and episode ordering is STABLE
   (EpisodeOrderingReceipt + cross-scene identity checks);
3. audio/asset branches run IN PARALLEL with measured critical path and
   idle time (EpisodeBranchScheduler + EpisodeTimingReceipt);
4. killing a worker mid-render resumes at FRAME-CHUNK granularity with
   PARTIAL rerender (EpisodeChunkSpec / EpisodeChunkReceipt /
   EpisodeResumePlanner.plan_chunks);
5. replacing one shot/camera/audio cue invalidates ONLY the correct
   downstream artifacts (EpisodeDependencyGraph + EpisodeInvalidationPlanner);
6. the cache report distinguishes hit, miss, invalidated and rejected reuse
   (EpisodeCacheReport).

The orchestrator (intelligence layer) walks scenes in order, reusing the
Phase 25 golden-scene step kernels per scene, and derives the verdict
fail-closed: any failed/cancelled node OR chunk, any unrepaired blocking
finding, any identity/continuity failure, any technical verification failure
or any unstable episode ordering REJECTS the run.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    EpisodeArtifactKind,
    EpisodeBranchKind,
    EpisodeCacheDecision,
    EpisodeChunkStatus,
    EpisodeVerdict,
    GoldenSceneNodeKind,
    GoldenSceneNodeStatus,
)
from windagent_core.domain.video_production.errors import (
    EpisodeDependencyCycleError,
    EpisodeValidationError,
)
from windagent_core.domain.video_production.golden_scene import (
    HumanApprovalEntry,
    IdentityContinuityReceipt,
    RepairEntry,
    TechnicalVerificationReceipt,
    compute_content_hash,
)
from windagent_core.domain.video_production.ids import (
    EpisodeArtifactId,
    EpisodeChunkId,
    EpisodeRunId,
    EpisodeSceneId,
    EpisodeShotId,
    VideoProjectId,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Fixture: scenes + shots
# ---------------------------------------------------------------------------
class EpisodeShotSpec(BaseModel):
    """One shot of the episode: characters, camera, audio, frame range."""

    model_config = ConfigDict(frozen=True, extra="allow")

    shot_id: EpisodeShotId
    scene_id: EpisodeSceneId
    order_index: int = 0
    character_ids: List[str] = Field(default_factory=list)
    camera_intent_ref: str = ""
    audio_cue_refs: List[str] = Field(default_factory=list)
    animation_intent_refs: List[str] = Field(default_factory=list)
    frame_start: int = 1
    frame_end: int = 24

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "shot_id": str(self.shot_id),
                "scene_id": str(self.scene_id),
                "order_index": self.order_index,
                "character_ids": self.character_ids,
                "camera_intent_ref": self.camera_intent_ref,
                "audio_cue_refs": self.audio_cue_refs,
                "animation_intent_refs": self.animation_intent_refs,
                "frame_start": self.frame_start,
                "frame_end": self.frame_end,
            }
        )


class EpisodeSceneSpec(BaseModel):
    """One scene of the episode: environment + ordered shots."""

    model_config = ConfigDict(frozen=True, extra="allow")

    scene_id: EpisodeSceneId
    order_index: int = 0
    environment_ref: str = ""
    character_ids: List[str] = Field(default_factory=list)
    shot_ids: List[EpisodeShotId] = Field(default_factory=list)
    frame_start: int = 1
    frame_end: int = 24

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "scene_id": str(self.scene_id),
                "order_index": self.order_index,
                "environment_ref": self.environment_ref,
                "character_ids": self.character_ids,
                "shot_ids": [str(s) for s in self.shot_ids],
                "frame_start": self.frame_start,
                "frame_end": self.frame_end,
            }
        )


class EpisodeFixture(BaseModel):
    """The versioned multi-scene episode fixture (stage_m.md §2/§4).

    Three+ scenes, five+ shots, two to four characters, multiple
    environments. Scene/shot ORDER lives in the fixture (order_index) — the
    episode ordering must be stable across runs.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    fixture_id: str
    title: str
    planned_duration_seconds: float = 150.0
    fps: int = 24
    screenplay_text: str = ""
    scenes: List[EpisodeSceneSpec] = Field(default_factory=list)
    shots: List[EpisodeShotSpec] = Field(default_factory=list)
    characters: List[Dict[str, Any]] = Field(default_factory=list)
    environments: List[Dict[str, Any]] = Field(default_factory=list)
    dialogue_lines: List[Dict[str, Any]] = Field(default_factory=list)
    animation_intents: List[Dict[str, Any]] = Field(default_factory=list)
    camera_intents: List[Dict[str, Any]] = Field(default_factory=list)
    lighting_intents: List[Dict[str, Any]] = Field(default_factory=list)
    audio_cues: List[Dict[str, Any]] = Field(default_factory=list)
    render_profile: Dict[str, Any] = Field(default_factory=dict)
    approvals: List[HumanApprovalEntry] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def validate_fixture(self) -> None:
        """Structural validation: scenes/shots non-empty and cross-referenced."""
        if not self.scenes:
            raise EpisodeValidationError(
                "Episode fixture requires at least one scene.",
                details={"fixture_id": self.fixture_id},
            )
        if not self.shots:
            raise EpisodeValidationError(
                "Episode fixture requires at least one shot.",
                details={"fixture_id": self.fixture_id},
            )
        scene_ids = {str(s.scene_id) for s in self.scenes}
        scene_orders = [s.order_index for s in self.scenes]
        if len(set(scene_orders)) != len(scene_orders):
            raise EpisodeValidationError(
                "Duplicate scene order_index in episode fixture.",
                details={"fixture_id": self.fixture_id},
            )
        shot_ids = {str(sh.shot_id) for sh in self.shots}
        for scene in self.scenes:
            for shot_ref in scene.shot_ids:
                if str(shot_ref) not in shot_ids:
                    raise EpisodeValidationError(
                        f"Scene {scene.scene_id} references unknown shot {shot_ref}.",
                        details={"fixture_id": self.fixture_id},
                    )
        for shot in self.shots:
            if str(shot.scene_id) not in scene_ids:
                raise EpisodeValidationError(
                    f"Shot {shot.shot_id} references unknown scene {shot.scene_id}.",
                    details={"fixture_id": self.fixture_id},
                )
            if shot.frame_end < shot.frame_start:
                raise EpisodeValidationError(
                    f"Shot {shot.shot_id} has an inverted frame range.",
                    details={
                        "frame_start": shot.frame_start,
                        "frame_end": shot.frame_end,
                    },
                )

    def ordered_scenes(self) -> List[EpisodeSceneSpec]:
        return sorted(self.scenes, key=lambda s: s.order_index)

    def ordered_shots(self) -> List[EpisodeShotSpec]:
        return sorted(self.shots, key=lambda s: (s.order_index, str(s.shot_id)))

    def shot(self, shot_id: str) -> Optional[EpisodeShotSpec]:
        for shot in self.shots:
            if str(shot.shot_id) == shot_id:
                return shot
        return None

    def scene(self, scene_id: str) -> Optional[EpisodeSceneSpec]:
        for scene in self.scenes:
            if str(scene.scene_id) == scene_id:
                return scene
        return None

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "fixture_id": self.fixture_id,
                "title": self.title,
                "planned_duration_seconds": self.planned_duration_seconds,
                "fps": self.fps,
                "screenplay_text": self.screenplay_text,
                "scenes": [s.content_hash() for s in sorted(self.scenes, key=lambda s: s.order_index)],
                "shots": [s.content_hash() for s in self.shots],
                "characters": self.characters,
                "environments": self.environments,
                "dialogue_lines": self.dialogue_lines,
                "animation_intents": self.animation_intents,
                "camera_intents": self.camera_intents,
                "lighting_intents": self.lighting_intents,
                "audio_cues": self.audio_cues,
                "render_profile": self.render_profile,
                "approvals": [a.content_hash() for a in self.approvals],
            }
        )


class EpisodeRunManifest(BaseModel):
    """Run manifest — every episode run pins its full environment."""

    model_config = ConfigDict(frozen=True, extra="allow")

    run_id: EpisodeRunId
    project_id: VideoProjectId
    revision_id: str
    fixture_hash: str
    candidate_sha: str
    hardware_baseline: Dict[str, str] = Field(default_factory=dict)
    tool_versions: Dict[str, str] = Field(default_factory=dict)
    budgets: Dict[str, float] = Field(default_factory=dict)
    pinned_seeds: Dict[str, int] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "run_id": str(self.run_id),
                "project_id": str(self.project_id),
                "revision_id": self.revision_id,
                "fixture_hash": self.fixture_hash,
                "candidate_sha": self.candidate_sha,
                "hardware_baseline": self.hardware_baseline,
                "tool_versions": self.tool_versions,
                "budgets": self.budgets,
                "pinned_seeds": self.pinned_seeds,
            }
        )


# ---------------------------------------------------------------------------
# Episode ordering (backlog 2 — stable ordering)
# ---------------------------------------------------------------------------
class EpisodeOrderingReceipt(BaseModel):
    """Scene/shot ordering — deterministic from the fixture.

    Stable episode ordering = the SAME fixture always produces the SAME
    ordering hash; the orchestrator records it in every run and the verdict
    policy fails closed when the recorded ordering differs from the
    fixture-derived one.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    scene_order: List[str] = Field(default_factory=list)
    shot_order: List[str] = Field(default_factory=list)

    def ordering_hash(self) -> str:
        return compute_content_hash(
            {
                "scene_order": self.scene_order,
                "shot_order": self.shot_order,
            }
        )

    def matches(self, expected_hash: str) -> bool:
        return self.ordering_hash() == expected_hash

    @classmethod
    def from_fixture(cls, fixture: EpisodeFixture) -> "EpisodeOrderingReceipt":
        scenes = sorted(fixture.scenes, key=lambda s: s.order_index)
        shot_order: List[str] = []
        for scene in scenes:
            scene_shots = [
                sh for sh in fixture.shots if str(sh.scene_id) == str(scene.scene_id)
            ]
            shot_order.extend(
                str(sh.shot_id)
                for sh in sorted(scene_shots, key=lambda sh: sh.order_index)
            )
        return cls(
            scene_order=[str(s.scene_id) for s in scenes],
            shot_order=shot_order,
        )


# ---------------------------------------------------------------------------
# Node + chunk receipts + checkpoint
# ---------------------------------------------------------------------------
class EpisodeNodeReceipt(BaseModel):
    """One episode node execution record (scene-scoped)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    node_id: str
    kind: GoldenSceneNodeKind
    scene_id: str = ""
    status: GoldenSceneNodeStatus
    attempt: int = 1
    started_at: str = ""
    finished_at: str = ""
    input_hashes: Dict[str, str] = Field(default_factory=dict)
    output_hashes: Dict[str, str] = Field(default_factory=dict)
    provenance: Dict[str, str] = Field(default_factory=dict)
    error: str = ""
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    repairs: List[RepairEntry] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "node_id": self.node_id,
                "kind": self.kind.value,
                "scene_id": self.scene_id,
                "status": self.status.value,
                "attempt": self.attempt,
                "input_hashes": self.input_hashes,
                "output_hashes": self.output_hashes,
                "provenance": self.provenance,
            }
        )

    def is_terminal_ok(self) -> bool:
        return self.status in (GoldenSceneNodeStatus.COMPLETED, GoldenSceneNodeStatus.SKIPPED)


class EpisodeArtifactRecord(BaseModel):
    """One artifact produced or reused by the episode run (backlog 1)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    artifact_id: EpisodeArtifactId
    kind: EpisodeArtifactKind
    ref_key: str
    revision: str
    content_hash: str
    source: str  # GENERATED | REUSED
    scene_id: str = ""
    producer_node: str = ""

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "artifact_id": str(self.artifact_id),
                "kind": self.kind.value,
                "ref_key": self.ref_key,
                "revision": self.revision,
                "content_hash": self.content_hash,
                "source": self.source,
                "scene_id": self.scene_id,
                "producer_node": self.producer_node,
            }
        )


class EpisodeChunkSpec(BaseModel):
    """One render frame chunk (backlog 4 — kill/resume granularity).

    `scene_frame_start` is the chunk's first frame expressed relative to
    its SCENE start (1-based) — the render leg uses it for stable,
    scene-relative output names so ffmpeg %04d globbing works and resume is
    idempotent (same names on restart).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    chunk_id: EpisodeChunkId
    shot_id: str
    scene_id: str
    frame_start: int
    frame_end: int
    scene_frame_start: int = 1
    input_hash: str = ""

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "chunk_id": str(self.chunk_id),
                "shot_id": self.shot_id,
                "scene_id": self.scene_id,
                "frame_start": self.frame_start,
                "frame_end": self.frame_end,
                "scene_frame_start": self.scene_frame_start,
                "input_hash": self.input_hash,
            }
        )


class EpisodeChunkReceipt(BaseModel):
    """One chunk execution record — the resume unit of the render node."""

    model_config = ConfigDict(frozen=True, extra="allow")

    chunk_id: EpisodeChunkId
    shot_id: str
    scene_id: str
    status: EpisodeChunkStatus
    attempt: int = 1
    input_hash: str = ""
    output_hash: str = ""
    started_at: str = ""
    finished_at: str = ""

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "chunk_id": str(self.chunk_id),
                "shot_id": self.shot_id,
                "scene_id": self.scene_id,
                "status": self.status.value,
                "attempt": self.attempt,
                "input_hash": self.input_hash,
                "output_hash": self.output_hash,
            }
        )

    def is_terminal_ok(self) -> bool:
        return self.status in (EpisodeChunkStatus.COMPLETED, EpisodeChunkStatus.SKIPPED)


class EpisodeCheckpoint(BaseModel):
    """Durable per-run checkpoint: node receipts + chunk receipts.

    Resume semantics (backlog 4): a node whose receipt is COMPLETED with the
    SAME input hashes is SKIPPED; a render node that was CANCELLED re-runs
    but its COMPLETED chunks with identical input hashes are SKIPPED — only
    the missing/failed chunks re-render (PARTIAL rerender, no duplicate).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    run_id: EpisodeRunId
    receipts: List[EpisodeNodeReceipt] = Field(default_factory=list)
    chunks: List[EpisodeChunkReceipt] = Field(default_factory=list)
    artifacts: List[EpisodeArtifactRecord] = Field(default_factory=list)
    updated_at: str = Field(default_factory=lambda: utc_now().isoformat())

    def receipt_for(self, node_key: str) -> Optional[EpisodeNodeReceipt]:
        for receipt in self.receipts:
            if receipt.node_id == node_key:
                return receipt
        return None

    def chunk_for(self, chunk_id: str) -> Optional[EpisodeChunkReceipt]:
        for receipt in self.chunks:
            if str(receipt.chunk_id) == chunk_id:
                return receipt
        return None

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "run_id": str(self.run_id),
                "receipts": [r.content_hash() for r in self.receipts],
                "chunks": [c.content_hash() for c in self.chunks],
                "artifacts": [a.content_hash() for a in self.artifacts],
            }
        )


class EpisodeResumePlanner:
    """Decides RUN vs SKIP per node and per chunk given a checkpoint.

    Node level: SKIP only when COMPLETED with identical input hashes.
    Chunk level: SKIP only when COMPLETED with the identical chunk input
    hash — everything else RUNs (partial rerender after a kill).
    """

    def plan(
        self,
        checkpoint: Optional[EpisodeCheckpoint],
        current_inputs: Dict[str, Dict[str, str]],
    ) -> Dict[str, str]:
        decisions: Dict[str, str] = {}
        for node_key, expected in current_inputs.items():
            if checkpoint is None:
                decisions[node_key] = "RUN"
                continue
            receipt = checkpoint.receipt_for(node_key)
            if (
                receipt is not None
                and receipt.status == GoldenSceneNodeStatus.COMPLETED
                and receipt.input_hashes == expected
            ):
                decisions[node_key] = "SKIP"
            else:
                decisions[node_key] = "RUN"
        return decisions

    def plan_chunks(
        self,
        checkpoint: Optional[EpisodeCheckpoint],
        chunk_specs: List[EpisodeChunkSpec],
    ) -> Dict[str, str]:
        decisions: Dict[str, str] = {}
        for spec in chunk_specs:
            chunk_id = str(spec.chunk_id)
            if checkpoint is None:
                decisions[chunk_id] = "RUN"
                continue
            receipt = checkpoint.chunk_for(chunk_id)
            if (
                receipt is not None
                and receipt.status == EpisodeChunkStatus.COMPLETED
                and receipt.input_hash == spec.input_hash
            ):
                decisions[chunk_id] = "SKIP"
            else:
                decisions[chunk_id] = "RUN"
        return decisions


# ---------------------------------------------------------------------------
# Asset cache (backlog 1 + 6)
# ---------------------------------------------------------------------------
class EpisodeCacheEntry(BaseModel):
    """One cache entry: an asset at a pinned revision with a content hash."""

    model_config = ConfigDict(frozen=True, extra="allow")

    cache_key: str
    kind: EpisodeArtifactKind
    revision: str
    content_hash: str
    approved: bool = True
    usage_count: int = 0
    last_used: str = ""

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "cache_key": self.cache_key,
                "kind": self.kind.value,
                "revision": self.revision,
                "content_hash": self.content_hash,
                "approved": self.approved,
            }
        )


class EpisodeCacheReport(BaseModel):
    """Per-run cache report (backlog 6): hit / miss / invalidated / rejected.

    HIT            — entry exists, hash matches, approved -> REUSED;
    MISS           — no entry -> generate;
    INVALIDATED    — entry exists but hash differs (stale revision) -> generate;
    REJECTED_REUSE — entry exists + hash matches but policy forbids reuse
                     (unapproved / locked) -> generate, never reuse.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    decisions: Dict[str, str] = Field(default_factory=dict)
    entries: Dict[str, EpisodeCacheEntry] = Field(default_factory=dict)

    @property
    def hits(self) -> int:
        return sum(1 for d in self.decisions.values() if d == EpisodeCacheDecision.HIT.value)

    @property
    def misses(self) -> int:
        return sum(1 for d in self.decisions.values() if d == EpisodeCacheDecision.MISS.value)

    @property
    def invalidated(self) -> int:
        return sum(
            1 for d in self.decisions.values() if d == EpisodeCacheDecision.INVALIDATED.value
        )

    @property
    def rejected(self) -> int:
        return sum(
            1 for d in self.decisions.values() if d == EpisodeCacheDecision.REJECTED_REUSE.value
        )

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "decisions": self.decisions,
                "entries": {k: e.content_hash() for k, e in self.entries.items()},
            }
        )


# ---------------------------------------------------------------------------
# Dependency graph + targeted invalidation (backlog 5)
# ---------------------------------------------------------------------------
class EpisodeDependencyGraph(BaseModel):
    """Directed edges: changing `changed` invalidates `affected`.

    Edges are derived from the fixture: characters/camera/audio/animation
    feed shots, scenes feed shots, shots feed their render, renders feed the
    scene media, scene media feeds the final episode media.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    edges: List[Tuple[str, str]] = Field(default_factory=list)

    @classmethod
    def build_from_fixture(cls, fixture: EpisodeFixture) -> "EpisodeDependencyGraph":
        """Edges use the namespaced ref convention of the invalidation
        planner (shot:sh_1 / scene:scn_1 / character:cm_x / camera:cam_x /
        audio_cue:cue_x / animation:ani_x / environment:env_x /
        render:sh_x / media:scn_x / final:episode)."""
        edges: List[Tuple[str, str]] = []
        scenes = {str(s.scene_id): s for s in fixture.scenes}
        for shot in fixture.shots:
            shot_ref = f"shot:{shot.shot_id}"
            scene_ref = f"scene:{shot.scene_id}"
            edges.append((scene_ref, shot_ref))
            for character in shot.character_ids:
                edges.append((f"character:{character}", shot_ref))
            if shot.camera_intent_ref:
                edges.append((f"camera:{shot.camera_intent_ref}", shot_ref))
            for cue in shot.audio_cue_refs:
                edges.append((f"audio_cue:{cue}", shot_ref))
            for anim in shot.animation_intent_refs:
                edges.append((f"animation:{anim}", shot_ref))
            edges.append((f"shot:{shot.shot_id}", f"render:{shot.shot_id}"))
        for scene_id, spec in scenes.items():
            scene_ref = f"scene:{scene_id}"
            if spec.environment_ref:
                edges.append((f"environment:{spec.environment_ref}", scene_ref))
            for shot_ref in spec.shot_ids:
                edges.append((f"render:{shot_ref}", f"media:{scene_id}"))
            for shot in fixture.shots:
                if str(shot.scene_id) == scene_id:
                    for cue in shot.audio_cue_refs:
                        edges.append((f"audio_cue:{cue}", f"media:{scene_id}"))
            edges.append((f"media:{scene_id}", "final:episode"))
        return cls(edges=edges)

    def downstream(self, refs: List[str]) -> List[str]:
        """Closure of everything invalidated by changing `refs`."""
        affected: List[str] = []
        queue = list(refs)
        seen = set(refs)
        adjacency: Dict[str, List[str]] = {}
        for changed, affected_ref in self.edges:
            adjacency.setdefault(changed, []).append(affected_ref)
        while queue:
            current = queue.pop(0)
            for next_ref in adjacency.get(current, []):
                if next_ref not in seen:
                    seen.add(next_ref)
                    queue.append(next_ref)
                    affected.append(next_ref)
        return affected


class EpisodeInvalidationPlan(BaseModel):
    """Targeted invalidation result (backlog 5)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    changed_refs: List[str] = Field(default_factory=list)
    invalidated: List[str] = Field(default_factory=list)
    preserved: List[str] = Field(default_factory=list)

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "changed_refs": self.changed_refs,
                "invalidated": self.invalidated,
                "preserved": self.preserved,
            }
        )


class EpisodeInvalidationPlanner:
    """Plans invalidation for a set of changed refs against the graph."""

    def plan(
        self,
        graph: EpisodeDependencyGraph,
        changed_refs: List[str],
        known_artifact_refs: List[str],
    ) -> EpisodeInvalidationPlan:
        invalidated = graph.downstream(changed_refs)
        known_set = set(known_artifact_refs)
        invalidated_in_scope = sorted(ref for ref in invalidated if ref in known_set)
        preserved = sorted(ref for ref in known_set if ref not in set(invalidated))
        return EpisodeInvalidationPlan(
            changed_refs=sorted(set(changed_refs)),
            invalidated=invalidated_in_scope,
            preserved=preserved,
        )


# ---------------------------------------------------------------------------
# Parallel branches + timing (backlog 3)
# ---------------------------------------------------------------------------
class EpisodeBranchSpec(BaseModel):
    """One schedulable branch of the episode run."""

    model_config = ConfigDict(frozen=True, extra="allow")

    branch_id: str
    kind: EpisodeBranchKind
    depends_on: List[str] = Field(default_factory=list)
    estimated_seconds: float = 0.0


def build_episode_branch_specs(fixture: EpisodeFixture) -> List[EpisodeBranchSpec]:
    """Default branch DAG: asset/audio prep run in PARALLEL at the top,
    then the per-scene pipeline (compile -> render -> review) serially per
    scene, then post-production."""
    specs: List[EpisodeBranchSpec] = [
        EpisodeBranchSpec(branch_id="asset_prep", kind=EpisodeBranchKind.ASSET_PREP),
        EpisodeBranchSpec(branch_id="audio_prep", kind=EpisodeBranchKind.AUDIO_PREP),
    ]
    scene_ids = [str(s.scene_id) for s in fixture.ordered_scenes()]
    for scene_id in scene_ids:
        compile_id = f"compile:{scene_id}"
        render_id = f"render:{scene_id}"
        review_id = f"review:{scene_id}"
        specs.append(
            EpisodeBranchSpec(
                branch_id=compile_id,
                kind=EpisodeBranchKind.SCENE_COMPILE,
                depends_on=["asset_prep", "audio_prep"],
            )
        )
        specs.append(
            EpisodeBranchSpec(
                branch_id=render_id,
                kind=EpisodeBranchKind.RENDER,
                depends_on=[compile_id],
            )
        )
        specs.append(
            EpisodeBranchSpec(
                branch_id=review_id,
                kind=EpisodeBranchKind.REVIEW_REPAIR,
                depends_on=[render_id],
            )
        )
    specs.append(
        EpisodeBranchSpec(
            branch_id="post",
            kind=EpisodeBranchKind.POST_PRODUCTION,
            depends_on=[f"review:{s}" for s in scene_ids],
        )
    )
    return specs


class EpisodeBranchTiming(BaseModel):
    """One branch's measured schedule (backlog 3)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    branch_id: str
    kind: EpisodeBranchKind
    start_seconds: float = 0.0
    finish_seconds: float = 0.0
    duration_seconds: float = 0.0
    idle_seconds: float = 0.0
    critical: bool = False


class EpisodeTimingReceipt(BaseModel):
    """Critical path + idle time of the parallel episode schedule."""

    model_config = ConfigDict(frozen=True, extra="allow")

    branches: List[EpisodeBranchTiming] = Field(default_factory=list)
    critical_path_seconds: float = 0.0
    parallel_span_seconds: float = 0.0
    idle_total_seconds: float = 0.0

    def timing(self, branch_id: str) -> Optional[EpisodeBranchTiming]:
        for timing in self.branches:
            if timing.branch_id == branch_id:
                return timing
        return None

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "branches": [
                    {
                        "branch_id": b.branch_id,
                        "kind": b.kind.value,
                        "start_seconds": b.start_seconds,
                        "finish_seconds": b.finish_seconds,
                        "duration_seconds": b.duration_seconds,
                        "idle_seconds": b.idle_seconds,
                        "critical": b.critical,
                    }
                    for b in self.branches
                ],
                "critical_path_seconds": self.critical_path_seconds,
                "parallel_span_seconds": self.parallel_span_seconds,
                "idle_total_seconds": self.idle_total_seconds,
            }
        )


class EpisodeBranchScheduler:
    """Computes the parallel schedule: earliest starts, critical path, idle.

    start(branch) = max(finish of deps); finish = start + duration. A branch
    is critical when it lies on the longest path from the roots to the end.
    Idle = the time a branch waits for its slowest dependency.
    """

    def schedule(
        self,
        specs: List[EpisodeBranchSpec],
        durations: Dict[str, float],
    ) -> EpisodeTimingReceipt:
        by_id = {spec.branch_id: spec for spec in specs}
        for spec in specs:
            for dep in spec.depends_on:
                if dep not in by_id:
                    raise EpisodeDependencyCycleError(
                        f"Branch {spec.branch_id} depends on unknown branch {dep}.",
                        details={"branch": spec.branch_id, "dep": dep},
                    )
        # Detect cycles (fail closed).
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(branch_id: str) -> None:
            if branch_id in visiting:
                raise EpisodeDependencyCycleError(
                    f"Cycle detected at branch {branch_id}.",
                    details={"branch": branch_id},
                )
            if branch_id in visited:
                return
            visiting.add(branch_id)
            for dep in by_id[branch_id].depends_on:
                visit(dep)
            visiting.discard(branch_id)
            visited.add(branch_id)

        for branch_id in by_id:
            visit(branch_id)

        starts: Dict[str, float] = {}
        finishes: Dict[str, float] = {}
        for branch_id, spec in by_id.items():
            start = 0.0
            for dep in spec.depends_on:
                start = max(start, finishes[dep])
            duration = durations.get(branch_id, spec.estimated_seconds)
            starts[branch_id] = start
            finishes[branch_id] = start + duration

        end = max(finishes.values(), default=0.0)
        # Trace the critical path back from the branch with the max finish.
        critical: set[str] = set()
        current = max(finishes, key=finishes.get)
        while current is not None:
            critical.add(current)
            spec = by_id[current]
            predecessors = [
                dep for dep in spec.depends_on if finishes[dep] == starts[current]
            ]
            current = predecessors[0] if predecessors else None

        branch_timings: List[EpisodeBranchTiming] = []
        idle_total = 0.0
        # Dependents per branch: for the idle metric we need, per branch,
        # the earliest start among the branches that depend on it.
        dependents: Dict[str, List[str]] = {b: [] for b in by_id}
        for branch_id, spec in by_id.items():
            for dep in spec.depends_on:
                dependents[dep].append(branch_id)
        for branch_id, spec in by_id.items():
            start = starts[branch_id]
            finish = finishes[branch_id]
            duration = finish - start
            dependent_starts = [
                starts[d] for d in dependents[branch_id]
            ]
            # Idle = how long this branch's output waits before its first
            # dependent starts (the worker sits idle after finishing).
            idle = max(0.0, (min(dependent_starts) if dependent_starts else finish) - finish)
            idle_total += idle
            branch_timings.append(
                EpisodeBranchTiming(
                    branch_id=branch_id,
                    kind=spec.kind,
                    start_seconds=start,
                    finish_seconds=finish,
                    duration_seconds=duration,
                    idle_seconds=idle,
                    critical=branch_id in critical,
                )
            )
        span = (end - min(starts.values())) if starts else 0.0
        return EpisodeTimingReceipt(
            branches=branch_timings,
            critical_path_seconds=end,
            parallel_span_seconds=span,
            idle_total_seconds=idle_total,
        )


# ---------------------------------------------------------------------------
# Production report + verdict policy
# ---------------------------------------------------------------------------
class EpisodeProductionReport(BaseModel):
    """Final episode production report (stage_m.md §10)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    run_id: EpisodeRunId
    verdict: EpisodeVerdict
    manifest_hash: str
    fixture_hash: str
    ordering: EpisodeOrderingReceipt = Field(default_factory=EpisodeOrderingReceipt)
    cache_report: EpisodeCacheReport = Field(default_factory=EpisodeCacheReport)
    invalidation_plans: List[EpisodeInvalidationPlan] = Field(default_factory=list)
    receipts: List[EpisodeNodeReceipt] = Field(default_factory=list)
    chunks: List[EpisodeChunkReceipt] = Field(default_factory=list)
    timing: EpisodeTimingReceipt = Field(default_factory=EpisodeTimingReceipt)
    identity_continuity: IdentityContinuityReceipt = Field(
        default_factory=IdentityContinuityReceipt
    )
    technical_verification: TechnicalVerificationReceipt = Field(
        default_factory=TechnicalVerificationReceipt
    )
    repair_entries: List[RepairEntry] = Field(default_factory=list)
    human_approvals: List[HumanApprovalEntry] = Field(default_factory=list)
    summary: str = ""
    decided_at: str = Field(default_factory=lambda: utc_now().isoformat())

    @property
    def repair_count(self) -> int:
        return len(self.repair_entries)

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "run_id": str(self.run_id),
                "verdict": self.verdict.value,
                "manifest_hash": self.manifest_hash,
                "fixture_hash": self.fixture_hash,
                "ordering": self.ordering.ordering_hash(),
                "cache_report": self.cache_report.content_hash(),
                "receipts": [r.content_hash() for r in self.receipts],
                "chunks": [c.content_hash() for c in self.chunks],
                "timing": self.timing.content_hash(),
                "identity_continuity": self.identity_continuity.content_hash(),
                "technical_verification": self.technical_verification.content_hash(),
                "repair_entries": [r.content_hash() for r in self.repair_entries],
                "human_approvals": [a.content_hash() for a in self.human_approvals],
            }
        )


class EpisodeVerdictPolicy:
    """Fail-closed verdict derivation for the multi-scene episode run.

    REJECT when any of:
    - a node receipt is FAILED or CANCELLED (unfinished run);
    - a render chunk is FAILED or CANCELLED (partial rerender not completed);
    - the recorded episode ordering does not match the fixture-derived one;
    - identity/continuity did not pass;
    - technical verification did not pass;
    - any blocking finding on any node was not repaired.
    """

    def decide(
        self,
        receipts: List[EpisodeNodeReceipt],
        chunks: List[EpisodeChunkReceipt],
        ordering_ok: bool,
        identity_continuity: IdentityContinuityReceipt,
        technical_verification: TechnicalVerificationReceipt,
    ) -> EpisodeVerdict:
        for receipt in receipts:
            if not receipt.is_terminal_ok():
                return EpisodeVerdict.REJECT
        for chunk in chunks:
            if not chunk.is_terminal_ok():
                return EpisodeVerdict.REJECT
        if not ordering_ok:
            return EpisodeVerdict.REJECT
        if not identity_continuity.passed:
            return EpisodeVerdict.REJECT
        if not technical_verification.passed:
            return EpisodeVerdict.REJECT
        for receipt in receipts:
            repaired_codes = {
                r.finding_code for r in receipt.repairs if r.outcome == "REPAIRED"
            }
            for finding in receipt.findings:
                if finding.get("blocking") and finding.get("code") not in repaired_codes:
                    return EpisodeVerdict.REJECT
        return EpisodeVerdict.PASS


__all__ = [
    "EpisodeVerdict",
    "EpisodeArtifactKind",
    "EpisodeCacheDecision",
    "EpisodeChunkStatus",
    "EpisodeBranchKind",
    "EpisodeShotSpec",
    "EpisodeSceneSpec",
    "EpisodeFixture",
    "EpisodeRunManifest",
    "EpisodeOrderingReceipt",
    "EpisodeNodeReceipt",
    "EpisodeArtifactRecord",
    "EpisodeChunkSpec",
    "EpisodeChunkReceipt",
    "EpisodeCheckpoint",
    "EpisodeResumePlanner",
    "EpisodeCacheEntry",
    "EpisodeCacheReport",
    "EpisodeDependencyGraph",
    "EpisodeInvalidationPlan",
    "EpisodeInvalidationPlanner",
    "EpisodeBranchSpec",
    "build_episode_branch_specs",
    "EpisodeBranchTiming",
    "EpisodeTimingReceipt",
    "EpisodeBranchScheduler",
    "EpisodeProductionReport",
    "EpisodeVerdictPolicy",
    "EpisodeValidationError",
    "EpisodeDependencyCycleError",
    "utc_now",
]
