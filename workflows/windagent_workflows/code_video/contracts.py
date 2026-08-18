"""
Code Video Contract and Intermediate Representation (IR) Models.

Defines strongly typed, validated, immutable data structures representing
the complete deterministic specification for code tutorial video production.
Adheres strictly to the Video 02 implementation specifications.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from enum import Enum
import io
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
from windagent_core.errors.exceptions import ValidationError


class ActionType(str, Enum):
    """Semantic actions executable by the Code Studio and Capture Engine."""
    OPEN_WORKSPACE = "OPEN_WORKSPACE"
    OPEN_FILE = "OPEN_FILE"
    CREATE_FILE = "CREATE_FILE"
    TYPE_TEXT = "TYPE_TEXT"
    REPLACE_TEXT = "REPLACE_TEXT"
    SELECT_RANGE = "SELECT_RANGE"
    HIGHLIGHT = "HIGHLIGHT"
    SCROLL = "SCROLL"
    ZOOM = "ZOOM"
    RUN_TERMINAL = "RUN_TERMINAL"
    WAIT = "WAIT"
    SHOW_OUTPUT = "SHOW_OUTPUT"
    SHOW_DIAGRAM = "SHOW_DIAGRAM"
    SHOW_TITLE = "SHOW_TITLE"
    SHOW_CHECKLIST = "SHOW_CHECKLIST"
    SHOW_ARCHITECTURE = "SHOW_ARCHITECTURE"
    SWITCH_LAYOUT = "SWITCH_LAYOUT"
    RESET_VIEW = "RESET_VIEW"


class VisualMode(str, Enum):
    """Visual stage layout modes for Code Video scenes."""
    CODE_STUDIO = "CODE_STUDIO"        # FileTree + CodeEditor + Terminal
    FULL_CODE = "FULL_CODE"            # Focused code editor view
    FULL_TERMINAL = "FULL_TERMINAL"    # Focused terminal view
    DIAGRAM = "DIAGRAM"                # Architecture / flow diagram stage
    TITLE_CARD = "TITLE_CARD"          # Fullscreen or overlay title card
    CHECKLIST = "CHECKLIST"            # Feature checklist card
    ARCHITECTURE = "ARCHITECTURE"      # Macro-architecture diagram
    SPLIT = "SPLIT"                    # Split view (Code + Diagram / Output)
    OUTRO = "OUTRO"                    # Outro / next video teaser


# Forbidden non-semantic parameter keys in actions
FORBIDDEN_COORDINATE_KEYS: Set[str] = {
    "x", "y", "pixel_x", "pixel_y", "coord_x", "coord_y", "screen_x", "screen_y",
    "mouse_x", "mouse_y", "click_x", "click_y"
}

# Forbidden audio configuration keys in Video 02 plans
FORBIDDEN_AUDIO_KEYS: Set[str] = {
    "audio_path", "tts_model", "voice_id", "voice_audio", "bgm_path", "audio_file"
}


@dataclass(frozen=True)
class Resolution:
    """Video frame resolution with standard presets and helpers."""
    width: int = 2560
    height: int = 1440

    @property
    def aspect_ratio(self) -> str:
        return f"{self.width}:{self.height}"

    def to_string(self) -> str:
        return f"{self.width}x{self.height}"

    @classmethod
    def from_string(cls, res_str: str) -> Resolution:
        parts = str(res_str).lower().replace("×", "x").split("x")
        if len(parts) != 2:
            raise ValidationError(f"Invalid resolution format '{res_str}'. Expected 'WIDTHxHEIGHT' (e.g. '2560x1440')")
        try:
            w, h = int(parts[0].strip()), int(parts[1].strip())
            if w <= 0 or h <= 0:
                raise ValueError()
            return cls(width=w, height=h)
        except Exception:
            raise ValidationError(f"Resolution width and height must be positive integers, got '{res_str}'")

    def to_dict(self) -> Dict[str, int]:
        return {"width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: Any) -> Resolution:
        if isinstance(data, Resolution):
            return data
        if isinstance(data, str):
            return cls.from_string(data)
        if isinstance(data, dict):
            return cls(
                width=int(data.get("width", 2560)),
                height=int(data.get("height", 1440)),
            )
        raise ValidationError(f"Cannot parse Resolution from type {type(data).__name__}")


@dataclass(frozen=True)
class OutputPolicy:
    """Output generation parameters and policy constraints."""
    master_resolution: str = "2560x1440"
    delivery_resolutions: List[str] = field(default_factory=lambda: ["1920x1080"])
    fps: int = 30
    audio_policy: str = "EXCLUDED"
    allow_live_network: bool = False
    color_space: str = "bt709"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "master_resolution": self.master_resolution,
            "delivery_resolutions": list(self.delivery_resolutions),
            "fps": self.fps,
            "audio_policy": self.audio_policy,
            "allow_live_network": self.allow_live_network,
            "color_space": self.color_space,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OutputPolicy:
        return cls(
            master_resolution=str(data.get("master_resolution", "2560x1440")),
            delivery_resolutions=list(data.get("delivery_resolutions", ["1920x1080"])),
            fps=int(data.get("fps", 30)),
            audio_policy=str(data.get("audio_policy", "EXCLUDED")),
            allow_live_network=bool(data.get("allow_live_network", False)),
            color_space=str(data.get("color_space", "bt709")),
        )


@dataclass(frozen=True)
class Action:
    """A semantic, deterministic action executed within a Scene."""
    action_id: str
    action_type: ActionType
    start_ms: int
    duration_ms: int
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.start_ms, int) or isinstance(self.start_ms, bool) or self.start_ms < 0:
            raise ValidationError(f"Action '{self.action_id}' start_ms must be a non-negative integer, got {self.start_ms}")
        if not isinstance(self.duration_ms, int) or isinstance(self.duration_ms, bool) or self.duration_ms < 0:
            raise ValidationError(f"Action '{self.action_id}' duration_ms must be a non-negative integer, got {self.duration_ms}")

        # Check forbidden coordinate keys
        for key in self.params:
            if key.lower() in FORBIDDEN_COORDINATE_KEYS:
                raise ValidationError(
                    f"Action '{self.action_id}' contains non-semantic coordinate key '{key}'. "
                    "Use semantic symbols, line numbers, or paths instead."
                )

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value if isinstance(self.action_type, ActionType) else str(self.action_type),
            "start_ms": self.start_ms,
            "duration_ms": self.duration_ms,
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Action:
        action_type_raw = data.get("action_type")
        if not action_type_raw:
            raise ValidationError(f"Missing 'action_type' in action data: {data}")
        try:
            action_type = ActionType(str(action_type_raw))
        except ValueError:
            raise ValidationError(f"Unknown action_type '{action_type_raw}'")

        return cls(
            action_id=str(data.get("action_id", "")),
            action_type=action_type,
            start_ms=int(data.get("start_ms", 0)),
            duration_ms=int(data.get("duration_ms", 0)),
            params=dict(data.get("params", {})),
        )


@dataclass(frozen=True)
class ExpectedState:
    """Expected verifiable studio state at scene boundary."""
    active_file: Optional[str] = None
    file_tree: Optional[List[str]] = None
    editor_content_hash: Optional[str] = None
    cursor_symbol: Optional[str] = None
    terminal_last_command: Optional[str] = None
    terminal_exit_code: Optional[int] = None
    custom_checks: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_file": self.active_file,
            "file_tree": list(self.file_tree) if self.file_tree is not None else None,
            "editor_content_hash": self.editor_content_hash,
            "cursor_symbol": self.cursor_symbol,
            "terminal_last_command": self.terminal_last_command,
            "terminal_exit_code": self.terminal_exit_code,
            "custom_checks": dict(self.custom_checks),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional[ExpectedState]:
        if not data:
            return None
        return cls(
            active_file=data.get("active_file"),
            file_tree=list(data["file_tree"]) if data.get("file_tree") is not None else None,
            editor_content_hash=data.get("editor_content_hash"),
            cursor_symbol=data.get("cursor_symbol"),
            terminal_last_command=data.get("terminal_last_command"),
            terminal_exit_code=data.get("terminal_exit_code"),
            custom_checks=dict(data.get("custom_checks", {})),
        )


@dataclass(frozen=True)
class Annotation:
    """Visual overlay annotation (callout, badge, highlight cue)."""
    annotation_id: str
    kind: str
    text: Optional[str] = None
    start_ms: int = 0
    duration_ms: int = 0
    target_symbol: Optional[str] = None
    target_line: Optional[int] = None
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "annotation_id": self.annotation_id,
            "kind": self.kind,
            "text": self.text,
            "start_ms": self.start_ms,
            "duration_ms": self.duration_ms,
            "target_symbol": self.target_symbol,
            "target_line": self.target_line,
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Annotation:
        return cls(
            annotation_id=str(data.get("annotation_id", "")),
            kind=str(data.get("kind", "callout")),
            text=data.get("text"),
            start_ms=int(data.get("start_ms", 0)),
            duration_ms=int(data.get("duration_ms", 0)),
            target_symbol=data.get("target_symbol"),
            target_line=data.get("target_line"),
            params=dict(data.get("params", {})),
        )


@dataclass(frozen=True)
class Scene:
    """A cohesive temporal scene in the code video."""
    scene_id: str
    title: str
    start_ms: int
    end_ms: int
    visual_mode: VisualMode
    actions: List[Action] = field(default_factory=list)
    expected_state: Optional[ExpectedState] = None
    annotations: List[Annotation] = field(default_factory=list)
    voice_cue_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.start_ms, int) or isinstance(self.start_ms, bool) or self.start_ms < 0:
            raise ValidationError(f"Scene '{self.scene_id}' start_ms must be a non-negative integer, got {self.start_ms}")
        if not isinstance(self.end_ms, int) or isinstance(self.end_ms, bool) or self.end_ms <= self.start_ms:
            raise ValidationError(f"Scene '{self.scene_id}' end_ms must be an integer greater than start_ms ({self.start_ms}), got {self.end_ms}")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def validate(self) -> List[str]:
        """Validate scene internal consistency and action bounds."""
        errors: List[str] = []
        action_ids: Set[str] = set()

        for action in self.actions:
            # Action uniqueness
            if action.action_id in action_ids:
                errors.append(f"Scene '{self.scene_id}': Duplicate action_id '{action.action_id}'")
            action_ids.add(action.action_id)

            # Action bounds within scene
            if action.start_ms < self.start_ms:
                errors.append(
                    f"Scene '{self.scene_id}': Action '{action.action_id}' start_ms ({action.start_ms}) "
                    f"is before scene start_ms ({self.start_ms})"
                )
            if action.end_ms > self.end_ms:
                errors.append(
                    f"Scene '{self.scene_id}': Action '{action.action_id}' end_ms ({action.end_ms}) "
                    f"exceeds scene end_ms ({self.end_ms})"
                )

        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "title": self.title,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "visual_mode": self.visual_mode.value if isinstance(self.visual_mode, VisualMode) else str(self.visual_mode),
            "actions": [a.to_dict() for a in self.actions],
            "expected_state": self.expected_state.to_dict() if self.expected_state else None,
            "annotations": [ann.to_dict() for ann in self.annotations],
            "voice_cue_id": self.voice_cue_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Scene:
        visual_mode_raw = data.get("visual_mode", VisualMode.CODE_STUDIO.value)
        try:
            visual_mode = VisualMode(str(visual_mode_raw))
        except ValueError:
            raise ValidationError(f"Unknown visual_mode '{visual_mode_raw}'")

        actions = [Action.from_dict(a) for a in data.get("actions", [])]
        expected_state = ExpectedState.from_dict(data.get("expected_state"))
        annotations = [Annotation.from_dict(ann) for ann in data.get("annotations", [])]

        return cls(
            scene_id=str(data.get("scene_id", "")),
            title=str(data.get("title", "")),
            start_ms=int(data.get("start_ms", 0)),
            end_ms=int(data.get("end_ms", 0)),
            visual_mode=visual_mode,
            actions=actions,
            expected_state=expected_state,
            annotations=annotations,
            voice_cue_id=data.get("voice_cue_id"),
        )


@dataclass(frozen=True)
class CodeVideoPlan:
    """
    Root intermediate representation (IR) for deterministic code video production.
    """
    video_id: str
    schema_version: str
    title: str
    duration_ms: int
    fps: int
    resolution: Resolution
    scenes: List[Scene]
    source_hash: str
    output_policy: OutputPolicy = field(default_factory=OutputPolicy)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.video_id:
            raise ValidationError("CodeVideoPlan video_id cannot be empty")
        if not self.source_hash:
            raise ValidationError("CodeVideoPlan source_hash is required and cannot be empty")
        if not isinstance(self.duration_ms, int) or isinstance(self.duration_ms, bool) or self.duration_ms <= 0:
            raise ValidationError(f"CodeVideoPlan duration_ms must be a positive integer, got {self.duration_ms}")
        if not isinstance(self.fps, int) or self.fps <= 0:
            raise ValidationError(f"CodeVideoPlan fps must be a positive integer, got {self.fps}")

        # Reject any forbidden audio parameters in metadata or root
        for k in self.metadata:
            if k.lower() in FORBIDDEN_AUDIO_KEYS:
                raise ValidationError(f"Forbidden audio parameter '{k}' in metadata. Audio is EXCLUDED for Video 02.")

    @property
    def total_duration_ms(self) -> int:
        return self.duration_ms

    @property
    def total_scenes(self) -> int:
        return len(self.scenes)

    @property
    def total_actions(self) -> int:
        return sum(len(scene.actions) for scene in self.scenes)

    def get_scene(self, scene_id: str) -> Optional[Scene]:
        for scene in self.scenes:
            if scene.scene_id == scene_id:
                return scene
        return None

    def get_action(self, action_id: str) -> Optional[Tuple[Scene, Action]]:
        for scene in self.scenes:
            for action in scene.actions:
                if action.action_id == action_id:
                    return scene, action
        return None

    def validate(self) -> None:
        """
        Comprehensive validation of the complete CodeVideoPlan.
        Raises ValidationError with diagnostic details if invalid.
        """
        errors: List[str] = []

        if not self.scenes:
            raise ValidationError("CodeVideoPlan must contain at least one Scene.")

        scene_ids: Set[str] = set()
        current_time = 0

        for idx, scene in enumerate(self.scenes):
            # Duplicate scene ID
            if scene.scene_id in scene_ids:
                errors.append(f"Duplicate scene_id '{scene.scene_id}' at index {idx}")
            scene_ids.add(scene.scene_id)

            # Contiguous timeline check (no gaps, no overlaps)
            if scene.start_ms != current_time:
                if scene.start_ms < current_time:
                    errors.append(
                        f"Scene '{scene.scene_id}' overlaps previous scene (starts at {scene.start_ms}ms, "
                        f"expected {current_time}ms)"
                    )
                else:
                    errors.append(
                        f"Gap before scene '{scene.scene_id}' (starts at {scene.start_ms}ms, "
                        f"expected {current_time}ms)"
                    )

            current_time = scene.end_ms

            # Internal scene validation
            scene_errors = scene.validate()
            errors.extend(scene_errors)

        # Total duration match check
        if current_time != self.duration_ms:
            errors.append(
                f"Sum of scene durations ({current_time}ms) does not match plan duration_ms ({self.duration_ms}ms)"
            )

        if errors:
            raise ValidationError(
                f"CodeVideoPlan validation failed with {len(errors)} error(s):\n" + "\n".join(f"- {e}" for e in errors)
            )

    def generate_cue_sheet_csv(self) -> str:
        """Generate voice cue sheet CSV for downstream voice recording handoff."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["scene_id", "title", "start_timecode", "end_timecode", "duration_seconds", "voice_reference"])

        for scene in self.scenes:
            start_tc = _format_timecode_ms(scene.start_ms)
            end_tc = _format_timecode_ms(scene.end_ms)
            dur_sec = f"{scene.duration_ms / 1000.0:.3f}"
            ref = scene.voice_cue_id or scene.title.upper().replace(" ", "_")
            writer.writerow([scene.scene_id, scene.title, start_tc, end_tc, dur_sec, ref])

        return output.getvalue()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "schema_version": self.schema_version,
            "title": self.title,
            "duration_ms": self.duration_ms,
            "fps": self.fps,
            "resolution": self.resolution.to_dict(),
            "source_hash": self.source_hash,
            "output_policy": self.output_policy.to_dict(),
            "metadata": dict(self.metadata),
            "scenes": [s.to_dict() for s in self.scenes],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CodeVideoPlan:
        # Check audio forbidden keys
        for k in data:
            if k.lower() in FORBIDDEN_AUDIO_KEYS:
                raise ValidationError(f"Forbidden root audio key '{k}' in CodeVideoPlan. Audio is EXCLUDED.")

        resolution = Resolution.from_dict(data.get("resolution", {"width": 2560, "height": 1440}))
        output_policy_data = data.get("output_policy", {})
        output_policy = OutputPolicy.from_dict(output_policy_data) if output_policy_data else OutputPolicy()
        scenes = [Scene.from_dict(s) for s in data.get("scenes", [])]

        return cls(
            video_id=str(data.get("video_id", "")),
            schema_version=str(data.get("schema_version", "1.0.0")),
            title=str(data.get("title", "")),
            duration_ms=int(data.get("duration_ms", 0)),
            fps=int(data.get("fps", 30)),
            resolution=resolution,
            scenes=scenes,
            source_hash=str(data.get("source_hash", "")),
            output_policy=output_policy,
            metadata=dict(data.get("metadata", {})),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> CodeVideoPlan:
        try:
            data = json.loads(json_str)
        except Exception as e:
            raise ValidationError(f"Failed to parse JSON for CodeVideoPlan: {e}")
        return cls.from_dict(data)

    def to_yaml(self) -> str:
        return yaml.dump(self.to_dict(), sort_keys=False, allow_unicode=True)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> CodeVideoPlan:
        try:
            data = yaml.safe_load(yaml_str)
        except Exception as e:
            raise ValidationError(f"Failed to parse YAML for CodeVideoPlan: {e}")
        if not isinstance(data, dict):
            raise ValidationError("YAML root must be a mapping dictionary")
        return cls.from_dict(data)


def _format_timecode_ms(ms: int) -> str:
    """Format millisecond integer to MM:SS.mmm format."""
    total_seconds = ms // 1000
    remainder_ms = ms % 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}.{remainder_ms:03d}"


__all__ = [
    "ActionType",
    "VisualMode",
    "Resolution",
    "OutputPolicy",
    "Action",
    "ExpectedState",
    "Annotation",
    "Scene",
    "CodeVideoPlan",
    "FORBIDDEN_COORDINATE_KEYS",
    "FORBIDDEN_AUDIO_KEYS",
]
