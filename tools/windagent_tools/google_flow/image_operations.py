"""
Phase 14 — Flow image operations mapping (plan 04 §17).

Each image operation maps a typed `FlowImageRequest` to typed configuration
steps (`FlowUiAction`), never to raw browser instructions (plan 04 §17):

    CREATE_CHARACTER_REFERENCE
    CREATE_LOCATION_REFERENCE
    CREATE_PROP_REFERENCE
    CREATE_STORYBOARD_FRAME
    CREATE_FIRST_FRAME
    CREATE_LAST_FRAME
    EDIT_IMAGE
    UPSCALE_IMAGE

`ImageOperationMapper` also answers capability and policy questions used by
the pre-submit guard and review gate: whether an operation is supported by
the provider, whether it requires an approved reference, and whether it is a
character-master operation (always human-approved in Release 0.1, §18.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from windagent_tools.google_flow.navigation import FlowUiAction


class FlowImageOperation(str, Enum):
    CREATE_CHARACTER_REFERENCE = "CREATE_CHARACTER_REFERENCE"
    CREATE_LOCATION_REFERENCE = "CREATE_LOCATION_REFERENCE"
    CREATE_PROP_REFERENCE = "CREATE_PROP_REFERENCE"
    CREATE_STORYBOARD_FRAME = "CREATE_STORYBOARD_FRAME"
    CREATE_FIRST_FRAME = "CREATE_FIRST_FRAME"
    CREATE_LAST_FRAME = "CREATE_LAST_FRAME"
    EDIT_IMAGE = "EDIT_IMAGE"
    UPSCALE_IMAGE = "UPSCALE_IMAGE"


# Operations that produce a character master — identity-critical, always
# human-approved in Release 0.1 (plan 04 §18.4).
_CHARACTER_MASTER_OPS = frozenset({FlowImageOperation.CREATE_CHARACTER_REFERENCE})

# Operations that consume an existing approved asset (edit / upscale).
_SOURCE_IMAGE_OPS = frozenset({FlowImageOperation.EDIT_IMAGE, FlowImageOperation.UPSCALE_IMAGE})

# Operations that REQUIRE an approved reference binding (identity/location/
# prop / first / last frame are created from a reference).
_REFERENCE_REQUIRED_OPS = frozenset(
    {
        FlowImageOperation.CREATE_CHARACTER_REFERENCE,
        FlowImageOperation.CREATE_LOCATION_REFERENCE,
        FlowImageOperation.CREATE_PROP_REFERENCE,
        FlowImageOperation.CREATE_FIRST_FRAME,
        FlowImageOperation.CREATE_LAST_FRAME,
    }
)


@dataclass(frozen=True)
class FlowImageRequest:
    """Typed, idempotent image generation request (plan 04 §17-§18)."""

    operation: FlowImageOperation
    request_hash: str  # 64-hex sha256 (from the compiled request)
    project_id: str
    revision_id: str
    shot_id: str = ""
    prompt: str = ""
    reference_bindings: tuple[tuple[str, str], ...] = ()  # (role, content_hash)
    candidate_limit: int = 4
    max_cost_credits: float = 0.0
    idempotency_token: str = ""


class ImageOperationMapper:
    """Maps a typed image operation to configuration steps + policy facts."""

    def __init__(
        self,
        *,
        capability: Optional[Sequence[FlowImageOperation]] = None,
    ) -> None:
        # Empty capability means NOTHING is supported (fail closed); only an
        # explicit None falls back to the full operation set.
        if capability is None:
            self.capability = frozenset(FlowImageOperation)
        else:
            self.capability = frozenset(capability)

    # ------------------------------------------------------------------
    def supported(self, operation: FlowImageOperation) -> bool:
        return operation in self.capability

    def is_character_master(self, operation: FlowImageOperation) -> bool:
        return operation in _CHARACTER_MASTER_OPS

    def requires_reference(self, operation: FlowImageOperation) -> bool:
        return operation in _REFERENCE_REQUIRED_OPS

    def requires_source_image(self, operation: FlowImageOperation) -> bool:
        return operation in _SOURCE_IMAGE_OPS

    # ------------------------------------------------------------------
    def configuration_actions(
        self, request: FlowImageRequest
    ) -> list[FlowUiAction]:
        """Typed configuration steps for the operation (plan 04 §17).

        Never a raw browser instruction: every step is a `FlowUiAction`
        with a semantic target consumed by the Phase 12/13 UI port.
        """
        op = request.operation
        actions: list[FlowUiAction] = [
            FlowUiAction("select", "generation_mode", "TEXT_TO_IMAGE", 60.0),
            FlowUiAction("select", "model_select", "model", 60.0),
            FlowUiAction("select", "aspect_ratio_select", "ratio", 60.0),
            FlowUiAction("fill", "prompt_field", request.prompt, 60.0),
        ]
        if self.requires_reference(op):
            for role, content_hash in request.reference_bindings:
                actions.append(
                    FlowUiAction(
                        "upload", "reference_upload", content_hash, 120.0
                    )
                )
        if self.requires_source_image(op):
            for role, content_hash in request.reference_bindings:
                actions.append(
                    FlowUiAction("upload", "source_upload", content_hash, 120.0)
                )
        return actions


__all__ = [
    "FlowImageOperation",
    "FlowImageRequest",
    "ImageOperationMapper",
]
