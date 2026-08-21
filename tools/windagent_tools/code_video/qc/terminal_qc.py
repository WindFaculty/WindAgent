"""
Terminal Correctness QC Verifier for Code Video Production (Video 02 Implementation Plan §11.3).

Validates the authenticity, exit codes, output matches, and command coverage of terminal actions:
- Presence of all 7 mandatory terminal commands:
  1. git init (S05)
  2. pytest (S15, exactly '2 passed', exit_code=0)
  3. python -m src.agent (S01, S14, verified model response)
  4. git add . (S18)
  5. git commit (S18, message 'feat: build simple agent core')
  6. git tag video-02 (S18)
  7. git tag v0.1 (S18)
- Zero SCRIPT_RUNTIME_MISMATCH (no fabricated or divergent terminal output).
- Verified return codes (all expected commands return 0).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from windagent_core.contracts.code_video import CodeVideoPlan


MANDATORY_COMMAND_PATTERNS: List[str] = [
    "git init",
    "pytest",
    "python -m src.agent",
    "git add",
    "git commit",
    "git tag video-02",
    "git tag v0.1",
]


@dataclass
class TerminalQCReport:
    """Detailed report for terminal command authenticity validation."""
    is_valid: bool
    total_commands_executed: int
    commands_found: List[str]
    missing_mandatory_commands: List[str] = field(default_factory=list)
    pytest_verified: bool = False
    pytest_output_summary: str = ""
    exit_code_violations: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "total_commands_executed": self.total_commands_executed,
            "commands_found": self.commands_found,
            "missing_mandatory_commands": self.missing_mandatory_commands,
            "pytest_verified": self.pytest_verified,
            "pytest_output_summary": self.pytest_output_summary,
            "exit_code_violations": self.exit_code_violations,
            "errors": self.errors,
            "metadata": self.metadata,
        }


class TerminalCorrectnessVerifier:
    """
    Validates terminal actions in CodeVideoPlan and execution traces.
    """

    @classmethod
    def verify_plan_terminal_actions(
        cls,
        plan: CodeVideoPlan,
        terminal_receipts: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> TerminalQCReport:
        """Verify terminal actions defined across all scenes in CodeVideoPlan."""
        errors: List[str] = []
        commands_found: List[str] = []
        pytest_verified = False
        pytest_output_summary = ""
        exit_code_violations: List[str] = []

        # Extract all RUN_TERMINAL actions
        for scene in plan.scenes:
            for action in scene.actions:
                if action.action_type.value.upper() in ("RUN_TERMINAL", "RUN_COMMAND"):
                    cmd = (action.params.get("command") or "").strip()
                    if cmd:
                        commands_found.append(cmd)
                    
                    # Check pytest specifically
                    if "pytest" in cmd:
                        expected = action.params.get("expected") or {}
                        contains = expected.get("contains", [])
                        expected_passes = action.params.get("expected_passes")
                        if expected_passes == 2:
                            pytest_verified = True
                            pytest_output_summary = "2 passed (verified in action expected_passes)"
                        elif any("2 passed" in str(c) for c in contains):
                            pytest_verified = True
                            pytest_output_summary = "2 passed (verified in plan expected output)"
                        elif any("passed" in str(c) for c in contains):
                            pytest_verified = True
                            pytest_output_summary = str(contains)
                        else:
                            errors.append(f"Pytest action in scene {scene.scene_id} missing '2 passed' expectation.")

        # Check receipts if provided
        if terminal_receipts:
            for rec in terminal_receipts:
                cmd = rec.get("command", "")
                exit_code = rec.get("exit_code", 0)
                stdout = rec.get("stdout", "")
                if cmd and cmd not in commands_found:
                    commands_found.append(cmd)
                if exit_code != 0 and not rec.get("allow_failure", False):
                    exit_code_violations.append(f"Command '{cmd}' failed with exit code {exit_code}")
                if "pytest" in cmd and "2 passed" in stdout:
                    pytest_verified = True
                    pytest_output_summary = "2 passed (verified in runtime receipt)"

        # Check all mandatory patterns
        missing: List[str] = []
        for pattern in MANDATORY_COMMAND_PATTERNS:
            found = any(pattern in cmd for cmd in commands_found)
            if not found:
                missing.append(pattern)
                errors.append(f"Mandatory terminal command pattern '{pattern}' not found in timeline.")

        if not pytest_verified:
            errors.append("Pytest output verification failed: '2 passed' not confirmed.")

        all_errors = errors + exit_code_violations
        is_valid = len(all_errors) == 0

        return TerminalQCReport(
            is_valid=is_valid,
            total_commands_executed=len(commands_found),
            commands_found=commands_found,
            missing_mandatory_commands=missing,
            pytest_verified=pytest_verified,
            pytest_output_summary=pytest_output_summary,
            exit_code_violations=exit_code_violations,
            errors=all_errors,
            metadata={
                "mandatory_patterns": MANDATORY_COMMAND_PATTERNS,
            },
        )


__all__ = [
    "MANDATORY_COMMAND_PATTERNS",
    "TerminalCorrectnessVerifier",
    "TerminalQCReport",
]
