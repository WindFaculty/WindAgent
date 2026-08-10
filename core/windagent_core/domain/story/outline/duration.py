"""
Deterministic duration planning (Plan B B5; versioned formula, no provider).

Adapts the proven `DurationBudgetPolicy` pattern (chars-per-second +
tolerance) into a Story-scoped, versioned formula. The final slice targets
180-300 seconds (3-5 minutes).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

__all__ = [
    "DURATION_FORMULA_VERSION",
    "MIN_EPISODE_SECONDS",
    "MAX_EPISODE_SECONDS",
    "DEFAULT_TOLERANCE_SECONDS",
    "DEFAULT_CHARS_PER_SECOND",
    "TRANSITION_BUDGET_SECONDS",
    "estimate_text_seconds",
    "estimate_scene_seconds",
    "duration_issues",
]

DURATION_FORMULA_VERSION = "duration_formula/v1"
MIN_EPISODE_SECONDS = 180
MAX_EPISODE_SECONDS = 300
DEFAULT_TOLERANCE_SECONDS = 15
DEFAULT_CHARS_PER_SECOND = 3.5          # Vietnamese narration: ~3.5 chars/sec
TRANSITION_BUDGET_SECONDS = 2.0         # per scene transition


def estimate_text_seconds(text: str, chars_per_second: float = DEFAULT_CHARS_PER_SECOND) -> int:
    """Deterministic seconds estimate for a block of text."""
    if not text or not text.strip():
        return 0
    return max(1, int(round(len(text.strip()) / chars_per_second)))


def estimate_scene_seconds(
    *,
    action_description: str = "",
    dialogue_texts: Optional[list[str]] = None,
    narration_text: str = "",
    transitions: int = 1,
) -> int:
    """Deterministic per-scene estimate: action + dialogue + narration + transitions."""
    dialogue = sum(estimate_text_seconds(t) for t in (dialogue_texts or []))
    action = estimate_text_seconds(action_description)
    narration = estimate_text_seconds(narration_text)
    total = dialogue + action + narration + TRANSITION_BUDGET_SECONDS * max(0, transitions)
    return max(1, int(round(total)))


def duration_issues(
    *,
    total_seconds: int,
    target_seconds: int,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    enforce_bounds: bool = True,
) -> list[Dict[str, Any]]:
    """Deterministic duration findings (empty list == within tolerance).

    Returns issue-shaped dicts (code/severity/evidence) so validators can
    attach JSON-pointer locations without duplicating the math.
    """
    findings: list[Dict[str, Any]] = []
    if abs(total_seconds - target_seconds) > tolerance_seconds:
        findings.append({
            "code": "DURATION_SUM",
            "severity": "BLOCKING",
            "evidence": (
                f"total {total_seconds}s vs target {target_seconds}s "
                f"(tolerance {tolerance_seconds}s)"
            ),
        })
    if enforce_bounds and not (MIN_EPISODE_SECONDS <= total_seconds <= MAX_EPISODE_SECONDS):
        findings.append({
            "code": "DURATION_BOUND",
            "severity": "BLOCKING",
            "evidence": (
                f"total {total_seconds}s outside [{MIN_EPISODE_SECONDS}, "
                f"{MAX_EPISODE_SECONDS}]s"
            ),
        })
    return findings
