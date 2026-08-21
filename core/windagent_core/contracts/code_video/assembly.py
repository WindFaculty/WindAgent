"""
Core contracts for Code Video Assembly types.

Pure data contracts — no implementation, no tool dependencies.
Consumers import from here; implementations live in windagent_tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Set

from windagent_core.contracts.code_video.models import CodeVideoPlan
from windagent_core.errors.exceptions import ValidationError


class TransitionType(str, Enum):
    """Allowed tutorial-safe visual transitions."""
    HARD_CUT = "hard_cut"
    CUT = "cut"
    SHORT_DISSOLVE = "short_dissolve"
    DISSOLVE = "dissolve"
    ZOOM = "zoom"
    PAN = "pan"
    HIGHLIGHT = "highlight"


FORBIDDEN_FLASHY_TRANSITIONS: Set[str] = {
    "spin", "wipe", "star", "explode", "cube", "flip",
    "circle", "flash", "glitch", "swirl", "spiral",
}


@dataclass(frozen=True)
class TransitionRule:
    """Individual transition rule between scenes."""
    transition_type: TransitionType
    duration_ms: int = 0
    source_scene: str = ""
    target_scene: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transition_type": self.transition_type.value,
            "duration_ms": self.duration_ms,
            "source_scene": self.source_scene,
            "target_scene": self.target_scene,
            "metadata": dict(self.metadata),
        }


@dataclass
class TransitionPolicy:
    """Policy enforcer for tutorial video transitions."""
    allowed_transitions: Set[str] = field(
        default_factory=lambda: {t.value for t in TransitionType}
    )
    max_dissolve_duration_ms: int = 1500

    def validate_transition(self, transition_name: str, duration_ms: int = 0) -> TransitionType:
        norm = transition_name.lower().strip()
        if norm in FORBIDDEN_FLASHY_TRANSITIONS:
            raise ValidationError(
                f"Flashy transition '{transition_name}' is strictly forbidden in code tutorial production. "
                f"Allowed: {sorted(list(self.allowed_transitions))}"
            )
        try:
            tt = TransitionType(norm)
        except ValueError:
            raise ValidationError(
                f"Unknown or disallowed transition '{transition_name}'. Allowed: {sorted(list(self.allowed_transitions))}"
            )
        if tt in (TransitionType.SHORT_DISSOLVE, TransitionType.DISSOLVE):
            if duration_ms > self.max_dissolve_duration_ms:
                raise ValidationError(
                    f"Dissolve duration {duration_ms}ms exceeds maximum allowable limit of {self.max_dissolve_duration_ms}ms"
                )
        return tt


@dataclass
class CueSheetEntry:
    """Single voiceover cue entry matching script scene timecodes."""
    scene_id: str
    title: str
    start_timecode: str
    end_timecode: str
    duration_seconds: float
    voice_reference: str

    def to_csv_row(self) -> str:
        return f"{self.scene_id},{self.title},{self.start_timecode},{self.end_timecode},{self.duration_seconds:.3f},{self.voice_reference}"


def format_timecode_ms(ms: int) -> str:
    """Format milliseconds into MM:SS.mmm format."""
    total_seconds = ms / 1000.0
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:06.3f}"


@dataclass
class CueSheet:
    """Voiceover cue sheet collection for post-production audio handoff."""
    entries: List[CueSheetEntry] = field(default_factory=list)

    def to_csv(self) -> str:
        header = "scene_id,title,start_timecode,end_timecode,duration_seconds,voice_reference\n"
        rows = [e.to_csv_row() for e in self.entries]
        return header + "\n".join(rows) + "\n"

    @classmethod
    def from_csv(cls, csv_text: str) -> CueSheet:
        lines = [line.strip() for line in csv_text.strip().splitlines() if line.strip()]
        if not lines:
            return cls()
        entries: List[CueSheetEntry] = []
        for line in lines[1:]:  # skip header
            parts = line.split(",")
            if len(parts) >= 6:
                entries.append(
                    CueSheetEntry(
                        scene_id=parts[0].strip(),
                        title=parts[1].strip(),
                        start_timecode=parts[2].strip(),
                        end_timecode=parts[3].strip(),
                        duration_seconds=float(parts[4].strip()),
                        voice_reference=parts[5].strip(),
                    )
                )
        return cls(entries=entries)

    @classmethod
    def from_plan(cls, plan: CodeVideoPlan) -> CueSheet:
        entries: List[CueSheetEntry] = []
        for scene in plan.scenes:
            entries.append(
                CueSheetEntry(
                    scene_id=scene.scene_id,
                    title=scene.title,
                    start_timecode=format_timecode_ms(scene.start_ms),
                    end_timecode=format_timecode_ms(scene.end_ms),
                    duration_seconds=scene.duration_ms / 1000.0,
                    voice_reference=f"CUE_{scene.scene_id.upper()}",
                )
            )
        return cls(entries=entries)


@dataclass
class VideoAssemblyConfig:
    """Assembly configuration parameters."""
    video_id: str = "video-02"
    master_resolution: str = "2560x1440"
    delivery_resolution: str = "1920x1080"
    fps: int = 30
    total_duration_ms: int = 975_000
    expected_scenes: int = 19
    expected_frames: int = 29_250
    audio_policy: str = "EXCLUDED"
    synthesize_real_video: bool = False
    output_dir: Path = field(default_factory=lambda: Path("artifacts/code_video/video_02/final"))


@dataclass
class MasterAssemblyResult:
    """Final outcome of Visual Master Assembly for Video 02."""
    video_id: str
    status: str  # VERIFIED
    master_1440p_path: str
    master_1440p_hash: str
    delivery_1080p_path: str
    delivery_1080p_hash: str
    timeline_path: str
    cue_sheet_path: str
    manifest_path: str
    total_duration_ms: int = 975_000
    total_frames: int = 29_250
    scene_count: int = 19
    audio_policy: str = "EXCLUDED"
    zero_audio_verified: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "status": self.status,
            "master_1440p_path": self.master_1440p_path,
            "master_1440p_hash": self.master_1440p_hash,
            "delivery_1080p_path": self.delivery_1080p_path,
            "delivery_1080p_hash": self.delivery_1080p_hash,
            "timeline_path": self.timeline_path,
            "cue_sheet_path": self.cue_sheet_path,
            "manifest_path": self.manifest_path,
            "total_duration_ms": self.total_duration_ms,
            "total_frames": self.total_frames,
            "scene_count": self.scene_count,
            "audio_policy": self.audio_policy,
            "zero_audio_verified": self.zero_audio_verified,
            "metadata": dict(self.metadata),
        }

    def to_json(self, indent: int = 2) -> str:
        import json
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class TakesManifest:
    """Consolidated manifest of all captured takes for a video project."""
    video_id: str
    total_takes: int
    total_duration_ms: int
    total_frames: int
    master_resolution: str = "2560x1440"
    fps: int = 30
    audio_policy: str = "EXCLUDED"
    takes: List[Any] = field(default_factory=list)  # List[TakeReceipt] - forward ref
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "total_takes": self.total_takes,
            "total_duration_ms": self.total_duration_ms,
            "total_frames": self.total_frames,
            "master_resolution": self.master_resolution,
            "fps": self.fps,
            "audio_policy": self.audio_policy,
            "takes": [t.to_dict() for t in self.takes] if self.takes else [],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TakesManifest:
        from windagent_core.contracts.code_video.capture import TakeReceipt
        takes = [TakeReceipt.from_dict(t) for t in data.get("takes", [])]
        return cls(
            video_id=str(data.get("video_id", "video-02")),
            total_takes=int(data.get("total_takes", len(takes))),
            total_duration_ms=int(data.get("total_duration_ms", sum(t.duration_ms for t in takes))),
            total_frames=int(data.get("total_frames", sum(t.frame_count for t in takes))),
            master_resolution=str(data.get("master_resolution", "2560x1440")),
            fps=int(data.get("fps", 30)),
            audio_policy=str(data.get("audio_policy", "EXCLUDED")),
            takes=takes,
            metadata=dict(data.get("metadata", {})),
        )

    def to_json(self, indent: int = 2) -> str:
        import json
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> TakesManifest:
        import json
        try:
            data = json.loads(json_str)
        except Exception as e:
            raise ValidationError(f"Failed to parse JSON for TakesManifest: {e}")
        return cls.from_dict(data)
