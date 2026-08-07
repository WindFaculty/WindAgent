"""
VP3D Phase 1 — Canonical Production IR models (engine-neutral).

The IR describes CINEMATIC INTENT — actors, action, camera, duration, dialogue,
lighting, simulation and render quality — and NEVER describes a provider,
a legacy generative-video mode, browser runtime, or engine SDK
(`bpy`, Unreal). The engine adapter (Blender, Unreal, ...) compiles this IR
onto its own execution path (plan §4, road_map.md Phase 1).

Design rules:

- Every entity has a stable opaque ID (never derived from a display name).
- Models are frozen (immutable) with `extra="allow"` so additive compatible
  fields are accepted within MAJOR version 1 (forward compatibility policy,
  same as VideoProductionPackage v1).
- `.blend` is ALWAYS a derived artifact; validation fails closed if a
  non-derived AssetReference uses `IrAssetFormat.BLEND`.
- The document content hash covers the logical content (scenes/shots/tracks/
  profiles) and excludes provenance + lock state so the same authored content
  always hashes identically.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from windagent_core.domain.video_production.enums import (
    CameraAngle,
    CameraMovement,
    CameraSide,
    ScreenDirection,
    ShotType,
    TransitionType,
)
from windagent_core.domain.video_production.errors import UnsupportedMajorVersionError
from windagent_core.domain.video_production.ids import (
    AnimationTrackId,
    CameraTrackId,
    CharacterId,
    CharacterInstanceId,
    DerivedArtifactId,
    DialogueLineId,
    DialogueTrackId,
    EngineJobId,
    EnvironmentInstanceId,
    FacialTrackId,
    LightRigId,
    LocationId,
    ProductionIrId,
    ProductionRevisionId,
    PropId,
    PropInstanceId,
    ReferenceAssetId,
    RenderIntentId,
    RenderProfileId,
    SceneDescriptionId,
    SceneId,
    ShotExecutionIntentId,
    ShotId,
    SimulationTrackId,
    TtsAudioAssetId,
    VideoProjectId,
)
from windagent_core.domain.video_production.production_ir.enums import (
    DerivedArtifactKind,
    EngineJobStatus,
    IrAssetFormat,
    LipSyncSource,
    RenderQuality,
    SimulationKind,
)

PRODUCTION_IR_VERSION = "1.0.0"
SUPPORTED_IR_MAJOR_VERSION = 1
DEFAULT_RENDER_PROFILE_ID = "rp_default"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Deep immutability primitives
# ---------------------------------------------------------------------------
class FrozenDict(dict):
    """A dict that blocks every mutating operation (deep-immutability).

    Subclasses `dict` so Pydantic's model_dump/model_dump_json keep working;
    mutation is rejected at runtime with TypeError. Nested values are frozen
    recursively by `_deep_freeze`.
    """

    def __setitem__(self, key, value):  # noqa: D105
        raise TypeError("FrozenDict is immutable")

    def __delitem__(self, key):  # noqa: D105
        raise TypeError("FrozenDict is immutable")

    def update(self, *args, **kwargs):  # noqa: D102
        raise TypeError("FrozenDict is immutable")

    def pop(self, *args, **kwargs):  # noqa: D102
        raise TypeError("FrozenDict is immutable")

    def popitem(self):  # noqa: D102
        raise TypeError("FrozenDict is immutable")

    def clear(self):  # noqa: D102
        raise TypeError("FrozenDict is immutable")

    def setdefault(self, key, default=None):  # noqa: D102
        raise TypeError("FrozenDict is immutable")

    def __ior__(self, other):  # noqa: D105
        raise TypeError("FrozenDict is immutable")

    def __deepcopy__(self, memo):  # noqa: D105
        return FrozenDict(
            {copy.deepcopy(k, memo): copy.deepcopy(v, memo) for k, v in self.items()}
        )

    def __copy__(self):  # noqa: D105
        return FrozenDict(dict(self))


class FrozenList(list):
    """A list that blocks every mutating operation (deep-immutability)."""

    def __setitem__(self, index, value):  # noqa: D105
        raise TypeError("FrozenList is immutable")

    def __delitem__(self, index):  # noqa: D105
        raise TypeError("FrozenList is immutable")

    def append(self, value):  # noqa: D102
        raise TypeError("FrozenList is immutable")

    def extend(self, values):  # noqa: D102
        raise TypeError("FrozenList is immutable")

    def insert(self, index, value):  # noqa: D102
        raise TypeError("FrozenList is immutable")

    def pop(self, *args, **kwargs):  # noqa: D102
        raise TypeError("FrozenList is immutable")

    def remove(self, value):  # noqa: D102
        raise TypeError("FrozenList is immutable")

    def clear(self):  # noqa: D102
        raise TypeError("FrozenList is immutable")

    def __iadd__(self, other):  # noqa: D105
        raise TypeError("FrozenList is immutable")

    def __imul__(self, other):  # noqa: D105
        raise TypeError("FrozenList is immutable")

    def sort(self, *args, **kwargs):  # noqa: D102
        raise TypeError("FrozenList is immutable")

    def reverse(self):  # noqa: D102
        raise TypeError("FrozenList is immutable")

    def __deepcopy__(self, memo):  # noqa: D105
        return FrozenList(copy.deepcopy(v, memo) for v in self)

    def __copy__(self):  # noqa: D105
        return FrozenList(iter(self))


def _deep_freeze(value: Any) -> Any:
    """Recursively convert dict/list containers into their frozen proxies."""
    if isinstance(value, dict):
        return FrozenDict({k: _deep_freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return FrozenList(_deep_freeze(v) for v in value)
    return value


class ProductionIrModel(BaseModel):
    """Base for all engine-neutral IR models.

    `frozen=True` already blocks attribute reassignment; this additionally
    deep-freezes contained lists/dicts (including nested ones) so the IR is
    genuinely immutable, not just shallowly frozen.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    def model_post_init(self, __context: Any) -> None:
        # `type(self).model_fields` (not `self.model_fields`) avoids the
        # Pydantic deprecation of instance-level model_fields access while
        # preserving deep immutability, serialization and model_copy(deep=True).
        for name in type(self).model_fields:
            value = getattr(self, name)
            frozen = _deep_freeze(value)
            if frozen is not value:
                object.__setattr__(self, name, frozen)


