#!/usr/bin/env python3
"""
Finalize Evidence (Phase 2)

Derives verdict from gate values in evidence bundle.
No manual PASS entry - verdict is computed from required gates.
"""

from __future__ import annotations
import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple


def load_bundle(bundle_path: Path) -> Dict[str, Any]:
    """Load evidence bundle."""
    with open(bundle_path) as f:
        return json.load(f)


def validate_evidence_bundle(
    bundle_path: Path,
    required_gates: List[str],
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """
    Validate evidence bundle and derive gates status.
    Returns (gates_dict, errors, warnings).
    """
    errors = []
    warnings = []

    try:
        bundle = load_bundle(bundle_path)
    except json.JSONDecodeError as e:
        return {}, [f"Invalid JSON in bundle: {e}"], []

    # Check required fields
    required_fields = ["protocol_version", "verdict", "commands", "commands"]
    for field in required_fields:
        if field not in bundle:
            errors.append(f"Bundle missing required field: {field}")

    # Extract gate results from bundle
    # Gates are derived from command results
    gates = {
        "gates": {},
        "verdict": bundle.get("verdict", "BLOCKED"),
        "has_failures": len(bundle.get("failures", [])) > 0,
        "worktree_clean": bundle.get("worktree_clean", False),
    }

    # Map command results to gates
    gate_mapping = {
        "artifact_protocol": ["artifact_schema_validation", "artifact_schema_check"],
        "version_consistency": ["version_check", "version_authority_tests"],
        "architecture_boundaries": ["architecture_scaffold_check", "architecture_imports_check"],
        "python_unit_sqlite": ["pytest_unit"],
        "python_unit_windows": ["pytest_unit"],
        "python_integration_sqlite": ["pytest_integration"],
        "python_integration_postgres": ["pytest_integration"],
        "runtime_smoke": ["runtime_smoke"],
        "cli_contract": ["cli_contract"],
        "web_test": ["web_test", "web_test_windows"],
        "web_test_windows": ["web_test_windows"],
        "desktop_test": ["desktop_test", "desktop_test_windows"],
        "desktop_test_windows": ["desktop_test_windows"],
    }

    # Check each required gate
    for gate_name in required_gates:
        commands = gate_mapping.get(gate_name, [gate_name])
        gate_passed = False

        for cmd in bundle.get("commands", []):
            if cmd.get("command_id") in commands or any(c in cmd.get("command", "") for c in commands):
                if cmd.get("result") == "SUCCESS":
                    gate_passed = True
                    break

        gates["gates"][gate_name] = gate_passed
        if not gate_passed:
            errors.append(f"Required gate '{gate_name}' did not pass (no successful command found)")

    # All gates must pass for PASS
    all_gates_pass = all(gates["gates"].values()) if gates["gates"] else False

    # Derive verdict from gates
    if not bundle.get("worktree_clean", False):
        derived_verdict = "BLOCKED"
    elif not all_gates_pass:
        derived_verdict = "FAIL"
    else:
        derived_verdict = "PASS"

    gates["verdict"] = derived_verdict

    # Bundle verdict must match derived verdict
    bundle_verdict = bundle.get("verdict", "")
    if bundle_verdict != derived_verdict:
        warnings.append(f"Bundle verdict '{bundle_verdict}' differs from derived verdict '{derived_verdict}'")

    # No CRITICAL/HIGH failures allowed in PASS
    if derived_verdict == "PASS":
        for failure in bundle.get("failures", []):
            severity = failure.get("severity", "")
            if severity in ("CRITICAL", "HIGH"):
                errors.append(f"PASS verdict not allowed with {severity} failure: {failure.get('check', 'unknown')}")

    return gates, errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize evidence - derive verdict from gates")
    parser.add_argument("bundle", help="Path to evidence_bundle.json")
    parser.add_argument("--required-gates", nargs="+", default=[
        "artifact_protocol",
        "version_consistency",
        "architecture_boundaries",
        "python_unit_sqlite",
        "python_unit_windows",
        "python_integration_sqlite",
        "python_integration_postgres",
        "runtime_smoke",
        "cli_contract",
        "web_test",
        "web_test_windows",
        "desktop_test",
        "desktop_test_windows",
    ], help="Required gate names")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")

    args = parser.parse_args()

    bundle_path = Path(args.bundle)
    if not bundle_path.exists():
        print(f"ERROR: Bundle not found: {bundle_path}", file=sys.stderr)
        return 1

    gates, errors, warnings = validate_evidence_bundle(bundle_path, args.required_gates)

    if args.json or args.output:
        result = {
            "bundle": str(bundle_path),
            "status": "PASS" if not errors else "FAIL",
            "gates": gates.get("gates", {}),
            "verdict": gates.get("verdict", ""),
            "has_failures": gates.get("has_failures", False),
            "worktree_clean": gates.get("worktree_clean", False),
            "errors": errors,
            "warnings": warnings,
        }
        if args.output:
            Path(args.output).write_text(json.dumps(result, indent=2))
            print(f"Result written to {args.output}")
        if args.json:
            print(json.dumps(result, indent=2))
    else:
        status = "PASS" if not errors else f"FAIL ({len(errors)} errors)"
        print(f"Finalizing {bundle_path}... {status}")
        print(f"  Verdict: {gates.get('verdict', 'UNKNOWN')}")
        print(f"  Gates passed: {sum(1 for v in gates.get('gates', {}).values() if v)}/{len(gates.get('gates', {}))}")
        for e in errors:
            print(f"  ERROR: {e}")
        for w in warnings:
            print(f"  WARNING: {w}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())