"""
Domain-specific errors for the WindAgent Video Production protocol (Phase 3).

These subclass the canonical WindAgent error hierarchy so they remain
serializable and retry-classified by the rest of the platform.
"""

from __future__ import annotations

from windagent_core.errors.exceptions import (
    DomainError,
    ValidationError,
    TerminalStateMutationError,
    IntegrityError,
)


class VideoProductionProtocolError(DomainError):
    """Base error for the video production protocol boundary."""

    code = "VP_PROTOCOL_ERROR"
    category = "VIDEO_PRODUCTION"


class UnsupportedMajorVersionError(ValidationError):
    """Raised when a package/event schema major version is not supported.

    Versioning policy is fail-closed: unknown major versions are rejected
    instead of being silently interpreted.
    """

    code = "VP_UNSUPPORTED_MAJOR_VERSION"
    category = "VIDEO_PRODUCTION_SCHEMA"
    retryable = False


class LockedRevisionMutationError(TerminalStateMutationError):
    """Raised when a locked revision is mutated or re-derived without intent.

    Locked revisions are immutable; any content change must create a new
    revision carrying an explicit downstream invalidation intent.
    """

    code = "VP_LOCKED_REVISION_MUTATION"
    category = "VIDEO_PRODUCTION_REVISION"
    retryable = False


class BrokenReferenceError(IntegrityError):
    """Raised when a package references an identifier that does not exist."""

    code = "VP_BROKEN_REFERENCE"
    category = "VIDEO_PRODUCTION_INTEGRITY"
    retryable = False


class DuplicateIdentifierError(IntegrityError):
    """Raised when two entities in the same aggregate share an identifier."""

    code = "VP_DUPLICATE_IDENTIFIER"
    category = "VIDEO_PRODUCTION_INTEGRITY"
    retryable = False


class ShotDependencyGraphCycleError(IntegrityError):
    """Raised when a shot dependency graph contains a cycle (Phase 9).

    `ShotDependencyGraph.topological_order()` fails closed on a cyclic
    blocking subgraph: instead of returning a partial order it raises this
    typed failure so callers can distinguish a genuine scheduling deadlock
    from other graph defects. The structural validator normally intercepts
    the cycle first; this exception is the direct-API guard.
    """

    code = "VP_SHOT_GRAPH_CYCLE"
    category = "VIDEO_PRODUCTION_GRAPH"
    retryable = False


class RigCompatibilityError(ValidationError):
    """Raised when a rig/clip fails a fail-closed compatibility gate (Phase 9).

    A clip that breaches any deformation threshold (foot sliding, limb
    stretch, mesh penetration, root drift, pose discontinuity) or was never
    tested MUST NOT enter the approved animation library (stage_d.md §4
    backlog 6). Callers route through this typed error so failures surface
    explicitly rather than degrading silently.
    """

    code = "VP_RIG_COMPATIBILITY"
    category = "VIDEO_PRODUCTION_RIGGING"
    retryable = False


class SilentSourceMutationError(IntegrityError):
    """Raised when a correction would mutate the source rig without a manifest.

    Manual correction is expressed ONLY as a derived rig revision carrying a
    correction manifest; the source rig file is never edited in place without
    traced intent (stage_d.md §4 backlog 7).
    """

    code = "VP_SILENT_SOURCE_MUTATION"
    category = "VIDEO_PRODUCTION_RIGGING"
    retryable = False


class TtsTimeoutError(VideoProductionProtocolError):
    """Raised when a TTS synthesis call exceeds the provider budget (Phase 10)."""

    code = "VP_TTS_TIMEOUT"
    category = "VIDEO_PRODUCTION_AUDIO"
    retryable = True


class TtsEmptyOutputError(ValidationError):
    """Raised when a TTS provider returns empty/zero-byte output (Phase 10)."""

    code = "VP_TTS_EMPTY_OUTPUT"
    category = "VIDEO_PRODUCTION_AUDIO"
    retryable = True


class TtsInvalidOutputError(ValidationError):
    """Raised when TTS output fails a validation axis — never published (Phase 10).

    Covers wrong sample rate, wrong channel layout, zero/negative duration, an
    undecodable stream, or a content-hash mismatch. A rejected output is never
    attached to a DialogueTrack (stage_e backlog 4).
    """

    code = "VP_TTS_INVALID_OUTPUT"
    category = "VIDEO_PRODUCTION_AUDIO"
    retryable = False


