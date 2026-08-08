"""
Stage H AI Motion Adapter domain (VP3D Phase 17 — AI Motion Adapter).

Frozen, engine-neutral DTOs for AI motion generation: the provider capability
contract, the typed generation request, the QUARANTINED raw artifact, the
skeleton remap receipt and the approved/retried candidates. No ``bpy``, no
provider SDK, no code execution: the adapter layer
(`intelligence/windagent_intelligence/video/ai_motion/`) runs the pipeline

    TextToMotionPort / VideoToMotionPort / MotionGenerationPort
    -> raw motion artifact        (quarantined, never imported directly)
    -> skeleton remap             (fail-closed on missing semantic bones)
    -> joint/foot/collision validation  (SAME thresholds as library/mocap)
    -> retarget                   (Stage D profile, Phase 15 RetargetService)
    -> approved AnimationTrack

Semantics (stage_h §5):
- Capability contract (backlog 1): every request must fit the provider's
  declared skeleton set, fps range, duration range, seed support, license
  states and output formats; a non-fitting request fails closed with
  `MotionCapabilityMismatchError` — no silent adaptation.
- Request provenance (backlog 2): every generation carries a deterministic
  request hash over provider/model/version, prompt hash, seed, fps, duration
  and skeleton, plus cost and provenance on the artifact.
- Quarantine (backlog 3): a raw artifact is inert data. It carries no track
  and there is no path from it to a production scene except the adapter's
  approve chain; any direct import attempt raises
  `MotionQuarantineViolationError`. Provider metadata is stored but never
  executed and never copied into the track (allow-list only).
- Fair comparison (backlog 4): the validator reuses the exact thresholds of
  the library/mocap and procedural validators — FOOT_SLIDING_MAX_M,
  MAX_JOINT_VIOLATIONS, MAX_COLLISIONS, MAX_BALANCE_OFFSET_M,
  ROOT_DRIFT_TOLERANCE, DURATION_TOLERANCE_FRAMES — so an AI motion is
  judged by the same numbers as a mocap clip.
- Fallback (backlog 5): a failing artifact is rejected; the caller falls
  back to library/procedural or human review. Validation is NEVER bypassed.
- Retry (backlog 6): retry is per cause and budget — only transient provider
  failures retry within the budget; validation/capability/license failures
  never retry. A different seed is a NEW candidate, never an overwrite.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.animation import (
    DURATION_TOLERANCE_FRAMES,
    ROOT_DRIFT_TOLERANCE,
)
from windagent_core.domain.video_production.enums import (
    LicenseState,
    MotionCandidateStatus,
    MotionOutputFormat,
    MotionRetryKind,
    SemanticBone,
)
from windagent_core.domain.video_production.ids import (
    MotionCapabilityId,
    MotionCandidateId,
    MotionFindingId,
    MotionRequestId,
    RawMotionArtifactId,
    SkeletonProfileId,
    SkeletonRemapReceiptId,
)
from windagent_core.domain.video_production.procedural import (
    FOOT_SLIDING_MAX_M,
    MAX_BALANCE_OFFSET_M,
    MAX_COLLISIONS,
    MAX_JOINT_VIOLATIONS,
)

MOTION_ADAPTER_COMPILER_VERSION = "1.0.0"
MOTION_CAPABILITY_SCHEMA_VERSION = "1.0.0"
MOTION_REQUEST_SCHEMA_VERSION = "1.0.0"
MOTION_ARTIFACT_SCHEMA_VERSION = "1.0.0"

# Executable markers that are NEVER allowed to ride provider metadata into a
# production artifact (stage_h §6: malicious AI motion metadata must not be
# executed). The check is string-level: metadata is inert data, and the
# adapter only ever copies allow-listed provenance fields into a track.
MALICIOUS_METADATA_MARKERS = (
    "eval(",
    "exec(",
    "__import__",
    "subprocess",
    "os.system",
    "pickle.loads",
)


def _stable_hash(*parts: str) -> str:
    canonical = json.dumps(list(parts), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Capability contract (backlog 1)
# ---------------------------------------------------------------------------
class MotionCapability(BaseModel):
    """What one provider can do — the capability contract (backlog 1).

    A request must fit: supported skeletons, fps and duration ranges, seed
    support, accepted licenses and output formats. Anything outside fails
    closed with `MotionCapabilityMismatchError` — the adapter never silently
    adapts a request the provider cannot honor.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    capability_id: MotionCapabilityId
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    supported_skeletons: List[SkeletonProfileId] = Field(default_factory=list)
    fps_min: int = Field(ge=1)
    fps_max: int = Field(ge=1)
    duration_min_seconds: float = Field(gt=0)
    duration_max_seconds: float = Field(gt=0)
    supports_seed: bool = True
    licenses: List[LicenseState] = Field(default_factory=list)
    output_formats: List[MotionOutputFormat] = Field(default_factory=list)
    max_retry_budget: int = Field(default=2, ge=0)
    description: str = ""