# ---------------------------------------------------------------------------
# Asset references (engine-neutral, URI + hash addressed)
# ---------------------------------------------------------------------------
class AssetReference(ProductionIrModel):
    """A content-addressed asset the IR points at.

    `uri` + `content_hash` identify the bytes; `format` is the interchange
    format. `derived` marks artifacts produced BY the pipeline (`.blend` is
    always derived; source assets such as glTF/FBX/USD are not).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    asset_id: ReferenceAssetId
    role: str = Field(min_length=1)  # e.g. CHARACTER_MESH | SKELETON | TEXTURE | ENVIRONMENT | PROP
    uri: str = ""
    format: IrAssetFormat = IrAssetFormat.UNKNOWN
    content_hash: str = Field(min_length=64, max_length=64)
    derived: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Instances
# ---------------------------------------------------------------------------
class CharacterInstance(ProductionIrModel):
    """One character as it appears in an IR scene.

    `character_id` is the stable CharacterMaster id; the same id is reused
    across episodes/shots so continuity is preserved (road_map.md Phase 8).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    instance_id: CharacterInstanceId
    character_id: CharacterId
    display_name: str = ""
    mesh: Optional[AssetReference] = None
    skeleton: Optional[AssetReference] = None
    materials: List[AssetReference] = Field(default_factory=list)
    rig_profile: str = ""
    scale: float = Field(default=1.0, gt=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PropInstance(ProductionIrModel):
    """One prop placed in an IR scene."""

    model_config = ConfigDict(frozen=True, extra="allow")

    instance_id: PropInstanceId
    prop_id: PropId
    asset: Optional[AssetReference] = None
    placement_hint: str = ""  # engine-neutral placement description
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EnvironmentInstance(ProductionIrModel):
    """One environment / set in an IR scene."""

    model_config = ConfigDict(frozen=True, extra="allow")

    instance_id: EnvironmentInstanceId
    location_id: LocationId
    asset: Optional[AssetReference] = None
    environment_style: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------
class CameraTrack(ProductionIrModel):
    """Camera intent for one shot (engine-neutral cinematography)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    track_id: CameraTrackId
    shot_type: ShotType = ShotType.MEDIUM
    angle: CameraAngle = CameraAngle.EYE_LEVEL
    movement: CameraMovement = CameraMovement.STATIC
    lens_intent: str = ""
    position_intent: str = ""
    camera_side: CameraSide = CameraSide.NEUTRAL  # 180-degree rule
    screen_direction: ScreenDirection = ScreenDirection.NEUTRAL
    duration_seconds: float = Field(gt=0)
    frame_rate: int = Field(default=24, ge=1)
    aspect_ratio: str = "16:9"
    transition_type: TransitionType = TransitionType.CUT
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AnimationTrack(ProductionIrModel):
    """Actor/object animation intent (e.g. ``walk_to desk_01``)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    track_id: AnimationTrackId
    target_instance_ids: List[str] = Field(default_factory=list)
    action: str = Field(min_length=1)
    reference_uri: str = ""
    reference_hash: str = ""
    timing: Dict[str, Any] = Field(default_factory=dict)
    loop: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FacialTrack(ProductionIrModel):
    """Facial performance intent: emotion beats + optional lip-sync source."""

    model_config = ConfigDict(frozen=True, extra="allow")

    track_id: FacialTrackId
    character_instance_id: str = Field(min_length=1)
    emotion_beats: List[Dict[str, Any]] = Field(default_factory=list)
    lip_sync_source: LipSyncSource = LipSyncSource.NONE
    audio_track_ids: List[DialogueTrackId] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DialogueTrack(ProductionIrModel):
    """Per-shot dialogue binding (value object — no own identity).

    References the screenplay dialogue lines and the audio-pipeline tracks
    (by `DialogueTrackId`) that play during the shot. The audio pipeline is
    the source of truth for the audio bytes; the IR binds them to the shot.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    dialogue_line_ids: List[DialogueLineId] = Field(default_factory=list)
    audio_track_ids: List[DialogueTrackId] = Field(default_factory=list)
    audio_asset_ids: List[TtsAudioAssetId] = Field(default_factory=list)
    target_start_seconds: float = Field(default=0.0, ge=0)
    target_end_seconds: float = Field(default=0.0, ge=0)
    lip_sync: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LightRig(ProductionIrModel):
    """Lighting intent for a scene (engine-neutral rig description)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    rig_id: LightRigId
    lighting_profile: str = "daylight"
    key_light: Dict[str, Any] = Field(default_factory=dict)
    fill_light: Dict[str, Any] = Field(default_factory=dict)
    rim_light: Dict[str, Any] = Field(default_factory=dict)
    environment_light: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SimulationTrack(ProductionIrModel):
    """Simulation intent (cloth/hair/fluid/particles/...)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    track_id: SimulationTrackId
    kind: SimulationKind = SimulationKind.CLOTH
    target_instance_ids: List[str] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Render intent
# ---------------------------------------------------------------------------
class RenderProfile(ProductionIrModel):
    """Engine-neutral render quality intent.

    `engine_hint` is a NON-authoritative preference (e.g. "cycles"); the
    engine adapter decides the actual configuration. `quality` is the
    authoritative ladder the adapter maps to concrete settings.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    profile_id: RenderProfileId
    quality: RenderQuality = RenderQuality.HIGH
    engine_hint: str = ""
    samples: int = Field(default=64, ge=1)
    resolution: Dict[str, int] = Field(default_factory=lambda: {"width": 1920, "height": 1080})
    denoise: bool = True
    adaptive_sampling: bool = True
    output_format: IrAssetFormat = IrAssetFormat.PNG
    frame_rate: int = Field(default=24, ge=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RenderIntent(ProductionIrModel):
    """What to render: scenes/shots, frame range, profile and output target."""

    model_config = ConfigDict(frozen=True, extra="allow")

    intent_id: RenderIntentId
    scene_id: SceneDescriptionId
    shot_execution_intent_ids: List[ShotExecutionIntentId] = Field(default_factory=list)
    profile: RenderProfile = Field(
        default_factory=lambda: RenderProfile(profile_id=RenderProfileId(DEFAULT_RENDER_PROFILE_ID))
    )
    frame_start: int = Field(default=1, ge=1)
    frame_end: int = Field(default=0, ge=0)  # 0 = derive from shot durations
    output_uri_template: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scene + shot intent
# ---------------------------------------------------------------------------
class SceneDescription(ProductionIrModel):
    """One IR scene: instances, environment, lights and scene action."""

    model_config = ConfigDict(frozen=True, extra="allow")

    scene_id: SceneDescriptionId
    screenplay_scene_id: SceneId
    characters: List[CharacterInstance] = Field(default_factory=list)
    props: List[PropInstance] = Field(default_factory=list)
    environment: List[EnvironmentInstance] = Field(default_factory=list)
    light_rigs: List[LightRig] = Field(default_factory=list)
    action: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ShotExecutionIntent(ProductionIrModel):
    """Engine-neutral execution intent for ONE shot.

    Describes actors/action/camera/duration/dialogue/assets — NOT how any
    engine should realize them. The engine adapter compiles this intent
    (road_map.md Phase 1: shot no longer names a generative-video mode; it says
    characters/action/camera/duration/dialogue).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    intent_id: ShotExecutionIntentId
    shot_id: ShotId
    scene_id: SceneDescriptionId
    order: int = Field(ge=1)
    characters: List[str] = Field(default_factory=list)  # CharacterInstanceId refs
    props: List[str] = Field(default_factory=list)  # PropInstanceId refs
    environment: List[str] = Field(default_factory=list)  # EnvironmentInstanceId refs
    action: str = ""
    camera: CameraTrack
    animation_tracks: List[AnimationTrack] = Field(default_factory=list)
    facial_tracks: List[FacialTrack] = Field(default_factory=list)
    dialogue_tracks: List[DialogueTrack] = Field(default_factory=list)
    light_rig_ids: List[LightRigId] = Field(default_factory=list)
    simulation_tracks: List[SimulationTrack] = Field(default_factory=list)
    duration_seconds: float = Field(gt=0)
    render_profile_id: RenderProfileId
    creative_prompt: str = ""  # separated creative value; provider parts live in adapters
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------
class ProductionIrDocument(ProductionIrModel):
    """Canonical engine-neutral IR document (VP3D Phase 1).

    `source_package_hash` ties the IR back to the VideoProductionPackage v1
    it was migrated from. The document is immutable; any change creates a new
    revision (locked revisions must not be mutated).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    ir_id: ProductionIrId
    schema_version: str = PRODUCTION_IR_VERSION
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    source_package_hash: str = Field(default="", max_length=64)
    scenes: List[SceneDescription] = Field(default_factory=list)
    shots: List[ShotExecutionIntent] = Field(default_factory=list)
    render_profiles: List[RenderProfile] = Field(default_factory=list)
    render_intents: List[RenderIntent] = Field(default_factory=list)
    locked: bool = False
    approval_state_ref: str = ""  # target approval content hash reference
    provenance: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def _validate_major_version(cls, v: str) -> str:
        major = int(v.split(".")[0])
        if major != SUPPORTED_IR_MAJOR_VERSION:
            raise UnsupportedMajorVersionError(
                f"Unsupported ProductionIrDocument major version {major}; "
                f"supported major is {SUPPORTED_IR_MAJOR_VERSION}.",
                details={"schema_version": v, "supported_major": SUPPORTED_IR_MAJOR_VERSION},
            )
        return v

    # Provenance and lock state are operational metadata: the SAME logical
    # authored content always hashes identically regardless of when/where it
    # was produced or whether it is currently locked.
    CONTENT_HASH_EXCLUDED_FIELDS: ClassVar[tuple[str, ...]] = (
        "provenance",
        "locked",
        "approval_state_ref",
    )

    def to_canonical_dict(self) -> Dict[str, Any]:
        """JSON-compatible canonical dict (UTC ISO timestamps, sorted keys)."""
        return json.loads(self.model_dump_json())

    def to_content_dict(self) -> Dict[str, Any]:
        data = self.to_canonical_dict()
        for excluded in self.CONTENT_HASH_EXCLUDED_FIELDS:
            data.pop(excluded, None)
        return data

    def canonical_bytes(self) -> bytes:
        canonical = json.dumps(
            self.to_content_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return canonical.encode("utf-8")

    def content_hash(self) -> str:
        """Stable SHA-256 over the logical IR content."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def serialize(self) -> str:
        """Serialize the FULL document to canonical JSON (round-trip stable)."""
        data = json.loads(self.model_dump_json())
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def deserialize(cls, raw: str) -> "ProductionIrDocument":
        return cls.model_validate(json.loads(raw))


# ---------------------------------------------------------------------------
# Engine job surface (used by ProductionEnginePort)
# ---------------------------------------------------------------------------
class EngineJobReceipt(ProductionIrModel):
    """Receipt returned by an engine adapter for a submitted IR unit."""

    model_config = ConfigDict(frozen=True, extra="allow")

    job_id: EngineJobId
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    ir_hash: str = Field(default="", max_length=64)
    status: EngineJobStatus = EngineJobStatus.SUBMITTED
    engine_name: str = ""
    submitted_at: datetime = Field(default_factory=utc_now)
    artifact_uris: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DerivedArtifact(ProductionIrModel):
    """An artifact the engine adapter published from an IR unit.

    `.blend` outputs are DerivedArtifact with kind SCENE_BLEND; they are
    always derived from the IR, never a source of truth.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    artifact_id: DerivedArtifactId
    job_id: EngineJobId
    kind: DerivedArtifactKind
    uri: str = ""
    format: IrAssetFormat = IrAssetFormat.UNKNOWN
    content_hash: str = Field(min_length=64, max_length=64)
    derived_from_ir_hash: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "utc_now",
    "PRODUCTION_IR_VERSION",
    "SUPPORTED_IR_MAJOR_VERSION",
    "DEFAULT_RENDER_PROFILE_ID",
    "AssetReference",
    "CharacterInstance",
    "PropInstance",
    "EnvironmentInstance",
    "CameraTrack",
    "AnimationTrack",
    "FacialTrack",
    "DialogueTrack",
    "LightRig",
    "SimulationTrack",
    "RenderProfile",
    "RenderIntent",
    "SceneDescription",
    "ShotExecutionIntent",
    "ProductionIrDocument",
    "EngineJobReceipt",
    "DerivedArtifact",
]