class UnsupportedLocaleError(ValidationError):
    """Raised when a provider does not support the requested locale (Phase 10).

    Locale support is part of the provider capability metadata; synthesizing
    against a provider that cannot produce the requested locale fails closed
    before any bytes are generated or charged.
    """

    code = "VP_TTS_UNSUPPORTED_LOCALE"
    category = "VIDEO_PRODUCTION_AUDIO"
    retryable = False


class LowConfidenceAlignmentError(ValidationError):
    """Raised when forced alignment confidence falls below threshold (Phase 10).

    Low-confidence alignment is NOT used for facial/lip-sync; it routes to
    human review instead of being silently accepted (stage_e backlog 5).
    """

    code = "VP_ALIGNMENT_LOW_CONFIDENCE"
    category = "VIDEO_PRODUCTION_AUDIO"
    retryable = False


class OverlongLineError(ValidationError):
    """Raised when a line is too long for its shot (stage_e Phase 10, backlog 6).

    The system never silently cuts a sentence; callers resolve the overlong
    line through a typed `LineTimingProposalType`, defaulting to human review.
    """

    code = "VP_LINE_OVERLONG"
    category = "VIDEO_PRODUCTION_AUDIO"
    retryable = False


class VoiceConsentMissingError(ValidationError):
    """Raised when a real-voice likeness lacks consent/approval (Phase 10).

    A real-voice preview profile can never transition to final without explicit
    rights/consent metadata and an approval actor (backlog test: real-voice
    profile missing consent cannot go preview -> final).
    """

    code = "VP_VOICE_CONSENT_MISSING"
    category = "VIDEO_PRODUCTION_AUDIO"
    retryable = False


class DuplicateSynthesisRequestError(IntegrityError):
    """Raised when a synthesis request hash is re-synthesized (idempotency guard).

    Phase 10 backlog 3: retry never re-synthesizes an identical request. A
    canonical request hash that already produced audio must reuse the artifact,
    not reprocess it, or else raise if it landed in an unexpected state.
    """

    code = "VP_DUPLICATE_SYNTHESIS"
    category = "VIDEO_PRODUCTION_AUDIO"
    retryable = False


class UnapprovedAssetError(ValidationError):
    """Raised when a plan references an asset with no approved revision (Phase 11).

    stage_f §3 backlog 2: the compiler validates completeness before compile;
    an asset that has not reached approved state is never compiled in.
    """

    code = "VP_SCENE_PLAN_UNAPPROVED_ASSET"
    category = "VIDEO_PRODUCTION_SCENE"
    retryable = False


class AssetRevisionMismatchError(ValidationError):
    """Raised when the resolved asset revision differs from the approved one (Phase 11)."""

    code = "VP_SCENE_PLAN_ASSET_REV_MISMATCH"
    category = "VIDEO_PRODUCTION_SCENE"
    retryable = False


class InvalidFrameRangeError(ValidationError):
    """Raised when the frame range is invalid (start < 1 or end < start) (Phase 11)."""

    code = "VP_SCENE_PLAN_INVALID_FRAME_RANGE"
    category = "VIDEO_PRODUCTION_SCENE"
    retryable = False


class ScenePlanIncompleteError(ValidationError):
    """Raised when inputs are missing/incomplete before compile (Phase 11)."""

    code = "VP_SCENE_PLAN_INCOMPLETE"
    category = "VIDEO_PRODUCTION_SCENE"
    retryable = False


class UnsafeCompilerOperationError(ValidationError):
    """Raised when plan content could become arbitrary code (Phase 11, allow-list).

    The trusted compiler never evaluates text from a model or asset metadata. A
    string carrying an execution marker (exec/eval/import os/bpy.ops/...) fails
    closed instead of being transcribed.
    """

    code = "VP_SCENE_PLAN_UNSAFE_OP"
    category = "VIDEO_PRODUCTION_SCENE"
    retryable = False


class CameraOverridePinMismatchError(ValidationError):
    """Raised when a manual camera override's pinned track revision drifts (Phase 13).

    stage_g §3 backlog 7: the compiler respects the pin — an active override
    whose pinned revision no longer matches the track's current revision fails
    closed instead of silently applying a stale or drifted placement.
    """

    code = "VP_CAMERA_OVERRIDE_PIN_MISMATCH"
    category = "VIDEO_PRODUCTION_CAMERA"
    retryable = False


