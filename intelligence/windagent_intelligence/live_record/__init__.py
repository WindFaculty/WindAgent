"""Live Record intelligence — RECORDING_PREPARER + LIVE_DIRECTOR + NARRATION_TTS roles.

See ban_ke_hoach_v1.md Section 5, 8, 11 — three distinct model roles:
  RECORDING_PREPARER  → builds Recording Preparation Package before recording
  LIVE_DIRECTOR       → observes screen + chooses next prepared action (Live API)
  NARRATION_TTS       → generates voice from timeline.jsonl after recording

This package owns prompt templates for RECORDING_PREPARER and wiring for
LIVE_DIRECTOR model routing (via ModelCapabilityProfile).
"""

from windagent_intelligence.live_record.preparation_service import (
    RecordingPreparationIntelligenceService,
)

__all__ = ["RecordingPreparationIntelligenceService"]
