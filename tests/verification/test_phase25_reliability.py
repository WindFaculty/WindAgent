"""
Phase 25 reliability regression tests (plan 07 Â§11, gate
VP25_RECOVERY_AND_CHAOS_VERIFIED).

Covers:
- verifier CLI contract: read-only default, --write-fixture temp-only,
  unknown flag rejection, no evidence-dir mutation;
- scenario-level mock tests: each mandatory chaos scenario runs against real
  orchestration machinery and observes the expected outcome;
- negative evidence fails closed (missing scenario, duplicate audit nonzero,
  fake observed expectations);
- chaos_scenario_manifest completeness (all 15 mandatory scenarios).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verification" / "verify_phase25_reliability.py"
FIXTURE = ROOT / "scripts" / "verification" / "fixture_phase25_reliability.py"

CANDIDATE_SHA = "1753831c752343aa89419e807aa57058266ff75c"


def _snapshot_dir(root: Path) -> dict[str, tuple[str, int]]:
    snap: dict[str, tuple[str, int]] = {}
    if not root.exists():
        return snap
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            st = path.stat()
            snap[rel] = (
                __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
                st.st_mtime_ns,
            )
    return snap


def _run(script: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *flags],
        capture_output=True, text=True, timeout=900, cwd=str(ROOT),
    )


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Mandatory scenario matrix (plan Â§8) â€” every scenario must be present
# ---------------------------------------------------------------------------

def test_manifest_covers_all_15_mandatory_scenarios():
    from scripts.verification import chaos_phase25

    assert len(chaos_phase25.REQUIRED_SCENARIO_IDS) == 15
    assert len(chaos_phase25.MANDATORY_SCENARIOS) == 15
    assert len(set(chaos_phase25.REQUIRED_SCENARIO_IDS)) == 15


@pytest.mark.parametrize("scenario_id", [
    "CH01_WORKER_KILL_GENERATING",
    "CH02_BROWSER_KILL_AFTER_SUBMIT",
    "CH03_NETWORK_LOSS",
    "CH04_SESSION_EXPIRY",
    "CH05_SELECTOR_DRIFT",
    "CH06_DOWNLOAD_ZERO_BYTE",
    "CH07_NO_VIDEO_STREAM",
    "CH08_INSUFFICIENT_CREDITS",
    "CH09_CAPTCHA",
    "CH10_USER_CANCEL",
    "CH11_DATABASE_RESTART",
    "CH12_DUPLICATE_EVENT",
    "CH13_LEASE_EXPIRY",
    "CH14_STALE_WORKER_WRITE",
    "CH15_ENGINE_PROJECT_DELETED",
])
def test_each_scenario_has_expected_behavior(scenario_id: str):
    from scripts.verification import chaos_phase25

    spec = next(s for s in chaos_phase25.MANDATORY_SCENARIOS if s["scenario_id"] == scenario_id)
    assert spec["expected_behavior"], "each scenario must declare expected behavior"
    assert spec["tier"] in ("MOCK_LEVEL", "INTEGRATION_LEVEL")
    assert scenario_id in chaos_phase25.SCENARIO_RUNNERS


# ---------------------------------------------------------------------------
# Scenario-level mock tests (real machinery, isolated workdirs)
# ---------------------------------------------------------------------------

def test_ch01_worker_kill_no_resubmit(tmp_path: Path):
    from scripts.verification import chaos_phase25

    receipt = chaos_phase25.run_ch01_worker_kill_generating(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["no_resubmit"] is True
    assert receipt["duplicates_prevented"]["submit"] == 0


def test_ch03_network_loss_bounded_retry(tmp_path: Path):
    from scripts.verification import chaos_phase25

    receipt = chaos_phase25.run_ch03_network_loss(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["bounded_retry_within_budget"] is True
    assert receipt["observed"]["budget_exhausted_terminal"] is True


def test_ch04_session_expiry_human_resume(tmp_path: Path):
    from scripts.verification import chaos_phase25

    receipt = chaos_phase25.run_ch04_session_expiry(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["human_login_required"] is True
    assert receipt["observed"]["safe_resume_no_duplicate"] is True


def test_ch08_insufficient_credits_circuit(tmp_path: Path):
    from scripts.verification import chaos_phase25

    receipt = chaos_phase25.run_ch08_insufficient_credits(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["budget_blocks_submit"] is True
    assert receipt["observed"]["circuit_open"] is True
    assert receipt["observed"]["ledger_no_double_debit"] is True


def test_ch09_captcha_zero_bypass(tmp_path: Path):
    from scripts.verification import chaos_phase25

    receipt = chaos_phase25.run_ch09_captcha(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["zero_bypass"] is True


def test_ch11_database_restart_atomic_replay(tmp_path: Path):
    from scripts.verification import chaos_phase25

    receipt = chaos_phase25.run_ch11_database_restart(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["atomic_no_tmp_residue"] is True
    assert receipt["observed"]["replay_idempotent_no_republish"] is True


def test_ch14_stale_write_cas_rejected(tmp_path: Path):
    from scripts.verification import chaos_phase25

    receipt = chaos_phase25.run_ch14_stale_worker_write(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["version_cas_rejects_stale"] is True


def test_soak_clean(tmp_path: Path):
    from scripts.verification import chaos_phase25

    report = chaos_phase25.run_soak(tmp_path, CANDIDATE_SHA, iterations=5)
    assert report["all_runs_terminal"] is True
    assert report["duplicate_events_total"] == 0
    assert report["leaks_total"] == 0
    assert report["flaky_races"] == 0


# ---------------------------------------------------------------------------
# Verifier CLI contract (R0)
# ---------------------------------------------------------------------------

def test_write_fixture_refuses_production_artifacts():
    result = _run(
        VERIFY, "--write-fixture",
        str(ROOT / "artifacts" / "video_production" / "phase_25"),
    )
    assert result.returncode == 2
    assert "refuses production artifacts" in result.stderr


def test_write_fixture_writes_only_to_temp_dir(tmp_path: Path):
    out = tmp_path / "fixtures"
    result = _run(VERIFY, "--write-fixture", str(out))
    assert result.returncode == 0
    assert (out / "contract_verdict.json").is_file()
    prod = ROOT / "artifacts" / "video_production" / "phase_25"
    assert not (prod / "contract_verdict.json").exists()


def test_unknown_flag_rejected():
    result = _run(VERIFY, "--bogus-flag")
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_missing_evidence_dir_blocks():
    result = _run(
        VERIFY, "--evidence-dir", str(ROOT / "does_not_exist_phase25"),
        "--candidate-sha", CANDIDATE_SHA,
    )
    assert result.returncode != 0
    assert "BLOCKED" in result.stdout


# ---------------------------------------------------------------------------
# Negative evidence fails closed
# ---------------------------------------------------------------------------

def _minimal_evidence(tmp_path: Path, sha: str) -> None:
    """A full-but-empty valid-shaped evidence dir (all receipts present)."""
    from scripts.verification import evidence_lib

    for name in ("duplicate_side_effect_audit.json",
                 "recovery_timing_report.json",
                 "soak_test_report.json",
                 "open_reliability_findings.json",
                 "phase_verdict.json"):
        _write_json(tmp_path / name, {
            "schema_version": "1.0.0", "candidate_sha": sha,
            "run_id": "neg", "started_at": "2026-08-02T00:00:00Z",
            "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "mock",
            "input_hashes": ["a" * 64], "output_hashes": ["b" * 64],
            "evidence_locator": name, "status": "PASSED",
        })
    _write_json(tmp_path / "chaos_scenario_manifest.json", {
        "schema_version": "1.0.0", "candidate_sha": sha,
        "gate": "VP25_RECOVERY_AND_CHAOS_VERIFIED", "scenario_count": 0,
        "scenarios": [],
    })
    _write_json(tmp_path / "evidence_manifest.json",
                evidence_lib.build_evidence_manifest(tmp_path, sha))


def test_missing_scenario_manifest_fails_closed(tmp_path: Path):
    """chaos_scenario_manifest missing scenarios -> BLOCKED/FAILED."""
    sha = CANDIDATE_SHA
    _minimal_evidence(tmp_path, sha)
    result = _run(VERIFY, "--evidence-dir", str(tmp_path), "--candidate-sha", sha)
    assert result.returncode != 0
    assert "missing mandatory scenarios" in result.stdout


def test_duplicate_audit_nonzero_fails_closed(tmp_path: Path):
    """duplicate_side_effect_audit with observed duplicates -> FAILED."""
    sha = CANDIDATE_SHA
    _minimal_evidence(tmp_path, sha)
    _write_json(tmp_path / "duplicate_side_effect_audit.json", {
        "schema_version": "1.0.0", "candidate_sha": sha,
        "total_duplicate_submits": 2, "total_duplicate_debits": 0,
        "total_duplicate_publishes": 0,
    })
    result = _run(VERIFY, "--evidence-dir", str(tmp_path), "--candidate-sha", sha)
    assert result.returncode != 0
    assert "total_duplicate_submits" in result.stdout


def test_fake_observed_expectations_fail_closed(tmp_path: Path):
    """A receipt whose observed expectations are not all true -> FAILED."""
    sha = CANDIDATE_SHA
    _minimal_evidence(tmp_path, sha)
    rec_dir = tmp_path / "failure_injection_receipts"
    rec_dir.mkdir()
    from scripts.verification import chaos_phase25

    for spec in chaos_phase25.MANDATORY_SCENARIOS:
        _write_json(rec_dir / f"{spec['scenario_id']}.json", {
            "schema_version": "1.0.0", "candidate_sha": sha,
            "run_id": "neg", "started_at": "2026-08-02T00:00:00Z",
            "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "mock",
            "input_hashes": ["a" * 64], "output_hashes": ["b" * 64],
            "evidence_locator": f"failure_injection_receipts/{spec['scenario_id']}.json",
            "status": "PASSED", "scenario_id": spec["scenario_id"],
            "tier": "INTEGRATION_LEVEL",
            "detection_time_ms": 0, "recovery_time_ms": 0,
            "observed": {"expectation": False},  # fake -> must fail
            "duplicates_prevented": {"submit": 0, "debit": 0, "publish": 0},
        })
    result = _run(VERIFY, "--evidence-dir", str(tmp_path), "--candidate-sha", sha)
    assert result.returncode != 0
    assert "observed expectations not all true" in result.stdout


# ---------------------------------------------------------------------------
# Read-only immutability
# ---------------------------------------------------------------------------

def test_read_only_verifier_does_not_mutate_evidence(tmp_path: Path):
    """A read-only run over real evidence must leave bytes + mtimes untouched."""
    sha = CANDIDATE_SHA
    _minimal_evidence(tmp_path, sha)
    from scripts.verification import chaos_phase25

    for spec in chaos_phase25.MANDATORY_SCENARIOS:
        runner = chaos_phase25.SCENARIO_RUNNERS[spec["scenario_id"]]
        receipt = runner(tmp_path / "scn", sha)
        receipt["scenario_id"] = spec["scenario_id"]
        _write_json(tmp_path / "failure_injection_receipts" / f"{spec['scenario_id']}.json",
                    receipt)
    _write_json(tmp_path / "chaos_scenario_manifest.json", {
        "schema_version": "1.0.0", "candidate_sha": sha,
        "gate": "VP25_RECOVERY_AND_CHAOS_VERIFIED",
        "scenario_count": len(chaos_phase25.MANDATORY_SCENARIOS),
        "scenarios": [
            {
                "scenario_id": spec["scenario_id"],
                "status": "PASSED",
                "observed_expectations": {"ok": True},
                "receipt": f"failure_injection_receipts/{spec['scenario_id']}.json",
            }
            for spec in chaos_phase25.MANDATORY_SCENARIOS
        ],
    })
    from scripts.verification import evidence_lib

    _write_json(tmp_path / "evidence_manifest.json",
                evidence_lib.build_evidence_manifest(tmp_path, sha))

    before = _snapshot_dir(tmp_path)
    _run(VERIFY, "--evidence-dir", str(tmp_path), "--candidate-sha", sha)
    after = _snapshot_dir(tmp_path)
    assert before == after, "read-only verifier mutated evidence files"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
