#!/usr/bin/env python3
"""
Generate Phase 7 Evidence Bundle (Phase 2 - Hardened)

Orchestrates command execution, receipt capture, hash computation,
and artifact validation in a staging directory before atomic publish.
"""

from __future__ import annotations
import json
import sys
import subprocess
import shutil
import uuid
import argparse
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import os
import hashlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_command_receipt import redact


def run_cmd(cmd: list[str], cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None, timeout: int = 300) -> tuple[int, str, str]:
    """Run command and return (exit_code, stdout, stderr)."""
    try:
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=process_env
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:
        return -1, "", str(e)


def get_git_sha(cwd: Path) -> str:
    """Get current git SHA."""
    code, out, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd)
    return out.strip() if code == 0 else "0" * 40


def get_branch(cwd: Path) -> str:
    """Get current git branch."""
    code, out, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return out.strip() if code == 0 else "unknown"


def is_worktree_clean(cwd: Path) -> bool:
    """Check if worktree is clean."""
    code, out, _ = run_cmd(["git", "status", "--porcelain"], cwd)
    return code == 0 and len(out.strip()) == 0


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_output_hash(stdout: bytes, stderr: bytes) -> str:
    """Compute SHA256 of combined output."""
    hasher = hashlib.sha256()
    hasher.update(stdout)
    hasher.update(stderr)
    return hasher.hexdigest()


def classify_result(exit_code: int, expected: List[int]) -> str:
    """Classify execution result."""
    if exit_code == -1:
        return "TIMEOUT"
    elif exit_code in expected:
        return "SUCCESS"
    else:
        return "FAILURE"


def get_environment(cwd: Path) -> Dict[str, Any]:
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
    code, out, _ = run_cmd(["uv", "--version"])
    return out.replace("uv ", "").strip() if code == 0 else "unknown"