# ---------------------------------------------------------------------------
# Generation request (backlog 2 — full provenance)
# ---------------------------------------------------------------------------
class MotionGenerationRequest(BaseModel):
    """One AI motion generation request (backlog 2).

    `request_hash` is deterministic over provider/model/version, prompt hash,
    seed, fps, duration, skeleton and format — the same request always hashes
    the same, so cost/provenance per generation is traceable. `prompt_hash`
    is the sha256 of the prompt text; the prompt itself never enters the
    production artifact.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    request_id: MotionRequestId
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    prompt_hash: str = Field(min_length=1)
    skeleton_profile_id: SkeletonProfileId
    fps: int = Field(ge=1)
    duration_seconds: float = Field(gt=0)
    seed: int = Field(ge=0)
    output_format: MotionOutputFormat = MotionOutputFormat.RAW_JSON
    retry_budget: int = Field(default=2, ge=0)
    episode_id: str = ""
    actor_id: str = Field(min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    request_hash: str = ""

    def compute_stable_hash(self) -> str:
        payload = json.loads(
            self.model_dump_json(exclude={"request_hash", "metadata", "prompt"}))
        canonical = json.dumps(
            {"schema_version": MOTION_REQUEST_SCHEMA_VERSION,
             "request": json.loads(json.dumps(payload, sort_keys=True,
                                              default=str))},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Raw artifact — QUARANTINED by construction (backlog 3)
# ---------------------------------------------------------------------------
class RawMotionArtifact(BaseModel):
    """Raw provider output. QUARANTINED: inert data, never a track.

    The artifact carries the provider's claimed `motion_metrics` and opaque
    `raw_payload` plus arbitrary `metadata`. None of it is executed, parsed
    for behavior or copied into the production track: the adapter only
    forwards allow-listed provenance fields (provider/model/version, prompt
    hash, seed, cost, license). There is deliberately no track field and no
    approved flag here — the only path to a scene is the adapter's approve
    chain, and any direct import attempt fails closed.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    artifact_id: RawMotionArtifactId
    request_id: MotionRequestId
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    prompt_hash: str = Field(min_length=1)
    seed: int = Field(ge=0)
    claimed_skeleton_profile_id: SkeletonProfileId
    fps: int = Field(ge=1)
    duration_seconds: float = Field(gt=0)
    output_format: MotionOutputFormat = MotionOutputFormat.RAW_JSON
    raw_payload: str = ""
    motion_metrics: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    cost: float = Field(default=0.0, ge=0)
    license: LicenseState = LicenseState.UNKNOWN
    received_at: str = ""
    content_hash: str = ""

    def compute_stable_hash(self) -> str:
        payload = json.loads(
            self.model_dump_json(exclude={"content_hash", "received_at"}))
        canonical = json.dumps(
            {"schema_version": MOTION_ARTIFACT_SCHEMA_VERSION,
             "artifact": json.loads(json.dumps(payload, sort_keys=True,
                                               default=str))},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Skeleton remap (pipeline step 2)
# ---------------------------------------------------------------------------
class SkeletonRemapReceipt(BaseModel):
    """Result of remapping the artifact's claimed skeleton (step 2).

    Fail-closed: `missing_bones` are semantic roles the target skeleton must
    provide but does not; the adapter refuses to continue when any are
    missing (no silent pose drop, stage_d §5 / stage_h §5).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    receipt_id: SkeletonRemapReceiptId
    artifact_id: RawMotionArtifactId
    source_skeleton: SkeletonProfileId
    target_skeleton: SkeletonProfileId
    mapped_bones: List[SemanticBone] = Field(default_factory=list)
    missing_bones: List[SemanticBone] = Field(default_factory=list)
    ok: bool = False


# ---------------------------------------------------------------------------
# Candidate (backlog 6 — new seed = new candidate, never overwrite)
# ---------------------------------------------------------------------------
class MotionCandidate(BaseModel):
    """One generation candidate for a request (backlog 6).

    Candidates are keyed by (request_id, seed): a different seed is a NEW
    candidate and never overwrites an existing one. `status` walks
    QUARANTINED -> REMAPPED -> APPROVED, or REJECTED when validation blocks.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    candidate_id: MotionCandidateId
    request_id: MotionRequestId
    artifact_id: RawMotionArtifactId
    seed: int = Field(ge=0)
    status: MotionCandidateStatus = MotionCandidateStatus.QUARANTINED
    remap: Optional[SkeletonRemapReceipt] = None
    validation_ok: bool = False
    blocking_kinds: List[str] = Field(default_factory=list)
    approved_track_id: str = ""
    created_at: str = ""

    def compute_stable_hash(self) -> str:
        payload = json.loads(self.model_dump_json(exclude={"created_at"}))
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Findings + validation (fail-closed, backlog 4/5)
# ---------------------------------------------------------------------------
class MotionFindingKind:
    """Typed AI motion finding kinds (stage_h §5 backlog 1-6 / §6 matrix)."""

    CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
    SKELETON_REMAP_FAILED = "SKELETON_REMAP_FAILED"
    FPS_OUT_OF_RANGE = "FPS_OUT_OF_RANGE"
    DURATION_OUT_OF_RANGE = "DURATION_OUT_OF_RANGE"
    FORMAT_UNSUPPORTED = "FORMAT_UNSUPPORTED"
    LICENSE_BLOCKED = "LICENSE_BLOCKED"
    MALICIOUS_METADATA = "MALICIOUS_METADATA"
    # Same validation axes as library/mocap (backlog 4): identical thresholds.
    JOINT_LIMIT_VIOLATED = "JOINT_LIMIT_VIOLATED"
    FOOT_SLIDING = "FOOT_SLIDING"
    COLLISION = "COLLISION"
    BALANCE_VIOLATED = "BALANCE_VIOLATED"
    ROOT_DRIFT = "ROOT_DRIFT"
    DURATION_MISMATCH = "DURATION_MISMATCH"
    FPS_MISMATCH = "FPS_MISMATCH"


class MotionFinding(BaseModel):
    """One typed AI motion finding (blocking or advisory)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: MotionFindingId
    kind: str
    detail: str = ""
    blocking: bool = False
    measured: Dict[str, Any] = Field(default_factory=dict)


class MotionValidationReport(BaseModel):
    """Aggregate result of AI motion validation over one artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool = False
    findings: List[MotionFinding] = Field(default_factory=list)
    checked_entity_count: int = Field(default=0, ge=0)

    @property
    def blocking_findings(self) -> List[MotionFinding]:
        return [f for f in self.findings if f.blocking]

    @property
    def blocking_kinds(self) -> List[str]:
        return sorted({f.kind for f in self.blocking_findings})


class MotionValidator:
    """Fail-closed AI motion validation (stage_h §5 backlog 1/4/5).

    Pure string/math checks; never executes anything and never parses the
    raw payload. Thresholds are the SAME constants the library/mocap and
    procedural validators use, so AI motion is judged fairly against the
    same numbers (backlog 4).
    """

    def validate_capability_fit(
        self,
        *,
        capability: MotionCapability,
        request: MotionGenerationRequest,
        finding_prefix: str = "mo",
    ) -> MotionValidationReport:
        findings: List[MotionFinding] = []

        def _add(kind: str, detail: str, **measured: Any) -> None:
            findings.append(MotionFinding(
                finding_id=MotionFindingId(f"{finding_prefix}:{kind}"),
                kind=kind, detail=detail, blocking=True, measured=measured))

        if str(request.skeleton_profile_id) not in {
                str(s) for s in capability.supported_skeletons}:
            _add(MotionFindingKind.CAPABILITY_MISMATCH,
                 f"skeleton {request.skeleton_profile_id} not supported by "
                 f"{capability.provider}",
                 skeleton=str(request.skeleton_profile_id),
                 supported=sorted(str(s) for s in
                                  capability.supported_skeletons))
        if not (capability.fps_min <= request.fps <= capability.fps_max):
            _add(MotionFindingKind.FPS_OUT_OF_RANGE,
                 f"fps {request.fps} outside [{capability.fps_min}, "
                 f"{capability.fps_max}]",
                 fps=request.fps, fps_min=capability.fps_min,
                 fps_max=capability.fps_max)
        if not (capability.duration_min_seconds <= request.duration_seconds
                <= capability.duration_max_seconds):
            _add(MotionFindingKind.DURATION_OUT_OF_RANGE,
                 f"duration {request.duration_seconds}s outside "
                 f"[{capability.duration_min_seconds}, "
                 f"{capability.duration_max_seconds}]",
                 duration_seconds=request.duration_seconds,
                 duration_min=capability.duration_min_seconds,
                 duration_max=capability.duration_max_seconds)
        if request.output_format not in capability.output_formats:
            _add(MotionFindingKind.FORMAT_UNSUPPORTED,
                 f"format {request.output_format.value} not offered",
                 format=request.output_format.value,
                 offered=[f.value for f in capability.output_formats])
        if request.seed != 0 and not capability.supports_seed:
            _add(MotionFindingKind.CAPABILITY_MISMATCH,
                 f"provider does not support seeds, request used "
                 f"{request.seed}", seed=request.seed)
        return MotionValidationReport(
            ok=not findings, findings=findings,
            checked_entity_count=1)

    def validate_artifact(
        self,
        *,
        artifact: RawMotionArtifact,
        remap: Optional[SkeletonRemapReceipt] = None,
        finding_prefix: str = "mo",
    ) -> MotionValidationReport:
        findings: List[MotionFinding] = []

        def _add(kind: str, detail: str, **measured: Any) -> None:
            findings.append(MotionFinding(
                finding_id=MotionFindingId(f"{finding_prefix}:{kind}"),
                kind=kind, detail=detail, blocking=True, measured=measured))

        # Malicious metadata (stage_h §6): string-level marker check. The
        # metadata is inert data — it is never executed, and the adapter
        # never copies it into the production track.
        payload = json.dumps(artifact.metadata, default=str)
        hit = next((m for m in MALICIOUS_METADATA_MARKERS if m in payload), "")
        if hit:
            _add(MotionFindingKind.MALICIOUS_METADATA,
                 f"provider metadata carries executable marker '{hit}'; "
                 f"metadata is discarded and never executed",
                 marker=hit)

        # License (backlog 1/§7): UNKNOWN or REJECTED never enters production.
        if artifact.license in (LicenseState.UNKNOWN, LicenseState.REJECTED):
            _add(MotionFindingKind.LICENSE_BLOCKED,
                 f"artifact license {artifact.license.value} is not "
                 f"production-safe",
                 license=artifact.license.value)

        # Same metrics + thresholds as library/mocap/procedural (backlog 4).
        joint_violations = int(artifact.motion_metrics.get(
            "joint_violations", 0))
        if joint_violations > MAX_JOINT_VIOLATIONS:
            _add(MotionFindingKind.JOINT_LIMIT_VIOLATED,
                 f"{joint_violations} joint limit violations > "
                 f"{MAX_JOINT_VIOLATIONS}",
                 joint_violations=joint_violations,
                 max_joint_violations=MAX_JOINT_VIOLATIONS)
        foot_sliding = float(artifact.motion_metrics.get("foot_sliding_m", 0.0))
        if foot_sliding > FOOT_SLIDING_MAX_M:
            _add(MotionFindingKind.FOOT_SLIDING,
                 f"foot sliding {foot_sliding:.3f}m > "
                 f"{FOOT_SLIDING_MAX_M}m",
                 foot_sliding_m=foot_sliding,
                 foot_sliding_max_m=FOOT_SLIDING_MAX_M)
        collisions = int(artifact.motion_metrics.get("collision_count", 0))
        if collisions > MAX_COLLISIONS:
            _add(MotionFindingKind.COLLISION,
                 f"{collisions} collisions > {MAX_COLLISIONS}",
                 collision_count=collisions, max_collisions=MAX_COLLISIONS)
        balance_offset = float(artifact.motion_metrics.get(
            "balance_offset_m", 0.0))
        if balance_offset > MAX_BALANCE_OFFSET_M:
            _add(MotionFindingKind.BALANCE_VIOLATED,
                 f"balance offset {balance_offset:.3f}m > "
                 f"{MAX_BALANCE_OFFSET_M}m",
                 balance_offset_m=balance_offset,
                 max_balance_offset_m=MAX_BALANCE_OFFSET_M)
        root_drift = float(artifact.motion_metrics.get("root_drift", 0.0))
        if root_drift > ROOT_DRIFT_TOLERANCE:
            _add(MotionFindingKind.ROOT_DRIFT,
                 f"root drift {root_drift:.2%} > {ROOT_DRIFT_TOLERANCE:.0%}",
                 root_drift=root_drift,
                 root_drift_tolerance=ROOT_DRIFT_TOLERANCE)
        # fps/duration mismatch against the requested contract (stage_h §6).
        requested_fps = int(artifact.motion_metrics.get(
            "requested_fps", artifact.fps))
        if artifact.fps != requested_fps:
            _add(MotionFindingKind.FPS_MISMATCH,
                 f"artifact fps {artifact.fps} deviates from the requested "
                 f"{requested_fps}",
                 artifact_fps=artifact.fps, requested_fps=requested_fps)
        target_frames = round(artifact.duration_seconds * artifact.fps)
        actual_frames = int(artifact.motion_metrics.get(
            "frame_count", target_frames))
        if abs(actual_frames - target_frames) > DURATION_TOLERANCE_FRAMES:
            _add(MotionFindingKind.DURATION_MISMATCH,
                 f"artifact {actual_frames} frames != requested "
                 f"{target_frames}",
                 actual_frames=actual_frames,
                 target_frames=target_frames)

        # Skeleton remap failure (step 2): required semantic bones missing.
        if remap is not None and remap.missing_bones:
            _add(MotionFindingKind.SKELETON_REMAP_FAILED,
                 f"target skeleton misses required semantic bones: "
                 f"{[b.value for b in remap.missing_bones]}",
                 missing_bones=[b.value for b in remap.missing_bones])

        return MotionValidationReport(
            ok=not findings, findings=findings,
            checked_entity_count=1)

    @staticmethod
    def is_retryable(kind: MotionRetryKind) -> bool:
        """Backlog 6: only transient provider failures retry within budget."""
        return kind == MotionRetryKind.TRANSIENT_PROVIDER


__all__ = [
    "MOTION_ADAPTER_COMPILER_VERSION",
    "MOTION_CAPABILITY_SCHEMA_VERSION",
    "MOTION_REQUEST_SCHEMA_VERSION",
    "MOTION_ARTIFACT_SCHEMA_VERSION",
    "MALICIOUS_METADATA_MARKERS",
    "MotionCapability",
    "MotionGenerationRequest",
    "RawMotionArtifact",
    "SkeletonRemapReceipt",
    "MotionCandidate",
    "MotionFindingKind",
    "MotionFinding",
    "MotionValidationReport",
    "MotionValidator",
]
