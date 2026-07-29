from __future__ import annotations

import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).parents[3]
INVENTORY_PATH = ROOT / "tests" / "fixtures" / "verification" / "phase6_skip_inventory.json"
EXPECTED_SKIP_IDS = {
    "tests.architecture.test_phase3_negative.TestSymlink.test_symlinked_package",
    "tests.unit.tools.test_tool_platform.test_path_sandbox_symlink_escape_prevention",
    "tests.architecture.test_phase3_negative.TestWindowsDrive.test_different_drive_repo_root",
}


def _load_inventory() -> list[dict[str, object]]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    assert payload["inventory_version"] == "1.0.0"
    skips = payload["skips"]
    assert isinstance(skips, list)
    return skips


def test_phase6_skip_inventory_is_complete_and_non_mandatory():
    skips = _load_inventory()
    required_fields = {
        "test_id",
        "reason",
        "owner",
        "expiry_date",
        "mandatory_gate",
        "tracking_issue",
    }

    assert {entry["test_id"] for entry in skips} == EXPECTED_SKIP_IDS
    for entry in skips:
        assert required_fields <= entry.keys()
        assert entry["mandatory_gate"] is False
        assert isinstance(entry["reason"], str) and entry["reason"]
        assert isinstance(entry["owner"], str) and entry["owner"]
        assert date.fromisoformat(str(entry["expiry_date"])) >= date.today()
        assert str(entry["tracking_issue"]).startswith(
            "https://github.com/WindFaculty/WindAgent/issues/"
        )


def test_phase7_composition_imports_cannot_be_skipped():
    source = (ROOT / "tests" / "unit" / "test_phase7_composition.py").read_text(
        encoding="utf-8"
    )
    assert "pytest.skip" not in source
