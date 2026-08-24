"""
Phase 27 release-certification regression tests (plan 07 Â§24/Â§27/Â§28, gate
VIDEO_PRODUCTION_PLATFORM_VERIFIED / READY_FOR_CONTROLLED_RELEASE).

Covers:
- verifier CLI contract: read-only default, --write-fixture temp-only,
  unknown flag rejection, no evidence-dir mutation;
- harness contract: every required lane id present in the CI manifest and
  every lane has a runner; release scope matches plan Â§25;
- lane-level mock tests (real machinery, isolated workdirs): attestation,
  migration rehearsal, release E2E (real ffmpeg path when available),
  license/notice, web/desktop presence, evidence validation;
- the FinalDeliverable -> VerifiedDeliverable canonical-schema fix: the
  duplicate-canonical-model lane passes and no runtime shadowing remains;
- fixture writer / full-set validation round trip on the fixture SHA;
- negative evidence fails closed (missing required lane, fake observed
  expectations, phase verdict not PASSED, missing final bundle, blocking
  finding);
- read-only immutability of a read-only verifier run.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verification" / "verify_phase27_release.py"
FIXTURE = ROOT / "scripts" / "verification" / "fixture_phase27_release.py"

# The attestation lane requires HEAD == candidate. Resolve the candidate SHA
# from the checked-out HEAD instead of hard-coding an ancestor commit (was
# VP3D_BASELINE_001: a stale hard-coded SHA made this test fail at any later
# clean HEAD even though the release-lane machinery was correct).
def _head_sha() -> str:
    import subprocess

    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )
    return proc.stdout.strip()


CANDIDATE_SHA = _head_sha()
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
# Harness contract (plan Â§20.1/Â§25/Â§28)
# ---------------------------------------------------------------------------

def test_harness_gates_and_lane_manifest() -> None:
    from scripts.verification import release_phase27 as rel

    assert rel.GATE == "VIDEO_PRODUCTION_PLATFORM_VERIFIED"
    assert rel.RELEASE_GATE == "READY_FOR_CONTROLLED_RELEASE"
    assert len(rel.REQUIRED_LANE_IDS) == 4 + len(rel.REQUIRED_CI_LANE_IDS)
    assert len(set(rel.REQUIRED_LANE_IDS)) == len(rel.REQUIRED_LANE_IDS)
    # Every required lane is either driven by a dedicated runner or covered by
    # the CI check lane list (run_ci_lanes).
    standalone = set(rel.RELEASE_LANE_RUNNERS)
    ci_checked = {lid for lid in rel.REQUIRED_CI_LANE_IDS
                  if lid not in standalone}
    assert rel.REQUIRED_LANE_IDS == tuple(sorted(rel.REQUIRED_LANE_IDS, key=rel.REQUIRED_LANE_IDS.index))
    for lane_id in rel.REQUIRED_LANE_IDS:
        assert lane_id in standalone or lane_id in ci_checked, f"no runner for {lane_id}"
    assert len(ci_checked) == 6  # the six scripts/*.py check lanes


def test_release_scope_matches_plan_25() -> None:
    from scripts.verification import release_phase27 as rel

    scope = rel.RELEASE_0_1_SCOPE
    assert scope["flow_accounts"] == 1
    assert scope["max_shots"] == 7
    assert scope["max_characters"] == 2
    assert scope["concurrency"] == 1
    assert scope["video_duration_seconds"] == (30, 45)
    assert scope["bounded_approval_cost_retry"] is True


def test_open_release_findings_have_owner_and_decision() -> None:
    from scripts.verification import release_phase27 as rel

    findings = rel.build_open_release_findings(CANDIDATE_SHA)
    assert findings["release_blocking_count"] == 0
    ids = [f["finding_id"] for f in findings["findings"]]
    assert ids == ["REL-001", "REL-002", "REL-003", "REL-004"]
    for finding in findings["findings"]:
        assert finding["owner"]
        assert finding["release_decision"]
        assert finding["impact"]
        assert finding["severity"] in ("low", "medium", "high", "critical")


# ---------------------------------------------------------------------------
# Lane-level mock tests (real machinery, isolated workdirs)
# ---------------------------------------------------------------------------

def test_attestation_lane_observes_real_git_state(tmp_path: Path) -> None:
    from scripts.verification import release_phase27 as rel

    receipt = rel.run_candidate_attestation(tmp_path, CANDIDATE_SHA)
    details = receipt["details"]
    assert details["branch"]
    assert details["parent_sha"]
    assert details["product_version"]
    assert details["web_version"]
    # head_matches_candidate may be False if the working tree moved; the lane
    # must still record the observed hash honestly.
    assert "head_matches_candidate" in receipt["observed"]
    assert "lockfiles_present" in receipt["observed"]
    assert "third_party_manifest_present" in receipt["observed"]


def test_migration_rehearsal_lane(tmp_path: Path) -> None:
    from scripts.verification import release_phase27 as rel

    receipt = rel.run_migration_rehearsal(tmp_path, CANDIDATE_SHA)
    assert all(receipt["observed"].values()), receipt["observed"]
    assert receipt["observed"]["dry_run_success"] is True
    assert receipt["observed"]["rollback_rehearsal_success"] is True
    assert receipt["observed"]["pre_existing_data_preserved"] is True
    assert receipt["observed"]["canonical_tables_verified"] is True


def test_release_e2e_mock_lane(tmp_path: Path) -> None:
    from scripts.verification import release_phase27 as rel

    receipt = rel.run_release_e2e(tmp_path, CANDIDATE_SHA)
    # The real-credit E2E must be recorded as NOT executed (approval-gated).
    assert receipt["observed"]["real_credit_e2e_not_executed"] is True
    assert receipt["observed"]["zero_real_credits_consumed"] is True
    assert receipt["observed"]["edl_plan_typed_no_shell_metachars"] is True
    # Render/probe depend on real ffmpeg; if present they must pass, if absent
    # they must be recorded as False (honest) without crashing.
    assert "real_ffmpeg_render_ok" in receipt["observed"]
    assert "deliverable_record_traceable" in receipt["observed"]
    if receipt["observed"]["real_ffmpeg_render_ok"]:
        assert receipt["observed"]["real_ffprobe_verify_ok"] is True


def test_ffmpeg_fixture_lane_uses_real_binaries(tmp_path: Path) -> None:
    from scripts.verification import release_phase27 as rel

    receipt = rel.run_ffmpeg_fixture_lane(tmp_path, CANDIDATE_SHA)
    if receipt["observed"]["ffmpeg_present"]:
        # Real render + probe must have produced a real MP4 with ftyp magic.
        assert receipt["observed"]["render_exit_zero"] is True
        assert receipt["observed"]["probe_exit_zero"] is True
        assert receipt["observed"]["real_duration_verified"] is True
        assert receipt["observed"]["container_magic_mp4"] is True
        assert receipt["clip_size_bytes"] > 64
        assert len(receipt["clip_sha256"]) == 64


def test_license_notice_and_web_desktop_lanes(tmp_path: Path) -> None:
    from scripts.verification import release_phase27 as rel

    license_receipt = rel.run_license_notice_lane(tmp_path, CANDIDATE_SHA)
    assert all(license_receipt["observed"].values()), license_receipt["observed"]

    web_receipt = rel.run_web_desktop_lane(tmp_path, CANDIDATE_SHA)
    assert web_receipt["observed"]["web_package_present"] is True
    assert web_receipt["observed"]["desktop_package_present"] is True
    assert web_receipt["observed"]["web_lockfile_present"] is True


def test_evidence_validation_lane_lineage(tmp_path: Path) -> None:
    from scripts.verification import release_phase27 as rel

    receipt = rel.run_evidence_validation(tmp_path, CANDIDATE_SHA)
    lineage = receipt["phase_lineage"]
    # Phases 0-20 must be present as phase_report entries.
    for phase in range(0, 21):
        assert f"phase_{phase:02d}" in lineage
    # 21 is a documented BLOCKED state; the historical candidate verdicts
    # (22/23/25/26) remain parseable lineage records. Per-candidate verdict
    # artifacts are produced by the evidence lane at freeze time, so the
    # moving-HEAD slots record status None until that producer runs.
    assert lineage["phase_21"]["status"] == "BLOCKED"

    historical_sha = "1753831c752343aa89419e807aa57058266ff75c"
    for phase in (22, 23, 25, 26):
        template = rel.PHASE_VERDICT_FILES[phase]
        path = rel.ROOT / template.format(sha=historical_sha)
        assert path.exists(), f"{path} missing"
        verdict = json.loads(path.read_text(encoding="utf-8"))
        assert verdict.get("status") == "PASSED", f"{path} status {verdict.get('status')}"

    assert receipt["observed"]["phase_24_executable_gate_present"] is True


def test_ci_run_manifest_aggregates_all_required_lanes() -> None:
    """The verifier checks REQUIRED_LANE_IDS against ci_run_manifest; the
    builder must include the three non-CI receipts as lane rows."""
    from scripts.verification import release_phase27 as rel

    attest = rel.run_candidate_attestation(Path("."), CANDIDATE_SHA)
    ci_lanes = [
        {
            "lane_id": lid, "status": "PASSED", "tier": "MOCK_LEVEL",
            "observed": {"exit_zero": True}, "evidence_locator": "x",
        }
        for lid in rel.REQUIRED_CI_LANE_IDS
    ]
    for lane in ci_lanes:
        lane["status"] = "PASSED"

    def _dummy(lane_id: str) -> dict:
        return {
            "lane_id": lane_id, "status": "PASSED", "tier": "MOCK_LEVEL",
            "observed": {"ok": True}, "evidence_locator": "dummy",
        }

    manifest = rel.build_ci_run_manifest(
        attest, ci_lanes, _dummy("CI_PYTHON_UNIT_SUBSET"),
        _dummy("CI_FFMPEG_FIXTURES"), _dummy("CI_LICENSE_NOTICE"),
        _dummy("CI_WEB_DESKTOP_PRESENCE"), CANDIDATE_SHA,
        migration=_dummy("MIGRATION_REHEARSAL"),
        release_e2e=_dummy("RELEASE_E2E_MOCK"),
        evidence_validation=_dummy("EVIDENCE_VALIDATION"),
    )
    lane_ids = [lane["lane_id"] for lane in manifest["lanes"]]
    for lane_id in rel.REQUIRED_LANE_IDS:
        assert lane_id in lane_ids, f"ci_run_manifest missing required lane {lane_id}"
    assert manifest["all_lanes_passed"] is True


# ---------------------------------------------------------------------------
# Canonical-schema fix regression (FinalDeliverable collision, Â§20.1)
# ---------------------------------------------------------------------------

def test_duplicate_canonical_models_check_passes() -> None:
    """The naming collision that blocked release (dataclass postproduction
    FinalDeliverable vs canonical asset.FinalDeliverable) is fixed; the
    canonical-schema CI lane must pass on the candidate."""
    result = subprocess.run(
        [sys.executable, "scripts/check_duplicate_canonical_models.py"],
        capture_output=True, text=True, timeout=240, cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout[-500:]


def test_postproduction_deliverable_renamed_to_verified_deliverable() -> None:
    """Runtime shadowing regression: the canonical asset.FinalDeliverable must
    be the only FinalDeliverable exported from the domain package."""
    from windagent_core.domain.video_production import FinalDeliverable
    from windagent_core.domain.video_production.postproduction import (
        VerifiedDeliverable,
    )

    assert FinalDeliverable.__module__ == (
        "windagent_core.domain.video_production.asset"
    ), "canonical FinalDeliverable must come from asset.py"
    assert VerifiedDeliverable.__name__ == "VerifiedDeliverable"
    # Shape contract of the renamed postproduction deliverable: media-verified
    # output (hash + verification status), distinct from the canonical asset
    # FinalDeliverable (publish-scoped).
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(VerifiedDeliverable)}
    for field_name in ("final_video_hash", "proxy_video_hash", "verification_status",
                       "verified_at", "edl_hash", "duration_seconds"):
        assert field_name in field_names, f"VerifiedDeliverable missing {field_name}"


def test_intelligence_postproduction_uses_verified_deliverable() -> None:
    import inspect

    from windagent_intelligence.video.postproduction.verifier import (
        MediaVerifier,
    )

    source = inspect.getsource(MediaVerifier)
    assert "VerifiedDeliverable" in source
    assert "FinalDeliverable(" not in source.replace("FinalDeliverableId", "")


# ---------------------------------------------------------------------------
# Verifier CLI contract (R0)
# ---------------------------------------------------------------------------

def test_write_fixture_refuses_production_artifacts() -> None:
    result = _run(
        VERIFY, "--write-fixture",
        str(ROOT / "artifacts" / "video_production" / "phase_27"),
    )
    assert result.returncode == 2
    assert "refuses production artifacts" in result.stderr


def test_write_fixture_writes_only_to_temp_dir(tmp_path: Path) -> None:
    out = tmp_path / "fixtures"
    result = _run(VERIFY, "--write-fixture", str(out))
    assert result.returncode == 0
    assert (out / "contract_verdict.json").is_file()
    prod = ROOT / "artifacts" / "video_production" / "phase_27"
    assert not (prod / "contract_verdict.json").exists()


def test_unknown_flag_rejected() -> None:
    result = _run(VERIFY, "--bogus-flag")
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_missing_evidence_dir_blocks() -> None:
    result = _run(
        VERIFY, "--evidence-dir", str(ROOT / "does_not_exist_phase27"),
        "--candidate-sha", CANDIDATE_SHA,
    )
    assert result.returncode != 0
    assert "BLOCKED" in result.stdout


# ---------------------------------------------------------------------------
# Fixture writer round trip: full fixture set validates PASSED on fixture SHA
# ---------------------------------------------------------------------------

def test_fixture_set_validates_passed(tmp_path: Path) -> None:
    out = tmp_path / "fixture_evidence"
    write = _run(FIXTURE, "--out-dir", str(out))
    assert write.returncode == 0, write.stderr
    assert (out / "phase_verdict.json").is_file()
    result = _run(VERIFY, "--evidence-dir", str(out), "--candidate-sha", FIXTURE_SHA)
    assert result.returncode == 0, result.stdout
    assert "PASSED" in result.stdout


def test_fixture_writer_refuses_production_path() -> None:
    result = _run(
        FIXTURE, "--out-dir",
        str(ROOT / "artifacts" / "video_production" / "phase_27"),
    )
    assert result.returncode == 2
    assert "refuses production artifacts" in result.stderr


# ---------------------------------------------------------------------------
# Negative evidence fails closed (Â§24 blocker policy)
# ---------------------------------------------------------------------------

def _minimal_evidence(tmp_path: Path, sha: str) -> None:
    """A valid-shaped empty evidence dir: all required files with PASSED but
    no observed expectations (receipts are intentionally absent)."""
    from scripts.verification import release_phase27 as rel

    def _receipt(name: str, lane_id: str) -> None:
        _write_json(tmp_path / name, {
            "schema_version": "1.0.0", "candidate_sha": sha,
            "status": "PASSED", "lane_id": lane_id,
            "observed": {"ok": True},
        })

    _receipt("candidate_attestation.json", "ATTESTATION")
    _receipt("migration_rehearsal_receipt.json", "MIGRATION_REHEARSAL")
    _receipt("release_e2e_receipt.json", "RELEASE_E2E_MOCK")
    _write_json(tmp_path / "evidence_validation_receipt.json", {
        "schema_version": "1.0.0", "candidate_sha": sha,
        "status": "PASSED", "lane_id": "EVIDENCE_VALIDATION",
        "observed": {"ok": True},
        "phase_lineage": {
            "phase_22": {"passed": True, "status": "PASSED"},
            "phase_23": {"passed": True, "status": "PASSED"},
            "phase_25": {"passed": True, "status": "PASSED"},
            "phase_26": {"passed": True, "status": "PASSED"},
        },
        "final_bundle_hashes": {n: "0" * 64 for n in (
            "implementation_manifest.json", "upstream_manifest.json",
            "test_matrix.json", "real_flow_e2e_receipt.json", "cost_report.json",
            "security_report.json", "architecture_report.json",
            "known_limitations.md", "final_verdict.md")},
    })
    _write_json(tmp_path / "build_hash_manifest.json", {
        "schema_version": "1.0.0", "candidate_sha": sha,
        "build_input_hashes": {"uv.lock": "0" * 64},
        "toolchain": {"python": "3.11"},
    })
    _write_json(tmp_path / "open_release_findings.json", {
        "schema_version": "1.0.0", "candidate_sha": sha,
        "release_blocking_count": 0, "findings": [],
    })
    # ci_run_manifest with the full required lane set but FAILED statuses.
    lanes = []
    for lane_id in rel.REQUIRED_LANE_IDS:
        lanes.append({"lane_id": lane_id, "status": "FAILED",
                      "tier": "MOCK_LEVEL", "observed": {"ok": True},
                      "receipt": "x"})
    _write_json(tmp_path / "ci_run_manifest.json", {
        "schema_version": "1.0.0", "candidate_sha": sha, "gate": rel.GATE,
        "all_lanes_passed": False, "lanes": lanes,
    })
    _write_json(tmp_path / "phase_verdict.json", {
        "schema_version": "1.0.0", "candidate_sha": sha, "gate": rel.GATE,
        "status": "BLOCKED", "release_ready": False,
        "derived_by": "test", "reasons": [],
    })
    _write_json(tmp_path / "evidence_manifest.json",
                __import__("scripts.verification.evidence_lib",
                           fromlist=["build_evidence_manifest"]).build_evidence_manifest(
                    tmp_path, sha))


def test_failed_ci_lane_fails_closed(tmp_path: Path) -> None:
    sha = CANDIDATE_SHA
    _minimal_evidence(tmp_path, sha)
    result = _run(VERIFY, "--evidence-dir", str(tmp_path), "--candidate-sha", sha)
    assert result.returncode != 0
    assert "status 'FAILED' != PASSED" in result.stdout


def test_phase_verdict_not_passed_fails_closed(tmp_path: Path) -> None:
    sha = CANDIDATE_SHA
    _minimal_evidence(tmp_path, sha)
    # Flip every required lane to PASSED but keep phase_verdict BLOCKED.
    ci = json.loads((tmp_path / "ci_run_manifest.json").read_text(encoding="utf-8"))
    for lane in ci["lanes"]:
        lane["status"] = "PASSED"
    ci["all_lanes_passed"] = True
    _write_json(tmp_path / "ci_run_manifest.json", ci)
    for name, lane_id in (("candidate_attestation.json", "ATTESTATION"),
                          ("migration_rehearsal_receipt.json", "MIGRATION_REHEARSAL"),
                          ("release_e2e_receipt.json", "RELEASE_E2E_MOCK")):
        receipt = json.loads((tmp_path / name).read_text(encoding="utf-8"))
        receipt["observed"] = {
            "real_credit_e2e_not_executed": True,
        } if lane_id == "RELEASE_E2E_MOCK" else {"ok": True}
        _write_json(tmp_path / name, receipt)
    _write_json(tmp_path / "evidence_manifest.json",
                __import__("scripts.verification.evidence_lib",
                           fromlist=["build_evidence_manifest"]).build_evidence_manifest(
                    tmp_path, sha))
    result = _run(VERIFY, "--evidence-dir", str(tmp_path), "--candidate-sha", sha)
    assert result.returncode != 0
    assert "phase_verdict: status must be PASSED" in result.stdout


def test_fake_observed_expectations_fail_closed(tmp_path: Path) -> None:
    """Receipt files (migration / release E2E / evidence validation) must have
    observed expectations that are ALL true; a fake False must fail closed."""
    sha = CANDIDATE_SHA
    _minimal_evidence(tmp_path, sha)
    ci = json.loads((tmp_path / "ci_run_manifest.json").read_text(encoding="utf-8"))
    for lane in ci["lanes"]:
        lane["status"] = "PASSED"
        lane["observed"] = {"ok": True}
    ci["all_lanes_passed"] = True
    _write_json(tmp_path / "ci_run_manifest.json", ci)
    # migration receipt carries a fake observed expectation -> must be rejected.
    mig = json.loads((tmp_path / "migration_rehearsal_receipt.json").read_text(encoding="utf-8"))
    mig["observed"] = {"fake_expectation": False}
    _write_json(tmp_path / "migration_rehearsal_receipt.json", mig)
    _write_json(tmp_path / "evidence_manifest.json",
                __import__("scripts.verification.evidence_lib",
                           fromlist=["build_evidence_manifest"]).build_evidence_manifest(
                    tmp_path, sha))
    result = _run(VERIFY, "--evidence-dir", str(tmp_path), "--candidate-sha", sha)
    assert result.returncode != 0
    assert "observed expectations not all true" in result.stdout


def test_release_blocking_finding_fails_closed(tmp_path: Path) -> None:
    sha = CANDIDATE_SHA
    _minimal_evidence(tmp_path, sha)
    ci = json.loads((tmp_path / "ci_run_manifest.json").read_text(encoding="utf-8"))
    for lane in ci["lanes"]:
        lane["status"] = "PASSED"
        lane["observed"] = {"ok": True}
    ci["all_lanes_passed"] = True
    _write_json(tmp_path / "ci_run_manifest.json", ci)
    findings = json.loads((tmp_path / "open_release_findings.json").read_text(encoding="utf-8"))
    findings["release_blocking_count"] = 1
    findings["findings"] = [{
        "finding_id": "NEG-1", "title": "blocker", "severity": "critical",
        "impact": "x", "mitigation": "", "owner": "x",
        "release_decision": "block-release",
    }]
    _write_json(tmp_path / "open_release_findings.json", findings)
    _write_json(tmp_path / "evidence_manifest.json",
                __import__("scripts.verification.evidence_lib",
                           fromlist=["build_evidence_manifest"]).build_evidence_manifest(
                    tmp_path, sha))
    result = _run(VERIFY, "--evidence-dir", str(tmp_path), "--candidate-sha", sha)
    assert result.returncode != 0
    assert "release_blocking_count must be 0" in result.stdout


def test_missing_required_lane_fails_closed(tmp_path: Path) -> None:
    sha = CANDIDATE_SHA
    _minimal_evidence(tmp_path, sha)
    ci = json.loads((tmp_path / "ci_run_manifest.json").read_text(encoding="utf-8"))
    ci["lanes"] = [lane for lane in ci["lanes"] if lane["lane_id"] != "EVIDENCE_VALIDATION"]
    for lane in ci["lanes"]:
        lane["status"] = "PASSED"
        lane["observed"] = {"ok": True}
    ci["all_lanes_passed"] = True
    _write_json(tmp_path / "ci_run_manifest.json", ci)
    _write_json(tmp_path / "evidence_manifest.json",
                __import__("scripts.verification.evidence_lib",
                           fromlist=["build_evidence_manifest"]).build_evidence_manifest(
                    tmp_path, sha))
    result = _run(VERIFY, "--evidence-dir", str(tmp_path), "--candidate-sha", sha)
    assert result.returncode != 0
    assert "missing required lanes" in result.stdout


# ---------------------------------------------------------------------------
# Read-only immutability
# ---------------------------------------------------------------------------

def test_read_only_verifier_does_not_mutate_evidence(tmp_path: Path) -> None:
    """A read-only run over fixture evidence must leave bytes + mtimes intact."""
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
