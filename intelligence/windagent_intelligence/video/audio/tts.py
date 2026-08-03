"""
TTS synthesis (plan 06 Phase 21 §8.3, gate VP21_AUDIO_PIPELINE_VERIFIED).

Provider-neutral TTS through a `TtsProviderPort` protocol (adapter injected
at composition — the module never imports a provider SDK).

Fail-closed rules:
- a synthesis request carries dialogue ID + voice profile hash + synthesis
  parameters and a deterministic `request_hash` (same inputs -> same hash) so
  duplicate submissions never double-charge;
- the returned audio must have a valid SHA-256 content hash, sample rate,
  channel layout and duration — an invalid output is NEVER published;
- a timeout / empty / corrupt output is a typed failure (never a silent
  fallback), recorded as an `AudioIssue`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from windagent_core.domain.video_production.audio import TtsAudioAsset
from windagent_core.domain.video_production.ids import TtsAudioAssetId, TtsRequestId

from windagent_intelligence.video.audio.models import AudioIssue, TtsSynthesisReceipt
from windagent_intelligence.video.ids import StableIdFactory

TTS_PIPELINE_VERSION = "1.0.0"


@dataclass(frozen=True)
class TtsSynthesisRequest:
    """Typed, provider-neutral TTS request (§8.3)."""

    request_id: TtsRequestId
    dialogue_id: str
    text: str
    voice_profile_hash: str
    language: str = "vi-VN"
    locale: str = "vi-VN"
    synthesis_params: Dict[str, Any] = field(default_factory=dict)
    request_hash: str = ""

    def compute_request_hash(self) -> str:
        canonical = json.dumps(
            {
                "dialogue_id": self.dialogue_id,
                "text": self.text,
                "voice_profile_hash": self.voice_profile_hash,
                "language": self.language,
                "locale": self.locale,
                "synthesis_params": self.synthesis_params,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TtsSynthesisResult:
    """Raw TTS completion (never raises on provider I/O)."""

    request_id: str
    content: bytes = b""
    sample_rate: int = 0
    channel_layout: str = ""
    duration_seconds: float = 0.0
    provider: str = ""
    model: str = ""
    voice_id: str = ""
    timed_out: bool = False


@runtime_checkable
class TtsProviderPort(Protocol):
    """Port for TTS synthesis (adapter implemented at composition)."""

    def synthesize(self, request: TtsSynthesisRequest) -> TtsSynthesisResult: ...
    async def asynthesize(self, request: TtsSynthesisRequest) -> TtsSynthesisResult: ...


class TtsSynthesizer:
    """Runs + strictly validates TTS output (plan §8.3)."""

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()

    # -- sync ------------------------------------------------------------
    def synthesize(
        self,
        port: TtsProviderPort,
        request: TtsSynthesisRequest,
    ) -> TtsSynthesisReceipt:
        raw = port.synthesize(request)
        return self._evaluate(raw, request)

    # -- async -----------------------------------------------------------
    async def asynthesize(
        self,
        port: TtsProviderPort,
        request: TtsSynthesisRequest,
    ) -> TtsSynthesisReceipt:
        raw = await port.asynthesize(request)
        return self._evaluate(raw, request)

    # -- validation core ----------------------------------------------------
    def _evaluate(self, raw: TtsSynthesisResult, request: TtsSynthesisRequest) -> TtsSynthesisReceipt:
        issues: List[AudioIssue] = []
        assets: List[TtsAudioAsset] = []

        if raw.timed_out:
            issues.append(
                AudioIssue(
                    code="TTS_TIMEOUT",
                    message=f"TTS synthesis timed out for dialogue {request.dialogue_id}.",
                    dialogue_id=request.dialogue_id,
                )
            )
            return TtsSynthesisReceipt(assets=assets, issues=issues)

        if not raw.content:
            issues.append(
                AudioIssue(
                    code="TTS_EMPTY_OUTPUT",
                    message=f"TTS returned empty audio for dialogue {request.dialogue_id}.",
                    dialogue_id=request.dialogue_id,
                )
            )
            return TtsSynthesisReceipt(assets=assets, issues=issues)

        if raw.sample_rate <= 0 or not raw.channel_layout or raw.duration_seconds <= 0:
            issues.append(
                AudioIssue(
                    code="TTS_INVALID_OUTPUT",
                    message=(
                        f"TTS output for dialogue {request.dialogue_id} is invalid "
                        "(missing sample rate / channel layout / duration)."
                    ),
                    dialogue_id=request.dialogue_id,
                    details={
                        "sample_rate": raw.sample_rate,
                        "channel_layout": raw.channel_layout,
                        "duration_seconds": raw.duration_seconds,
                    },
                )
            )
            return TtsSynthesisReceipt(assets=assets, issues=issues)

        content_hash = hashlib.sha256(raw.content).hexdigest()
        assets.append(
            TtsAudioAsset(
                asset_id=TtsAudioAssetId(
                    self.id_factory.entity_id("tsa", request.request_hash)
                ),
                content_hash=content_hash,
                sample_rate=raw.sample_rate,
                channel_layout=raw.channel_layout,
                duration_seconds=raw.duration_seconds,
                byte_size=len(raw.content),
                source_request_hash=request.request_hash,
                provider=raw.provider,
                model=raw.model,
                voice_id=raw.voice_id,
            )
        )
        return TtsSynthesisReceipt(assets=assets, issues=issues)


__all__ = [
    "TTS_PIPELINE_VERSION",
    "TtsSynthesisRequest",
    "TtsSynthesisResult",
    "TtsProviderPort",
    "TtsSynthesizer",
]
