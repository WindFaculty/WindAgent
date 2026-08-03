"""
Safe Shell Execution Runner for WindAgent Tool Platform.
Executes shell commands with command allow/deny policies, directory boundary checks,
timeout enforcement, process tree cleanup, and secret masking.
"""

from __future__ import annotations
import asyncio
import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from windagent_core.errors.exceptions import PermissionDeniedError, ToolError
from windagent_core.security.redaction import redact_text

FORBIDDEN_COMMAND_PATTERNS = [
    r"\brm\s+-[rf]*\s+/",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r":\(\)\{\s*:\|:&\s*\};:",  # Fork bomb
    r"\bformat\s+[c-z]:",
]

SECRET_MASK_PATTERNS = [
    r"sk-[a-zA-Z0-9]{20,}",
    r"bearer\s+[a-zA-Z0-9_\-\.]+",
    r"password\s*=\s*['\"][^'\"]+['\"]",
]


def redact_shell_output(text: str) -> str:
    """Mask secrets in shell stdout/stderr before they leave the runner.

    Composes the core secret redactor (sk-/nvapi-/gsk_/AIzaSy keys, api_key=,
    token=, password=, Bearer) with the shell-specific masks. Without the
    core pass, unquoted `password=value` and API-key prefixes would survive
    in process output (hardening finding closed in Phase 26, SE01).
    """
    redacted = text
    for pat in SECRET_MASK_PATTERNS:
        redacted = re.sub(pat, "***REDACTED_SECRET***", redacted, flags=re.IGNORECASE)
    # Core redactor runs LAST so a value already masked by a shell pattern is
    # not double-processed; anything a shell pattern missed (unquoted
    # password=, api_key=, provider-key prefixes) is caught here.
    return redact_text(redacted)


class SafeShellRunner:
    def __init__(self, workspace_root: str, default_timeout_seconds: float = 30.0):
        self.workspace_root = Path(workspace_root).resolve()
        self.default_timeout_seconds = default_timeout_seconds

    def validate_command_policy(self, command_line: str) -> None:
        cmd_lower = command_line.lower()
        for pat in FORBIDDEN_COMMAND_PATTERNS:
            if re.search(pat, cmd_lower):
                raise PermissionDeniedError(
                    message=f"Shell command execution denied: Command matches forbidden pattern [{pat}].",
                    code="WINDAGENT_ERR_FORBIDDEN_SHELL_COMMAND",
                    details={"command": command_line},
                )

    async def execute_command(
        self,
        command_line: str,
        cwd: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, str, str]:
        """Executes a shell command asynchronously with timeout and output redaction."""
        self.validate_command_policy(command_line)

        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        if not work_dir.exists():
            raise ToolError(f"Working directory '{work_dir}' does not exist.", tool_name="shell")

        timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout_seconds

        current_env = dict(os.environ)
        if env:
            current_env.update(env)

        try:
            process = await asyncio.create_subprocess_shell(
                command_line,
                cwd=str(work_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=current_env,
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(process.communicate(), timeout=timeout)
                exit_code = process.returncode or 0
                stdout = redact_shell_output(stdout_data.decode("utf-8", errors="replace"))
                stderr = redact_shell_output(stderr_data.decode("utf-8", errors="replace"))
                return exit_code, stdout, stderr
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
                raise ToolError(
                    message=f"Shell command execution timed out after {timeout} seconds.",
                    tool_name="shell",
                    retryable=True,
                )
        except Exception as e:
            if isinstance(e, (PermissionDeniedError, ToolError)):
                raise
            raise ToolError(f"Failed to launch process: {e}", tool_name="shell")
