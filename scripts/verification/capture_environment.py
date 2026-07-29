#!/usr/bin/env python3
"""
Capture Environment (Phase 2)

Captures git and runtime environment for evidence bundles.
"""

from __future__ import annotations
import json
import sys
import subprocess
import platform
from pathlib import Path
from typing import Dict, Any, Optional
import argparse


def run_cmd(cmd: list[str], cwd: Optional[Path] = None) -> str:
    """Run command and return stdout or empty string on failure."""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except Exception:
        return ""


def get_git_info(cwd: Path) -> Dict[str, Any]:
    """Get git repository information."""
    source_sha = run_cmd(["git", "rev-parse", "HEAD"], cwd)
    branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)

    # Check worktree clean
    status = run_cmd(["git", "status", "--porcelain"], cwd)
    worktree_clean = len(status) == 0

    # verified_sha is typically the same as source_sha unless specified
    verified_sha = source_sha

    return {
        "source_sha": source_sha,
        "verified_sha": verified_sha,
        "branch": branch,
        "worktree_clean": worktree_clean,
    }


def get_runtime_info() -> Dict[str, Any]:
    """Get runtime environment information."""
    postgres_output = run_cmd(["psql", "--version"])
    return {
        "os": platform.system().lower(),
        "os_version": platform.release(),
        "python": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "uv": run_cmd(["uv", "--version"]).replace("uv ", ""),
        "node": run_cmd(["node", "--version"]).lstrip("v"),
        "npm": run_cmd(["npm", "--version"]),
        "postgres": postgres_output.split()[-1] if postgres_output else None,
    }


def get_tool_versions() -> Dict[str, str]:
    """Get versions of key tools."""
    def last_token(command: list[str]) -> Optional[str]:
        output = run_cmd(command)
        return output.split()[-1] if output else None

    return {
        "pytest": last_token([sys.executable, "-m", "pytest", "--version"]),
        "ruff": last_token(["ruff", "--version"]),
        "mypy": last_token(["mypy", "--version"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture environment for evidence bundle")
    parser.add_argument("--cwd", default=".", help="Working directory")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--verified-sha", help="Override verified SHA")

    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    if not cwd.exists():
        print(f"ERROR: Working directory does not exist: {cwd}", file=sys.stderr)
        return 1

    git_info = get_git_info(cwd)

    if args.verified_sha:
        git_info["verified_sha"] = args.verified_sha

    runtime_info = get_runtime_info()
    tool_versions = get_tool_versions()

    environment = {
        "git": git_info,
        "runtime": runtime_info,
        "tools": tool_versions,
    }

    output = json.dumps(environment, indent=2)

    if args.output:
        Path(args.output).write_text(output)
        print(f"Environment written to {args.output}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
