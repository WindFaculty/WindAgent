"""
R0 remediation regression tests (plan 08 §6.1, §6.4, gate R0).

Covers the new verification boundary contract:
- read-only verifiers never mutate evidence (hash + mtime snapshot);
- --write-fixture refuses production artifact paths and writes only temp dirs;
- unknown CLI flags are rejected;
- the negative evidence matrix fails closed (mock .mp4, placeholder hashes,
  self-reported build receipts, Flow receipt without external ID, duration out
  of scope, missing final MP4);
- the §3 production receipt schema rejects adversarial receipts.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERIFY_21 = ROOT / "scripts" / "verification" / "verify_phase21_audio_pipeline.py"
VERIFY_22 = ROOT / "scripts" / "verification" / "verify_phase22_postproduction.py"
VERIFY_23 = ROOT / "scripts" / "verification" / "verify_phase23_production_workspace.py"
VERIFY_24 = ROOT / "scripts" / "verification" / "verify_phase24_e2e_poc.py"

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


def _run_verifier(script: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *flags],
        capture_output=True, text=True, timeout=900, cwd=str(ROOT),
    )


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Read-only immutability (gate R0)
# ---------------------------------------------------------------------------

def test_read_only_verifier_does_not_mutate_evidence(tmp_path: Path):
    """A read-only verifier run must leave evidence bytes + mtimes untouched."""
    # Build a minimal-but-valid VP22 evidence dir with a real manifest.

    sha = CANDIDATE_SHA
    for name in ("toolchain_receipt.json", "render_manifest.json",
                 "media_decode_receipt.json", "reproducibility_report.json",
                 "final_media_manifest.json"):
        _write_json(tmp_path / name, {
            "schema_version": "1.0.0", "candidate_sha": sha,
            "run_id": "ro_test", "started_at": "2026-08-02T00:00:00Z",
            "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "ffmpeg",
            "input_hashes": ["a" * 64], "output_hashes": ["b" * 64],
            "evidence_locator": name, "status": "PASSED",
        })
    (tmp_path / "ffmpeg_command_receipts").mkdir()
    _write_json(tmp_path / "ffmpeg_command_receipts" / "cmd_01.json", {
        "argv": ["ffmpeg", "-y", "-i", "in.mp4", "out.mp4"],
        "return_code": 0, "execution_time_seconds": 1.5,
        "input_hashes": ["a" * 64], "output_hash": "b" * 64,
    })
    # A real-ish MP4 magic file (ftyp) so media validation can run.
    (tmp_path / "final.mp4").write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 200)
    _write_json(tmp_path / "ffprobe_raw.json", {
        "streams": [
            {"codec_type": "video", "codec_name": "h264"},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
        "format": {"format_name": "mov,mp4,m4a"},
    })
    from scripts.verification import evidence_lib
    _write_json(tmp_path / "evidence_manifest.json",
                evidence_lib.build_evidence_manifest(tmp_path, sha))

    before = _snapshot_dir(tmp_path)
    _run_verifier(VERIFY_22, "--evidence-dir", str(tmp_path),
                  "--candidate-sha", sha)
    after = _snapshot_dir(tmp_path)
    assert before == after, "read-only verifier mutated evidence files"


# ---------------------------------------------------------------------------
# Fixture writer isolation + unknown flags
# ---------------------------------------------------------------------------

def test_write_fixture_refuses_production_artifacts():
    result = _run_verifier(
        VERIFY_21, "--write-fixture",
        str(ROOT / "artifacts" / "video_production" / "phase_21"),
    )
    assert result.returncode == 2, "must refuse production artifact path"
    assert "refuses production artifacts" in result.stderr


def test_write_fixture_writes_only_to_temp_dir(tmp_path: Path):
    out = tmp_path / "fixtures"
    result = _run_verifier(VERIFY_21, "--write-fixture", str(out))
    assert result.returncode == 0
    assert (out / "contract_verdict.json").is_file()
    # Nothing under production artifacts was touched.
    prod = ROOT / "artifacts" / "video_production" / "phase_21"
    assert not (prod / "contract_verdict.json").exists()


def test_unknown_flag_rejected():
    result = _run_verifier(VERIFY_21, "--bogus-flag")
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


# ---------------------------------------------------------------------------
# Negative evidence matrix (plan §6.4) — each legacy fake must fail closed
# ---------------------------------------------------------------------------

def test_mock_mp4_payload_fails_closed(tmp_path: Path):
    """R22-01: a mock byte-string .mp4 must never pass VP22."""
    sha = CANDIDATE_SHA
    _write_json(tmp_path / "final_media_manifest.json", {
        "schema_version": "1.0.0", "candidate_sha": sha,
        "run_id": "neg", "started_at": "2026-08-02T00:00:00Z",
        "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "mock",
        "input_hashes": ["a" * 64], "output_hashes": ["b" * 64],
        "evidence_locator": "final_media_manifest.json", "status": "PASSED",
        "media_locator": "fake.mp4", "final_media_sha256": "c" * 64,
        "duration_seconds": 36.0, "verification_status": "PASSED",
    })
    (tmp_path / "fake.mp4").write_bytes(b"mock_data_fake.mp4")
    from scripts.verification import evidence_lib
    _write_json(tmp_path / "evidence_manifest.json",
                evidence_lib.build_evidence_manifest(tmp_path, sha))
    result = _run_verifier(VERIFY_22, "--evidence-dir", str(tmp_path),
                           "--candidate-sha", sha)
    assert result.returncode != 0
    assert "BLOCKED" in result.stdout or "FAILED" in result.stdout


def test_placeholder_sha256_hash_fails_closed(tmp_path: Path):
    """R24-01: placeholder hash must never pass VP24."""
    _write_json(tmp_path / "poc_run_manifest.json", {
        "schema_version": "1.0.0", "candidate_sha": "git_sha_v2_poc_release_0_1",
        "run_id": "neg", "started_at": "2026-08-02T00:00:00Z",
        "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "mock",
        "input_hashes": ["sha256_screenplay_rev_01"], "output_hashes": ["x" * 64],
        "evidence_locator": "poc_run_manifest.json", "status": "PASSED",
        "planned_shots": 6, "planned_duration_seconds": 35.0,
    })
    from scripts.verification import evidence_lib
    _write_json(tmp_path / "evidence_manifest.json",
                evidence_lib.build_evidence_manifest(tmp_path, "a" * 40))
    result = _run_verifier(VERIFY_24, "--evidence-dir", str(tmp_path),
                           "--candidate-sha", "a" * 40)
    assert result.returncode != 0


def test_self_reported_build_receipt_fails_closed(tmp_path: Path):
    """R23-01: build receipt with no command log must never pass VP23."""
    sha = CANDIDATE_SHA
    for name in ("web_command_receipt.json", "desktop_command_receipt.json"):
        _write_json(tmp_path / name, {
            "schema_version": "1.0.0", "candidate_sha": sha,
            "run_id": "neg", "started_at": "2026-08-02T00:00:00Z",
            "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "self-reported",
            "input_hashes": ["a" * 64], "output_hashes": ["b" * 64],
            "evidence_locator": name, "status": "PASSED",
            "unit_tests_passed": 14,  # self-reported counter, no command
        })
    for name in ("api_integration_receipt.json", "realtime_e2e_receipt.json",
                 "web_build_manifest.json", "desktop_build_manifest.json",
                 "accessibility_core_flow_receipt.json"):
        _write_json(tmp_path / name, {
            "schema_version": "1.0.0", "candidate_sha": sha,
            "run_id": "neg", "started_at": "2026-08-02T00:00:00Z",
            "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "self-reported",
            "input_hashes": ["a" * 64], "output_hashes": ["b" * 64],
            "evidence_locator": name, "status": "PASSED",
        })
    from scripts.verification import evidence_lib
    _write_json(tmp_path / "evidence_manifest.json",
                evidence_lib.build_evidence_manifest(tmp_path, sha))
    result = _run_verifier(VERIFY_23, "--evidence-dir", str(tmp_path),
                           "--candidate-sha", sha)
    assert result.returncode != 0


def test_flow_receipt_without_external_id_fails_closed(tmp_path: Path):
    """R24-01: Flow job receipt without external_job_id must never pass VP24."""
    sha = CANDIDATE_SHA
    job_dir = tmp_path / "flow_job_receipts"
    job_dir.mkdir()
    _write_json(job_dir / "job_01.json", {
        "job_id": "job_flow_shot_01", "run_id": "neg", "shot_id": "shot_01",
        "status": "COMPLETED", "candidate_hash": "a" * 64,
        "request_hash": "b" * 64,  # no external_job_id
    })
    for name in ("poc_run_manifest.json", "input_revision_manifest.json",
                 "workflow_event_receipt.json", "browser_recovery_receipt.json",
                 "candidate_review_report.json", "audio_production_receipt.json",
                 "postproduction_receipt.json", "final_media_manifest.json",
                 "final_media_verification.json", "cost_report.json",
                 "traceability_graph.json", "automation_rate.json",
                 "final_cut_approval.json", "vp21_receipt.json",
                 "vp22_receipt.json", "vp23_receipt.json"):
        _write_json(tmp_path / name, {
            "schema_version": "1.0.0", "candidate_sha": sha,
            "run_id": "neg", "started_at": "2026-08-02T00:00:00Z",
            "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "mock",
            "input_hashes": ["a" * 64], "output_hashes": ["b" * 64],
            "evidence_locator": name, "status": "PASSED",
            "approved": True, "ledger_reconciled": True, "automation_rate": 0.9,
            "duplicate_submits_count": 0, "reattach_verified": True,
            "job_reconciled": True, "final_artifact_sha256": "a" * 64, "nodes": [],
        })
    from scripts.verification import evidence_lib
    _write_json(tmp_path / "evidence_manifest.json",
                evidence_lib.build_evidence_manifest(tmp_path, sha))
    result = _run_verifier(VERIFY_24, "--evidence-dir", str(tmp_path),
                           "--candidate-sha", sha)
    assert result.returncode != 0
    assert "external_job_id" in result.stdout


def test_duration_out_of_scope_fails_closed(tmp_path: Path):
    """Duration outside the 30-45s POC scope must fail VP22."""
    sha = CANDIDATE_SHA
    _write_json(tmp_path / "final_media_manifest.json", {
        "schema_version": "1.0.0", "candidate_sha": sha,
        "run_id": "neg", "started_at": "2026-08-02T00:00:00Z",
        "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "ffmpeg",
        "input_hashes": ["a" * 64], "output_hashes": ["b" * 64],
        "evidence_locator": "final_media_manifest.json", "status": "PASSED",
        "media_locator": "out.mp4", "final_media_sha256": "c" * 64,
        "duration_seconds": 120.0, "verification_status": "PASSED",
    })
    (tmp_path / "out.mp4").write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 200)
    from scripts.verification import evidence_lib
    _write_json(tmp_path / "evidence_manifest.json",
                evidence_lib.build_evidence_manifest(tmp_path, sha))
    result = _run_verifier(VERIFY_22, "--evidence-dir", str(tmp_path),
                           "--candidate-sha", sha)
    assert result.returncode != 0
    assert "outside POC policy" in result.stdout


def test_missing_final_mp4_fails_closed(tmp_path: Path):
    """R24-02: missing final MP4 must block VP24."""
    sha = CANDIDATE_SHA
    _write_json(tmp_path / "final_media_manifest.json", {
        "schema_version": "1.0.0", "candidate_sha": sha,
        "run_id": "neg", "started_at": "2026-08-02T00:00:00Z",
        "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "ffmpeg",
        "input_hashes": ["a" * 64], "output_hashes": ["b" * 64],
        "evidence_locator": "final_media_manifest.json", "status": "PASSED",
        "media_locator": "does_not_exist.mp4", "final_media_sha256": "c" * 64,
        "duration_seconds": 36.0, "verification_status": "PASSED",
    })
    from scripts.verification import evidence_lib
    _write_json(tmp_path / "evidence_manifest.json",
                evidence_lib.build_evidence_manifest(tmp_path, sha))
    result = _run_verifier(VERIFY_24, "--evidence-dir", str(tmp_path),
                           "--candidate-sha", sha)
    assert result.returncode != 0
    assert "final media file missing" in result.stdout


# ---------------------------------------------------------------------------
# §3 receipt schema validation
# ---------------------------------------------------------------------------

def test_production_receipt_schema_rejects_adversarial():
    from scripts.verification import evidence_lib

    good = {
        "schema_version": "1.0.0", "candidate_sha": CANDIDATE_SHA,
        "run_id": "golden", "started_at": "2026-08-02T00:00:00Z",
        "completed_at": "2026-08-02T00:01:00Z", "command_or_provider": "ffmpeg",
        "input_hashes": ["a" * 64], "output_hashes": ["b" * 64],
        "evidence_locator": "evidence/golden.json", "status": "PASSED",
    }
    bad = {
        "schema_version": "2.0", "candidate_sha": "sha256_placeholder",
        "run_id": "", "started_at": "not-a-date",
        "completed_at": "2020-01-01T00:00:00Z", "command_or_provider": "",
        "input_hashes": ["short"], "output_hashes": [],
        "evidence_locator": "C:\\Users\\admin\\profile", "status": "MAYBE",
    }
    assert evidence_lib.validate_production_receipt(good, candidate_sha=CANDIDATE_SHA) == []
    errors = evidence_lib.validate_production_receipt(bad, candidate_sha=CANDIDATE_SHA)
    assert len(errors) >= 8  # schema_version, sha, run_id, timestamps, hashes, locator, status


def test_evidence_manifest_content_addressed(tmp_path: Path):
    from scripts.verification import evidence_lib

    (tmp_path / "receipt.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    (tmp_path / "media.mp4").write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 100)
    manifest = evidence_lib.build_evidence_manifest(tmp_path, CANDIDATE_SHA)
    errors = evidence_lib.validate_evidence_manifest(
        manifest, tmp_path, candidate_sha=CANDIDATE_SHA
    )
    assert errors == []
    # Tampering must be detected.
    (tmp_path / "receipt.json").write_text(json.dumps({"a": 2}), encoding="utf-8")
    errors = evidence_lib.validate_evidence_manifest(
        manifest, tmp_path, candidate_sha=CANDIDATE_SHA
    )
    assert errors, "tampered file must be detected by content-addressed manifest"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
