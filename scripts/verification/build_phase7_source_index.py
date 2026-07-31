#!/usr/bin/env python3
"""Construct the canonical Phase 7 source-evidence index from explicit inputs.

This helper deliberately has no directory discovery or fallback behaviour.
The CI job supplies every source artifact and its GitHub provenance metadata;
the helper hashes the exact bytes referenced by those records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

try:
    from .finalize_phase7 import (
        REQUIRED_SOURCE_GATES,
        SOURCE_INDEX_SCHEMA,
        Phase7ValidationError,
        _validate_schema,
        load_json,
        resolve_evidence_path,
    )
except ImportError:  # Direct execution from scripts/verification.
    from finalize_phase7 import (
        REQUIRED_SOURCE_GATES,
        SOURCE_INDEX_SCHEMA,
        Phase7ValidationError,
        _validate_schema,
        load_json,
        resolve_evidence_path,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema() -> Draft7Validator:
    return Draft7Validator(load_json(SOURCE_INDEX_SCHEMA, label="source-index schema"))


def _load_metadata(path: Path) -> dict[str, dict[str, Any]]:
    data = load_json(path, label="source provenance metadata")
    entries = data.get("sources")
    if not isinstance(entries, list):
        raise Phase7ValidationError("source provenance metadata: sources must be an array")
    by_path: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise Phase7ValidationError("source provenance metadata: every source needs path")
        path = entry["path"].replace("\\", "/")
        if path in by_path:
            raise Phase7ValidationError(f"source provenance metadata: duplicate path {path}")
        by_path[path] = entry
    return by_path


def _parse_source(value: str) -> tuple[str, str, str]:
    try:
        gate, kind, raw_path = value.split(":", 2)
    except ValueError as exc:
        raise Phase7ValidationError(
            "--source must use gate:kind:relative/path"
        ) from exc
    if gate not in REQUIRED_SOURCE_GATES:
        raise Phase7ValidationError(f"--source uses unknown gate {gate}")
    if kind not in {"receipt", "report", "pytest_xml", "skip_inventory"}:
        raise Phase7ValidationError(f"--source uses invalid kind {kind}")
    if not raw_path:
        raise Phase7ValidationError("--source path is required")
    return gate, kind, raw_path.replace("\\", "/")


def build_index(
    *,
    implementation_sha: str,
    tooling_sha: str,
    implementation_ci: dict[str, Any],
    tooling_ci: dict[str, Any],
    evidence_root: Path,
    provenance: dict[str, dict[str, Any]],
    sources: list[tuple[str, str, str]],
    branch_protection_for: str,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {gate: [] for gate in REQUIRED_SOURCE_GATES}
    for gate, kind, raw_path in sources:
        if raw_path not in provenance:
            raise Phase7ValidationError(
                f"source {raw_path}: provenance metadata is missing"
            )
        artifact = resolve_evidence_path(evidence_root, raw_path, label=f"source {gate}")
        if not artifact.is_file():
            raise Phase7ValidationError(f"source {raw_path}: evidence file is missing")
        entry = dict(provenance[raw_path])
        entry["path"] = raw_path
        entry["kind"] = kind
        entry["sha256"] = _sha256(artifact)
        grouped[gate].append(entry)
    missing = [gate for gate, entries in grouped.items() if not entries]
    if missing:
        raise Phase7ValidationError(f"source index has no source for gate(s): {', '.join(missing)}")
    result = {
        "implementation_verified_sha": implementation_sha,
        "verification_tooling_verified_sha": tooling_sha,
        "implementation_ci": implementation_ci,
        "tooling_ci": tooling_ci,
        "branch_protection_for": branch_protection_for,
        "sources": grouped,
    }
    _validate_schema(result, _schema(), label="source evidence index")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the immutable Phase 7 source-evidence index")
    parser.add_argument("--implementation-verified-sha", required=True)
    parser.add_argument("--verification-tooling-sha", required=True)
    parser.add_argument("--implementation-ci", type=Path, required=True)
    parser.add_argument("--tooling-ci", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--source", action="append", default=[], required=True)
    parser.add_argument("--branch-protection-for", choices=("implementation", "tooling"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        index = build_index(
            implementation_sha=args.implementation_verified_sha,
            tooling_sha=args.verification_tooling_sha,
            implementation_ci=load_json(args.implementation_ci, label="implementation CI"),
            tooling_ci=load_json(args.tooling_ci, label="tooling CI"),
            evidence_root=args.evidence_root.resolve(),
            provenance=_load_metadata(args.provenance),
            sources=[_parse_source(value) for value in args.source],
            branch_protection_for=args.branch_protection_for,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    except Phase7ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
