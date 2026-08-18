"""
Deterministic Terminal Renderer for Code Video Production.

Emulates PowerShell terminal playback, sanitizes system hostnames and paths,
provides deterministic command typing, stdout/stderr formatting, and exit code rendering.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import html
from typing import Any, Dict, List, Optional, Sequence

from windagent_workflows.code_video.contracts import Action, ActionType


class TerminalLineType(str, Enum):
    PROMPT = "prompt"
    COMMAND = "command"
    STDOUT = "stdout"
    STDERR = "stderr"
    EXIT_CODE = "exit_code"
    SYSTEM = "system"


@dataclass(frozen=True)
class TerminalLine:
    line_type: TerminalLineType
    text: str
    timestamp_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.line_type.value,
            "text": self.text,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass
class TerminalState:
    """State of the terminal viewport at a given instant."""
    working_dir: str = "agentic-studio"
    prompt_prefix: str = "PS D:\\code\\agentic-studio> "
    history: List[TerminalLine] = field(default_factory=list)
    current_input: str = ""
    is_running: bool = False
    last_command: Optional[str] = None
    last_exit_code: Optional[int] = None
    max_history_lines: int = 500

    def to_dict(self) -> Dict[str, Any]:
        return {
            "working_dir": self.working_dir,
            "prompt_prefix": self.prompt_prefix,
            "history": [line.to_dict() for line in self.history],
            "current_input": self.current_input,
            "is_running": self.is_running,
            "last_command": self.last_command,
            "last_exit_code": self.last_exit_code,
        }

    def render_html(self) -> str:
        """Render self-contained terminal viewport HTML."""
        lines_html: List[str] = []

        for line in self.history:
            escaped = html.escape(line.text)
            cls_name = f"term-{line.line_type.value}"

            if line.line_type == TerminalLineType.COMMAND:
                lines_html.append(
                    f'<div class="term-row {cls_name}">'
                    f'<span class="term-prompt">{html.escape(self.prompt_prefix)}</span>'
                    f'<span class="term-cmd-text">{escaped}</span>'
                    f'</div>'
                )
            elif line.line_type == TerminalLineType.EXIT_CODE:
                status_cls = "pass" if line.text.endswith("0") or "PASS" in line.text else "fail"
                lines_html.append(
                    f'<div class="term-row {cls_name} {status_cls}">'
                    f'<span class="term-badge">{escaped}</span>'
                    f'</div>'
                )
            else:
                lines_html.append(f'<div class="term-row {cls_name}">{escaped or "&nbsp;"}</div>')

        # Active typing line
        if not self.is_running:
            lines_html.append(
                f'<div class="term-row term-active-prompt">'
                f'<span class="term-prompt">{html.escape(self.prompt_prefix)}</span>'
                f'<span class="term-input-text">{html.escape(self.current_input)}</span>'
                f'<span class="term-cursor-caret"></span>'
                f'</div>'
            )

        return (
            f'<div class="terminal-container" data-working-dir="{html.escape(self.working_dir)}">\n'
            f'<div class="terminal-header">\n'
            f'  <span class="terminal-title">TERMINAL — PowerShell (agentic-studio)</span>\n'
            f'  <span class="terminal-status {"running" if self.is_running else "ready"}">'
            f'{"RUNNING..." if self.is_running else "READY"}</span>\n'
            f'</div>\n'
            f'<div class="terminal-body">\n'
            + "\n".join(lines_html) + "\n"
            f'</div>\n</div>'
        )


class TerminalRenderer:
    """Renderer and controller for deterministic terminal playback."""

    def __init__(self, initial_state: Optional[TerminalState] = None) -> None:
        self._state = initial_state or TerminalState()

    @property
    def state(self) -> TerminalState:
        return self._state

    def set_working_dir(self, directory: str) -> TerminalState:
        self._state.working_dir = directory
        self._state.prompt_prefix = f"PS D:\\code\\{directory}> "
        return self._state

    def type_command(self, command: str) -> TerminalState:
        self._state.current_input = command
        return self._state

    def clear(self) -> TerminalState:
        self._state.history = []
        self._state.current_input = ""
        self._state.is_running = False
        return self._state

    def execute_command(
        self,
        command: str,
        output: str = "",
        exit_code: int = 0,
        timestamp_ms: int = 0
    ) -> TerminalState:
        # Add command row
        self._state.history.append(
            TerminalLine(
                line_type=TerminalLineType.COMMAND,
                text=command,
                timestamp_ms=timestamp_ms,
            )
        )
        self._state.last_command = command
        self._state.current_input = ""
        self._state.is_running = False
        self._state.last_exit_code = exit_code

        # Add output lines
        if output:
            for out_line in output.split("\n"):
                line_type = TerminalLineType.STDERR if "ERROR" in out_line or "FAILED" in out_line else TerminalLineType.STDOUT
                self._state.history.append(
                    TerminalLine(
                        line_type=line_type,
                        text=out_line,
                        timestamp_ms=timestamp_ms,
                    )
                )

        # Add exit code tag
        self._state.history.append(
            TerminalLine(
                line_type=TerminalLineType.EXIT_CODE,
                text=f"Process exited with code {exit_code}",
                timestamp_ms=timestamp_ms,
            )
        )

        return self._state

    def show_output(
        self,
        output_lines: Sequence[str],
        exit_code: int = 0,
        timestamp_ms: int = 0
    ) -> TerminalState:
        for line in output_lines:
            line_type = TerminalLineType.STDERR if "ERROR" in line or "FAILED" in line else TerminalLineType.STDOUT
            self._state.history.append(
                TerminalLine(
                    line_type=line_type,
                    text=line,
                    timestamp_ms=timestamp_ms,
                )
            )
        self._state.last_exit_code = exit_code
        return self._state

    def apply_action(self, action: Action) -> TerminalState:
        """Apply a semantic action to update terminal state."""
        params = action.params

        if action.action_type == ActionType.RUN_TERMINAL:
            cmd = str(params.get("command", ""))
            output = str(params.get("output", params.get("expected_output", "")))
            expected_dict = params.get("expected", {})
            exit_code = int(expected_dict.get("exit_code", params.get("exit_code", 0)))
            self.execute_command(
                command=cmd,
                output=output,
                exit_code=exit_code,
                timestamp_ms=action.start_ms,
            )

        elif action.action_type == ActionType.SHOW_OUTPUT:
            output = params.get("output", params.get("text", ""))
            lines = output.split("\n") if isinstance(output, str) else list(output)
            exit_code = int(params.get("exit_code", 0))
            self.show_output(lines, exit_code=exit_code, timestamp_ms=action.start_ms)

        elif action.action_type == ActionType.RESET_VIEW:
            self.clear()

        return self._state
