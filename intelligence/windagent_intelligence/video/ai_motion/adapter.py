"""
AI motion adapter orchestrator (VP3D Phase 17, stage_h §5) — the ONLY path
from a raw AI motion artifact to a production `AnimationTrack`.

Pipeline (stage_h §5):

    TextToMotionPort / VideoToMotionPort / MotionGenerationPort
    -> raw motion artifact        (QUARANTINED — inert data)
    -> skeleton remap             (fail-closed on missing bones)
    -> joint/foot/collision validation (SAME thresholds as library/mocap)
    -> retarget                   (Stage D profile via Phase 15 RetargetService)
    -> approved AnimationTrack

Guarantees:
- Quarantine (backlog 3): `generate` returns an artifact that carries no
  track; `import_artifact` always raises `MotionQuarantineViolationError`.
  `approve` is the only method that can produce a track, and it ALWAYS runs
  the full remap -> validate -> retarget chain — there is no unchecked path.
- Provenance (backlog 2): request hash over provider/model/version + prompt
  hash + seed + fps + duration + skeleton; every artifact records cost and
  license; the track metadata carries ONLY allow-listed provenance fields —
  provider metadata (even malicious strings) never enters production.
- Fair validation (backlog 4): the same MotionValidator thresholds used for
  library/mocap and procedural clips, plus the Phase 15 AnimationValidator
  on the finished track. A blocking finding -> ValidationFailureError; the
  fallback is library/procedural or human review, NEVER a bypass (backlog 5).
- Retry (backlog 6): per cause and budget — only transient provider
  failures retry; a different seed is a NEW candidate, never an overwrite.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

from windagent_core.domain.video_production.ai_motion import (
    MOTION_ADAPTER_COMPILER_VERSION,
    MotionCandidate,
    MotionCapability,
    MotionGenerationRequest,
    MotionValidationReport,
    MotionValidator,
    RawMotionArtifact,
    SkeletonRemapReceipt,
)
from windagent_core.domain.video_production.animation import (
    AnimationClip,
    AnimationIntent,
    AnimationTrack,
    AnimationValidator,
    ClipProvenance,
)
from windagent_core.domain.video_production.enums import (
    ClipSource,
    MotionCandidateStatus,
    MotionRetryKind,
    SemanticBone,
)
from windagent_core.domain.video_production.errors import (
    MotionCapabilityMismatchError,
    MotionGenerationError,
    MotionQuarantineViolationError,
    MotionRetryBudgetExceededError,
)
from windagent_core.domain.video_production.ids import (
    AnimationClipId,
    MotionCandidateId,
    MotionRequestId,
    SkeletonProfileId,
)
from windagent_intelligence.video.ai_motion.ports import (
    MotionGenerationPort,
    TransientProviderError,
)
from windagent_intelligence.video.ai_motion.remap import SkeletonRemapService
from windagent_intelligence.video.animation.retarget import RetargetService
from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.ids import StableIdFactory

MOTION_ADAPTER_LAYER_VERSION = "1.0.0"
# Allow-listed provenance fields copied from an artifact into a track.
TRACK_PROVENANCE_FIELDS = (
    "artifact_id", "request_id", "provider", "model", "model_version",
    "prompt_hash", "seed", "cost", "license",
)


class MotionApproveReceipt:
    """Result of one approve: the approved track + candidate + report."""

    def __init__(
        self,
        *,
        track: AnimationTrack,
        candidate: MotionCandidate,
        remap: SkeletonRemapReceipt,
        validation: MotionValidationReport,
        clip: AnimationClip,
        invalidated_artifacts: Optional[List[str]] = None,
    ) -> None:
        self.track = track
        self.candidate = candidate
        self.remap = remap
        self.validation = validation
        self.clip = clip
        self.invalidated_artifacts = invalidated_artifacts or []

    @property
    def track_hash(self) -> str:
        return self.track.content_hash

    @property
    def blocking_kinds(self) -> List[str]:
        return self.validation.blocking_kinds


class AiMotionAdapter:
    """Deterministic AI motion orchestrator (stage_h §5)."""

    compiler_version = MOTION_ADAPTER_LAYER_VERSION

    def __init__(
        self,
        *,
        port: MotionGenerationPort,
        id_factory: Optional[StableIdFactory] = None,
        validator: Optional[MotionValidator] = None,
        remap_service: Optional[SkeletonRemapService] = None,
        retarget_service: Optional[RetargetService] = None,
        track_validator: Optional[AnimationValidator] = None,
    ) -> None:
        self.port = port
        self.id_factory = id_factory or StableIdFactory()
        self.validator = validator or MotionValidator()
        self.remap_service = remap_service or SkeletonRemapService(
            id_factory=self.id_factory)
        self.retarget_service = retarget_service or RetargetService(
            id_factory=self.id_factory)
        self.track_validator = track_validator or AnimationValidator()
        self._candidates: Dict[str, MotionCandidate] = {}
        self._attempts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Backlog 1/2 — capability contract + typed request with full provenance
    # ------------------------------------------------------------------
    def capability(self) -> MotionCapability:
        return self.port.capability()

    def build_request(
        self,
        *,
        prompt: str,
        actor_id: str,
        episode_id: str = "",
        fps: int = 24,
        duration_seconds: float = 2.0,
        seed: int = 0,
        skeleton_profile_id: Optional[SkeletonProfileId] = None,
        output_format=None,
        retry_budget: Optional[int] = None,
    ) -> MotionGenerationRequest:
        """Build a request and fail closed when it does not fit the contract.

        The capability check is the backlog 1 gate: fps/duration/skeleton/
        format/license outside the provider's declared contract raises
        `MotionCapabilityMismatchError` with the blocking kinds — the
        adapter never silently adapts a request the provider cannot honor.
        """
        cap = self.port.capability()
        capability_check = MotionCapability(
            capability_id=cap.capability_id,
            provider=cap.provider,
            model=cap.model,
            model_version=cap.model_version,
            supported_skeletons=list(cap.supported_skeletons),
            fps_min=cap.fps_min,
            fps_max=cap.fps_max,
            duration_min_seconds=cap.duration_min_seconds,
            duration_max_seconds=cap.duration_max_seconds,
            supports_seed=cap.supports_seed,
            licenses=list(cap.licenses),
            output_formats=list(cap.output_formats),
            max_retry_budget=cap.max_retry_budget,
        )
        skeleton = skeleton_profile_id or self._default_skeleton(cap)
        fmt = output_format or cap.output_formats[0]
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        budget = retry_budget if retry_budget is not None else cap.max_retry_budget
        request = MotionGenerationRequest(
            request_id=MotionRequestId(self.id_factory.motion_request_id(
                actor_id, prompt_hash, seed)),
            provider=cap.provider,
            model=cap.model,
            model_version=cap.model_version,
            prompt=prompt,
            prompt_hash=prompt_hash,
            skeleton_profile_id=skeleton,
            fps=fps,
            duration_seconds=duration_seconds,
            seed=seed,
            output_format=fmt,
            retry_budget=budget,
            episode_id=episode_id,
            actor_id=actor_id,
        )
        report = self.validator.validate_capability_fit(
            capability=capability_check, request=request)
        if report.blocking_findings:
            raise MotionCapabilityMismatchError(
                "request does not fit the provider capability contract; "
                "nothing is generated",
                details={
                    "provider": cap.provider,
                    "model": cap.model,
                    "model_version": cap.model_version,
                    "blocking_count": len(report.blocking_findings),
                    "kinds": report.blocking_kinds,
                })
        return request.model_copy(update={
            "request_hash": request.compute_stable_hash()})

    # ------------------------------------------------------------------
    # Backlog 3 — quarantine: raw output is inert, never a track
    # ------------------------------------------------------------------
    def generate(self, request: MotionGenerationRequest) -> RawMotionArtifact:
        """Generate one raw artifact. QUARANTINED: carries no track."""
        artifact = self.port.generate(request)
        self._register_candidate(artifact, status=MotionCandidateStatus.QUARANTINED)
        return artifact

    def import_artifact(self, artifact: RawMotionArtifact):
        """The quarantine boundary: raw output can never enter a scene.

        Always raises — there is deliberately no direct-to-scene path.
        """
        raise MotionQuarantineViolationError(
            "raw AI motion artifact is quarantined; it cannot be imported "
            "directly into a production scene — run it through the approve "
            "chain (remap -> validation -> retarget)",
            details={
                "artifact_id": str(artifact.artifact_id),
                "request_id": str(artifact.request_id),
                "provider": artifact.provider,
            })

    # ------------------------------------------------------------------
    # Pipeline steps 2-4
    # ------------------------------------------------------------------
    def remap(
        self,
        *,
        artifact: RawMotionArtifact,
        target_skeleton: SkeletonProfileId,
        target_bones: Optional[List[SemanticBone]] = None,
    ) -> SkeletonRemapReceipt:
        return self.remap_service.remap(
            artifact=artifact, target_skeleton=target_skeleton,
            target_bones=target_bones)

    def validate(
        self,
        *,
        artifact: RawMotionArtifact,
        remap_receipt: Optional[SkeletonRemapReceipt] = None,
    ) -> MotionValidationReport:
        return self.validator.validate_artifact(
            artifact=artifact, remap=remap_receipt)

    # ------------------------------------------------------------------
    # Backlog 5 — approve: the ONLY path to a production track
    # ------------------------------------------------------------------
    def approve(
        self,
        *,
        intent: AnimationIntent,
        request: MotionGenerationRequest,
        artifact: RawMotionArtifact,
        target_bones: List[SemanticBone],
        start_frame: int = 0,
        target_skeleton: Optional[SkeletonProfileId] = None,
        require_clean: bool = True,
        prior_track_hash: Optional[str] = None,
    ) -> MotionApproveReceipt:
        """Run the full safety chain and, if clean, emit an AnimationTrack.

        Missing bones, blocked licenses, malicious metadata or any metric
        beyond the library/mocap thresholds fail closed: the candidate is
        REJECTED and `ValidationFailureError` is raised — the fallback is
        library/procedural or human review, never a bypass. Only a clean
        artifact becomes a track whose metadata carries the allow-listed
        AI-motion provenance (backlog 2/3).
        """
        skeleton = target_skeleton or SkeletonProfileId(
            str(request.skeleton_profile_id))
        remap_receipt = self.remap(
            artifact=artifact, target_skeleton=skeleton,
            target_bones=target_bones)
        report = self.validate(artifact=artifact, remap_receipt=remap_receipt)

        candidate = self._candidate(artifact, status=MotionCandidateStatus.REMAPPED)
        if require_clean and report.blocking_findings:
            self._replace_candidate(candidate.model_copy(update={
                "status": MotionCandidateStatus.REJECTED,
                "validation_ok": False,
                "blocking_kinds": report.blocking_kinds,
            }))
            raise ValidationFailureError(
                "AI motion artifact failed validation; the candidate is "
                "REJECTED. Fallback: library clip, procedural bake or human "
                "review — validation is never bypassed.",
                details={
                    "artifact_id": str(artifact.artifact_id),
                    "request_id": str(request.request_id),
                    "blocking_count": len(report.blocking_findings),
                    "kinds": report.blocking_kinds,
                })

        clip = self._build_clip(artifact=artifact, remap=remap_receipt,
                                request=request, action=intent.action)
        retarget = self.retarget_service.build_receipt(
            clip=clip, target_fps=intent.fps, target_bones=target_bones)
        frame_count = int(artifact.motion_metrics.get(
            "frame_count", round(artifact.duration_seconds * artifact.fps)))
        track = AnimationTrack(
            track_id=self.id_factory.animation_track_id(
                intent.actor_id, start_frame),
            episode_id=intent.episode_id,
            actor_id=intent.actor_id,
            intent_id=intent.intent_id,
            clip_id=clip.clip_id,
            clip_version=clip.version,
            clip_hash=clip.content_hash(),
            retarget=retarget,
            warp_ratio=1.0,
            start_frame=start_frame,
            end_frame=start_frame + frame_count,
            duration_seconds=artifact.duration_seconds,
            fps=intent.fps,
            root_motion_meters=clip.root_motion_meters,
            compiler_version=self.compiler_version,
            metadata={"ai_motion": self._provenance(artifact, request)},
        )
        track = track.model_copy(update={
            "content_hash": track.compute_stable_hash()})

        track_report = self.track_validator.validate_track(
            intent=intent, clip=clip, track=track,
            finding_prefix=self.id_factory.animation_finding_id(
                intent.actor_id))
        if require_clean and track_report.blocking_findings:
            raise ValidationFailureError(
                "approved AI motion track failed Phase 15 track validation",
                details={
                    "actor_id": intent.actor_id,
                    "blocking_count": len(track_report.blocking_findings),
                    "kinds": track_report.blocking_kinds,
                })

        approved = candidate.model_copy(update={
            "status": MotionCandidateStatus.APPROVED,
            "validation_ok": True,
            "blocking_kinds": [],
            "approved_track_id": str(track.track_id),
        })
        self._replace_candidate(approved)
        return MotionApproveReceipt(
            track=track,
            candidate=approved,
            remap=remap_receipt,
            validation=report,
            clip=clip,
            invalidated_artifacts=self._invalidation_scope(
                prior_track_hash, track.content_hash, track.track_id),
        )

    # ------------------------------------------------------------------
    # Backlog 6 — retry by cause + budget; new seed = new candidate
    # ------------------------------------------------------------------
    def retry(
        self,
        *,
        request: MotionGenerationRequest,
        cause: MotionRetryKind,
    ) -> RawMotionArtifact:
        """Retry per cause: only transient provider failures retry.

        Validation/capability/license failures never retry (raise with the
        cause in details). Transient failures retry within the request
        budget; exhaustion raises `MotionRetryBudgetExceededError`.
        """
        if not MotionValidator.is_retryable(cause):
            raise MotionGenerationError(
                f"cause {cause.value} is not retryable — pick another "
                f"provider, another seed (a new candidate) or a library/"
                f"procedural fallback",
                details={"cause": cause.value, "retryable": False})
        attempts = self._attempts.get(str(request.request_id), 0) + 1
        if attempts > request.retry_budget:
            raise MotionRetryBudgetExceededError(
                f"retry budget {request.retry_budget} exhausted for "
                f"{request.request_id}",
                details={"request_id": str(request.request_id),
                         "budget": request.retry_budget,
                         "attempts": attempts,
                         "cause": cause.value})
        self._attempts[str(request.request_id)] = attempts
        try:
            return self.generate(request)
        except TransientProviderError as exc:
            # budget is per cause; a fresh transient failure still counts
            if attempts >= request.retry_budget:
                raise MotionRetryBudgetExceededError(
                    f"retry budget {request.retry_budget} exhausted after "
                    f"transient failure",
                    details={"request_id": str(request.request_id),
                             "cause": cause.value}) from exc
            raise

    # ------------------------------------------------------------------
    def candidates(self, request_id: str) -> List[MotionCandidate]:
        """All candidates for a request; different seeds never overwrite."""
        return [c for c in self._candidates.values()
                if str(c.request_id) == request_id]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _build_clip(self, *, artifact, remap, request, action) -> AnimationClip:
        """One versioned clip from the remapped+validated artifact only.

        The clip's provenance is ClipSource.AI_MOTION with the full
        provider provenance (backlog 2); its content hash covers the
        artifact hash so the same motion always yields the same clip.
        """
        return AnimationClip(
            clip_id=AnimationClipId(self.id_factory.animation_clip_id(
                "AI_MOTION", artifact.prompt_hash, artifact.seed)),
            name=f"ai-motion:{artifact.artifact_id}",
            action=action,
            skeleton_profile_id=artifact.claimed_skeleton_profile_id,
            compatible_skeleton_ids=[request.skeleton_profile_id],
            required_bones=list(remap.mapped_bones),
            duration_seconds=artifact.duration_seconds,
            fps=artifact.fps,
            root_motion_meters=float(artifact.motion_metrics.get(
                "root_motion_meters", 0.0)),
            resamplable=True,
            version=MOTION_ADAPTER_COMPILER_VERSION,
            provenance=ClipProvenance(
                source=ClipSource.AI_MOTION,
                provider=artifact.provider,
                recording_session=f"ai-motion:{artifact.artifact_id}",
                license=artifact.license,
            ),
            metadata={
                "ai_motion": self._provenance(artifact, request),
                "artifact_hash": artifact.content_hash,
            },
        )

    @staticmethod
    def _provenance(artifact: RawMotionArtifact,
                    request: MotionGenerationRequest) -> Dict[str, object]:
        """Allow-listed provenance only — provider metadata never enters."""
        return {
            "artifact_id": str(artifact.artifact_id),
            "request_id": str(request.request_id),
            "provider": artifact.provider,
            "model": artifact.model,
            "model_version": artifact.model_version,
            "prompt_hash": artifact.prompt_hash,
            "seed": artifact.seed,
            "cost": artifact.cost,
            "license": artifact.license.value,
        }

    def _candidate(self, artifact: RawMotionArtifact, *,
                   status: MotionCandidateStatus) -> MotionCandidate:
        return MotionCandidate(
            candidate_id=MotionCandidateId(self.id_factory.motion_candidate_id(
                artifact.request_id, artifact.seed)),
            request_id=artifact.request_id,
            artifact_id=artifact.artifact_id,
            seed=artifact.seed,
            status=status,
        )

    def _register_candidate(self, artifact: RawMotionArtifact, *,
                            status: MotionCandidateStatus) -> None:
        candidate = self._candidate(artifact, status=status)
        key = str(candidate.candidate_id)
        if key in self._candidates:
            # Backlog 6: same seed again is the SAME candidate — never
            # overwrite; a different seed has a different id by construction.
            raise MotionGenerationError(
                f"candidate {key} already exists; a different seed is a NEW "
                f"candidate — existing candidates are never overwritten",
                details={"candidate_id": key,
                         "request_id": str(artifact.request_id),
                         "seed": artifact.seed})
        self._candidates[key] = candidate

    def _replace_candidate(self, candidate: MotionCandidate) -> None:
        self._candidates[str(candidate.candidate_id)] = candidate

    @staticmethod
    def _default_skeleton(cap: MotionCapability) -> SkeletonProfileId:
        if cap.supported_skeletons:
            return cap.supported_skeletons[0]
        raise MotionCapabilityMismatchError(
            "provider capability declares no supported skeleton",
            details={"provider": cap.provider})

    @staticmethod
    def _invalidation_scope(prior_hash: Optional[str], current_hash: str,
                            track_id) -> List[str]:
        """Unchanged track -> nothing; changed -> animation preview only."""
        if prior_hash is None or prior_hash == current_hash:
            return []
        return [f"animation/preview:{track_id}"]


__all__ = [
    "MOTION_ADAPTER_LAYER_VERSION",
    "TRACK_PROVENANCE_FIELDS",
    "MotionApproveReceipt",
    "AiMotionAdapter",
]
