#!/usr/bin/env python3
"""Derive a Phase 2 verdict from validated evidence.

The finalizer has no option for supplying a verdict. It validates the bundle,
loads the canonical command registry, and derives PASS/FAIL/BLOCKED from the
persisted required-command evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_evidence_bundle import validate_evidence_bundle


def _command_id(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", name.lower()).strip("_")


def load_required_commands(registry_path: Path) -> dict[str, dict[str, Any]]:
    """Load only verdict-bearing commands from the canonical registry."""
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    commands = payload.get("commands") if isinstance(payload, dict) else None
    if not isinstance(commands, dict) or not commands:
        raise ValueError("command registry must contain a non-empty commands mapping")

    required: dict[str, dict[str, Any]] = {}
    for name, spec in commands.items():
        if not isinstance(name, str) or not isinstance(spec, dict):
            raise ValueError("each registry command must have a string name and mapping")
        if spec.get("required", True):
            required[name] = spec
    if not required:
        raise ValueError("command registry contains no required commands")
    return required


def derive_verdict(
    bundle: dict[str, Any],
    required_commands: dict[str, dict[str, Any]],
    protocol_errors: list[str] | None = None,
    protocol_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Return gate results and a verdict derived only from persisted evidence."""
    errors = list(protocol_errors or [])
    warnings = list(protocol_warnings or [])
    receipts = {
        receipt.get("command_id"): receipt
        for receipt in bundle.get("commands", [])
        if isinstance(receipt, dict) and isinstance(receipt.get("command_id"), str)
    }
    result_map = bundle.get("results", {})
    if not isinstance(result_map, dict):
        result_map = {}

    gates: dict[str, bool] = {}
    for name, spec in required_commands.items():
        command_id = _command_id(name)
        receipt = receipts.get(command_id)
        expected = spec.get("expected_exit_codes", [0])
        command_result = result_map.get(name)
        passed = (
            isinstance(receipt, dict)
            and receipt.get("result") == "SUCCESS"
            and receipt.get("exit_code") in expected
            and isinstance(command_result, dict)
            and command_result.get("success") is True
            and command_result.get("exit_code") in expected
        )
        gates[name] = passed
        if not passed:
            errors.append(f"required command did not pass: {name}")

    if protocol_errors or protocol_warnings:
        derived_verdict = "FAIL"
    elif not bundle.get("worktree_clean", False):
        derived_verdict = "BLOCKED"
        errors.append("worktree is not clean; PASS evidence cannot be finalized")
    elif not all(gates.values()) or bundle.get("failures"):
        derived_verdict = "FAIL"
    else:
        derived_verdict = "PASS"

    bundle_verdict = bundle.get("verdict")
    if bundle_verdict != derived_verdict:
        errors.append(
            f"bundle verdict {bundle_verdict!r} does not match derived "
            f"verdict {derived_verdict!r}"
        )

    return {
        "status": "PASS" if derived_verdict == "PASS" and not errors else "FAIL",
        "verdict": derived_verdict,
        "bundle_verdict": bundle_verdict,
        "worktree_clean": bool(bundle.get("worktree_clean", False)),
        "gates": gates,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate evidence and derive its verdict"
    )
    parser.add_argument("bundle", help="Path to evidence_bundle.json")
    parser.add_argument(
        "--commands-file",
        default=str(Path(__file__).with_name("command_registry.yaml")),
        help="Canonical command registry",
    )
    parser.add_argument("--output", "-o", help="Optional JSON result path")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    args = parser.parse_args()

    bundle_path = Path(args.bundle).resolve()
    registry_path = Path(args.commands_file).resolve()
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        required_commands = load_required_commands(registry_path)
        protocol_errors, protocol_warnings = validate_evidence_bundle(bundle_path)
        result = derive_verdict(
            bundle,
            required_commands,
            protocol_errors,
            protocol_warnings,
        )
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    if args.json:
        print(rendered, end="")
    else:
        print(
            f"Final evidence verdict: {result['verdict']} "
            f"({sum(result['gates'].values())}/{len(result['gates'])} gates)"
        )
        for error in result["errors"]:
            print(f"ERROR: {error}")
        for warning in result["warnings"]:
            print(f"WARNING: {warning}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
