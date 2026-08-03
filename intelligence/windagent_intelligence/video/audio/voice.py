"""
Voice casting (plan 06 Phase 21 §8.2, gate VP21_AUDIO_PIPELINE_VERIFIED).

Picks a voice per character profile:
- the profile binds to a CHARACTER ID (never a display name) and records
  provider/model/voice/version + license/terms;
- a preview is NEVER a final track without explicit human approval
  (plan §8.2: \"Voice preview không trở thành final track nếu chưa approve\");
- real-voice likenesses require rights/consent metadata + approval;
- the same voice is not reused for two distinct characters when policy forbids
  (identity confusion guard).

Fully deterministic and offline (the TTS provider is a separate port).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from windagent_core.domain.video_production.audio import CharacterVoiceProfile

from windagent_intelligence.video.audio.models import AudioIssue, VoiceCastReceipt
from windagent_intelligence.video.ids import StableIdFactory

VOICE_CAST_VERSION = "1.0.0"


class VoiceCastingService:
    """Deterministic voice casting with approval gating (plan §8.2)."""

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        forbid_voice_reuse: bool = True,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.forbid_voice_reuse = forbid_voice_reuse

    def cast(
        self,
        *,
        character_ids: List[str],
        character_names: Dict[str, str],
        catalog: List[CharacterVoiceProfile],
        approvals: Optional[Dict[str, str]] = None,
    ) -> VoiceCastReceipt:
        """Map characters to approved voice profiles (deterministic).

        `catalog` holds candidate profiles (approved or preview). `approvals`
        maps `profile_id -> actor` for profiles approved by a human. A preview
        profile never becomes the final cast unless approved.
        """
        approvals = approvals or {}
        candidates: List[CharacterVoiceProfile] = []
        issues: List[AudioIssue] = []

        available: Dict[str, List[CharacterVoiceProfile]] = {}
        for profile in catalog:
            available.setdefault(str(profile.character_id), []).append(profile)

        used_voice_keys: Dict[str, str] = {}  # voice identity -> character

        for character_id in character_ids:
            char_name = character_names.get(character_id, character_id)
            pool = available.get(character_id, [])
            if not pool:
                issues.append(
                    AudioIssue(
                        code="NO_VOICE_PROFILE",
                        message=f"Character {character_id} ({char_name}) has no voice profile.",
                        details={"character_id": character_id},
                    )
                )
                continue

            # Prefer an APPROVED profile (by actor), else preview flagged.
            chosen: Optional[CharacterVoiceProfile] = None
            for profile in pool:
                if profile.approved:
                    chosen = profile
                    break
            if chosen is None:
                # human approval recorded in `approvals`
                for profile in pool:
                    if profile.profile_id.value in approvals:
                        chosen = profile.model_copy(
                            update={"approved": True, "approval_actor": approvals[profile.profile_id.value]}
                        )
                        break
            if chosen is None:
                # Only a preview is available -> not final without approval.
                preview = sorted(pool, key=lambda p: p.profile_id.value)[0]
                if self.forbid_voice_reuse:
                    # even a preview must not already be claimed by another char
                    voice_key = f"{preview.provider}:{preview.model}:{preview.voice_id}"
                    if voice_key in used_voice_keys and used_voice_keys[voice_key] != character_id:
                        issues.append(
                            AudioIssue(
                                code="VOICE_REUSE_FORBIDDEN",
                                message=(
                                    f"Voice {voice_key} already cast for "
                                    f"{used_voice_keys[voice_key]}; identity confusion risk."
                                ),
                                details={"character_id": character_id, "voice": voice_key},
                            )
                        )
                        continue
                    used_voice_keys[voice_key] = character_id
                issues.append(
                    AudioIssue(
                        code="PREVIEW_NOT_APPROVED",
                        message=(
                            f"Character {character_id} ({char_name}) only has a PREVIEW "
                            "voice; approval required before it becomes a final track."
                        ),
                        details={"profile_id": str(preview.profile_id)},
                    )
                )
                candidates.append(preview)
                continue

            if chosen.approved:
                voice_key = f"{chosen.provider}:{chosen.model}:{chosen.voice_id}"
                if self.forbid_voice_reuse and voice_key in used_voice_keys and used_voice_keys[voice_key] != character_id:
                    issues.append(
                        AudioIssue(
                            code="VOICE_REUSE_FORBIDDEN",
                            message=f"Approved voice {voice_key} already cast for {used_voice_keys[voice_key]}.",
                            details={"character_id": character_id, "voice": voice_key},
                        )
                    )
                    continue
                used_voice_keys[voice_key] = character_id
            candidates.append(chosen)

        return VoiceCastReceipt(profiles=candidates, issues=issues)

    def approve(self, profile: CharacterVoiceProfile, *, actor: str) -> CharacterVoiceProfile:
        """Audited human approval of a voice profile (§8.2).

        Approval NEVER fabricates a license state: an UNKNOWN rights_state
        stays UNKNOWN so the provenance gate can still block publishing
        (plan §7 — real-voice likenesses need rights/consent metadata).
        """
        return profile.model_copy(
            update={
                "approved": True,
                "approval_actor": actor,
                "preview_only": False,
            }
        )


__all__ = ["VOICE_CAST_VERSION", "VoiceCastingService"]
