#!/usr/bin/env python3
"""Unit tests for the Phase 5 characterization verifier (plan 02 §13).

Covers:
- canonicalization strips only unstable fields (timestamps, random ids, paths)
  and preserves order/errors/relationships;
- capability coverage requires happy + failure paths for every retained CAP;
- defect inventory requires an explicit decision for every defect;
- nondeterminism inventory requires cause + accepted boundary;
- the verifier runs end-to-end and derives a real verdict.
"""

import json
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(ROOT))

from scripts.verification import verify_phase5_characterization as v  # noqa: E402


def test_canonicalize_strips_timestamps_and_random_ids():
    raw = {
        "created_at": "2026-07-31T12:00:00.000000+00:00",
        "session_id": "abc123",
        "character_id": "char_9f3a1b",
        "units": [{"unit_id": "U001", "text": "台词"}],
        "error": "some warning",
    }
    canon = v.canonicalize(raw)
    assert "created_at" not in canon
    assert "session_id" not in canon
    assert canon["character_id"] == "char_<RANDOM>"
    assert canon["units"][0]["unit_id"] == "U001"  # stable relationship kept
    assert canon["error"] == "some warning"  # errors never stripped


def test_canonicalize_keeps_content_and_order():
    raw = {"episodes": [{"episode_number": 1, "content": "第1集"}, {"episode_number": 2}]}
    canon = v.canonicalize(raw)
    assert [e["episode_number"] for e in canon["episodes"]] == [1, 2]
    assert canon["episodes"][0]["content"] == "第1集"


def test_capability_coverage_requires_happy_and_failure():
    matrix = {
        "cases": [
            {"capability": "CAP-001", "failure_class": "HAPPY"},
            {"capability": "CAP-001", "failure_class": "FAILURE_MISSING_MODEL"},
        ]
    }
    coverage = v.check_capability_coverage(matrix)
    assert coverage["coverage"]["CAP-001"]["happy"] == 1
    assert coverage["coverage"]["CAP-001"]["failure"] == 1
    assert coverage["coverage"]["CAP-001"]["covered"] is True


def test_capability_coverage_fails_when_failure_missing():
    matrix = {
        "cases": [
            {"capability": "CAP-001", "failure_class": "HAPPY"},
        ]
    }
    coverage = v.check_capability_coverage(matrix)
    assert coverage["all_covered"] is False
    assert coverage["coverage"]["CAP-001"]["covered"] is False


def test_defect_inventory_requires_decisions():
    defects = v.build_defect_inventory({}, {})
    assert defects["defect_count"] >= 1
    assert defects["all_decided"] is True
    for d in defects["defects"]:
        assert d["decision"], f"{d['defect_id']} missing decision"


def test_nondeterminism_inventory_explained():
    golden = {"stable_after_canonicalization": True}
    inventory = v.build_nondeterminism_inventory(golden)
    assert inventory["all_explained"] is True
    for entry in inventory["entries"]:
        assert entry["cause"]
        assert entry["accepted_boundary"]


def test_verifier_runs_and_derives_verdict():
    """End-to-end: --no-write must exit 0 with a PASSED verdict and write nothing."""
    git_before = _git_porcelain(ROOT)
    proc = subprocess.run(
        [sys.executable, "scripts/verification/verify_phase5_characterization.py", "--no-write"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Phase 5 verdict: PASSED" in proc.stdout
    # No evidence files written in --no-write mode.
    phase_dir = ROOT / "artifacts" / "video_production" / "phase_05"
    if phase_dir.is_dir():
        verdict = json.loads((phase_dir / "phase_verdict.json").read_text(encoding="utf-8"))
        assert verdict["status"] == "PASSED"
        assert verdict["gate"] == "VP5_VIDEOCLAW_BEHAVIOR_CHARACTERIZED"
    assert _git_porcelain(ROOT) == git_before, "verifier mutated the working tree"


def _git_porcelain(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(root),
        check=True,
    )
    return sorted(line for line in result.stdout.splitlines() if line.strip())


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
