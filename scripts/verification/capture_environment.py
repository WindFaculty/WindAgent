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
import sysconfig
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
    return {
        "os": platform.system().lower(),
        "os_version": platform.release(),
        "python": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "uv": run_cmd(["uv", "--version"]).replace("uv ", ""),
        "node": run_cmd(["node", "--version"]).lstrip("v"),
        "npm": run_cmd(["npm", "--version"]),
        "postgres": run_cmd(["psql", "--version"]).split()[-1] if run_cmd(["psql", "--version"]) else None,
    }


def get_tool_versions() -> Dict[str, str]:
    """Get versions of key tools."""
    return {
        "pytest": run_cmd(["uv", "run", "pytest", "--version"]).split()[-1],
        "ruff": run_cmd(["ruff", "--version"]).split()[-1] if run_cmd(["ruff", "--version"]) else None,
        "mypy": run_cmd(["mypy", "--version"]).split()[-1] if run_cmd(["mypy", "--version"]) else None,
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