def generate_receipt(
    name: str,
    command: List[str],
    cwd: Path,
    exit_code: int,
    stdout: str,
    stderr: str,
    duration_ms: float,
    started_at: datetime,
    finished_at: datetime,
    expected_exit_codes: List[int],
    git_sha: str,
) -> Dict[str, Any]:
    """Generate canonical command receipt."""
    command_id = name.replace(" ", "_").lower()
    
    env = get_environment(cwd)
    
    stdout_bytes = stdout.encode()
    stderr_bytes = stderr.encode()
    
    return {
        "command_id": command_id,
        "command": redact(" ".join(command)),
        "cwd": str(cwd.absolute()),
        "started_at": started_at.isoformat() + "Z",
        "finished_at": finished_at.isoformat() + "Z",
        "duration_ms": int(duration_ms),
        "exit_code": exit_code,
        "stdout_tail": redact(stdout[-500:]) if stdout else "",
        "stderr_tail": redact(stderr[-500:]) if stderr else "",
        "environment": env,
        "expected_exit_codes": expected_exit_codes,
        "result": classify_result(exit_code, expected_exit_codes),
        "output_sha256": compute_output_hash(stdout_bytes, stderr_bytes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 7 evidence bundle")
    parser.add_argument("--commands-file", required=True, help="YAML/JSON file with command specs")
    parser.add_argument("--output-dir", required=True, help="Final output directory (atomic publish)")
    parser.add_argument("--cwd", default=".", help="Working directory")
    parser.add_argument("--staging-base", default=".tmp/phase7-evidence", help="Staging base directory")
    
    args = parser.parse_args()
    
    cwd = Path(args.cwd).resolve()
    if not cwd.exists():
        print(f"ERROR: Working directory does not exist: {cwd}", file=sys.stderr)
        return 1
    
    # Parse commands file
    commands_path = Path(args.commands_file)
    if not commands_path.exists():
        print(f"ERROR: Commands file not found: {commands_path}", file=sys.stderr)
        return 1
    
    if commands_path.suffix in (".yaml", ".yml"):
        import yaml
        with open(commands_path) as f:
            commands_data = yaml.safe_load(f)
    else:
        with open(commands_path) as f:
            commands_data = json.load(f)
    
    commands = commands_data.get("commands", {})
    if not commands:
        print("ERROR: No commands specified", file=sys.stderr)
        return 1
    
    # Create staging directory
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + "-" + str(uuid.uuid4())[:8]
    staging_dir = Path(args.staging_base) / run_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    
    output_dir = Path(args.output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        print(f"Staging directory: {staging_dir}")
        print(f"Output directory: {output_dir}")
        
        # Capture environment at start
        git_sha = get_git_sha(cwd)
        branch = get_branch(cwd)
        worktree_clean = is_worktree_clean(cwd)
        
        receipts = []
        results = {}
        failures = []
        warnings = []
        
        for name, spec in commands.items():
            command = spec["command"]
            expected = spec.get("expected_exit_codes", [0])
            timeout = spec.get("timeout", 300)
            
            print(f"\nExecuting: {name} -> {' '.join(command)}")
            
            started_at = datetime.utcnow()
            exit_code, stdout, stderr = run_cmd(command, cwd=cwd, timeout=timeout)
            finished_at = datetime.utcnow()
            duration_ms = (finished_at - started_at).total_seconds() * 1000
            
            # Generate receipt
            receipt = generate_receipt(
                name=name,
                command=command,
                cwd=cwd,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
                started_at=started_at,
                finished_at=finished_at,
                expected_exit_codes=expected,
                git_sha=git_sha,
            )
            
            # Save receipt
            receipts_dir = staging_dir / "receipts"
            receipts_dir.mkdir(parents=True, exist_ok=True)
            receipt_path = receipts_dir / f"{receipt['command_id']}.json"
            with open(receipt_path, "w") as f:
                json.dump(receipt, f, indent=2)
            
            receipts.append(receipt)
            
            # Track results
            results[name] = {
                "exit_code": exit_code,
                "duration_ms": int(duration_ms),
                "success": exit_code in expected,
            }
            
            if exit_code not in expected:
                failures.append({
                    "check": name,
                    "message": f"Command failed with exit code {exit_code}, expected {expected}",
                    "severity": "HIGH",
                })
                warnings.append({
                    "check": name,
                    "message": f"Command {name} failed but continuing",
                    "severity": "LOW",
                    "accepted": True,
                    "rationale": "Some commands may fail in partial verification",
                })
            
            print(f"  exit_code: {exit_code}, duration_ms: {int(duration_ms)}, result: {receipt['result']}")
        
        # Generate artifact hashes for all JSON files in staging
        artifact_hashes = {}
        for json_file in staging_dir.rglob("*.json"):
            rel_path = json_file.relative_to(staging_dir)
            artifact_hashes[str(rel_path)] = compute_file_hash(json_file)
        
        # Determine verdict
        if failures:
            verdict = "FAIL"
        elif not worktree_clean:
            verdict = "BLOCKED"
        else:
            verdict = "PASS"
        
        # Generate final bundle
        bundle = {
            "protocol_version": "1.0.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source_sha": git_sha,
            "verified_sha": git_sha,
            "branch": branch,
            "worktree_clean": worktree_clean,
            "commands": receipts,
            "results": results,
            "failures": failures,
            "warnings": warnings,
            "artifact_hashes": artifact_hashes,
            "verdict": verdict,
        }
        
        # Save bundle
        bundle_path = staging_dir / "evidence_bundle.json"
        with open(bundle_path, "w") as f:
            json.dump(bundle, f, indent=2)
        
        # Atomic publish: copy staging to output
        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.copytree(staging_dir, output_dir)
        
        print(f"\n{'='*60}")
        print(f"Evidence bundle generated at: {output_dir}")
        print(f"Run ID: {run_id}")
        print(f"Verdict: {verdict}")
        print(f"Commands executed: {len(receipts)}")
        print(f"Failures: {len(failures)}")
        print(f"Worktree clean: {worktree_clean}")
        print(f"Git SHA: {git_sha}")
        print(f"{'='*60}")
        
        return 0 if verdict != "FAIL" else 1
        
    finally:
        # Cleanup staging
        if staging_dir.exists():
            shutil.rmtree(staging_dir)


if __name__ == "__main__":
    sys.exit(main())