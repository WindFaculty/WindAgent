""""
TtsProviderPort — TTS synthesis contract (VP3D Phase 10, Stage E).

Provider-neutral by design: this port is the ONLY surface a TTS provider
adapter talks through, exactly like `MediaGenerationProviderPort` for media.
No provider SDK, no credentials, no browser objects, no `windagent_providers`
import ever appears here. Secrets are redacted before a result is persisted.

Capability metadata (stage_e backlog 1):
  - supported languages/locales,
  - emotion support,
  - output sample rates,
  - whether the provider returns word/token/phoneme timing,
  - local vs API execution mode.

A capability the provider does NOT advertise is never assumed: the orchestrator
plans the alignment DAG from the advertised features and the forced-aligner is
a separate adapter that never fabricates confidence.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from windagent_core.domain.video_production.enums import (
    TtsCapabilityFeature,
    TtsMode,
)


@runtime_checkable
class TtsProviderCapability(Protocol):
    """Capability metadata a TTS provider advertises to the audio orchestrator.

    Shown as a Protocol only so the adapter owns the concrete value object;
    the domain uses `TtsProviderCapability` duck-typed via the port.
    """

    provider_id: str
    name: str
    supported_locales: List[str]
    modes: List[TtsMode]
    sample_rates: List[int]
    channels: List[str]
    features: List[TtsCapabilityFeature]
    emotion_labels: List[str]

    def supports_locale(self, locale: str) -> bool:
        ...
        return locale in self.supported_locales

    def supports_feature(self, feature: TtsCapabilityFeature) -> bool:
        ...
        return feature in self.features

    def supports_sample_rate(self, rate: int) -> bool:
        ...
        return rate in self.sample_rates


@runtime_checkable
class TtsProviderPort(Protocol):
    """Port for a TTS synthesis provider (local engine or remote API).

    Synthesize takes a synthesizable request (text + voice identity + params)
    and returns a raw audio handle (bytes/stream + declared metadata). The
    domain validates the handle before it may be published (backlog 4); a
    provider's returned bytes are never trusted without validation.
    """

    async def capability(self) -> TtsProviderCapability:
        """Advertised capability metadata for this provider instance."""

    async def synthesize(self, request: object) -> "TtsSynthesisHandle":
        """Synthesize one voice line.

        `request` is a `TtsSynthesisRequest` (domain value object). Returns a
        raw handle carrying the byte stream plus *declared* sample-rate /
        channel / duration metadata that the domain MUST validate before use.

        Raises:
          TtsTimeoutError — exceeded the provider budget;
          TtsEmptyOutputError — zero-byte / absent output;
          UnsupportedLocaleError — locale not in advertised capability.
        """


@runtime_checkable
class TtsSynthesisHandle(Protocol):
    """Raw TTS output handle: bytes + *declared* metadata (never trusted)."""

    provider_id: str
    provider_name: str
    audio_bytes: bytes
    declared_sample_rate: int
    declared_channel_layout: str
    declared_duration_seconds: Optional[float]
    mime_type: str


__all__ = ["TtsProviderPort", "TtsProviderCapability", "TtsSynthesisHandle"]
