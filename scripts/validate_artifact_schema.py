#!/usr/bin/env python3
"""
WindAgent Artifact Schema Validator (Phase 7A)

Validates artifact JSON files against the standardized schema.
"""

from __future__ import annotations
import json
import sys
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import jsonschema
from jsonschema import validate, ValidationError


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "scripts" / "artifact_schema.json"

VALID_VERDICTS = {"PASS", "FAIL", "BLOCKED", "PARTIAL"}
VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


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


def validate_artifact(artifact_path: Path, schema: Dict[str, Any]) -> List[str]:
    """Validate a single artifact file against schema and additional rules.
    Returns list of error messages (empty if valid)."""
    errors = []

    try:
        with open(artifact_path) as f:
            artifact = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

    # Schema validation
    try:
        validate(instance=artifact, schema=schema)
    except ValidationError as e:
        errors.append(f"Schema validation failed: {e.message}")

    # Additional semantic validations
    if not errors:
        errors.extend(_validate_semantics(artifact, artifact_path))

    return errors


def _validate_semantics(artifact: Dict[str, Any], artifact_path: Path) -> List[str]:
    """Validate semantic rules beyond JSON schema."""
    errors = []

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

    # 3. worktree_clean=false but verdict=PASS is invalid
    if artifact.get("worktree_clean") is False and artifact.get("verdict") == "PASS":
        errors.append("worktree_clean=false but verdict=PASS (dirty worktree cannot PASS)")

    # 4. commands array must not be empty
    commands = artifact.get("commands", [])
    if not commands or len(commands) == 0:
        errors.append("commands array must have at least one command receipt")

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

    return errors


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python validate_artifact_schema.py <artifact.json> [artifact2.json ...]")
        return 1

    schema = load_schema()
    all_errors = []

    for arg in sys.argv[1:]:
        artifact_path = Path(arg)
        if not artifact_path.exists():
            print(f"ERROR: File not found: {artifact_path}")
            all_errors.append(f"File not found: {artifact_path}")
            continue

        print(f"Validating {artifact_path}...")
        errors = validate_artifact(artifact_path, schema)

        if errors:
            print(f"  FAIL: {len(errors)} error(s)")
            for err in errors:
                print(f"    - {err}")
            all_errors.extend([f"{artifact_path}: {e}" for e in errors])
        else:
            print(f"  PASS")

    if all_errors:
        print(f"\nVALIDATION FAILED: {len(all_errors)} total error(s)")
        return 1

    print("\nAll artifacts PASSED schema validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())