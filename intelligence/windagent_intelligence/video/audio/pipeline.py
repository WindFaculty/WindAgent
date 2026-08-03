"""
Audio pipeline orchestrator (plan 06 Phase 21 §8, gate
VP21_AUDIO_PIPELINE_VERIFIED).

Runs the audio workstream IN ORDER:

    dialogue preparation (§8.1)
        ↓
    voice casting (§8.2)
        ↓
    TTS synthesis (§8.3) — provider-neutral port, fail closed
        ↓
    forced alignment + timing proposal (§8.4)
        ↓
    mix plan (§8.5) — license + loudness/peak technical gates

Fail-closed guarantees:
- a dialogue line that is empty/overlong is surfaced, never silently dropped;
- a voice preview is never a final track without human approval;
- a TTS timeout / empty / invalid output is never published;
- low alignment confidence routes to human review, timing issues are never
  hidden; an overlong line is proposed (timing/shot change), never cut;
- an SFX/BGM cue with unknown/rejected license blocks the mix.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional

from windagent_core.domain.video_production.audio import (
    AudioMixPlan,
    CharacterVoiceProfile,
    TtsAudioAsset,
    WordTimestamp,
)
from windagent_core.domain.video_production.ids import TtsRequestId
from windagent_core.domain.video_production.screenplay import DialogueLine

from windagent_intelligence.video.audio.alignment import AlignmentService
from windagent_intelligence.video.audio.dialogue import DialoguePreparer
from windagent_intelligence.video.audio.mix import MixPlanner
from windagent_intelligence.video.audio.models import (
    AlignmentReceipt,
    AudioIssue,
    AudioPipelineReceipt,
    TtsSynthesisReceipt,
)
from windagent_intelligence.video.audio.tts import (
    TtsProviderPort,
    TtsSynthesisRequest,
    TtsSynthesizer,
)
from windagent_intelligence.video.audio.voice import VoiceCastingService
from windagent_intelligence.video.ids import StableIdFactory

AUDIO_PIPELINE_VERSION = "1.0.0"


@dataclass(frozen=True)
class AudioPipelineConfig:
    """Typed pipeline options (release 0.1)."""

    language: str = "vi-VN"
    locale: str = "vi-VN"
    require_mix: bool = True  # the PoC always needs a mix plan


class AudioPipelineService:
    """Orchestrates the audio workstream (plan §8)."""

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        dialogue_preparer: Optional[DialoguePreparer] = None,
        voice_casting: Optional[VoiceCastingService] = None,
        tts: Optional[TtsSynthesizer] = None,
        alignment: Optional[AlignmentService] = None,
        mix_planner: Optional[MixPlanner] = None,
        config: Optional[AudioPipelineConfig] = None,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.dialogue_preparer = dialogue_preparer or DialoguePreparer(id_factory=self.id_factory)
        self.voice_casting = voice_casting or VoiceCastingService(id_factory=self.id_factory)
        self.tts = tts or TtsSynthesizer(id_factory=self.id_factory)
        self.alignment = alignment or AlignmentService(id_factory=self.id_factory)
        self.mix_planner = mix_planner or MixPlanner(id_factory=self.id_factory)
        self.config = config or AudioPipelineConfig()

    def run(
        self,
        *,
        project_id: str,
        revision_id: str,
        dialogue_lines: List[DialogueLine],
        tts_port: TtsProviderPort,
        voice_catalog: Optional[List[CharacterVoiceProfile]] = None,
        voice_approvals: Optional[Dict[str, str]] = None,
        word_timestamps_by_track: Optional[Dict[str, List[WordTimestamp]]] = None,
        shot_duration_by_track: Optional[Dict[str, float]] = None,
        sfx_cues=None,
        music_cues=None,
    ) -> AudioPipelineReceipt:
        """Run the full audio pipeline and return the immutable receipt."""
        issues: List[AudioIssue] = []

        # 1. Dialogue preparation (§8.1).
        dialogue = self.dialogue_preparer.prepare(
            dialogue_lines,
            language=self.config.language,
            locale=self.config.locale,
        )
        issues.extend(dialogue.issues)

        # 2. Voice casting (§8.2) — bind every character to an approved voice.
        character_ids = sorted({str(t.character_id) for t in dialogue.tracks})
        character_names = {
            str(t.character_id): str(t.character_id) for t in dialogue.tracks
        }
        cast = self.voice_casting.cast(
            character_ids=character_ids,
            character_names=character_names,
            catalog=voice_catalog or [],
            approvals=voice_approvals,
        )
        issues.extend(cast.issues)
        profile_by_char = {str(p.character_id): p for p in cast.profiles}

        # 3. TTS synthesis (§8.3) — provider-neutral, fail closed.
        tts_assets: List[TtsAudioAsset] = []
        tts_issues: List[AudioIssue] = []
        tracks_by_dialogue = {str(t.dialogue_id): t for t in dialogue.tracks}
        for track in dialogue.tracks:
            profile = profile_by_char.get(str(track.character_id))
            if profile is None or not profile.approved:
                continue  # casting issue already recorded; no TTS without approval
            request = TtsSynthesisRequest(
                request_id=TtsRequestId(
                    self.id_factory.entity_id("ttr", str(track.dialogue_id))
                ),
                dialogue_id=str(track.dialogue_id),
                text=track.prepared_text or track.text,
                voice_profile_hash=profile.profile_hash(),
                language=track.language,
                locale=track.locale,
                synthesis_params={"mode": "standard", "sample_rate": 48000, "channels": 2},
            )
            request = replace(
                request, request_hash=request.compute_request_hash()
            )
            receipt = self.tts.synthesize(tts_port, request)
            tts_issues.extend(receipt.issues)
            for asset in receipt.assets:
                tts_assets.append(asset)
                # attach the validated asset to the track
                current = tracks_by_dialogue[str(track.dialogue_id)]
                tracks_by_dialogue[str(track.dialogue_id)] = current.model_copy(
                    update={"audio": asset, "voice_profile_hash": profile.profile_hash()}
                )
        issues.extend(tts_issues)
        tts_receipt = TtsSynthesisReceipt(assets=tts_assets, issues=tts_issues)

        # 4. Forced alignment + timing proposal (§8.4).
        aligned_tracks = [t for t in tracks_by_dialogue.values() if t.audio is not None]
        alignment: AlignmentReceipt = self.alignment.align(
            aligned_tracks,
            word_timestamps_by_track=word_timestamps_by_track,
            shot_duration_by_track=shot_duration_by_track,
        )
        issues.extend(alignment.issues)

        # 5. Mix plan (§8.5).
        mix: Optional[AudioMixPlan] = None
        if self.config.require_mix:
            mix, mix_issues = self.mix_planner.plan(
                project_id=project_id,
                revision_id=revision_id,
                dialogue_tracks=alignment.tracks,
                sfx_cues=sfx_cues,
                music_cues=music_cues,
            )
            issues.extend(mix_issues)

        return AudioPipelineReceipt(
            pipeline_version=AUDIO_PIPELINE_VERSION,
            dialogue=dialogue,
            voice_cast=cast,
            tts=tts_receipt,
            alignment=alignment,
            mix=mix,
            issues=issues,
        )


__all__ = ["AUDIO_PIPELINE_VERSION", "AudioPipelineConfig", "AudioPipelineService"]
