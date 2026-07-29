#!/usr/bin/env python3
"""Validate a complete Phase 2 evidence bundle.

The validator closes the chain:
bundle -> inline receipt -> persisted receipt -> persisted redacted logs.
Every hash is recomputed from bytes on disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from jsonschema import Draft7Validator, FormatChecker
from referencing import Registry, Resource


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
SCHEMA_PATH = SCHEMA_DIR / "artifact_protocol_v1.schema.json"
RECEIPT_SCHEMA_PATH = SCHEMA_DIR / "command_receipt_v1.schema.json"


def load_schema(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        schema = json.load(stream)
    schema["$id"] = path.resolve().as_uri()
    return schema


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _schema_errors(instance: Any, schema: Dict[str, Any]) -> List[str]:
    receipt_schema = load_schema(RECEIPT_SCHEMA_PATH)
    registry = Registry().with_resource(
        RECEIPT_SCHEMA_PATH.resolve().as_uri(),
        Resource.from_contents(receipt_schema),
    )
    validator = Draft7Validator(
        schema,
        format_checker=FormatChecker(),
        registry=registry,
    )
    return [
        error.message
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    ]


def _safe_bundle_path(bundle_dir: Path, relative_path: str) -> Path:
    candidate = (bundle_dir / relative_path).resolve()
    try:
        candidate.relative_to(bundle_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes bundle directory: {relative_path}") from exc
    return candidate


def _validate_environment(bundle: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    environment = bundle.get("environment")
    if not isinstance(environment, dict):
        return ["Evidence bundle must contain an environment manifest"]

    git = environment.get("git", {})
    identity_pairs = {
        "source_sha": bundle.get("source_sha"),
        "verified_sha": bundle.get("verified_sha"),
        "branch": bundle.get("branch"),
        "worktree_clean": bundle.get("worktree_clean"),
    }
    for field, expected in identity_pairs.items():
        if git.get(field) != expected:
            errors.append(f"environment.git.{field} does not match bundle {field}")

    runtime = environment.get("runtime", {})
    for field in ("os", "python", "uv", "node", "npm", "postgres"):
        if field not in runtime:
            errors.append(f"environment.runtime missing required field: {field}")
    return errors


def _validate_receipt_chain(
    bundle_dir: Path,
    receipt: Dict[str, Any],
    receipt_schema: Dict[str, Any],
    verified_sha: str,
    artifact_hashes: Dict[str, str],
) -> List[str]:
    errors: List[str] = []
    command_id = receipt.get("command_id", "<missing>")

    for error in _schema_errors(receipt, receipt_schema):
        errors.append(f"{command_id}: receipt schema validation failed: {error}")

    if receipt.get("environment", {}).get("git_sha") != verified_sha:
        errors.append(f"{command_id}: environment.git_sha does not equal verified_sha")

    receipt_rel = f"receipts/{command_id}.json"
    try:
        receipt_path = _safe_bundle_path(bundle_dir, receipt_rel)
    except ValueError as exc:
        return errors + [f"{command_id}: {exc}"]
    if not receipt_path.is_file():
        return errors + [f"{command_id}: persisted receipt not found: {receipt_rel}"]

    try:
        persisted_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return errors + [f"{command_id}: persisted receipt is unreadable: {exc}"]
    if persisted_receipt != receipt:
        errors.append(f"{command_id}: persisted receipt differs from inline receipt")

    log_paths = receipt.get("log_paths")
    if not isinstance(log_paths, dict):
        errors.append(f"{command_id}: log_paths is required")
        return errors

    log_bytes: Dict[str, bytes] = {}
    for stream_name, path_key in (
        ("stdout", "stdout_log"),
        ("stderr", "stderr_log"),
    ):
        relative_path = log_paths.get(path_key)
        if not isinstance(relative_path, str) or not relative_path:
            errors.append(f"{command_id}: log_paths.{path_key} is required")
            continue
        try:
            log_path = _safe_bundle_path(bundle_dir, relative_path)
        except ValueError as exc:
            errors.append(f"{command_id}: {exc}")
            continue
        if not log_path.is_file():
            errors.append(f"{command_id}: persisted log not found: {relative_path}")
            continue
        log_bytes[stream_name] = log_path.read_bytes()

        expected_hash = receipt.get(f"{stream_name}_sha256")
        actual_hash = _sha256(log_bytes[stream_name])
        if expected_hash != actual_hash:
            errors.append(
                f"{command_id}: {stream_name}_sha256 mismatch "
                f"(expected {expected_hash}, got {actual_hash})"
            )
        if relative_path not in artifact_hashes:
            errors.append(f"{command_id}: artifact_hashes missing {relative_path}")

    if set(log_bytes) == {"stdout", "stderr"}:
        combined_hash = _sha256(log_bytes["stdout"] + log_bytes["stderr"])
        if receipt.get("output_sha256") != combined_hash:
            errors.append(
                f"{command_id}: output_sha256 mismatch "
                f"(expected {receipt.get('output_sha256')}, got {combined_hash})"
            )

    if receipt_rel not in artifact_hashes:
        errors.append(f"{command_id}: artifact_hashes missing {receipt_rel}")
    return errors


def validate_evidence_bundle(
    bundle_path: Path,
    artifact_schema: Dict[str, Any] | None = None,
    receipt_schema: Dict[str, Any] | None = None,
) -> Tuple[List[str], List[str]]:
    """Validate a complete bundle and return ``(errors, warnings)``."""
    errors: List[str] = []
    warnings: List[str] = []
    artifact_schema = artifact_schema or load_schema(SCHEMA_PATH)
    receipt_schema = receipt_schema or load_schema(RECEIPT_SCHEMA_PATH)

    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Invalid bundle JSON: {exc}"], []

    for error in _schema_errors(bundle, artifact_schema):
        errors.append(f"Bundle schema validation failed: {error}")

    if bundle.get("artifact_type") != "evidence_bundle":
        errors.append("artifact_type must be evidence_bundle")
    errors.extend(_validate_environment(bundle))

    artifact_hashes = bundle.get("artifact_hashes", {})
    if not isinstance(artifact_hashes, dict):
        artifact_hashes = {}

    if bundle_path.name in artifact_hashes:
        errors.append("Evidence bundle must not contain a self-hash")

    bundle_dir = bundle_path.parent
    for relative_path, expected_hash in artifact_hashes.items():
        try:
            artifact_path = _safe_bundle_path(bundle_dir, relative_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not artifact_path.is_file():
            errors.append(f"Artifact file not found: {relative_path}")
            continue
        actual_hash = _sha256(artifact_path.read_bytes())
        if actual_hash != expected_hash:
            errors.append(
                f"Artifact hash mismatch for {relative_path}: "
                f"expected {expected_hash}, got {actual_hash}"
            )

    verified_sha = bundle.get("verified_sha", "")
    seen_ids: set[str] = set()
    for receipt in bundle.get("commands", []):
        command_id = receipt.get("command_id", "")
        if command_id in seen_ids:
            errors.append(f"Duplicate command_id: {command_id}")
        seen_ids.add(command_id)
        errors.extend(
            _validate_receipt_chain(
                bundle_dir,
                receipt,
                receipt_schema,
                verified_sha,
                artifact_hashes,
            )
        )

    if bundle.get("verdict") == "PASS" and not bundle.get("worktree_clean"):
        errors.append("Dirty worktree cannot produce a PASS evidence bundle")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Phase 2 evidence bundle")
    parser.add_argument("bundle", help="Path to evidence_bundle.json")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    bundle_path = Path(args.bundle)
    if not bundle_path.is_file():
        print(f"ERROR: Bundle not found: {bundle_path}", file=sys.stderr)
        return 1

    errors, warnings = validate_evidence_bundle(bundle_path)
    result = {
        "file": str(bundle_path),
        "status": "PASS" if not errors and not warnings else "FAIL",
        "errors": errors,
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Validating {bundle_path}... {result['status']}")
        for error in errors:
            print(f"  ERROR: {error}")
        for warning in warnings:
            print(f"  WARNING: {warning}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
