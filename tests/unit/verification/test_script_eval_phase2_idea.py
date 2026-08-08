"""Script Eval Phase 2 — idea generation benchmark, fail-closed matrix.

Each Phase 2 check (test_kich_ban.md section 5) gets an injected fault and
must be detected; the valid idea must pass clean against its sibling; the
benchmark must expand to 12 briefs x 3 durations = 36 runs.
Gate SCRIPT_EVAL_IDEA_VALID.
"""

from __future__ import annotations

import pytest

from windagent_evals.script_eval import (
    BENCHMARK_BRIEFS,
    DURATIONS_MINUTES,
    IDEA_SCHEMA_VERSION,
    benchmark_runs,
    validate_idea,
)
from windagent_evals.script_eval.fixtures import (
    IDEA_FAULT_INJECTIONS,
    SIBLING_DIFFERENTIATION,
    broken_idea,
    sibling_idea,
    valid_idea,
)


@pytest.mark.parametrize("check", sorted(IDEA_FAULT_INJECTIONS))
def test_idea_fault_detected(check: str) -> None:
    injection = IDEA_FAULT_INJECTIONS[check]
    doc = valid_idea()
    injection["mutator"](doc)
    report = validate_idea(doc, siblings=[sibling_idea()])
    matches = [f for f in report.findings if f.check == check]
    assert matches, f"check {check} not fired"
    assert all(f.severity == injection["severity"] for f in matches)
    if injection["severity"] == "ERROR":
        assert not report.valid, f"gate must fail on {check}"


def test_valid_idea_passes_clean() -> None:
    report = validate_idea(valid_idea(), siblings=[sibling_idea()])
    assert report.valid
    assert report.findings == ()
    assert report.case_id == "T01"
    assert report.duration_minutes == 5.0


def test_non_dict_fails_closed() -> None:
    for bad in (None, [], "idea", 42, {"case_id": "T01"}):
        report = validate_idea(bad)
        assert not report.valid
        assert report.errors, f"no errors for {type(bad).__name__}"


def test_warning_only_idea_still_valid() -> None:
    """Preachy lesson and thin visual language flag but never fail the gate."""
    doc = valid_idea()
    doc["lesson"] = "Con phai luon luon nghe loi nguoi lon."
    doc["visual_potential"] = "ngan"
    report = validate_idea(doc, siblings=[sibling_idea()])
    assert report.valid
    assert report.warnings


def test_duplicate_premise_fails_differentiation() -> None:
    doc = valid_idea()
    doc["premise"] = sibling_idea()["premise"]
    report = validate_idea(doc, siblings=[sibling_idea()])
    assert not report.differentiation_valid
    assert any(f.check == "duplicate_idea" for f in report.findings)


def test_same_differentiation_fails_differentiation() -> None:
    doc = valid_idea()
    doc["differentiation"] = SIBLING_DIFFERENTIATION
    report = validate_idea(doc, siblings=[sibling_idea()])
    assert not report.valid
    assert any(f.check == "duplicate_idea" for f in report.findings)


def test_broken_fixture_hits_all_checks() -> None:
    """The evidence fixture must trip every idea check at least once."""
    report = validate_idea(broken_idea(), siblings=[sibling_idea()])
    assert not report.valid
    assert {f.check for f in report.findings} >= set(IDEA_FAULT_INJECTIONS)


def test_benchmark_expands_to_36_runs() -> None:
    runs = benchmark_runs()
    assert len(runs) == 36
    assert len(BENCHMARK_BRIEFS) == 12
    assert set(DURATIONS_MINUTES) == {5, 10, 20}
    assert len({r["run_id"] for r in runs}) == 36
    # every brief x every duration present
    pairs = {(r["case_id"], r["duration_minutes"]) for r in runs}
    assert pairs == {(b["case_id"], m)
                     for b in BENCHMARK_BRIEFS for m in DURATIONS_MINUTES}
    assert runs[0]["run_id"] == "T01_005m"
    assert runs[-1]["run_id"] == "T12_020m"


def test_idea_schema_version_pinned() -> None:
    assert IDEA_SCHEMA_VERSION == "1.0.0"
