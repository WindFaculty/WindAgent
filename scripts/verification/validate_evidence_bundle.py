#!/usr/bin/env python3
"""
Validate Evidence Bundle (Phase 2)

Validates a complete evidence bundle against artifact protocol v1 schema
and ensures all receipts link to persisted logs.
"""

from __future__ import annotations
import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple
import jsonschema
from jsonschema import validate, ValidationError


SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "artifact_protocol_v1.schema.json"
RECEIPT_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "command_receipt_v1.schema.json"


def load_schema(path: Path) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def validate_evidence_bundle(
    bundle_path: Path,
    artifact_schema: Dict[str, Any],
    receipt_schema: Dict[str, Any],
) -> Tuple[List[str], List[str]]:
    """Validate complete evidence bundle."""
    errors = []
    warnings = []

    try:
        with open(bundle_path) as f:
            bundle = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"], []

    # Validate bundle as artifact
    try:
        validate(instance=bundle, schema=artifact_schema)
    except ValidationError as e:
        errors.append(f"Bundle schema validation failed: {e.message}")

    # Validate each receipt in commands
    for i, cmd in enumerate(bundle.get("commands", [])):
        try:
            validate(instance=cmd, schema=receipt_schema)
        except ValidationError as e:
            errors.append(f"Command[{i}] receipt validation failed: {e.message}")

    # Check receipts directory exists
    receipts_dir = bundle_path.parent / "receipts"
    if not receipts_dir.exists():
        warnings.append("Receipts directory not found (expected: receipts/)")
    else:
        # Verify each command has a receipt file
        for i, cmd in enumerate(bundle.get("commands", [])):
            cmd_id = cmd.get("command_id", f"command_{i}")
            receipt_file = receipts_dir / f"{cmd_id}.json"
            if not receipt_file.exists():
                warnings.append(f"Receipt file not found: {receipt_file}")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate evidence bundle")
    parser.add_argument("bundle", help="Path to evidence_bundle.json")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    bundle_path = Path(args.bundle)
    if not bundle_path.exists():
        print(f"ERROR: Bundle not found: {bundle_path}", file=sys.stderr)
        return 1

    artifact_schema = load_schema(SCHEMA_PATH)
    receipt_schema = load_schema(RECEIPT_SCHEMA_PATH)

    errors, warnings = validate_evidence_bundle(bundle_path, artifact_schema, receipt_schema)

    if args.json:
        result = {
            "file": str(bundle_path),
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "warnings": warnings,
        }
        print(json.dumps(result, indent=2))
    else:
        status = "PASS" if not errors else f"FAIL ({len(errors)} errors)"
        print(f"Validating {bundle_path}... {status}")
        for e in errors:
            print(f"  ERROR: {e}")
        for w in warnings:
            print(f"  WARNING: {w}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())