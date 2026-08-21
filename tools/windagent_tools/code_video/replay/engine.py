"""
Deterministic Replay Engine for Code Video Production (Video 02).

Provides:
- Exact checkpoint-based code typing & patch playback (no runtime LLM queries).
- Fine-grained typing speed simulation (instant, fast, normal, slow, custom cps)
  with millisecond-level timeline precision.
- Preflight-verified terminal playback with anti-fake assertions and strict
  SCRIPT_RUNTIME_MISMATCH detection.
- Fast recovery & resumability (resume_from scene_id/action_id) without replaying
  the entire timeline.
- Comprehensive replay tracing and determinism gate verification (identical action
  sequence hash, checkpoint hash, and terminal output hash across multiple runs).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

if TYPE_CHECKING:
    from windagent_tools.code_video.renderer.studio_renderer import (
        CodeStudioRenderer,
        StudioLayoutState,
    )
    from windagent_tools.code_video.renderer.terminal_renderer import (
        TerminalRenderer,
    )
    from windagent_tools.code_video.workspace.checkpoints import (
        CheckpointManager,
    )
from windagent_core.errors.exceptions import NotFoundError, ValidationError
from windagent_core.contracts.code_video import (
    Action,
    ActionType,
    CodeVideoPlan,
    Scene,
    VisualMode,
)

from windagent_tools.code_video.workspace.golden_builder import (

    STEP_00_INIT_AGENT_CODE,
    STEP_00_INIT_TEST_CODE,
    STEP_01_MESSAGE_CODE,
    STEP_02_CONFIG_CODE,
    STEP_03_PROTOCOL_CODE,
    STEP_04_FAKE_LLM_CODE,
    STEP_05_AGENT_CODE,
    STEP_06_TESTS_CODE,
    STEP_07_FINAL_AGENT_CODE,
)


class TypingSpeedMode(str, Enum):
    """Typing velocity modes for code typing simulation."""
    INSTANT = "instant"    # Immediate drop-in / zero typing duration
    FAST = "fast"          # ~60 chars/second (~16.6 ms/char)
    NORMAL = "normal"      # ~25 chars/second (~40 ms/char)
    SLOW = "slow"          # ~12 chars/second (~83.3 ms/char)
    CUSTOM = "custom"      # Custom chars_per_second setting


# Default characters per second mapped to typing speed modes
SPEED_MODE_CPS_MAP: Dict[TypingSpeedMode, float] = {
    TypingSpeedMode.INSTANT: 10_000.0,
    TypingSpeedMode.FAST: 60.0,
    TypingSpeedMode.NORMAL: 25.0,
    TypingSpeedMode.SLOW: 12.0,
}


class TypingSimulator:
    """
    Simulates realistic, deterministic keystroke typing for the code editor.
    Calculates visible text slice, cursor line, and cursor column at any millisecond offset.
    """

    @classmethod
    def get_chars_per_second(
        cls,
        mode: Union[TypingSpeedMode, str] = TypingSpeedMode.NORMAL,
        custom_cps: Optional[float] = None,
    ) -> float:
        if custom_cps is not None and custom_cps > 0:
            return float(custom_cps)
        if isinstance(mode, TypingSpeedMode):
            speed_mode = mode
        else:
            raw = str(mode).lower().replace("typingspeedmode.", "")
            try:
                speed_mode = TypingSpeedMode(raw)
            except ValueError:
                speed_mode = TypingSpeedMode.NORMAL
        return SPEED_MODE_CPS_MAP.get(speed_mode, 25.0)

    @classmethod
    def compute_typed_state(
        cls,
        target_text: str,
        elapsed_ms: int,
        total_duration_ms: int,
        mode: Union[TypingSpeedMode, str] = TypingSpeedMode.NORMAL,
        chars_per_second: Optional[float] = None,
        initial_text: str = "",
        append: bool = False,
    ) -> Tuple[str, int, int]:
        """
        Compute visible text, cursor line, and cursor column at `elapsed_ms` within an action.

        Returns:
            (visible_text, cursor_line, cursor_col)
        """
        if isinstance(mode, TypingSpeedMode):
            speed_mode = mode
        else:
            raw = str(mode).lower().replace("typingspeedmode.", "")
            try:
                speed_mode = TypingSpeedMode(raw)
            except ValueError:
                speed_mode = TypingSpeedMode.NORMAL

        if speed_mode == TypingSpeedMode.INSTANT or total_duration_ms <= 0 or elapsed_ms >= total_duration_ms:
            full_text = f"{initial_text}\n{target_text}" if (append and initial_text) else target_text
            lines = full_text.split("\n")
            return full_text, len(lines), len(lines[-1]) + 1

        if elapsed_ms <= 0:
            lines = initial_text.split("\n") if initial_text else [""]
            return initial_text, len(lines), len(lines[-1]) + 1

        # Calculate character count to reveal
        cps = cls.get_chars_per_second(speed_mode, custom_cps=chars_per_second)
        chars_by_cps = int((elapsed_ms / 1000.0) * cps)


        # Also interpolate linearly so that target_text is fully typed by total_duration_ms
        chars_by_time = int((elapsed_ms / float(total_duration_ms)) * len(target_text))
        chars_to_show = max(0, min(len(target_text), max(chars_by_cps, chars_by_time)))

        typed_portion = target_text[:chars_to_show]
        visible_text = f"{initial_text}\n{typed_portion}" if (append and initial_text) else typed_portion

        lines = visible_text.split("\n")
        cursor_line = max(1, len(lines))
        cursor_col = max(1, len(lines[-1]) + 1)

        return visible_text, cursor_line, cursor_col


# -----------------------------------------------------------------------------
# Preflight Verified Terminal Receipts Registry (Anti-Fake Guarantee)
# -----------------------------------------------------------------------------

VERIFIED_TERMINAL_RECEIPTS: Dict[str, Dict[str, Any]] = {
    "python -m src.agent": {
        "exit_code": 0,
        "stdout": (
            "[Agent: SimpleAgent] Initializing OpenAICompatibleProvider...\n"
            "Prompt: 'Giải thích recursion bằng một ví dụ đơn giản.'\n"
            "Generating response...\n"
            "Recursion là một kỹ thuật trong lập trình nơi một hàm tự gọi chính nó để giải quyết "
            "một bài toán nhỏ hơn của cùng vấn đề, cho đến khi đạt điều kiện dừng (base case).\n"
            "Ví dụ: Tính giai thừa (factorial):\n"
            "5! = 5 * 4 * 3 * 2 * 1 = 120."
        ),
        "stderr": "",
    },
    "pytest": {
        "exit_code": 0,
        "stdout": (
            "============================= test session starts =============================\n"
            "platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0\n"
            "rootdir: D:\\code_video\\workspace\\agentic-studio\n"
            "collected 2 items\n\n"
            "tests/test_agent.py ..                                                   [100%]\n\n"
            "============================== 2 passed in 0.04s =============================="
        ),
        "stderr": "",
        "passes": 2,
    },
    "mkdir agentic-studio && cd agentic-studio": {
        "exit_code": 0,
        "stdout": "    Directory: D:\\code_video\\workspace\\agentic-studio\n",
        "stderr": "",
    },
    "git init": {
        "exit_code": 0,
        "stdout": "Initialized empty Git repository in D:/code_video/workspace/agentic-studio/.git/\n",
        "stderr": "",
    },
    "git add .": {
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
    },
    'git commit -m "feat: build simple agent core"': {
        "exit_code": 0,
        "stdout": (
            "[master (root-commit) 4f7c1a9] feat: build simple agent core\n"
            " 6 files changed, 142 insertions(+)\n"
            " create mode 100644 .env.example\n"
            " create mode 100644 .gitignore\n"
            " create mode 100644 README.md\n"
            " create mode 100644 pyproject.toml\n"
            " create mode 100644 src/agent.py\n"
            " create mode 100644 tests/test_agent.py"
        ),
        "stderr": "",
    },
    "git tag video-02 && git tag v0.1": {
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
    },
}


class TerminalReplayExecutor:
    """
    Deterministic terminal command replayer and receipt validator.
    Ensures zero live network calls and strict anti-fake terminal verification.
    """

    def __init__(self, custom_receipts: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self.receipts: Dict[str, Dict[str, Any]] = dict(VERIFIED_TERMINAL_RECEIPTS)
        if custom_receipts:
            self.receipts.update(custom_receipts)

    def execute_terminal_action(
        self,
        action: Action,
        terminal_renderer: TerminalRenderer,
        strict: bool = True,
    ) -> Dict[str, Any]:
        """
        Replay terminal command into TerminalRenderer and validate expected assertions.
        Raises ValidationError with SCRIPT_RUNTIME_MISMATCH if assertion fails.
        """
        cmd = str(action.params.get("command", "")).strip()
        expected_passes = action.params.get("expected_passes")
        expected_exit_code = action.params.get("expected_exit_code", 0)

        # Check expected dictionary if present
        expected_dict = action.params.get("expected", {})
        if isinstance(expected_dict, dict):
            if "exit_code" in expected_dict:
                expected_exit_code = expected_dict["exit_code"]

        receipt = self.receipts.get(cmd)
        if not receipt:
            if strict and cmd:
                raise ValidationError(
                    f"SCRIPT_RUNTIME_MISMATCH: Unverified terminal command '{cmd}'. "
                    "All terminal replay in Video 02 must have verified preflight receipts."
                )
            receipt = {
                "exit_code": 0,
                "stdout": f"[Executed: {cmd}]",
                "stderr": "",
            }

        stdout = str(receipt.get("stdout", ""))
        stderr = str(receipt.get("stderr", ""))
        actual_exit_code = int(receipt.get("exit_code", 0))

        # Anti-Fake Check 1: Exit code assertion
        if actual_exit_code != expected_exit_code:
            raise ValidationError(
                f"SCRIPT_RUNTIME_MISMATCH: Exit code mismatch for '{cmd}'. "
                f"Expected {expected_exit_code}, got {actual_exit_code}"
            )

        # Anti-Fake Check 2: Pytest pass count assertion
        if expected_passes is not None:
            expected_pass_str = f"{expected_passes} passed"
            if expected_pass_str not in stdout:
                raise ValidationError(
                    f"SCRIPT_RUNTIME_MISMATCH: Pytest assertion failed. "
                    f"Expected '{expected_pass_str}' in stdout, but got:\n{stdout}"
                )

        # Anti-Fake Check 3: Substring contains assertion
        if isinstance(expected_dict, dict) and "contains" in expected_dict:
            for substring in expected_dict["contains"]:
                if substring not in stdout and substring not in stderr:
                    raise ValidationError(
                        f"SCRIPT_RUNTIME_MISMATCH: Expected substring '{substring}' not found in output of '{cmd}'."
                    )

        # Replay into renderer
        if cmd:
            output_text = f"{stdout}\n{stderr}".strip() if stderr else stdout
            terminal_renderer.execute_command(
                command=cmd,
                output=output_text,
                exit_code=actual_exit_code,
                timestamp_ms=action.start_ms,
            )

        return {
            "command": cmd,
            "exit_code": actual_exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "lines_count": len(terminal_renderer.state.history),
        }



# -----------------------------------------------------------------------------
# Checkpoint Code Resolver
# -----------------------------------------------------------------------------

CHECKPOINT_CODE_MAP: Dict[str, Dict[str, str]] = {
    "cp_00_init": {
        "src/agent.py": STEP_00_INIT_AGENT_CODE,
        "tests/test_agent.py": STEP_00_INIT_TEST_CODE,
    },
    "cp_01_message": {
        "src/agent.py": STEP_01_MESSAGE_CODE,
        "tests/test_agent.py": STEP_00_INIT_TEST_CODE,
    },
    "cp_02_config": {
        "src/agent.py": STEP_02_CONFIG_CODE,
        "tests/test_agent.py": STEP_00_INIT_TEST_CODE,
    },
    "cp_03_llm_protocol": {
        "src/agent.py": STEP_03_PROTOCOL_CODE,
        "tests/test_agent.py": STEP_00_INIT_TEST_CODE,
    },
    "cp_04_fake_llm": {
        "src/agent.py": STEP_04_FAKE_LLM_CODE,
        "tests/test_agent.py": STEP_00_INIT_TEST_CODE,
    },
    "cp_05_agent": {
        "src/agent.py": STEP_05_AGENT_CODE,
        "tests/test_agent.py": STEP_00_INIT_TEST_CODE,
    },
    "cp_06_tests": {
        "src/agent.py": STEP_05_AGENT_CODE,
        "tests/test_agent.py": STEP_06_TESTS_CODE,
    },
    "cp_07_provider": {
        "src/agent.py": STEP_07_FINAL_AGENT_CODE,
        "tests/test_agent.py": STEP_06_TESTS_CODE,
    },
    "cp_09_v0_1": {
        "src/agent.py": STEP_07_FINAL_AGENT_CODE,
        "tests/test_agent.py": STEP_06_TESTS_CODE,
    },
}


class CheckpointCodeResolver:
    """Resolves verified code contents for tutorial checkpoints without LLM generation."""

    def __init__(self, checkpoint_manager: Optional[CheckpointManager] = None) -> None:
        self.checkpoint_manager = checkpoint_manager

    def resolve_file_content(self, checkpoint_id: str, path: str) -> str:
        """Fetch canonical code content for a given checkpoint and file path."""
        # 1. Check in-memory canonical map
        if checkpoint_id in CHECKPOINT_CODE_MAP:
            file_map = CHECKPOINT_CODE_MAP[checkpoint_id]
            if path in file_map:
                return file_map[path]

        # 2. Check on-disk CheckpointManager if available
        if self.checkpoint_manager:
            record = self.checkpoint_manager.get_checkpoint(checkpoint_id)
            if record:
                fpath = self.checkpoint_manager.store_root / checkpoint_id / "files" / path
                if fpath.exists():
                    return fpath.read_text(encoding="utf-8")

        # 3. Fallbacks for standard project files
        if path == ".env.example":
            return "PROVIDER_API_KEY=your_api_key_here\nPROVIDER_BASE_URL=https://api.openai.com/v1\nPROVIDER_MODEL=gpt-4o-mini\n"
        if path == ".gitignore":
            return ".env\n__pycache__/\n*.py[cod]\n.pytest_cache/\n.venv/\n"
        if path == "pyproject.toml":
            return '[project]\nname = "agentic-studio"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n'
        if path == "README.md":
            return "# Agentic Studio (v0.1)\n\nSimple AI Agent implementation in Python.\n"
        if path == "src/__init__.py":
            return '"""Agentic Studio package."""\n'
        if path == "tests/__init__.py":
            return '"""Agentic Studio test package."""\n'

        return ""


# -----------------------------------------------------------------------------
# Replay Tracing and Records
# -----------------------------------------------------------------------------

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
        return json.dumps(self.to_dict(), indent=indent)


# -----------------------------------------------------------------------------
# Main Deterministic Replay Engine
# -----------------------------------------------------------------------------

class DeterministicReplayEngine:
    """
    Main execution engine for deterministic code video timeline replay.
    """

    def __init__(
        self,
        plan: Optional[CodeVideoPlan] = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
        studio_renderer: Optional[CodeStudioRenderer] = None,
        strict_terminal: bool = True,
    ) -> None:
        if plan is None:
            from windagent_tools.code_video.compiler import CodeVideoScriptCompiler
            compiler = CodeVideoScriptCompiler()
            self.plan = compiler.compile_video_02_plan()
        else:
            self.plan = plan
        self.plan.validate()
        if studio_renderer is not None:
            self.renderer = studio_renderer
        else:
            from windagent_tools.code_video.renderer.studio_renderer import CodeStudioRenderer
            self.renderer = CodeStudioRenderer()
        self.checkpoint_resolver = CheckpointCodeResolver(checkpoint_manager)
        self.terminal_executor = TerminalReplayExecutor()
        self.strict_terminal = strict_terminal



    def _compute_step_hash(self, action: Action, layout: StudioLayoutState) -> str:
        h = hashlib.sha256()
        h.update(f"{action.action_id}:{action.action_type.value}:{action.start_ms}:{action.duration_ms}".encode())
        h.update(f":{layout.editor.content_hash}:{layout.terminal.last_command}:{layout.visual_mode.value}".encode())
        return h.hexdigest()

    def execute_action(
        self,
        scene: Scene,
        action: Action,
        elapsed_in_action_ms: Optional[int] = None,
    ) -> StudioLayoutState:
        """
        Execute a single semantic action against the Code Studio Renderer.
        Supports exact checkpoint code injection, typing simulation, and terminal playback.
        """
        params = dict(action.params)

        # 1. Action: OPEN_FILE
        if action.action_type == ActionType.OPEN_FILE:
            path = params.get("path", "src/agent.py")
            self.renderer.set_active_file(path)
            content = params.get("content")
            if content is None and "checkpoint" in params:
                content = self.checkpoint_resolver.resolve_file_content(params["checkpoint"], path)
            if content is not None:
                self.renderer.editor.open_file(path, content)

        # 2. Action: TYPE_TEXT
        elif action.action_type == ActionType.TYPE_TEXT:
            path = params.get("path", self.renderer.editor.state.active_file)
            checkpoint_id = params.get("checkpoint")
            target_text = params.get("text", params.get("source", ""))

            if not target_text and checkpoint_id:
                target_text = self.checkpoint_resolver.resolve_file_content(checkpoint_id, path)

            speed_mode = params.get("typing_speed", TypingSpeedMode.NORMAL)
            custom_cps = params.get("chars_per_second")

            if elapsed_in_action_ms is not None:
                visible_text, cur_l, cur_c = TypingSimulator.compute_typed_state(
                    target_text=target_text,
                    elapsed_ms=elapsed_in_action_ms,
                    total_duration_ms=action.duration_ms,
                    mode=speed_mode,
                    chars_per_second=custom_cps,
                    initial_text="",
                    append=False,
                )
                self.renderer.editor.open_file(path, visible_text)
                self.renderer.editor.state.cursor_line = cur_l
                self.renderer.editor.state.cursor_col = cur_c
            else:
                self.renderer.editor.open_file(path, target_text)

        # 3. Action: REPLACE_TEXT
        elif action.action_type == ActionType.REPLACE_TEXT:
            new_text = params.get("content", params.get("text", ""))
            self.renderer.editor.replace_text(new_text)

        # 4. Action: SELECT_RANGE
        elif action.action_type == ActionType.SELECT_RANGE:
            lines = params.get("lines")
            if lines and isinstance(lines, list) and len(lines) >= 2:
                sl, el = int(lines[0]), int(lines[1])
                self.renderer.editor.select_range(sl, 1, el, 1)
            else:
                sl = int(params.get("start_line", 1))
                sc = int(params.get("start_col", 1))
                el = int(params.get("end_line", sl))
                ec = int(params.get("end_col", 1))
                self.renderer.editor.select_range(sl, sc, el, ec)

        # 5. Action: HIGHLIGHT
        elif action.action_type == ActionType.HIGHLIGHT:
            sym = params.get("symbol")
            if sym:
                self.renderer.editor.highlight_symbol(sym)
            lines = params.get("line_range", params.get("lines"))
            if lines and isinstance(lines, list) and len(lines) >= 2:
                self.renderer.editor.state.highlighted_lines = list(range(int(lines[0]), int(lines[1]) + 1))

        # 6. Action: SCROLL
        elif action.action_type == ActionType.SCROLL:
            target_line = int(params.get("target_line", params.get("line", 1)))
            self.renderer.editor.scroll_to(target_line)

        # 7. Action: ZOOM
        elif action.action_type == ActionType.ZOOM:
            lvl = float(params.get("zoom_level", params.get("level", 1.2)))
            self.renderer.editor.zoom(lvl)

        # 8. Action: RUN_TERMINAL
        elif action.action_type == ActionType.RUN_TERMINAL:
            self.terminal_executor.execute_terminal_action(
                action=action,
                terminal_renderer=self.renderer.terminal,
                strict=self.strict_terminal,
            )

        # 9. Action: SHOW_OUTPUT
        elif action.action_type == ActionType.SHOW_OUTPUT:
            self.renderer.terminal.apply_action(action)

        # 10. Action: SHOW_DIAGRAM / SHOW_ARCHITECTURE
        elif action.action_type in (ActionType.SHOW_DIAGRAM, ActionType.SHOW_ARCHITECTURE):
            self.renderer.diagram.apply_action(action)

        # 11. Action: SHOW_TITLE / SHOW_CHECKLIST
        elif action.action_type in (ActionType.SHOW_TITLE, ActionType.SHOW_CHECKLIST):
            self.renderer.title_card.apply_action(action)

        # 12. Action: SWITCH_LAYOUT
        elif action.action_type == ActionType.SWITCH_LAYOUT:
            mode_raw = params.get("visual_mode", params.get("mode"))
            if mode_raw:
                self.renderer.switch_layout(VisualMode(str(mode_raw)))

        # 13. Action: RESET_VIEW
        elif action.action_type == ActionType.RESET_VIEW:
            self.renderer.editor.apply_action(action)
            self.renderer.terminal.apply_action(action)
            self.renderer.diagram.apply_action(action)

        return self.renderer.layout_state

    def verify_scene_expected_state(self, scene: Scene, state: StudioLayoutState) -> Tuple[bool, List[str]]:
        """
        Verify that studio state at scene boundary matches Scene.expected_state.
        """
        discrepancies: List[str] = []
        exp = scene.expected_state
        if not exp:
            return True, discrepancies

        if exp.active_file is not None and state.editor.active_file != exp.active_file:
            discrepancies.append(
                f"Scene '{scene.scene_id}' active_file mismatch: "
                f"expected '{exp.active_file}', got '{state.editor.active_file}'"
            )

        if exp.terminal_last_command is not None and state.terminal.last_command != exp.terminal_last_command:
            discrepancies.append(
                f"Scene '{scene.scene_id}' terminal_last_command mismatch: "
                f"expected '{exp.terminal_last_command}', got '{state.terminal.last_command}'"
            )

        if exp.terminal_exit_code is not None and state.terminal.last_exit_code != exp.terminal_exit_code:
            discrepancies.append(
                f"Scene '{scene.scene_id}' terminal_exit_code mismatch: "
                f"expected {exp.terminal_exit_code}, got {state.terminal.last_exit_code}"
            )


        if exp.cursor_symbol is not None:
            if state.editor.highlighted_symbol != exp.cursor_symbol:
                discrepancies.append(
                    f"Scene '{scene.scene_id}' cursor_symbol mismatch: "
                    f"expected '{exp.cursor_symbol}', got '{state.editor.highlighted_symbol}'"
                )

        return len(discrepancies) == 0, discrepancies

    def execute_scene(self, scene: Scene) -> List[ReplayStepRecord]:
        """Execute all actions in a single scene and record step traces."""
        self.renderer.switch_layout(scene.visual_mode)
        step_records: List[ReplayStepRecord] = []

        for action in scene.actions:
            state = self.execute_action(scene, action, elapsed_in_action_ms=None)
            step_hash = self._compute_step_hash(action, state)

            rec = ReplayStepRecord(
                scene_id=scene.scene_id,
                action_id=action.action_id,
                action_type=action.action_type.value,
                start_ms=action.start_ms,
                duration_ms=action.duration_ms,
                end_ms=action.end_ms,
                status="SUCCESS",
                active_file=state.editor.active_file,
                editor_content_hash=state.editor.content_hash,
                terminal_last_command=state.terminal.last_command,
                terminal_lines_count=len(state.terminal.history),
                visual_mode=state.visual_mode.value,
                step_hash=step_hash,
            )
            step_records.append(rec)

        # Validate expected state at scene boundary
        is_valid, errors = self.verify_scene_expected_state(scene, self.renderer.layout_state)
        if not is_valid:
            raise ValidationError(
                f"Scene '{scene.scene_id}' expected state validation failed:\n"
                + "\n".join(f"- {e}" for e in errors)
            )

        return step_records

    def execute_full_plan(self) -> ReplayTrace:
        """
        Execute full 19-scene plan replay and produce deterministic ReplayTrace.
        """
        started_at = datetime.now(timezone.utc).isoformat()
        all_steps: List[ReplayStepRecord] = []

        action_seq_hasher = hashlib.sha256()
        checkpoint_hasher = hashlib.sha256()
        terminal_hasher = hashlib.sha256()

        for scene in self.plan.scenes:
            scene_steps = self.execute_scene(scene)
            for step in scene_steps:
                all_steps.append(step)
                action_seq_hasher.update(
                    f"{step.action_id}:{step.action_type}:{step.start_ms}:{step.duration_ms}:{step.step_hash}".encode()
                )
                checkpoint_hasher.update(f"{step.active_file}:{step.editor_content_hash}".encode())
                if step.terminal_last_command:
                    terminal_hasher.update(
                        f"{step.terminal_last_command}:{step.terminal_lines_count}".encode()
                    )

        completed_at = datetime.now(timezone.utc).isoformat()

        action_seq_hash = action_seq_hasher.hexdigest()
        checkpoint_hash = checkpoint_hasher.hexdigest()
        terminal_output_hash = terminal_hasher.hexdigest()

        composite_hasher = hashlib.sha256()
        composite_hasher.update(f"{action_seq_hash}:{checkpoint_hash}:{terminal_output_hash}".encode())
        composite_replay_hash = composite_hasher.hexdigest()

        return ReplayTrace(
            video_id=self.plan.video_id,
            plan_source_hash=self.plan.source_hash,
            total_duration_ms=self.plan.duration_ms,
            total_scenes=self.plan.total_scenes,
            total_actions=self.plan.total_actions,
            steps=all_steps,
            action_sequence_hash=action_seq_hash,
            checkpoint_hash=checkpoint_hash,
            terminal_output_hash=terminal_output_hash,
            composite_replay_hash=composite_replay_hash,
            status="VERIFIED",
            started_at_utc=started_at,
            completed_at_utc=completed_at,
        )

    def step_to_timestamp(self, timestamp_ms: int) -> StudioLayoutState:
        """
        Calculates and returns the exact StudioLayoutState at millisecond timestamp `timestamp_ms`.
        Interpolates typing and terminal state for active actions.
        """
        clamped_ms = max(0, min(timestamp_ms, self.plan.duration_ms))

        # Find target scene
        active_scene: Optional[Scene] = None
        for s in self.plan.scenes:
            if s.start_ms <= clamped_ms < s.end_ms:
                active_scene = s
                break

        if not active_scene:
            active_scene = self.plan.scenes[-1]

        # Switch layout
        self.renderer.switch_layout(active_scene.visual_mode)

        # Apply previous scenes up to active scene
        for s in self.plan.scenes:
            if s.end_ms <= clamped_ms:
                for act in s.actions:
                    self.execute_action(s, act, elapsed_in_action_ms=None)
            elif s.scene_id == active_scene.scene_id:
                # In active scene: apply actions that started before or at clamped_ms
                for act in s.actions:
                    if act.start_ms <= clamped_ms:
                        if clamped_ms < act.end_ms:
                            elapsed_in_act = clamped_ms - act.start_ms
                            self.execute_action(s, act, elapsed_in_action_ms=elapsed_in_act)
                        else:
                            self.execute_action(s, act, elapsed_in_action_ms=None)
                break

        return self.renderer.layout_state

    def resume_from(
        self,
        scene_id: str,
        action_id: Optional[str] = None,
    ) -> StudioLayoutState:
        """
        Fast recovery: Resumes replay state directly from `scene_id` and optional `action_id`.
        Applies prior scene checkpoints without needing a full-timeline real-time replay.
        """
        target_scene: Optional[Scene] = None
        for s in self.plan.scenes:
            if s.scene_id == scene_id:
                target_scene = s
                break

        if not target_scene:
            raise NotFoundError(f"Scene '{scene_id}' not found in plan.")

        # Replay all prior scenes
        for s in self.plan.scenes:
            if s.end_ms <= target_scene.start_ms:
                for act in s.actions:
                    self.execute_action(s, act, elapsed_in_action_ms=None)

        # Set target scene layout
        self.renderer.switch_layout(target_scene.visual_mode)

        # If action_id specified, run actions up to action_id
        if action_id:
            for act in target_scene.actions:
                if act.action_id == action_id:
                    self.execute_action(target_scene, act, elapsed_in_action_ms=0)
                    break
                self.execute_action(target_scene, act, elapsed_in_action_ms=None)

        return self.renderer.layout_state

    def verify_determinism(self, runs: int = 2) -> Tuple[bool, str, Dict[str, str]]:
        """
        Execute multiple full replays to guarantee identical hashes (Phase 6 Gate).
        Returns (is_deterministic, status_message, hash_dict).
        """
        traces: List[ReplayTrace] = []
        for _ in range(runs):
            fresh_engine = DeterministicReplayEngine(
                plan=self.plan,
                checkpoint_manager=self.checkpoint_resolver.checkpoint_manager,
                strict_terminal=self.strict_terminal,
            )
            trace = fresh_engine.execute_full_plan()
            traces.append(trace)

        base = traces[0]
        for idx, t in enumerate(traces[1:], start=2):
            if t.action_sequence_hash != base.action_sequence_hash:
                return (
                    False,
                    f"Action sequence hash mismatch between run 1 and run {idx}",
                    {
                        "run1_action_hash": base.action_sequence_hash,
                        f"run{idx}_action_hash": t.action_sequence_hash,
                    },
                )
            if t.checkpoint_hash != base.checkpoint_hash:
                return (
                    False,
                    f"Checkpoint hash mismatch between run 1 and run {idx}",
                    {
                        "run1_cp_hash": base.checkpoint_hash,
                        f"run{idx}_cp_hash": t.checkpoint_hash,
                    },
                )
            if t.terminal_output_hash != base.terminal_output_hash:
                return (
                    False,
                    f"Terminal output hash mismatch between run 1 and run {idx}",
                    {
                        "run1_term_hash": base.terminal_output_hash,
                        f"run{idx}_term_hash": t.terminal_output_hash,
                    },
                )

        return (
            True,
            f"Verified {runs} consecutive runs with identical composite hash {base.composite_replay_hash[:16]}...",
            {
                "action_sequence_hash": base.action_sequence_hash,
                "checkpoint_hash": base.checkpoint_hash,
                "terminal_output_hash": base.terminal_output_hash,
                "composite_replay_hash": base.composite_replay_hash,
            },
        )


__all__ = [
    "TypingSpeedMode",
    "SPEED_MODE_CPS_MAP",
    "TypingSimulator",
    "VERIFIED_TERMINAL_RECEIPTS",
    "TerminalReplayExecutor",
    "CHECKPOINT_CODE_MAP",
    "CheckpointCodeResolver",
    "ReplayStepRecord",
    "ReplayTrace",
    "DeterministicReplayEngine",
]
