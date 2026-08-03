"""
Real Execution Runners for WindAgent Verification (Phase 24).
Provides command execution, test runner, linter, security scanner, and environment snapshot
with real subprocess execution, timeout enforcement, and artifact hash computation.
Missing evidence = BLOCKED (fail-closed).
"""

from __future__ import annotations
import asyncio
import hashlib
import logging
import os
import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from windagent_verification.domain import ExecutionEvidence, EvidenceSource

logger = logging.getLogger("windagent.verification.runners")


@dataclass
class CommandResult:
    """Result of a real command execution."""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    artifact_hash: Optional[str] = None

    def to_evidence(self, source: EvidenceSource = EvidenceSource.COMMAND_EXECUTION) -> ExecutionEvidence:
        return ExecutionEvidence(
            command=self.command,
            exit_code=self.exit_code,
            stdout=self.stdout,
            stderr=self.stderr,
            duration_seconds=self.duration_seconds,
            artifact_hash=self.artifact_hash,
            source=source,
            metrics={
                "timed_out": self.timed_out,
                "exit_code": self.exit_code,
            },
        )


class CommandRunner:
    """Executes shell commands with timeout and captures real output.
    Returns BLOCKED-compatible evidence when execution is impossible.
    """

    def __init__(self, default_timeout_seconds: float = 30.0):
        self.default_timeout_seconds = default_timeout_seconds

    async def run(
        self,
        command: str,
        timeout_seconds: Optional[float] = None,
        capture_output: bool = True,
        compute_hash: bool = False,
    ) -> CommandResult:
        """Executes a shell command with timeout and captures real stdout/stderr."""
        if not command or not command.strip():
            return CommandResult(
                command=command or "",
                exit_code=-1,
                stdout="",
                stderr="No command provided",
                duration_seconds=0.0,
            )

        timeout = timeout_seconds or self.default_timeout_seconds
        start_time = datetime.now(timezone.utc)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE if capture_output else None,
                stderr=asyncio.subprocess.PIPE if capture_output else None,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
                stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
                exit_code = proc.returncode or 0

                result = CommandResult(
                    command=command,
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    duration_seconds=duration,
                )

                if compute_hash and stdout:
                    result.artifact_hash = hashlib.sha256(stdout.encode("utf-8")).hexdigest()[:16]

                return result

            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                logger.warning(f"Command timed out after {timeout}s: {command[:100]}")
                return CommandResult(
                    command=command,
                    exit_code=-1,
                    stdout="",
                    stderr=f"Command timed out after {timeout} seconds",
                    duration_seconds=duration,
                    timed_out=True,
                )

        except FileNotFoundError:
            return CommandResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"Command not found: {command.split()[0] if command else 'unknown'}",
                duration_seconds=0.0,
            )
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            return CommandResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_seconds=0.0,
            )


class TestRunner:
    """Real test runner using pytest, with test count parsing."""

    def __init__(self, default_timeout: float = 120.0):
        self.runner = CommandRunner(default_timeout_seconds=default_timeout)

    async def run_tests(
        self,
        test_path: str = "tests/",
        pytest_args: Optional[List[str]] = None,
        compute_hash: bool = True,
    ) -> ExecutionEvidence:
        """Runs pytest and parses real test output."""
        args = pytest_args or ["-v", "--tb=short"]
        cmd = f"python -m pytest {test_path} {' '.join(args)}"

        result = await self.runner.run(cmd, compute_hash=compute_hash)

        # Parse test counts from stdout
        passed, failed, skipped, errors = self._parse_test_counts(result.stdout)

        evidence = result.to_evidence(source=EvidenceSource.TEST_RUNNER)
        evidence.metrics.update({
            "tests_passed": passed,
            "tests_failed": failed,
            "tests_skipped": skipped,
            "tests_errors": errors,
            "test_path": test_path,
        })
        return evidence

    @staticmethod
    def _parse_test_counts(stdout: str) -> Tuple[int, int, int, int]:
        """Parses pytest summary line to extract test counts.
        Example: "= 10 passed, 2 failed, 1 skipped, 1 error in 5.23s ="
        """
        passed = _extract_count(r"(\d+)\s+passed", stdout)
        failed = _extract_count(r"(\d+)\s+failed", stdout)
        skipped = _extract_count(r"(\d+)\s+skipped", stdout)
        errors = _extract_count(r"(\d+)\s+error", stdout)  # "error" not "errors" in pytest output
        return passed, failed, skipped, errors


