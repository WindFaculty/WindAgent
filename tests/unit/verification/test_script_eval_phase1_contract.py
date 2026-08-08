"""Script Eval Phase 1 — production-script contract, fail-closed matrix.

Each check from test_kich_ban.md section 4 gets an injected fault and must be
detected; valid script must pass clean. Gate SCRIPT_EVAL_CONTRACT_VALID.
"""

from __future__ import annotations

import pytest

from windagent_evals.script_eval import (
    SCRIPT_SCHEMA_VERSION,
    validate_script,
)
from windagent_evals.script_eval.fixtures import (
    FAULT_INJECTIONS,
    broken_production_script,
    mutate,
    valid_production_script,
)


@pytest.mark.parametrize("check", sorted(FAULT_INJECTIONS))
def test_fault_detected(check: str) -> None:
    injection = FAULT_INJECTIONS[check]
    report = validate_script(mutate(injection["mutator"]))
    matches = [f for f in report.findings if f.check == check]
    assert matches, f"check {check} not fired"
    assert all(f.severity == injection["severity"] for f in matches)
    if injection["severity"] == "ERROR":
        assert not report.valid, f"gate must fail on {check}"


def test_scene_id_without_numeric_suffix_detected() -> None:
    report = validate_script(mutate(lambda d: d["scenes"][1].__setitem__(
        "scene_id", "NO_SUFFIX")))
    assert any(f.check == "scene_ordering" for f in report.findings)
    assert not report.valid


def test_valid_script_passes_clean() -> None:
    report = validate_script(valid_production_script())
    assert report.valid
    assert report.findings == ()
    assert report.scene_count == 3
    assert report.character_count == 2
    assert report.target_seconds == 300.0
    assert report.estimated_seconds == 300.0
    assert report.duration_delta_pct == 0.0


def test_non_dict_fails_closed() -> None:
    for bad in (None, [], "script", 42, {"project": {}}):
        report = validate_script(bad)
        assert not report.valid
        assert report.errors, f"no errors for {type(bad).__name__}"


def test_warning_only_doc_still_valid() -> None:
    """Wordless episodes (T12) and duration drift must not fail the gate."""
    doc = valid_production_script()
    doc["scenes"][1]["dialogue"] = ""
    doc["scenes"][2]["estimated_duration_seconds"] = 400
    report = validate_script(doc)
    assert report.valid
    assert report.warnings


def test_dangling_reference_is_hard_fail() -> None:
    doc = valid_production_script()
    doc["scenes"][1]["location"] = "nowhere"
    report = validate_script(doc)
    assert not report.reference_integrity
    assert not report.valid


def test_broken_fixture_hits_all_checks() -> None:
    """The evidence fixture must trip every contract check at least once."""
    report = validate_script(broken_production_script())
    assert not report.valid
    assert {f.check for f in report.findings} >= set(FAULT_INJECTIONS)


def test_schema_version_pinned() -> None:
    assert SCRIPT_SCHEMA_VERSION == "1.0.0"
