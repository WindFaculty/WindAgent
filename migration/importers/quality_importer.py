"""Importer for legacy evaluation datasets into V2 Quality bounded context."""

from __future__ import annotations

from typing import Any


class QualityImporter:
    """Imports legacy eval suites into V2 Quality datasets & test cases."""

    def __init__(self) -> None:
        self.imported_datasets: list[dict[str, Any]] = []
        self.imported_test_cases: list[dict[str, Any]] = []

    def import_legacy_dataset(self, legacy_ds: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        """Convert legacy eval dataset into V2 QualityDataset aggregate."""
        v2_ds = {
            "id": legacy_ds.get("id") or f"ds-{legacy_ds['name'].lower().replace(' ', '-')}",
            "name": legacy_ds["name"],
            "dimension": legacy_ds.get("category", legacy_ds.get("dimension", "General Quality")),
            "description": legacy_ds.get("description", ""),
            "test_cases_count": len(legacy_ds.get("cases", [])),
        }

        if not dry_run:
            self.imported_datasets.append(v2_ds)

        return v2_ds

    def import_legacy_cases(self, dataset_id: str, legacy_cases: list[dict[str, Any]], *, dry_run: bool = False) -> list[dict[str, Any]]:
        """Convert test cases with rubric types."""
        cases = []
        for c in legacy_cases:
            case = {
                "id": c.get("id") or f"tc-{c['name'].lower().replace(' ', '-')}",
                "dataset_id": dataset_id,
                "name": c["name"],
                "input_prompt": c["prompt"],
                "rubric_type": c.get("rubric", "exact_match"),
                "expected_output": c.get("expected", ""),
            }
            cases.append(case)
            if not dry_run:
                self.imported_test_cases.append(case)

        return cases
