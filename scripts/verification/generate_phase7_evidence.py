#!/usr/bin/env python3
"""Generate deterministic, immutable Phase 7 evidence.

Runs are assembled and validated in staging. A clean PASS is published to
``runs/<run-id>`` and atomically selected by ``latest.json``. FAIL/BLOCKED
runs are retained under ``quarantine/<run-id>`` and never move the pointer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_environment import get_git_info, get_runtime_info, get_tool_versions
from run_command_receipt import classify_result, redact, redact_bytes
from validate_evidence_bundle import validate_evidence_bundle


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _command_id(name: str) -> str:
    value = re.sub(r"[^a-z0-9_-]+", "_", name.lower()).strip("_")
    if not value:
        raise ValueError(f"Command name does not produce a valid id: {name!r}")
    return value


def _run_process(
    argv: List[str],
    cwd: Path,
    timeout: int,
    env: Optional[Dict[str, str]] = None,
) -> tuple[int, bytes, bytes]:
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
            env=process_env,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        return -1, exc.stdout or b"", (exc.stderr or b"") + b"TIMEOUT"
    except KeyboardInterrupt:
        return -2, b"", b"INTERRUPTED"
    except Exception as exc:
        return -3, b"", str(exc).encode("utf-8", errors="replace")


def _classify(exit_code: int, expected: List[int]) -> str:
    if exit_code == -2:
        return "INTERRUPTED"
    return classify_result(exit_code, expected)


def _execute_command(
    name: str,
    spec: Dict[str, Any],
    cwd: Path,
    receipts_dir: Path,
    logs_dir: Path,
    receipt_environment: Dict[str, str],
) -> Dict[str, Any]:
    command_id = _command_id(name)
    shell = spec.get("shell", "process")
    command = spec.get("argv", spec.get("command"))
    expected = spec.get("expected_exit_codes", [0])
    timeout = spec.get("timeout", 300)

    if shell not in {"process", "pwsh"}:
        raise ValueError(f"{name}: unsupported shell {shell!r}")
    if not isinstance(command, list) or not command or not all(
        isinstance(item, str) and item for item in command
    ):
        raise ValueError(f"{name}: argv must be a non-empty string array")
    if not isinstance(expected, list) or not expected or not all(
        isinstance(code, int) for code in expected
    ):
        raise ValueError(f"{name}: expected_exit_codes must be a non-empty int array")
    if not isinstance(timeout, int) or timeout <= 0:
        raise ValueError(f"{name}: timeout must be a positive integer")

    argv = command
    if shell == "pwsh":
        argv = ["pwsh", "-NoProfile", "-NonInteractive", "-Command", *command]

    print(f"Executing: {name} -> {redact(' '.join(argv))}")
    started_at = _utc_now()
    exit_code, stdout, stderr = _run_process(argv, cwd, timeout)
    finished_at = _utc_now()

    persisted_stdout = redact_bytes(stdout)
    persisted_stderr = redact_bytes(stderr)
    stdout_path = logs_dir / f"{command_id}.stdout.log"
    stderr_path = logs_dir / f"{command_id}.stderr.log"
    stdout_path.write_bytes(persisted_stdout)
    stderr_path.write_bytes(persisted_stderr)

    stdout_text = persisted_stdout.decode("utf-8")
    stderr_text = persisted_stderr.decode("utf-8")
    receipt = {
        "command_id": command_id,
        "command": redact(" ".join(argv)),
        "cwd": str(cwd),
        "started_at": _timestamp(started_at),
        "finished_at": _timestamp(finished_at),
        "duration_ms": max(
            0, int((finished_at - started_at).total_seconds() * 1000)
        ),
        "exit_code": exit_code,
        "stdout_tail": stdout_text[-500:],
        "stderr_tail": stderr_text[-500:],
        "environment": receipt_environment,
        "expected_exit_codes": expected,
        "result": _classify(exit_code, expected),
        "stdout_sha256": _sha256(persisted_stdout),
        "stderr_sha256": _sha256(persisted_stderr),
        "output_sha256": _sha256(persisted_stdout + persisted_stderr),
        "log_paths": {
            "stdout_log": f"logs/{command_id}.stdout.log",
            "stderr_log": f"logs/{command_id}.stderr.log",
        },
    }
    receipt_path = receipts_dir / f"{command_id}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    success = exit_code in expected
    print(
        f"  exit_code={exit_code} result={receipt['result']} "
        f"duration_ms={receipt['duration_ms']}"
    )
    return {
        "receipt": receipt,
        "success": success,
        "exit_code": exit_code,
        "duration_ms": receipt["duration_ms"],
    }


def _load_commands(path: Path) -> Dict[str, Dict[str, Any]]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    commands = data.get("commands") if isinstance(data, dict) else None
    if not isinstance(commands, dict) or not commands:
        raise ValueError("commands file must contain a non-empty commands mapping")
    selected = {
        name: spec
        for name, spec in commands.items()
        if isinstance(spec, dict) and spec.get("required", True)
    }
    if not selected:
        raise ValueError("commands file contains no required commands")
    command_ids = [_command_id(name) for name in selected]
    if len(command_ids) != len(set(command_ids)):
        raise ValueError("command names produce duplicate command_id values")
    return selected


def _capture_environment(cwd: Path) -> Dict[str, Any]:
    return {
        "git": get_git_info(cwd),
        "runtime": get_runtime_info(),
        "tools": get_tool_versions(),
    }


def _artifact_hashes(staging_dir: Path) -> Dict[str, str]:
    hashes: Dict[str, str] = {}
    for path in sorted(staging_dir.rglob("*")):
        if path.is_file() and path.name != "evidence_bundle.json":
            relative = path.relative_to(staging_dir).as_posix()
            hashes[relative] = _file_sha256(path)
    return hashes


def _publish(
    staging_dir: Path,
    output_root: Path,
    run_id: str,
    verdict: str,
    verified_sha: str,
) -> Path:
    category = "runs" if verdict == "PASS" else "quarantine"
    destination = output_root / category / run_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Immutable destination already exists: {destination}")

    # Path.replace is an atomic directory rename on the same filesystem.
    staging_dir.replace(destination)

    if verdict == "PASS":
        pointer = {
            "protocol_version": "1.0.0",
            "run_id": run_id,
            "bundle": f"runs/{run_id}/evidence_bundle.json",
            "verified_sha": verified_sha,
            "published_at": _timestamp(_utc_now()),
        }
        pointer_tmp = output_root / f".latest-{uuid.uuid4().hex}.json"
        pointer_tmp.write_text(
            json.dumps(pointer, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(pointer_tmp, output_root / "latest.json")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 7 evidence bundle")
    parser.add_argument("--commands-file", required=True)
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Authoritative root containing runs/, quarantine/, and latest.json",
    )
    parser.add_argument("--cwd", default=".")
    parser.add_argument(
        "--staging-base",
        help="Staging parent; defaults to <output-dir>/.staging on the same filesystem",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Deprecated compatibility flag; validation is always mandatory",
    )
    parser.add_argument("--run-id", help="Deterministic run id for automation/tests")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    commands_path = Path(args.commands_file).resolve()
    output_root = Path(args.output_dir).resolve()
    if not cwd.is_dir():
        print(f"ERROR: Working directory does not exist: {cwd}", file=sys.stderr)
        return 1
    if not commands_path.is_file():
        print(f"ERROR: Commands file not found: {commands_path}", file=sys.stderr)
        return 1

    run_id = args.run_id or (
        _utc_now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    )
    if not RUN_ID_PATTERN.fullmatch(run_id):
        print(f"ERROR: Invalid run id: {run_id}", file=sys.stderr)
        return 1

    output_root.mkdir(parents=True, exist_ok=True)
    staging_base = (
        Path(args.staging_base).resolve()
        if args.staging_base
        else output_root / ".staging"
    )
    staging_base.mkdir(parents=True, exist_ok=True)
    staging_dir = staging_base / run_id
    if staging_dir.exists():
        print(f"ERROR: Staging destination already exists: {staging_dir}", file=sys.stderr)
        return 1
    staging_dir.mkdir()

    published = False
    try:
        commands = _load_commands(commands_path)
        environment = _capture_environment(cwd)
        git = environment["git"]
        source_sha = git.get("source_sha", "")
        verified_sha = git.get("verified_sha", "")

        receipts_dir = staging_dir / "receipts"
        logs_dir = staging_dir / "logs"
        receipts_dir.mkdir()
        logs_dir.mkdir()
        receipt_environment = {
            "os": environment["runtime"].get("os", "unknown"),
            "python": environment["runtime"].get("python", "unknown"),
            "uv": environment["runtime"].get("uv") or "unknown",
            "git_sha": verified_sha,
        }

        receipts: List[Dict[str, Any]] = []
        results: Dict[str, Any] = {}
        failures: List[Dict[str, str]] = []
        for name, spec in commands.items():
            result = _execute_command(
                name,
                spec,
                cwd,
                receipts_dir,
                logs_dir,
                receipt_environment,
            )
            receipts.append(result["receipt"])
            results[name] = {
                "exit_code": result["exit_code"],
                "duration_ms": result["duration_ms"],
                "success": result["success"],
            }
            if not result["success"]:
                failures.append(
                    {
                        "check": name,
                        "message": (
                            f"Command exited {result['exit_code']}; expected "
                            f"{spec.get('expected_exit_codes', [0])}"
                        ),
                        "severity": "HIGH",
                    }
                )

        worktree_clean = bool(git.get("worktree_clean"))
        verdict = "FAIL" if failures else ("PASS" if worktree_clean else "BLOCKED")
        bundle = {
            "artifact_type": "evidence_bundle",
            "protocol_version": "1.0.0",
            "generated_at": _timestamp(_utc_now()),
            "source_sha": source_sha,
            "verified_sha": verified_sha,
            "branch": git.get("branch") or "unknown",
            "worktree_clean": worktree_clean,
            "environment": environment,
            "commands": receipts,
            "results": results,
            "failures": failures,
            "warnings": [],
            "artifact_hashes": _artifact_hashes(staging_dir),
            "verdict": verdict,
        }
        bundle_path = staging_dir / "evidence_bundle.json"
        bundle_path.write_text(
            json.dumps(bundle, indent=2) + "\n", encoding="utf-8"
        )

        validation_errors, validation_warnings = validate_evidence_bundle(bundle_path)
        if validation_errors or validation_warnings:
            for error in validation_errors:
                print(f"VALIDATION ERROR: {error}", file=sys.stderr)
            for warning in validation_warnings:
                print(f"VALIDATION WARNING: {warning}", file=sys.stderr)
            print("ERROR: Invalid evidence was not published", file=sys.stderr)
            return 1

        destination = _publish(
            staging_dir,
            output_root,
            run_id,
            verdict,
            verified_sha,
        )
        published = True
        print(f"Evidence published: {destination}")
        print(f"Verdict: {verdict}")
        if verdict == "PASS":
            print(f"Authoritative pointer: {output_root / 'latest.json'}")
            return 0
        if verdict == "BLOCKED":
            print("Dirty worktree: run quarantined; latest.json unchanged")
            return 2
        print("Failed command: run quarantined; latest.json unchanged")
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if not published and staging_dir.exists():
            shutil.rmtree(staging_dir)


if __name__ == "__main__":
    sys.exit(main())
