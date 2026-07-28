#!/usr/bin/env python3
"""
WindAgent Artifact Schema Validator (Phase 7A - Hardened)

Validates artifact JSON files against the standardized schema v1.

Usage:
  python validate_artifact_schema.py <artifact.json> [artifact2.json ...]
  python validate_artifact_schema.py --directory <dir> [--recursive]
  python validate_artifact_schema.py --schema-only <artifact.json>
  python validate_artifact_schema.py --semantic <artifact.json>
  python validate_artifact_schema.py --verify-hashes <artifact.json>
  python validate_artifact_schema.py --json <artifact.json>
  python validate_artifact_schema.py --fail-on-warning <artifact.json>
"""

from __future__ import annotations
import json
import sys
import hashlib
import argparse
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Set, Tuple
import jsonschema
from jsonschema import validate, ValidationError


SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "artifact_protocol_v1.schema.json"

VALID_VERDICTS = {"PASS", "FAIL", "BLOCKED", "PARTIAL"}
VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
VALID_WARNING_SEVERITIES = {"LOW", "MEDIUM", "HIGH"}
VALID_RESULTS = {"SUCCESS", "FAILURE", "TIMEOUT", "INTERRUPTED"}
VALID_COMMAND_ID_PATTERN = r"^[a-z0-9_-]+$"