class CameraCompileError(ValidationError):
    """Raised when a camera intent cannot be compiled into a rig plan (Phase 13).

    Base for camera compile failures that are not pin mismatches (e.g. an
    unresolvable rig primitive for a movement value). Camera validation
    findings themselves fail closed through the validator report.
    """

    code = "VP_CAMERA_COMPILE"
    category = "VIDEO_PRODUCTION_CAMERA"
    retryable = False


class LightingCompileError(ValidationError):
    """Raised when a lighting intent cannot resolve to a preset (Phase 14).

    stage_g §4 backlog 1/2: the compiler selects a versioned preset from
    style + time-of-day; an unknown style or an unresolved combination fails
    closed instead of letting the model place unlimited lights.
    """

    code = "VP_LIGHTING_COMPILE"
    category = "VIDEO_PRODUCTION_LIGHTING"
    retryable = False


class LightingOverrideOutOfBoundsError(ValidationError):
    """Raised when a lighting override exceeds its bounded adjustment (Phase 14).

    stage_g §4 backlog 3: every override is bounded (exposure shift, key
    multiplier, CCT shift). An out-of-bounds or mismatched-preset override
    fails closed — the rig is never silently pushed outside the policy.
    """

    code = "VP_LIGHTING_OVERRIDE_OUT_OF_BOUNDS"
    category = "VIDEO_PRODUCTION_LIGHTING"
    retryable = False


class AnimationCompileError(ValidationError):
    """Raised when an animation intent cannot be compiled (Phase 15).

    stage_h §3: base for compile failures that are not pin mismatches or
    retarget failures — an unresolvable action, an incompatible skeleton, a
    missing destination for an anchor-bound clip, a time-warp outside the
    bounded band, or an overlap beyond the blend window. All fail closed so
    no partial or conflicting track is ever published.
    """

    code = "VP_ANIMATION_COMPILE"
    category = "VIDEO_PRODUCTION_ANIMATION"
    retryable = False


class AnimationPinMismatchError(ValidationError):
    """Raised when a compile breaks an episode's pinned clip revision (Phase 15).

    stage_h §3 backlog 7: an episode pins a clip revision so library updates
    cannot change locked production. Compiling a pinned episode against any
    other revision fails closed.
    """

    code = "VP_ANIMATION_PIN_MISMATCH"
    category = "VIDEO_PRODUCTION_ANIMATION"
    retryable = False


class ClipRetargetError(ValidationError):
    """Raised when a clip cannot be retargeted to the target skeleton (Phase 15).

    stage_h §3 backlog 4: retarget normalizes root motion, fps and units
    through a Stage D profile. A clip whose fps cannot be resampled or whose
    required semantic bones are missing in the target skeleton fails closed
    instead of producing a degraded track.
    """

    code = "VP_CLIP_RETARGET"
    category = "VIDEO_PRODUCTION_ANIMATION"
    retryable = False


class MotionGenerationError(ValidationError):
    """Base AI motion generation failure (Phase 17).

    stage_h §5: parent of capability mismatch, quarantine violation and
    retry budget exhaustion. Everything fails closed — a raw artifact never
    reaches a production scene by any path other than the adapter's approve
    chain.
    """

    code = "VP_MOTION_GENERATION"
    category = "VIDEO_PRODUCTION_MOTION"
    retryable = False


class MotionCapabilityMismatchError(MotionGenerationError):
    """Raised when a request does not fit the provider capability (Phase 17).

    stage_h §5 backlog 1: fps, duration, skeleton, seed support, license or
    output format outside the declared contract fails closed with the
    blocking kinds (FPS_OUT_OF_RANGE, DURATION_OUT_OF_RANGE,
    CAPABILITY_MISMATCH, FORMAT_UNSUPPORTED...) — the adapter never silently
    adapts a request the provider cannot honor.
    """

    code = "VP_MOTION_CAPABILITY_MISMATCH"
    category = "VIDEO_PRODUCTION_MOTION"
    retryable = False


class MotionQuarantineViolationError(MotionGenerationError):
    """Raised when quarantined raw output is used as if it were production.

    stage_h §5 backlog 3: raw AI motion is inert data; importing it
    directly into a production scene (bypassing the remap/validation/
    retarget chain) is the exact violation this gate forbids.
    """

    code = "VP_MOTION_QUARANTINE_VIOLATION"
    category = "VIDEO_PRODUCTION_MOTION"
    retryable = False


