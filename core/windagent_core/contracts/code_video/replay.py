"""
Core contracts for Code Video Replay data types.

Pure data contracts — no implementation, no tool dependencies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TypingSpeedMode(str, Enum):
    """Typing velocity modes for code typing simulation."""
    INSTANT = "instant"
    FAST = "fast"
    NORMAL = "normal"
    SLOW = "slow"
    CUSTOM = "custom"


SPEED_MODE_CPS_MAP: Dict[TypingSpeedMode, float] = {
    TypingSpeedMode.INSTANT: 10_000.0,
    TypingSpeedMode.FAST: 60.0,
    TypingSpeedMode.NORMAL: 25.0,
    TypingSpeedMode.SLOW: 12.0,
}


@dataclass(frozen=True)
class ReplayStepRecord:
    """Immutable record of an executed action step during replay."""
    scene_id: str
    action_id: str
    action_type: str
    start_ms: int
    duration_ms: int
    end_ms: int
    status: str
    active_file: Optional[str]
    editor_content_hash: str
    terminal_last_command: Optional[str]
    terminal_lines_count: int
    visual_mode: str
    step_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReplayTrace:
    """Complete execution trace and determinism receipt for a Code Video Plan replay."""
    video_id: str
    plan_source_hash: str
    total_duration_ms: int
    total_scenes: int
    total_actions: int
    steps: List[ReplayStepRecord]
    action_sequence_hash: str
    checkpoint_hash: str
    terminal_output_hash: str
    composite_replay_hash: str
    status: str
    started_at_utc: str
    completed_at_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "plan_source_hash": self.plan_source_hash,
            "total_duration_ms": self.total_duration_ms,
            "total_scenes": self.total_scenes,
            "total_actions": self.total_actions,
            "action_sequence_hash": self.action_sequence_hash,
            "checkpoint_hash": self.checkpoint_hash,
            "terminal_output_hash": self.terminal_output_hash,
            "composite_replay_hash": self.composite_replay_hash,
            "status": self.status,
            "started_at_utc": self.started_at_utc,
            "completed_at_utc": self.completed_at_utc,
            "steps": [s.to_dict() for s in self.steps],
        }

    def to_json(self, indent: int = 2) -> str:
        import json
        return json.dumps(self.to_dict(), indent=indent)


@dataclass(frozen=True)
class CheckpointDefinition:
    """Definition of a verified code checkpoint."""
    checkpoint_id: str
    description: str
    files: Dict[str, str] = field(default_factory=dict)