def load_schema() -> Dict[str, Any]:
    """Load the artifact JSON schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate_artifact(
    artifact_path: Path,
    schema: Dict[str, Any],
    mode: str = "full",
    verify_hashes: bool = False,
    fail_on_warning: bool = False,
    artifact_dir: Optional[Path] = None,
) -> Tuple[List[str], List[str]]:
    """Validate a single artifact file against schema and additional rules.
    Returns (errors, warnings)."""
    errors = []
    warnings = []

    try:
        with open(artifact_path) as f:
            artifact = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"], []

    # Schema validation (always run unless schema-only is false and we only want semantic)
    if mode in ("full", "schema-only"):
        try:
            validate(instance=artifact, schema=schema)
        except ValidationError as e:
            errors.append(f"Schema validation failed: {e.message}")

    # Semantic validations
    if mode in ("full", "semantic"):
        sem_errors, sem_warnings = _validate_semantics(artifact, artifact_path, artifact_dir, verify_hashes)
        errors.extend(sem_errors)
        warnings.extend(sem_warnings)

    # Hash verification
    if mode in ("full", "verify-hashes") and artifact_dir:
        hash_errors = _verify_artifact_hashes(artifact, artifact_dir)
        errors.extend(hash_errors)

    if fail_on_warning and warnings:
        errors.extend([f"WARNING (treated as error): {w}" for w in warnings])

    return errors, warnings


def _validate_semantics(
    artifact: Dict[str, Any],
    artifact_path: Path,
    artifact_dir: Optional[Path] = None,
    verify_hashes: bool = False,
) -> Tuple[List[str], List[str]]:
    """Validate semantic rules beyond JSON schema."""
    errors = []
    warnings = []

    # 1. verified_sha must be valid 40-char hex
    verified_sha = artifact.get("verified_sha", "")
    if verified_sha and len(verified_sha) != 40:
        errors.append(f"verified_sha must be 40 hex chars, got {len(verified_sha)}")
    elif verified_sha and not all(c in "0123456789abcdef" for c in verified_sha):
        errors.append("verified_sha must be lowercase hex")

    # 2. source_sha must be valid 40-char hex
    source_sha = artifact.get("source_sha", "")
    if source_sha and len(source_sha) != 40:
        errors.append(f"source_sha must be 40 hex chars, got {len(source_sha)}")
    elif source_sha and not all(c in "0123456789abcdef" for c in source_sha):
        errors.append("source_sha must be lowercase hex")

    # 3. worktree_clean=false but verdict=PASS is invalid
    if artifact.get("worktree_clean") is False and artifact.get("verdict") == "PASS":
        errors.append("worktree_clean=false but verdict=PASS (dirty worktree cannot PASS)")

    # 4. commands array must not be empty
    commands = artifact.get("commands", [])
    if not commands or len(commands) == 0:
        errors.append("commands array must have at least one command receipt")
    else:
        # Validate each command receipt
        for i, cmd in enumerate(commands):
            cmd_errors = _validate_command_receipt(cmd, i)
            errors.extend(cmd_errors)

    # 5. artifact_hashes must not be empty
    hashes = artifact.get("artifact_hashes", {})
    if not hashes or len(hashes) == 0:
        errors.append("artifact_hashes must not be empty")

    # 6. artifact hash values must be valid SHA256 (64 hex chars)
    for fname, fhash in hashes.items():
        if len(fhash) != 64:
            errors.append(f"Artifact hash for {fname} must be 64 hex chars (SHA256), got {len(fhash)}")
        elif not all(c in "0123456789abcdef" for c in fhash):
            errors.append(f"Artifact hash for {fname} must be lowercase hex")

    # 7. verdict must be valid
    verdict = artifact.get("verdict", "")
    if verdict not in VALID_VERDICTS:
        errors.append(f"verdict must be one of {VALID_VERDICTS}, got '{verdict}'")

    # 8. failures severity must be valid
    for failure in artifact.get("failures", []):
        severity = failure.get("severity", "")
        if severity not in VALID_SEVERITIES:
            errors.append(f"Failure severity must be one of {VALID_SEVERITIES}, got '{severity}'")

    # 9. generated_at must be valid ISO8601
    generated_at = artifact.get("generated_at", "")
    try:
        datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        errors.append("generated_at must be valid ISO8601 datetime")

    # 10. warnings must be structured objects (not strings)
    for warning in artifact.get("warnings", []):
        if isinstance(warning, str):
            errors.append("warnings must be structured objects, not strings. Use {check, message, severity, accepted, rationale}")
        elif isinstance(warning, dict):
            check = warning.get("check", "")
            severity = warning.get("severity", "")
            accepted = warning.get("accepted", None)
            rationale = warning.get("rationale", "")
            if not check:
                warnings.append("Warning missing 'check' field")
            if severity not in VALID_WARNING_SEVERITIES:
                warnings.append(f"Warning severity must be one of {VALID_WARNING_SEVERITIES}, got '{severity}'")
            if accepted is None:
                warnings.append("Warning missing 'accepted' field")
            if not rationale:
                warnings.append("Warning missing 'rationale' field")

    # 11. Self-hash check: artifact should not contain its own hash
    artifact_name = artifact_path.name
    if artifact_name in hashes:
        warnings.append(f"Artifact contains its own hash ({artifact_name}) - self-referential hash detected")

    return errors, warnings


def _validate_command_receipt(cmd: Dict[str, Any], index: int) -> List[str]:
    """Validate a single command receipt."""
    errors = []

    # Required fields per new schema
    required_fields = [
        "command_id", "command", "cwd", "started_at", "finished_at",
        "duration_ms", "exit_code", "stdout_tail", "stderr_tail",
        "environment", "expected_exit_codes", "result", "output_sha256"
    ]
    for field in required_fields:
        if field not in cmd:
            errors.append(f"Command[{index}] missing required field: {field}")

    # Validate command_id format
    cmd_id = cmd.get("command_id", "")
    if cmd_id and not re.match(VALID_COMMAND_ID_PATTERN, cmd_id):
        errors.append(f"Command[{index}] command_id must match {VALID_COMMAND_ID_PATTERN}, got '{cmd_id}'")

    # Validate timestamps
    for ts_field in ["started_at", "finished_at"]:
        ts = cmd.get(ts_field, "")
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"Command[{index}] {ts_field} must be valid ISO8601 datetime")

    # Validate duration_ms
    duration = cmd.get("duration_ms", -1)
    if not isinstance(duration, int) or duration < 0:
        errors.append(f"Command[{index}] duration_ms must be non-negative integer")

    # Validate exit_code
    exit_code = cmd.get("exit_code", None)
    if not isinstance(exit_code, int):
        errors.append(f"Command[{index}] exit_code must be integer")

    # Validate expected_exit_codes
    expected = cmd.get("expected_exit_codes", [])
    if not isinstance(expected, list) or len(expected) == 0:
        errors.append(f"Command[{index}] expected_exit_codes must be non-empty array")
    elif not all(isinstance(x, int) for x in expected):
        errors.append(f"Command[{index}] expected_exit_codes must contain only integers")

    # Validate result
    result = cmd.get("result", "")
    if result not in VALID_RESULTS:
        errors.append(f"Command[{index}] result must be one of {VALID_RESULTS}, got '{result}'")

    # Validate output_sha256
    out_hash = cmd.get("output_sha256", "")
    if out_hash and (len(out_hash) != 64 or not all(c in "0123456789abcdef" for c in out_hash)):
        errors.append(f"Command[{index}] output_sha256 must be 64 lowercase hex chars")

    # Validate environment
    env = cmd.get("environment", {})
    required_env = ["os", "python", "uv", "git_sha"]
    for field in required_env:
        if field not in env:
            errors.append(f"Command[{index}] environment missing required field: {field}")
    if "git_sha" in env:
        gs = env["git_sha"]
        if len(gs) != 40 or not all(c in "0123456789abcdef" for c in gs):
            errors.append(f"Command[{index}] environment.git_sha must be 40 lowercase hex chars")

    return errors


def _verify_artifact_hashes(artifact: Dict[str, Any], artifact_dir: Path) -> List[str]:
    """Verify artifact hashes against actual files."""
    errors = []
    hashes = artifact.get("artifact_hashes", {})

    for fname, expected_hash in hashes.items():
        file_path = artifact_dir / fname
        if not file_path.exists():
            errors.append(f"Artifact file not found for hash verification: {fname}")
            continue
        actual_hash = compute_file_hash(file_path)
        if actual_hash != expected_hash:
            errors.append(f"Hash mismatch for {fname}: expected {expected_hash}, got {actual_hash}")

    return errors


def collect_artifact_files(
    paths: List[str],
    recursive: bool = False,
) -> List[Path]:
    """Collect artifact files from paths (files, directories, or globs)."""
    artifacts = []
    for path_str in paths:
        path = Path(path_str)
        if path.is_file():
            if path.suffix == ".json":
                artifacts.append(path)
        elif path.is_dir():
            pattern = "**/*.json" if recursive else "*.json"
            artifacts.extend(path.glob(pattern))
        else:
            # Try as glob
            parent = path.parent if path.parent != Path(".") else Path(".")
            pattern = path.name
            artifacts.extend(parent.glob(pattern))
    return sorted(set(artifacts))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate WindAgent artifact schema v1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python validate_artifact_schema.py artifact.json
  python validate_artifact_schema.py --directory artifacts/phase_07 --recursive
  python validate_artifact_schema.py --schema-only artifact.json
  python validate_artifact_schema.py --semantic artifact.json
  python validate_artifact_schema.py --verify-hashes artifact.json
  python validate_artifact_schema.py --json artifact.json
  python validate_artifact_schema.py --fail-on-warning artifact.json
"""
    )
    parser.add_argument("files", nargs="*", help="Artifact JSON files to validate")
    parser.add_argument("--directory", "-d", help="Directory containing artifact JSON files")
    parser.add_argument("--recursive", "-r", action="store_true", help="Recursively search subdirectories")
    parser.add_argument("--schema-only", action="store_true", help="Only validate JSON schema, skip semantic checks")
    parser.add_argument("--semantic", action="store_true", help="Only run semantic validations (skip JSON schema)")
    parser.add_argument("--verify-hashes", action="store_true", help="Verify artifact_hashes against actual files")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--fail-on-warning", action="store_true", help="Treat warnings as errors")

    args = parser.parse_args()

    # Determine mode
    if args.schema_only:
        mode = "schema-only"
    elif args.semantic:
        mode = "semantic"
    elif args.verify_hashes:
        mode = "verify-hashes"
    else:
        mode = "full"

    schema = load_schema()
    all_errors = []
    all_warnings = []
    results = []

    # Collect files to validate
    files_to_validate = []
    if args.files:
        files_to_validate = [Path(f) for f in args.files]
    elif args.directory:
        files_to_validate = collect_artifact_files([args.directory], args.recursive)
    else:
        parser.print_help()
        return 1

    if not files_to_validate:
        print("No JSON artifact files found to validate")
        return 1

    for artifact_path in files_to_validate:
        if not artifact_path.exists():
            all_errors.append(f"File not found: {artifact_path}")
            continue

        artifact_dir = artifact_path.parent if args.verify_hashes else None
        errors, warnings = validate_artifact(
            artifact_path,
            schema,
            mode=mode,
            verify_hashes=args.verify_hashes,
            fail_on_warning=args.fail_on_warning,
            artifact_dir=artifact_dir,
        )

        result = {
            "file": str(artifact_path),
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "warnings": warnings,
        }
        results.append(result)

        if errors:
            all_errors.extend([f"{artifact_path}: {e}" for e in errors])
        all_warnings.extend([f"{artifact_path}: {w}" for w in warnings])

        if not args.json:
            status = "PASS" if not errors else f"FAIL ({len(errors)} errors)"
            print(f"Validating {artifact_path}... {status}")
            for e in errors:
                print(f"  ERROR: {e}")
            for w in warnings:
                print(f"  WARNING: {w}")

    if args.json:
        output = {
            "summary": {
                "total": len(results),
                "passed": sum(1 for r in results if r["status"] == "PASS"),
                "failed": sum(1 for r in results if r["status"] == "FAIL"),
                "total_errors": len(all_errors),
                "total_warnings": len(all_warnings),
            },
            "results": results,
        }
        print(json.dumps(output, indent=2))

    if all_errors:
        if not args.json:
            print(f"\nVALIDATION FAILED: {len(all_errors)} total error(s)")
        return 1

    if not args.json:
        print(f"\nAll {len(results)} artifact(s) PASSED schema validation")
        if all_warnings:
            print(f"Warnings: {len(all_warnings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())