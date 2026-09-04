#!/usr/bin/env python3
"""Validate the constrained YAML manifests that define the Phase 0 freeze.

The V2 repository deliberately has no dependency manager before Phase 1, so
this gate uses only the Python standard library.  It validates the manifest
shape used here; a full YAML parser may replace it once the repository
foundation exists.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "migration" / "manifests"
MATRIX_NAME = "migration_matrix.yaml"
INVENTORY_NAMES = (
    "backend_inventory.yaml",
    "frontend_inventory.yaml",
    "api_inventory.yaml",
    "database_inventory.yaml",
    "event_inventory.yaml",
)
ALL_NAMES = (*INVENTORY_NAMES, MATRIX_NAME)
REQUIRED_FIELDS = (
    "id",
    "capability",
    "source",
    "target",
    "owner",
    "action",
    "dependencies",
    "test_oracle",
    "status",
)
ALLOWED_ACTIONS = {"REWRITE", "EXTRACT_LOGIC", "KEEP_ASSET", "ADAPT", "DELETE"}


def parse_records(path: Path) -> list[dict[str, str]]:
    """Extract top-level capability records from the deliberately simple YAML."""
    records: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    field = re.compile(r"^    ([a-z_]+):(?:\s*(.*))?$")

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("  - id:"):
            if current is not None:
                records.append(current)
            current = {"id": line.split(":", 1)[1].strip(), "_line": str(line_number)}
            continue
        if current is None:
            continue
        match = field.match(line)
        if match:
            # A nested YAML value (for example ``source:`` followed by a
            # sequence) is deliberately represented by a non-empty sentinel.
            # The gate needs to enforce field presence without depending on a
            # YAML package before Phase 1 establishes dependencies.
            current[match.group(1)] = (match.group(2) or "<nested>").strip()
    if current is not None:
        records.append(current)
    return records


def validate_inventory(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    if "schema_version: 1" not in text:
        errors.append(f"{path.name}: schema_version must be 1")
    if "commit: 01695ca48dddb7220efd60c212e52dac1d6a5f2d" not in text:
        errors.append(f"{path.name}: source baseline commit is missing or changed")

    records = parse_records(path)
    if not records:
        errors.append(f"{path.name}: no capability records found")
        return records, errors

    ids: set[str] = set()
    for record in records:
        label = f"{path.name}:{record.get('id', '<missing>')} (line {record.get('_line', '?')})"
        missing = [field for field in REQUIRED_FIELDS if not record.get(field)]
        if missing:
            errors.append(f"{label}: missing {', '.join(missing)}")
        if record.get("id") in ids:
            errors.append(f"{label}: duplicate capability id")
        ids.add(record.get("id", ""))
        if record.get("action") not in ALLOWED_ACTIONS:
            errors.append(f"{label}: invalid action {record.get('action')!r}")
        if record.get("status") != "FROZEN":
            errors.append(f"{label}: Phase 0 status must be FROZEN")
        target = record.get("target", "")
        if "../" in target or "\\..\\" in target or "WindAgent/" in target:
            errors.append(f"{label}: target must not point into the legacy repository")
    return records, errors


def main() -> int:
    errors: list[str] = []
    missing_files = [name for name in ALL_NAMES if not (MANIFEST_DIR / name).is_file()]
    if missing_files:
        print("FAIL: missing manifest(s): " + ", ".join(missing_files))
        return 1

    inventory_ids: set[str] = set()
    for name in INVENTORY_NAMES:
        records, manifest_errors = validate_inventory(MANIFEST_DIR / name)
        errors.extend(manifest_errors)
        for record in records:
            capability_id = record.get("id", "")
            if capability_id in inventory_ids:
                errors.append(f"{name}:{capability_id}: capability belongs to more than one specialist inventory")
            inventory_ids.add(capability_id)

    matrix_records, matrix_errors = validate_inventory(MANIFEST_DIR / MATRIX_NAME)
    errors.extend(matrix_errors)
    matrix_ids = {record.get("id", "") for record in matrix_records}
    if inventory_ids != matrix_ids:
        missing_from_matrix = sorted(inventory_ids - matrix_ids)
        missing_from_inventory = sorted(matrix_ids - inventory_ids)
        if missing_from_matrix:
            errors.append("matrix missing IDs: " + ", ".join(missing_from_matrix))
        if missing_from_inventory:
            errors.append("matrix has unowned IDs: " + ", ".join(missing_from_inventory))

    if errors:
        print("PHASE 0 MANIFEST GATE: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PHASE 0 MANIFEST GATE: PASS")
    print(f"- {len(inventory_ids)} capabilities frozen at source revision 01695ca48dddb7220efd60c212e52dac1d6a5f2d")
    print(f"- inventories: {', '.join(INVENTORY_NAMES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