class MotionRetryBudgetExceededError(MotionGenerationError):
    """Raised when the retry budget for a cause is exhausted (Phase 17).

    stage_h §5 backlog 6: retries are per cause and budget. Only transient
    provider failures retry; validation/capability/license failures never
    retry, and a different seed is a NEW candidate, never an overwrite.
    """

    code = "VP_MOTION_RETRY_BUDGET"
    category = "VIDEO_PRODUCTION_MOTION"
    retryable = False


# ---------------------------------------------------------------------------
# Stage I Facial Animation (VP3D Phase 18 — Lip-sync / Facial Pipeline)
# ---------------------------------------------------------------------------
class FacialCompileError(ValidationError):
    """Raised when a facial track cannot be compiled (Phase 18).

    stage_i §3: input phoneme timing that is non-monotonic or outside the
    shot frame range, or an emotion curve whose controls overlap the
    articulation (jaw/lips) controls, fails closed — a broken or ambiguous
    input never silently produces a wrong face. `details[\"kinds\"]` lists
    the `FacialFindingKind` values that were breached.
    """

    code = "VP_FACIAL_COMPILE"
    category = "VIDEO_PRODUCTION_FACIAL"
    retryable = False


class VisemeMapMissingPhonemeError(ValidationError):
    """Raised when a phoneme has no viseme entry and no fallback rule.

    stage_i backlog 2: a viseme map must version by language + facial rig
    profile and cover every phoneme explicitly or via a named fallback rule
    (NEUTRAL / CLOSED). An unknown phoneme with no rule is never silently
    skipped — the compile fails closed.
    """

    code = "VP_VISEME_MAP_MISSING_PHONEME"
    category = "VIDEO_PRODUCTION_FACIAL"
    retryable = False


class FacialRepairError(ValidationError):
    """Raised when a per-layer repair cannot be applied (Phase 18).

    stage_i backlog 8: repairing a facial track is scoped to one layer
    (lip-sync / gaze / emotion / blink / head motion); an unknown scope or
    a repair that would leave the track inconsistent fails closed.
    """

    code = "VP_FACIAL_REPAIR"
    category = "VIDEO_PRODUCTION_FACIAL"
    retryable = False


class FacialBakeError(ValidationError):
    """Raised when a facial track cannot be baked into a derived action.

    stage_i backlog 7: bake records compiler version, input hashes and the
    frame range; a track that is not baked-ready fails closed instead of
    producing a partial derived action.
    """

    code = "VP_FACIAL_BAKE"
    category = "VIDEO_PRODUCTION_FACIAL"
    retryable = False


class ProceduralCompileError(ValidationError):
    """Raised when a procedural recipe cannot be built/baked (Phase 16).

    stage_h §4: a layer spec outside its kind's bone ownership, two layers
    fighting over the same bones at the same priority, an unknown layer kind,
    or a missing/wrong anchor for grab/sitting layers fail closed — no layer
    ever overwrites keyframes outside its ownership and no recipe is baked
    partially.
    """

    code = "VP_PROCEDURAL_COMPILE"
    category = "VIDEO_PRODUCTION_ANIMATION"
    retryable = False


__all__ = [
    "VideoProductionProtocolError",
    "UnsupportedMajorVersionError",
    "LockedRevisionMutationError",
    "BrokenReferenceError",
    "DuplicateIdentifierError",
    "ShotDependencyGraphCycleError",
    "RigCompatibilityError",
    "SilentSourceMutationError",
    "TtsTimeoutError",
    "TtsEmptyOutputError",
    "TtsInvalidOutputError",
    "UnsupportedLocaleError",
    "LowConfidenceAlignmentError",
    "OverlongLineError",
    "VoiceConsentMissingError",
    "DuplicateSynthesisRequestError",
    "UnapprovedAssetError",
    "AssetRevisionMismatchError",
    "InvalidFrameRangeError",
    "ScenePlanIncompleteError",
    "UnsafeCompilerOperationError",
    "CameraOverridePinMismatchError",
    "CameraCompileError",
    "LightingCompileError",
    "LightingOverrideOutOfBoundsError",
    "AnimationCompileError",
    "AnimationPinMismatchError",
    "ClipRetargetError",
    "ProceduralCompileError",
    # Stage H AI Motion Adapter (VP3D Phase 17)
    "MotionGenerationError",
    "MotionCapabilityMismatchError",
    "MotionQuarantineViolationError",
    "MotionRetryBudgetExceededError",
    # Stage I Facial Animation (VP3D Phase 18)
    "FacialCompileError",
    "VisemeMapMissingPhonemeError",
    "FacialRepairError",
    "FacialBakeError",
]
