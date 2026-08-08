"""
Provider-neutral AI motion ports (VP3D Phase 17, stage_h §5).

`MotionGenerationPort` is the base contract every motion provider adapter
implements; `TextToMotionPort` and `VideoToMotionPort` are the two concrete
modalities the pipeline consumes. No provider SDK object, endpoint or session
ever leaks into the kernel — adapters (e.g. the deterministic fake) implement
these protocols and return typed `RawMotionArtifact`s that stay QUARANTINED
until the adapter's approve chain clears them.

A provider failure that is transient (network blip, provider 5xx) is
signalled with `TransientProviderError` so the retry policy can distinguish
"retry within budget" from "never retry" causes (backlog 6).
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from windagent_core.domain.video_production.ai_motion import (
    MotionCapability,
    MotionGenerationRequest,
    RawMotionArtifact,
)


class TransientProviderError(Exception):
    """A transient provider-side failure (backlog 6: retryable by cause).

    Only this cause is retried within the request budget; validation,
    capability and license failures never retry.
    """


@runtime_checkable
class MotionGenerationPort(Protocol):
    """Base port: capability contract + one generation call."""

    def capability(self) -> MotionCapability:
        """The provider's capability contract (backlog 1)."""
        ...

    def generate(self, request: MotionGenerationRequest) -> RawMotionArtifact:
        """Generate one raw artifact; may raise TransientProviderError."""
        ...


@runtime_checkable
class TextToMotionPort(MotionGenerationPort, Protocol):
    """Text-prompt driven motion generation (stage_h §5 pipeline)."""

    def generate_text(self, request: MotionGenerationRequest) -> RawMotionArtifact:
        """Generate from a text prompt (the request carries the prompt)."""
        ...


@runtime_checkable
class VideoToMotionPort(MotionGenerationPort, Protocol):
    """Video-reference driven motion generation (stage_h §5 pipeline)."""

    def generate_video(
        self,
        request: MotionGenerationRequest,
        video_ref: str,
    ) -> RawMotionArtifact:
        """Generate from a video reference; `video_ref` names the source."""
        ...


__all__ = [
    "TransientProviderError",
    "MotionGenerationPort",
    "TextToMotionPort",
    "VideoToMotionPort",
]
