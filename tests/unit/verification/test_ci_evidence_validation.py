from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.verification.validate_ci_evidence import (
    _find_job_root,
    _validate_job,
)


SHA = "a" * 40


def _write_job_evidence(root: Path, job: str) -> Path:
    job_root = root / f"{job}-evidence"
    logs = job_root / "receipts" / "logs"
    logs.mkdir(parents=True)
    stdout = b"passed\n"
    stderr = b""
    stdout_path = logs / "pytest.stdout.log"
    stderr_path = logs / "pytest.stderr.log"
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    (job_root / "environment.json").write_text(
        json.dumps({"git_sha": SHA}),
        encoding="utf-8",
    )
    receipt = {
        "command_id": "pytest",
        "command": "pytest -q",
        "cwd": str(root),
        "started_at": "2026-07-29T00:00:00Z",
        "finished_at": "2026-07-29T00:00:01Z",
        "duration_ms": 1000,
        "exit_code": 0,
        "stdout_tail": "passed\n",
        "stderr_tail": "",
        "environment": {
            "os": "test",
            "python": "3.11.0",
            "uv": "uv 0.5.0",
            "git_sha": SHA,
        },
        "expected_exit_codes": [0],
        "result": "SUCCESS",
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "output_sha256": hashlib.sha256(stdout + stderr).hexdigest(),
        "log_paths": {
            "stdout_log": "receipts/logs/pytest.stdout.log",
            "stderr_log": "receipts/logs/pytest.stderr.log",
        },
    }
    (job_root / "receipts" / "pytest.json").write_text(
        json.dumps(receipt),
        encoding="utf-8",
    )
    return job_root


def _validator() -> Draft202012Validator:
    schema_path = (
        Path(__file__).parents[3]
        / "scripts"
        / "schemas"
        / "command_receipt_v1.schema.json"
    )
    return Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8"))
    )


def test_valid_ci_job_evidence_passes(tmp_path: Path):
    expected_root = _write_job_evidence(tmp_path, "unit")
    discovered = _find_job_root(tmp_path, "unit")

    result = _validate_job(
        job="unit",
        root=discovered,
        expected_sha=SHA,
        receipt_validator=_validator(),
    )

    assert discovered == expected_root
    assert result["status"] == "PASS"
    assert result["errors"] == []


def test_tampered_ci_log_fails(tmp_path: Path):
    job_root = _write_job_evidence(tmp_path, "unit")
    (job_root / "receipts" / "logs" / "pytest.stdout.log").write_text(
        "tampered\n",
        encoding="utf-8",
    )

    result = _validate_job(
        job="unit",
        root=job_root,
        expected_sha=SHA,
        receipt_validator=_validator(),
    )

    assert result["status"] == "FAIL"
    assert any("hash mismatch" in error for error in result["errors"])


def test_wrong_candidate_sha_fails(tmp_path: Path):
    job_root = _write_job_evidence(tmp_path, "unit")

    result = _validate_job(
        job="unit",
        root=job_root,
        expected_sha="b" * 40,
        receipt_validator=_validator(),
    )

    assert result["status"] == "FAIL"
    assert any("git_sha" in error for error in result["errors"])


def test_find_job_root_prefers_evidence_bundle_over_auxiliary_receipts(
    tmp_path: Path,
):
    source = _write_job_evidence(tmp_path / "source", "artifact-protocol")
    download_root = tmp_path / "downloaded"
    bundle_root = (
        download_root
        / "artifact-protocol-evidence"
        / "artifacts"
        / "architecture_v2_production_hardening"
        / "phase_07"
        / "runs"
        / "ci-123-1"
    )
    shutil.copytree(source, bundle_root)
    (bundle_root / "evidence_bundle.json").write_text("{}", encoding="utf-8")
    (
        download_root
        / "artifact-protocol-evidence"
        / "artifacts"
        / "ci"
        / "artifact-protocol"
        / "negative-injections"
        / "receipts"
    ).mkdir(parents=True)

    assert _find_job_root(download_root, "artifact-protocol") == bundle_root
