"""
Phase 26 security/privacy regression tests (plan 07 Â§17, gate
VP26_SECURITY_VERIFIED).

Covers:
- verifier CLI contract: read-only default, --write-fixture temp-only,
  unknown flag rejection, no evidence-dir mutation;
- scenario-level mock tests: each mandatory security scenario runs against
  real machinery and observes the expected outcome;
- negative evidence fails closed (missing threat-model boundary, secret
  canary found, fake observed expectations);
- the SE01 hardening fix: redact_shell_output now masks unquoted password=
  and API-key prefixes (SEC-001 closed);
- fixture writer / full-set validation round trip.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verification" / "verify_phase26_security.py"
FIXTURE = ROOT / "scripts" / "verification" / "fixture_phase26_security.py"

CANDIDATE_SHA = "1753831c752343aa89419e807aa57058266ff75c"
FIXTURE_SHA = "f" * 40


def _snapshot_dir(root: Path) -> dict[str, tuple[str, int]]:
    snap: dict[str, tuple[str, int]] = {}
    if not root.exists():
        return snap
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            st = path.stat()
            snap[rel] = (hashlib.sha256(path.read_bytes()).hexdigest(), st.st_mtime_ns)
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
# Mandatory scenario matrix (plan Â§15) â€” every scenario must be present
# ---------------------------------------------------------------------------

def test_manifest_covers_all_13_mandatory_scenarios():
    from scripts.verification import security_phase26 as sec

    assert len(sec.REQUIRED_SCENARIO_IDS) == 13
    assert len(sec.MANDATORY_SCENARIOS) == 13
    assert len(set(sec.REQUIRED_SCENARIO_IDS)) == 13


@pytest.mark.parametrize("scenario_id", [
    "SE01", "SE02", "SE03", "SE04", "SE05", "SE06", "SE07",
    "SE08", "SE09", "SE10", "SE11", "SE12", "SE13",
])
def test_each_scenario_has_expected_behavior(scenario_id: str):
    from scripts.verification import security_phase26 as sec

    spec = next(s for s in sec.MANDATORY_SCENARIOS if s["scenario_id"] == scenario_id)
    assert spec["expected_behavior"], "each scenario must declare expected behavior"
    assert spec["test_tier"] in ("MOCK_LEVEL", "INTEGRATION_LEVEL")
    assert spec["trust_boundary"], "each scenario must map to a trust boundary"
    assert scenario_id in sec.SECURITY_TEST_RUNNERS


# ---------------------------------------------------------------------------
# Scenario-level mock tests (real machinery, isolated workdirs)
# ---------------------------------------------------------------------------

def test_se01_canaries_never_survive_any_sink(tmp_path: Path):
    from scripts.verification import security_phase26 as sec

    receipt = sec.run_se01_canary_redaction(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["all_canaries_redacted_in_logs"] is True
    assert receipt["redaction_notes"]["canaries_found_in_sinks"] == []


def test_se01_hardening_redact_shell_output_masks_unquoted_password():
    """SEC-001 regression: unquoted password=/api_key= must be masked now."""
    from windagent_tools.shell.runner import redact_shell_output

    out = redact_shell_output(
        "cmd: password=canaryPass123456 api_key=canaryKey123456 "
        "sk-canarySkKey1234567890"
    )
    for canary in ("canaryPass123456", "canaryKey123456", "canarySkKey1234567890"):
        assert canary not in out
    assert "[REDACTED]" in out or "REDACTED_SECRET" in out


def test_se02_profile_encryption_at_rest(tmp_path: Path):
    from scripts.verification import security_phase26 as sec

    receipt = sec.run_se02_profile_encryption(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["encrypted_at_rest"] is True
    assert receipt["observed"]["no_plaintext_leak"] is True
    assert receipt["observed"]["wrong_key_rejected"] is True


def test_se06_media_validation_rejects_and_sanitizes(tmp_path: Path):
    from scripts.verification import security_phase26 as sec

    receipt = sec.run_se06_media_validation(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["pixel_bomb_rejected"] is True
    assert receipt["observed"]["exif_stripped"] is True
    assert receipt["observed"]["metadata_canary_absent_downstream"] is True


def test_se07_prompt_injection_stays_data(tmp_path: Path):
    from scripts.verification import security_phase26 as sec

    receipt = sec.run_se07_prompt_injection(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["injection_stays_data"] is True
    assert receipt["observed"]["filter_graph_safe"] is True


def test_se08_eval_and_shell_denied(tmp_path: Path):
    from scripts.verification import security_phase26 as sec

    receipt = sec.run_se08_eval_shell_ffmpeg(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["eval_denied"] is True
    assert receipt["observed"]["forbidden_shell_blocked"] is True


def test_se10_confirmation_gates(tmp_path: Path):
    from scripts.verification import security_phase26 as sec

    receipt = sec.run_se10_confirmation(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["terms_confirmation"] is True
    assert receipt["observed"]["publish_requires_approval"] is True
    assert receipt["observed"]["hard_deny"] is True


def test_se11_api_idempotency_and_stale_revision(tmp_path: Path):
    from scripts.verification import security_phase26 as sec

    receipt = sec.run_se11_api_authz(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["idempotency_dedup"] is True
    assert receipt["observed"]["stale_revision_conflict"] is True
    assert receipt["observed"]["media_token_path_denied"] is True


def test_se12_stale_approval_rejected(tmp_path: Path):
    from scripts.verification import security_phase26 as sec

    receipt = sec.run_se12_stale_approval(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["wrong_hash_approval_rejected"] is True
    assert receipt["observed"]["duplicate_approval_idempotent"] is True
    assert receipt["observed"]["stale_approval_after_catalog_change"] is True


def test_se13_retention_deletion_receipt(tmp_path: Path):
    from scripts.verification import security_phase26 as sec

    receipt = sec.run_se13_retention_deletion(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values())
    assert receipt["observed"]["invalidation_stale_not_deleted"] is True
    assert receipt["observed"]["deletion_receipt_no_content"] is True


# ---------------------------------------------------------------------------
# Verifier CLI contract (R0)
# ---------------------------------------------------------------------------

def test_write_fixture_refuses_production_artifacts():
    result = _run(
        VERIFY, "--write-fixture",
        str(ROOT / "artifacts" / "video_production" / "phase_26"),
    )
    assert result.returncode == 2
    assert "refuses production artifacts" in result.stderr


def test_write_fixture_writes_only_to_temp_dir(tmp_path: Path):
    out = tmp_path / "fixtures"
    result = _run(VERIFY, "--write-fixture", str(out))
    assert result.returncode == 0
    assert (out / "contract_verdict.json").is_file()
    prod = ROOT / "artifacts" / "video_production" / "phase_26"
    assert not (prod / "contract_verdict.json").exists()


def test_unknown_flag_rejected():
    result = _run(VERIFY, "--bogus-flag")
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_missing_evidence_dir_blocks():
    result = _run(
        VERIFY, "--evidence-dir", str(ROOT / "does_not_exist_phase26"),
        "--candidate-sha", CANDIDATE_SHA,
    )
    assert result.returncode != 0
    assert "BLOCKED" in result.stdout


# ---------------------------------------------------------------------------
# Fixture writer round trip: full fixture set validates PASSED on fixture SHA
# ---------------------------------------------------------------------------

def test_fixture_set_validates_passed(tmp_path: Path):
    out = tmp_path / "fixture_evidence"
    write = _run(FIXTURE, "--out-dir", str(out))
    assert write.returncode == 0
    assert (out / "phase_verdict.json").is_file()
    result = _run(VERIFY, "--evidence-dir", str(out), "--candidate-sha", FIXTURE_SHA)
    assert result.returncode == 0, result.stdout
    assert "PASSED" in result.stdout


def test_fixture_writer_refuses_production_path():
    result = _run(
        FIXTURE, "--out-dir",
        str(ROOT / "artifacts" / "video_production" / "phase_26"),
    )
    assert result.returncode == 2
    assert "refuses production artifacts" in result.stderr


# ---------------------------------------------------------------------------
# Negative evidence fails closed
# ---------------------------------------------------------------------------

def _minimal_evidence(tmp_path: Path, sha: str) -> None:
    """A valid-shaped empty evidence dir (aggregates present, no receipts)."""
    from scripts.verification.produce_phase26_evidence import TRUST_BOUNDARIES

    _write_json(tmp_path / "threat_model_manifest.json", {
        "schema_version": "1.0.0", "candidate_sha": sha,
        "trust_boundaries": TRUST_BOUNDARIES, "entry_count": 0, "entries": [],
    })
    for name in ("secret_redaction_report.json",
                 "api_authorization_report.json",
                 "file_network_sandbox_report.json",
                 "privacy_deletion_receipt.json",
                 "open_security_findings.json",
                 "phase_verdict.json"):
        _write_json(tmp_path / name, {
            "schema_version": "1.0.0", "candidate_sha": sha,
            "gate": "VP26_SECURITY_VERIFIED", "status": "PASSED",
        })
    _write_json(tmp_path / "evidence_manifest.json",
                __import__("scripts.verification.evidence_lib",
                           fromlist=["build_evidence_manifest"]).build_evidence_manifest(
                    tmp_path, sha))


def test_missing_receipts_fails_closed(tmp_path: Path):
    sha = CANDIDATE_SHA
    _minimal_evidence(tmp_path, sha)
    result = _run(VERIFY, "--evidence-dir", str(tmp_path), "--candidate-sha", sha)
    assert result.returncode != 0
    assert "missing security_test_receipts/ directory" in result.stdout


def test_threat_model_missing_boundary_fails_closed(tmp_path: Path):
    sha = CANDIDATE_SHA
    _minimal_evidence(tmp_path, sha)
    from scripts.verification import security_phase26 as sec
    from scripts.verification.produce_phase26_evidence import TRUST_BOUNDARIES

    _write_json(tmp_path / "threat_model_manifest.json", {
        "schema_version": "1.0.0", "candidate_sha": sha,
        "trust_boundaries": TRUST_BOUNDARIES[:-1], "entry_count": 0, "entries": [],
    })
    rec_dir = tmp_path / "security_test_receipts"
    for spec in sec.MANDATORY_SCENARIOS:
        _write_json(rec_dir / f"{spec['scenario_id']}.json", {
            "schema_version": "1.0.0", "candidate_sha": sha,
            "run_id": "neg", "started_at": "2026-08-02T00:00:00Z",
            "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "mock",
            "input_hashes": ["a" * 64], "output_hashes": ["b" * 64],
            "evidence_locator": f"security_test_receipts/{spec['scenario_id']}.json",
            "status": "PASSED", "scenario_id": spec["scenario_id"],
            "tier": "MOCK_LEVEL",
            "observed": {"expectation": True},
            "controlled_environment": (
                {"isolation": "neg"}
                if spec["scenario_id"] in sec.BROWSER_SESSION_SCENARIOS else None
            ),
        })
    result = _run(VERIFY, "--evidence-dir", str(tmp_path), "--candidate-sha", sha)
    assert result.returncode != 0
    assert "missing trust boundaries" in result.stdout


def test_secret_canary_found_fails_closed(tmp_path: Path):
    sha = CANDIDATE_SHA
    _minimal_evidence(tmp_path, sha)
    from scripts.verification import security_phase26 as sec

    for spec in sec.MANDATORY_SCENARIOS:
        _write_json(tmp_path / "security_test_receipts" / f"{spec['scenario_id']}.json", {
            "schema_version": "1.0.0", "candidate_sha": sha,
            "run_id": "neg", "started_at": "2026-08-02T00:00:00Z",
            "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "mock",
            "input_hashes": ["a" * 64], "output_hashes": ["b" * 64],
            "evidence_locator": f"security_test_receipts/{spec['scenario_id']}.json",
            "status": "PASSED", "scenario_id": spec["scenario_id"],
            "tier": "MOCK_LEVEL",
            "observed": {"expectation": True},
            "controlled_environment": (
                {"isolation": "neg"}
                if spec["scenario_id"] in sec.BROWSER_SESSION_SCENARIOS else None
            ),
        })
    _write_json(tmp_path / "secret_redaction_report.json", {
        "schema_version": "1.0.0", "candidate_sha": sha,
        "canaries_injected": 8, "canaries_found_in_output": 1,  # canary leaked
        "evidence_locator_markers_observed": 0,
    })
    result = _run(VERIFY, "--evidence-dir", str(tmp_path), "--candidate-sha", sha)
    assert result.returncode != 0
    assert "canaries_found_in_output" in result.stdout


def test_fake_observed_expectations_fail_closed(tmp_path: Path):
    sha = CANDIDATE_SHA
    _minimal_evidence(tmp_path, sha)
    from scripts.verification import security_phase26 as sec
    from scripts.verification.produce_phase26_evidence import TRUST_BOUNDARIES

    _write_json(tmp_path / "threat_model_manifest.json", {
        "schema_version": "1.0.0", "candidate_sha": sha,
        "trust_boundaries": TRUST_BOUNDARIES,
        "entry_count": len(sec.REQUIRED_SCENARIO_IDS),
        "entries": [
            {
                "finding_id": f"NEG-{sid}", "asset": "x",
                "trust_boundary": "x", "threat": "x", "likelihood": "low",
                "impact": "low", "control": "x", "test": sid,
                "residual_risk": "low", "severity": "low",
                "release_decision": "neg",
            }
            for sid in sec.REQUIRED_SCENARIO_IDS
        ],
    })
    for spec in sec.MANDATORY_SCENARIOS:
        _write_json(tmp_path / "security_test_receipts" / f"{spec['scenario_id']}.json", {
            "schema_version": "1.0.0", "candidate_sha": sha,
            "run_id": "neg", "started_at": "2026-08-02T00:00:00Z",
            "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "mock",
            "input_hashes": ["a" * 64], "output_hashes": ["b" * 64],
            "evidence_locator": f"security_test_receipts/{spec['scenario_id']}.json",
            "status": "PASSED", "scenario_id": spec["scenario_id"],
            "tier": "MOCK_LEVEL",
            "observed": {"expectation": False},  # fake -> must fail
            "controlled_environment": (
                {"isolation": "neg"}
                if spec["scenario_id"] in sec.BROWSER_SESSION_SCENARIOS else None
            ),
        })
    result = _run(VERIFY, "--evidence-dir", str(tmp_path), "--candidate-sha", sha)
    assert result.returncode != 0
    assert "observed expectations not all true" in result.stdout


# ---------------------------------------------------------------------------
# Read-only immutability
# ---------------------------------------------------------------------------

def test_read_only_verifier_does_not_mutate_evidence(tmp_path: Path):
    """A read-only run over real evidence must leave bytes + mtimes untouched."""
    out = tmp_path / "evidence"
    write = _run(FIXTURE, "--out-dir", str(out))
    assert write.returncode == 0

    before = _snapshot_dir(out)
    result = _run(VERIFY, "--evidence-dir", str(out), "--candidate-sha", FIXTURE_SHA)
    assert result.returncode == 0
    after = _snapshot_dir(out)
    assert before == after, "read-only verifier mutated evidence files"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
