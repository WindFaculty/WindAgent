"""
Duration budget policy (plan §9.2 / docs: director/duration_budget_policy.md).

The policy is versioned and deterministic:
- frame-rate assumption and rounding rule are explicit and versioned;
- dialogue duration is estimated from a chars-per-second reading rate;
- lead/tail handle time and transition time are explicit, never hidden;
- dialogue is NEVER silently cut — a dialogue that does not fit its shot is
  surfaced as a `DIALOGUE_DURATION_MISMATCH` issue (plan §9.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from windagent_core.domain.video_production.enums import TransitionType

# Canonical reading-rate assumptions (chars per second). Latin/CJK tolerant:
# CJK text is denser, so a conservative global rate avoids silently over-tight
# durations. Rate is a policy input and versioned with the policy.
DEFAULT_DIALOGUE_CHARS_PER_SECOND = 8.0
DEFAULT_LINE_PAUSE_SECONDS = 0.4
DEFAULT_HANDLE_SECONDS = 0.5  # lead-in + tail per shot
DEFAULT_TOTAL_TOLERANCE = 0.10  # ±10% per DIR-REQ-001

DEFAULT_TRANSITION_SECONDS: Dict[TransitionType, float] = {
    TransitionType.CUT: 0.0,
    TransitionType.FADE: 0.6,
    TransitionType.DISSOLVE: 0.8,
    TransitionType.WIPE: 0.6,
    TransitionType.MATCH_CUT: 0.4,
}


@dataclass(frozen=True)
class DurationBudgetPolicy:
    """Versioned, deterministic duration budget rules."""

    version: str = "1.0.0"
    frame_rate: int = 24
    dialogue_chars_per_second: float = DEFAULT_DIALOGUE_CHARS_PER_SECOND
    line_pause_seconds: float = DEFAULT_LINE_PAUSE_SECONDS
    handle_seconds: float = DEFAULT_HANDLE_SECONDS
    total_tolerance: float = DEFAULT_TOTAL_TOLERANCE
    transition_seconds: Dict[TransitionType, float] = field(
        default_factory=lambda: dict(DEFAULT_TRANSITION_SECONDS)
    )

    def round_to_frame(self, seconds: float) -> float:
        """Round to the nearest frame at the policy frame rate."""
        return round(seconds * self.frame_rate) / self.frame_rate

    def dialogue_duration(self, text: str) -> float:
        """Estimated on-screen duration of one dialogue line (incl. pause)."""
        if not text:
            return 0.0
        speaking = len(text) / self.dialogue_chars_per_second
        return self.round_to_frame(speaking + self.line_pause_seconds)

    def shot_duration_with_handles(self, planned_seconds: float) -> float:
        """Planned shot duration plus explicit lead-in/tail handles."""
        return self.round_to_frame(planned_seconds + 2 * self.handle_seconds)

    def transition_seconds_for(self, transition: TransitionType) -> float:
        return self.transition_seconds.get(transition, 0.0)

    def total_timeline_seconds(self, shots: list) -> float:
        """Sum of shot durations + handles + inter-shot transition time."""
        if not shots:
            return 0.0
        body = sum(self.shot_duration_with_handles(s.duration_seconds) for s in shots)
        transitions = sum(
            self.transition_seconds_for(_transition_between(prev, curr))
            for prev, curr in zip(shots, shots[1:])
        )
        return self.round_to_frame(body + transitions)

    def in_budget(self, total_seconds: float, target_seconds: float) -> bool:
        if target_seconds <= 0:
            return True
        low = target_seconds * (1 - self.total_tolerance)
        high = target_seconds * (1 + self.total_tolerance)
        return low <= total_seconds <= high

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "frame_rate": self.frame_rate,
            "dialogue_chars_per_second": self.dialogue_chars_per_second,
            "line_pause_seconds": self.line_pause_seconds,
            "handle_seconds": self.handle_seconds,
            "total_tolerance": self.total_tolerance,
            "transition_seconds": {
                k.value: v for k, v in self.transition_seconds.items()
            },
        }


def _transition_between(prev: object, curr: object) -> TransitionType:
    """Transition type of the OUTGOING shot (`prev`), CUT when unknown."""
    transition = getattr(prev, "transition_type", TransitionType.CUT)
    return transition if isinstance(transition, TransitionType) else TransitionType.CUT


__all__ = [
    "DurationBudgetPolicy",
    "DEFAULT_DIALOGUE_CHARS_PER_SECOND",
    "DEFAULT_LINE_PAUSE_SECONDS",
    "DEFAULT_HANDLE_SECONDS",
    "DEFAULT_TOTAL_TOLERANCE",
    "DEFAULT_TRANSITION_SECONDS",
]
