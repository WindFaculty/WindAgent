#!/usr/bin/env python3
"""
Run Command Receipt Generator (Phase 2)

Executes a command and generates a canonical command receipt artifact.
Usage:
  python scripts/verification/run_command_receipt.py \
    --name full_pytest \
    --cwd . \
    --output artifacts/.../receipts/full_pytest.json \
    -- uv run pytest -q
"""

from __future__ import annotations
import json
import sys
import subprocess
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import os
import re
import uuid

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|authorization|bearer)\s*[:=]\s*[^\s\"']+"),
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]


def redact(text: str) -> str:
    """Redact common secret patterns from output."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("***REDACTED***", text)
    return text


def get_git_sha(cwd: Path) -> str:
    """Get current git SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "0" * 40


def get_environment(cwd: Path) -> Dict[str, str]:
    """Capture environment snapshot."""
    git_sha = get_git_sha(cwd)
    return {
        "os": f"{os.name} {os.uname().sysname if hasattr(os, 'uname') else 'windows'}",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "uv": get_uv_version(),
        "git_sha": git_sha,
    }


def get_uv_version() -> str:
    """Get uv version."""
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def compute_output_hash(stdout: bytes, stderr: bytes) -> str:
    """Compute SHA256 of combined output."""
    hasher = hashlib.sha256()
    hasher.update(stdout)
    hasher.update(stderr)
    return hasher.hexdigest()


def run_command(
    command: List[str],
    cwd: Path,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
) -> tuple[int, bytes, bytes, float]:
    """Run command and return (exit_code, stdout, stderr, duration_ms)."""
    start = datetime.now()
    try:
        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            env=process_env,
            timeout=timeout,
        )
        duration_ms = (datetime.now() - start).total_seconds() * 1000
        return result.returncode, result.stdout, result.stderr, duration_ms
    except subprocess.TimeoutExpired:
        duration_ms = (datetime.now() - start).total_seconds() * 1000
        return -1, b"", b"TIMEOUT", duration_ms
    except Exception as e:
        duration_ms = (datetime.now() - start).total_seconds() * 1000
        return -1, b"", str(e).encode(), duration_ms


def classify_result(exit_code: int, expected: List[int]) -> str:
    """Classify execution result."""
    if exit_code in expected:
        return "SUCCESS"
    elif exit_code == -1:
        return "TIMEOUT"
    else:
        return "FAILURE"


def generate_receipt(
    name: str,
    command: List[str],
    cwd: Path,
    exit_code: int,
    stdout: bytes,
    stderr: bytes,
    duration_ms: float,
    started_at: datetime,
    finished_at: datetime,
    expected_exit_codes: List[int],
    environment: Dict[str, str],
) -> Dict[str, Any]:
    """Generate canonical command receipt."""
    command_id = name.replace(" ", "_").lower().replace("-", "_")
    
    stdout_text = redact(stdout.decode("utf-8", errors="replace"))
    stderr_text = redact(stderr.decode("utf-8", errors="replace"))
    return {
        "command_id": command_id,
        "command": redact(" ".join(command)),
        "cwd": str(cwd.absolute()),
        "started_at": started_at.isoformat() + "Z",
        "finished_at": finished_at.isoformat() + "Z",
        "duration_ms": int(duration_ms),
        "exit_code": exit_code,
        "stdout_tail": stdout_text[-500:],
        "stderr_tail": stderr_text[-500:],
        "environment": environment,
        "expected_exit_codes": expected_exit_codes,
        "result": classify_result(exit_code, expected_exit_codes),
        "output_sha256": compute_output_hash(stdout, stderr),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute command and generate canonical receipt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/verification/run_command_receipt.py \\
    --name full_pytest \\
    --output receipts/full_pytest.json \\
    -- uv run pytest -q

  python scripts/verification/run_command_receipt.py \\
    --name arch_check \\
    --cwd . \\
    --output receipts/arch_check.json \\
    --timeout 60 \\
    -- uv run python scripts/check_architecture_imports.py
"""
    )
    parser.add_argument("--name", required=True, help="Command name/identifier")
    parser.add_argument("--cwd", default=".", help="Working directory")
    parser.add_argument("--output", required=True, help="Output receipt JSON path")
    parser.add_argument("--expected-exit-codes", nargs="+", type=int, default=[0], help="Expected exit codes")
    parser.add_argument("--timeout", type=int, help="Command timeout in seconds")
    parser.add_argument("--env", action="append", help="Environment variable KEY=VALUE")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute")
    
    args = parser.parse_args()
    
    if not args.command:
        print("ERROR: No command specified", file=sys.stderr)
        return 1
    
    if args.command[0] == "--":
        args.command = args.command[1:]
    
    cwd = Path(args.cwd).resolve()
    if not cwd.exists():
        print(f"ERROR: Working directory does not exist: {cwd}", file=sys.stderr)
        return 1
    
    # Parse env vars
    env = {}
    if args.env:
        for e in args.env:
            if "=" in e:
                k, v = e.split("=", 1)
                env[k] = v
    
    # Prepare output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Executing: {' '.join(args.command)}")
    print(f"Working directory: {cwd}")
    print(f"Expected exit codes: {args.expected_exit_codes}")
    
    # Capture environment
    environment = get_environment(cwd)
    
    # Execute
    started_at = datetime.utcnow()
    exit_code, stdout, stderr, duration_ms = run_command(
        args.command, cwd, env, args.timeout
    )
    finished_at = datetime.utcnow()
    
    print(f"Exit code: {exit_code}")
    print(f"Duration: {duration_ms:.0f}ms")
    print(f"Stdout: {len(stdout)} bytes")
    print(f"Stderr: {len(stderr)} bytes")
    
    # Generate receipt
    receipt = generate_receipt(
        name=args.name,
        command=args.command,
        cwd=cwd,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        started_at=started_at,
        finished_at=finished_at,
        expected_exit_codes=args.expected_exit_codes,
        environment=environment,
    )
    
    # Write receipt
    with open(output_path, "w") as f:
        json.dump(receipt, f, indent=2)
    
    print(f"Receipt written to: {output_path}")
    print(f"Result: {receipt['result']}")
    print(f"Output SHA256: {receipt['output_sha256']}")
    
    return 0 if receipt["result"] == "SUCCESS" else 1


if __name__ == "__main__":
    sys.exit(main())