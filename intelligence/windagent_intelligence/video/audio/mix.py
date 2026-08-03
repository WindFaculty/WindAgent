"""
SFX / BGM / mix planning (plan 06 Phase 21 §8.5, gate
VP21_AUDIO_PIPELINE_VERIFIED).

Rules (plan §8.5):
- SFX/music cues carry license + provenance — an unknown license is a
  blocking finding, never published;
- cues bind to a timeline position/shot with fade intent;
- dialogue ducking, loudness target and peak ceiling are a VERSIONED mix
  policy (not hard-coded in the domain);
- a BGM change invalidates ONLY the mix/final cut, never the visual clips;
- the mix output carries a command/parameter manifest.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from windagent_core.domain.video_production.audio import (
    AudioMixPlan,
    MusicCue,
    SoundEffectCue,
    compute_mix_hash,
)
from windagent_core.domain.video_production.enums import LicenseState
from windagent_core.domain.video_production.ids import AudioMixPlanId

from windagent_intelligence.video.audio.models import AudioIssue
from windagent_intelligence.video.ids import StableIdFactory

MIX_VERSION = "1.0.0"
DEFAULT_LOUDNESS_TARGET_LUFS = -16.0
DEFAULT_PEAK_CEILING_DB = -1.0
DEFAULT_DUCKING_DB = -12.0


class MixPlanner:
    """Deterministic mix planning with license + technical gates (§8.5)."""

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        loudness_target_lufs: float = DEFAULT_LOUDNESS_TARGET_LUFS,
        peak_ceiling_db: float = DEFAULT_PEAK_CEILING_DB,
        ducking_db: float = DEFAULT_DUCKING_DB,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.loudness_target_lufs = loudness_target_lufs
        self.peak_ceiling_db = peak_ceiling_db
        self.ducking_db = ducking_db

    def plan(
        self,
        *,
        project_id: str,
        revision_id: str,
        dialogue_tracks,
        sfx_cues: Optional[List[SoundEffectCue]] = None,
        music_cues: Optional[List[MusicCue]] = None,
        command_manifest: Optional[Dict[str, Any]] = None,
    ) -> tuple[AudioMixPlan, List[AudioIssue]]:
        """Build the versioned mix plan; unknown-license cues fail closed."""
        issues: List[AudioIssue] = []
        sfx_cues = list(sfx_cues or [])
        music_cues = list(music_cues or [])

        for cue in sfx_cues:
            if cue.license_state == LicenseState.UNKNOWN or cue.license_state == LicenseState.REJECTED:
                issues.append(
                    AudioIssue(
                        code="UNKNOWN_CUE_LICENSE",
                        message=(
                            f"SFX cue {cue.cue_id} has license state "
                            f"{cue.license_state.value} — not publishable."
                        ),
                        details={"cue_id": str(cue.cue_id), "license": cue.license_state.value},
                    )
                )
        for cue in music_cues:
            if cue.license_state == LicenseState.UNKNOWN or cue.license_state == LicenseState.REJECTED:
                issues.append(
                    AudioIssue(
                        code="UNKNOWN_CUE_LICENSE",
                        message=(
                            f"Music cue {cue.cue_id} has license state "
                            f"{cue.license_state.value} — not publishable."
                        ),
                        details={"cue_id": str(cue.cue_id), "license": cue.license_state.value},
                    )
                )

        mix = AudioMixPlan(
            mix_id=AudioMixPlanId(self.id_factory.entity_id("amx", f"{project_id}:{revision_id}")),
            project_id=project_id,
            revision_id=revision_id,
            dialogue_tracks=list(dialogue_tracks),
            sound_effect_cues=sfx_cues,
            music_cues=music_cues,
            dialogue_ducking_db=self.ducking_db,
            loudness_target_lufs=self.loudness_target_lufs,
            peak_ceiling_db=self.peak_ceiling_db,
            mix_policy_version="1.0.0",
            command_manifest=dict(command_manifest or {}),
        )
        mix = mix.model_copy(
            update={
                "mix_hash": compute_mix_hash(
                    project_id=project_id,
                    revision_id=revision_id,
                    mix_payload=json.loads(mix.model_dump_json()),
                    mix_policy_version=mix.mix_policy_version,
                )
            }
        )
        return mix, issues


__all__ = ["MIX_VERSION", "MixPlanner"]