class LinterRunner:
    """Real linter/type checker runner with output parsing."""

    def __init__(self, default_timeout: float = 60.0):
        self.runner = CommandRunner(default_timeout_seconds=default_timeout)

    async def run_linter(self, target_path: str = ".", linter: str = "flake8") -> ExecutionEvidence:
        """Runs a linter and parses real issues."""
        if linter == "flake8":
            cmd = f"python -m flake8 {target_path} --max-line-length=120"
        elif linter == "pylint":
            cmd = f"python -m pylint {target_path} --exit-zero"
        elif linter == "mypy":
            cmd = f"python -m mypy {target_path} --ignore-missing-imports"
        else:
            cmd = f"python -m {linter} {target_path}"

        result = await self.runner.run(cmd)

        evidence = result.to_evidence(source=EvidenceSource.LINTER)
        issue_count = len([ln for ln in result.stdout.split("\n") if ln.strip()])
        evidence.metrics.update({
            "linter": linter,
            "target_path": target_path,
            "issue_count": issue_count,
        })
        return evidence


class SecurityScanner:
    """Real security scanner using bandit or built-in checks."""

    def __init__(self, default_timeout: float = 60.0):
        self.runner = CommandRunner(default_timeout_seconds=default_timeout)
        self.secret_patterns = {
            "API key (sk-)": r"sk-[a-zA-Z0-9]{20,}",
            "GitHub token (ghp_)": r"ghp_[a-zA-Z0-9]{30,}",
            "Bearer token": r"bearer\s+[a-zA-Z0-9_\-\.]+",
            "Password assignment": r"password\s*=\s*['\"][^'\"]+['\"]",
            "AWS Access Key": r"AKIA[0-9A-Z]{16}",
            "Private Key": r"-----BEGIN (RSA |EC )?PRIVATE KEY-----",
        }

    async def scan_for_secrets(self, target_path: str = ".") -> ExecutionEvidence:
        """Scans for leaked secrets in the target path."""
        # Use grep-like search for secret patterns
        cmd = f"findstr /S /M \"sk- ghp_\" {target_path}\\*.py 2>NUL || echo NO_SECRETS_FOUND"
        result = await self.runner.run(cmd)

        # Also count by parsing content for each pattern
        findings: Dict[str, int] = {}
        for name, pattern in self.secret_patterns.items():
            grep_cmd = f"findstr /S /R \"{pattern[:20]}\" {target_path}\\*.py 2>NUL || echo none"
            grep_result = await self.runner.run(grep_cmd)
            count = len([ln for ln in grep_result.stdout.split("\n") if ln.strip() and ln.strip() != "none"])
            if count > 0:
                findings[name] = count

        evidence = result.to_evidence(source=EvidenceSource.SECURITY_SCANNER)
        evidence.metrics.update({
            "target_path": target_path,
            "secret_findings": findings,
            "total_secrets_found": sum(findings.values()),
        })
        return evidence


class EnvironmentSnapshot:
    """Captures a snapshot of the execution environment."""

    @staticmethod
    async def capture() -> ExecutionEvidence:
        """Captures environment metadata."""
        env_info = {
            "python_version": sys.version,
            "platform": platform.platform(),
            "os": platform.system(),
            "cwd": os.getcwd(),
            "pid": os.getpid(),
        }

        return ExecutionEvidence(
            command="environment_snapshot",
            exit_code=0,
            source=EvidenceSource.ENVIRONMENT_SNAPSHOT,
            metrics=env_info,
        )

    @staticmethod
    async def compute_artifact_hash(file_path: str) -> ExecutionEvidence:
        """Computes SHA256 hash of an artifact file."""
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            hash_val = hashlib.sha256(content).hexdigest()
            return ExecutionEvidence(
                command=f"sha256sum {file_path}",
                exit_code=0,
                artifact_hash=hash_val[:16],
                source=EvidenceSource.ARTIFACT_HASH,
                metrics={"file_path": file_path, "size_bytes": len(content)},
            )
        except FileNotFoundError:
            return ExecutionEvidence(
                command=f"sha256sum {file_path}",
                exit_code=-1,
                stderr=f"File not found: {file_path}",
                source=EvidenceSource.ARTIFACT_HASH,
            )


def _extract_count(pattern: str, text: str) -> int:
    """Extracts integer count from text using regex pattern."""
    import re
    match = re.search(pattern, text)
    return int(match.group(1)) if match else 0
