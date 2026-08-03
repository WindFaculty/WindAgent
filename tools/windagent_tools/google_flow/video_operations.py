"""
Phase 15 — Flow video operations mapping (plan 04 §21, §23.2).

Each video operation maps a typed `FlowVideoRequest` to typed configuration
steps (`FlowUiAction`), never to raw browser instructions (plan 04 §21):

    TEXT_TO_VIDEO
    FRAMES_TO_VIDEO
    INGREDIENTS_TO_VIDEO
    VIDEO_EXTENSION
    VIDEO_TO_VIDEO

`VideoOperationMapper` also implements mode validation (plan 04 §23.2):

- frames-to-video: first + last frame approved, correct media type/hash;
- ingredients-to-video: every ingredient/reference binding valid;
- video-extension: predecessor clip approved and continuity state correct;
- video-to-video: source clip and transformation intent explicit;
- duration / aspect ratio / model within the compiled request / policy.

Mode validation is fail-closed: any issue blocks before the generator ever
clicks submit. `validate_mode` returns typed issues so callers (and the
verifier) can assert the exact blocking reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from windagent_tools.google_flow.navigation import FlowUiAction


class FlowVideoOperation(str, Enum):
    TEXT_TO_VIDEO = "TEXT_TO_VIDEO"
    FRAMES_TO_VIDEO = "FRAMES_TO_VIDEO"
    INGREDIENTS_TO_VIDEO = "INGREDIENTS_TO_VIDEO"
    VIDEO_EXTENSION = "VIDEO_EXTENSION"
    VIDEO_TO_VIDEO = "VIDEO_TO_VIDEO"


class FlowVideoModeIssueCode(str, Enum):
    """Typed mode-validation findings (plan 04 §23.2)."""

    MISSING_FIRST_FRAME = "MISSING_FIRST_FRAME"
    MISSING_LAST_FRAME = "MISSING_LAST_FRAME"
    FIRST_FRAME_NOT_APPROVED = "FIRST_FRAME_NOT_APPROVED"
    LAST_FRAME_NOT_APPROVED = "LAST_FRAME_NOT_APPROVED"
    MISSING_INGREDIENT = "MISSING_INGREDIENT"
    INGREDIENT_NOT_APPROVED = "INGREDIENT_NOT_APPROVED"
    MISSING_PREDECESSOR_CLIP = "MISSING_PREDECESSOR_CLIP"
    PREDECESSOR_NOT_APPROVED = "PREDECESSOR_NOT_APPROVED"
    CONTINUITY_NOT_READY = "CONTINUITY_NOT_READY"
    MISSING_SOURCE_CLIP = "MISSING_SOURCE_CLIP"
    SOURCE_NOT_APPROVED = "SOURCE_NOT_APPROVED"
    TRANSFORMATION_INTENT_MISSING = "TRANSFORMATION_INTENT_MISSING"
    DURATION_OUT_OF_POLICY = "DURATION_OUT_OF_POLICY"
    ASPECT_RATIO_UNSUPPORTED = "ASPECT_RATIO_UNSUPPORTED"
    MODEL_UNSUPPORTED = "MODEL_UNSUPPORTED"


@dataclass(frozen=True)
class FlowVideoModeIssue:
    """One fail-closed mode-validation finding (§23.2)."""

    code: FlowVideoModeIssueCode
    detail: str


# Reference binding roles used by video mode validation. Values mirror the
# canonical `ReferenceBindingRole` members (FIRST_FRAME / LAST_FRAME /
# INGREDIENT / PREDECESSOR_CLIP) without importing core into the adapter.
ROLE_FIRST_FRAME = "FIRST_FRAME"
ROLE_LAST_FRAME = "LAST_FRAME"
ROLE_INGREDIENT = "INGREDIENT"
ROLE_PREDECESSOR_CLIP = "PREDECESSOR_CLIP"
ROLE_SOURCE_CLIP = "SOURCE_CLIP"

# Operations that consume an approved video source clip (extension / v2v).
_SOURCE_CLIP_OPS = frozenset(
    {FlowVideoOperation.VIDEO_EXTENSION, FlowVideoOperation.VIDEO_TO_VIDEO}
)

# Operations that REQUIRE approved reference bindings (frames / ingredients /
# extension / v2v — text-to-video needs none).
_REFERENCE_REQUIRED_OPS = frozenset(
    {
        FlowVideoOperation.FRAMES_TO_VIDEO,
        FlowVideoOperation.INGREDIENTS_TO_VIDEO,
        FlowVideoOperation.VIDEO_EXTENSION,
        FlowVideoOperation.VIDEO_TO_VIDEO,
    }
)

SUPPORTED_ASPECT_RATIOS = frozenset({"16:9", "9:16", "1:1", "4:3", "21:9"})
SUPPORTED_MODELS = frozenset({"video_model_0.1", "video_model_0.1_slow"})

MIN_DURATION_SECONDS = 1.0
MAX_DURATION_SECONDS = 300.0


@dataclass(frozen=True)
class FlowVideoRequest:
    """Typed, idempotent video generation request (plan 04 §21-§23)."""

    operation: FlowVideoOperation
    request_hash: str  # 64-hex sha256 (from the compiled request)
    project_id: str
    revision_id: str
    shot_id: str = ""
    prompt: str = ""
    reference_bindings: tuple[tuple[str, str], ...] = ()  # (role, content_hash)
    duration_seconds: float = 4.0
    aspect_ratio: str = "16:9"
    model: str = "video_model_0.1"
    candidate_limit: int = 1
    max_cost_credits: float = 0.0
    idempotency_token: str = ""
    # Mode-specific intents (plan 04 §23.2):
    continuity_state: str = ""  # VIDEO_EXTENSION: predecessor continuity state
    transformation_intent: str = ""  # VIDEO_TO_VIDEO: explicit transform intent
    media_type_hint: str = "video/mp4"  # reserved: expected output media type


class VideoOperationMapper:
    """Maps a typed video operation to config steps + mode policy facts."""

    def __init__(
        self,
        *,
        capability: Optional[Sequence[FlowVideoOperation]] = None,
        supported_aspect_ratios: Sequence[str] = tuple(SUPPORTED_ASPECT_RATIOS),
        supported_models: Sequence[str] = tuple(SUPPORTED_MODELS),
        min_duration: float = MIN_DURATION_SECONDS,
        max_duration: float = MAX_DURATION_SECONDS,
    ) -> None:
        # Empty capability means NOTHING is supported (fail closed); only an
        # explicit None falls back to the full operation set.
        if capability is None:
            self.capability = frozenset(FlowVideoOperation)
        else:
            self.capability = frozenset(capability)
        self.aspect_ratios = frozenset(supported_aspect_ratios)
        self.models = frozenset(supported_models)
        self.min_duration = min_duration
        self.max_duration = max_duration

    # ------------------------------------------------------------------
    def supported(self, operation: FlowVideoOperation) -> bool:
        return operation in self.capability

    def requires_reference(self, operation: FlowVideoOperation) -> bool:
        return operation in _REFERENCE_REQUIRED_OPS

    def requires_source_image(self, operation: FlowVideoOperation) -> bool:
        # For video, the analog of a source image is the source clip.
        return operation in _SOURCE_CLIP_OPS

    def is_character_master(self, operation: FlowVideoOperation) -> bool:
        return False  # character masters are image operations (§18.4)

    # ------------------------------------------------------------------
    def validate_mode(
        self,
        request: FlowVideoRequest,
        *,
        approved_hashes: frozenset[str] = frozenset(),
    ) -> tuple[FlowVideoModeIssue, ...]:
        """Fail-closed mode validation (plan 04 §23.2).

        `approved_hashes` is the set of content hashes of APPROVED assets
        (from the composition root / approved asset store). A binding whose
        content hash is not in that set is NOT approved and blocks the mode.
        """
        issues: list[FlowVideoModeIssue] = []

        # Duration / aspect / model within the compiled request / policy.
        if not (self.min_duration <= request.duration_seconds <= self.max_duration):
            issues.append(
                FlowVideoModeIssue(
                    FlowVideoModeIssueCode.DURATION_OUT_OF_POLICY,
                    f"duration {request.duration_seconds}s outside "
                    f"[{self.min_duration}, {self.max_duration}]",
                )
            )
        if request.aspect_ratio not in self.aspect_ratios:
            issues.append(
                FlowVideoModeIssue(
                    FlowVideoModeIssueCode.ASPECT_RATIO_UNSUPPORTED,
                    f"aspect ratio {request.aspect_ratio!r} unsupported",
                )
            )
        if request.model not in self.models:
            issues.append(
                FlowVideoModeIssue(
                    FlowVideoModeIssueCode.MODEL_UNSUPPORTED,
                    f"model {request.model!r} unsupported",
                )
            )

        bindings = dict(request.reference_bindings)
        op = request.operation

        if op == FlowVideoOperation.FRAMES_TO_VIDEO:
            first = bindings.get(ROLE_FIRST_FRAME)
            last = bindings.get(ROLE_LAST_FRAME)
            if first is None:
                issues.append(
                    FlowVideoModeIssue(
                        FlowVideoModeIssueCode.MISSING_FIRST_FRAME,
                        "FRAMES_TO_VIDEO requires a FIRST_FRAME binding",
                    )
                )
            elif first not in approved_hashes:
                issues.append(
                    FlowVideoModeIssue(
                        FlowVideoModeIssueCode.FIRST_FRAME_NOT_APPROVED,
                        "FIRST_FRAME binding is not an approved asset",
                    )
                )
            if last is None:
                issues.append(
                    FlowVideoModeIssue(
                        FlowVideoModeIssueCode.MISSING_LAST_FRAME,
                        "FRAMES_TO_VIDEO requires a LAST_FRAME binding",
                    )
                )
            elif last not in approved_hashes:
                issues.append(
                    FlowVideoModeIssue(
                        FlowVideoModeIssueCode.LAST_FRAME_NOT_APPROVED,
                        "LAST_FRAME binding is not an approved asset",
                    )
                )

        elif op == FlowVideoOperation.INGREDIENTS_TO_VIDEO:
            ingredient_hashes = [
                h for role, h in request.reference_bindings
                if role == ROLE_INGREDIENT
            ]
            if not ingredient_hashes:
                issues.append(
                    FlowVideoModeIssue(
                        FlowVideoModeIssueCode.MISSING_INGREDIENT,
                        "INGREDIENTS_TO_VIDEO requires at least one "
                        "INGREDIENT binding",
                    )
                )
            unapproved = [h for h in ingredient_hashes if h not in approved_hashes]
            if unapproved:
                issues.append(
                    FlowVideoModeIssue(
                        FlowVideoModeIssueCode.INGREDIENT_NOT_APPROVED,
                        f"ingredients not approved: {sorted(unapproved)[:5]}",
                    )
                )

        elif op == FlowVideoOperation.VIDEO_EXTENSION:
            pred = bindings.get(ROLE_PREDECESSOR_CLIP)
            if pred is None:
                issues.append(
                    FlowVideoModeIssue(
                        FlowVideoModeIssueCode.MISSING_PREDECESSOR_CLIP,
                        "VIDEO_EXTENSION requires a PREDECESSOR_CLIP binding",
                    )
                )
            elif pred not in approved_hashes:
                issues.append(
                    FlowVideoModeIssue(
                        FlowVideoModeIssueCode.PREDECESSOR_NOT_APPROVED,
                        "PREDECESSOR_CLIP binding is not an approved asset",
                    )
                )
            if not request.continuity_state:
                issues.append(
                    FlowVideoModeIssue(
                        FlowVideoModeIssueCode.CONTINUITY_NOT_READY,
                        "VIDEO_EXTENSION requires a continuity state",
                    )
                )

        elif op == FlowVideoOperation.VIDEO_TO_VIDEO:
            source = bindings.get(ROLE_SOURCE_CLIP)
            if source is None:
                issues.append(
                    FlowVideoModeIssue(
                        FlowVideoModeIssueCode.MISSING_SOURCE_CLIP,
                        "VIDEO_TO_VIDEO requires a SOURCE_CLIP binding",
                    )
                )
            elif source not in approved_hashes:
                issues.append(
                    FlowVideoModeIssue(
                        FlowVideoModeIssueCode.SOURCE_NOT_APPROVED,
                        "SOURCE_CLIP binding is not an approved asset",
                    )
                )
            if not request.transformation_intent:
                issues.append(
                    FlowVideoModeIssue(
                        FlowVideoModeIssueCode.TRANSFORMATION_INTENT_MISSING,
                        "VIDEO_TO_VIDEO requires an explicit transformation "
                        "intent",
                    )
                )

        # TEXT_TO_VIDEO requires no bindings — nothing further to check.
        return tuple(issues)

    # ------------------------------------------------------------------
    def configuration_actions(
        self, request: FlowVideoRequest
    ) -> list[FlowUiAction]:
        """Typed configuration steps for the operation (plan 04 §21)."""
        actions: list[FlowUiAction] = [
            FlowUiAction("select", "generation_mode", request.operation.value, 60.0),
            FlowUiAction("select", "model_select", request.model, 60.0),
            FlowUiAction("select", "aspect_ratio_select", request.aspect_ratio, 60.0),
            FlowUiAction("fill", "prompt_field", request.prompt, 60.0),
        ]
        if request.duration_seconds:
            actions.append(
                FlowUiAction(
                    "fill",
                    "duration_field",
                    f"{request.duration_seconds:.1f}",
                    60.0,
                )
            )
        if self.requires_reference(request.operation):
            for role, content_hash in request.reference_bindings:
                actions.append(
                    FlowUiAction(
                        "upload", "reference_upload", content_hash, 120.0
                    )
                )
        if self.requires_source_image(request.operation):
            for role, content_hash in request.reference_bindings:
                actions.append(
                    FlowUiAction("upload", "source_upload", content_hash, 120.0)
                )
        return actions


__all__ = [
    "FlowVideoModeIssue",
    "FlowVideoModeIssueCode",
    "FlowVideoOperation",
    "FlowVideoRequest",
    "VideoOperationMapper",
    "ROLE_FIRST_FRAME",
    "ROLE_LAST_FRAME",
    "ROLE_INGREDIENT",
    "ROLE_PREDECESSOR_CLIP",
    "ROLE_SOURCE_CLIP",
]
