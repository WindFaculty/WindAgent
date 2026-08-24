"""Fail-closed invariants for the Phase 7 evidence finalizer."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.verification.finalize_phase7 import (
    FINAL_JSON_ARTIFACTS,
    PHASE_ROOT,
    REQUIRED_PRODUCER_JOBS,
    REQUIRED_STATUS_CONTEXTS,
    Phase7ValidationError,
    ReceiptReference,
    SourceRecord,
    ValidationState,
    _require_flag_results,
    build_artifacts,
    build_parser,
    evaluate_source_gates,
    file_sha256,
    git_commit_exists,
    is_ancestor,
    main,
    parse_pytest_xml,
    resolve_evidence_path,
    validate_artifact_manifest,
    validate_branch_protection_report,
    validate_ci_section,
    validate_commit_scope,
    validate_finalizer_receipt,
    validate_no_self_reference,
    validate_receipt,
)
from scripts.verification.build_phase7_source_index import build_index


IMPLEMENTATION_SHA = "a" * 40
TOOLING_SHA = "b" * 40


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_receipt(
    root: Path,
    *,
    name: str = "validation",
    sha: str = TOOLING_SHA,
    exit_code: int = 0,
    expected_exit_codes: list[int] | None = None,
) -> Path:
    expected_exit_codes = expected_exit_codes or [exit_code]
    receipt_dir = root / "receipts"
    logs = receipt_dir.parent / "logs"
    receipt_dir.mkdir(parents=True)
    logs.mkdir()
    stdout = b"actual stdout\n"
    stderr = b"actual stderr\n"
    stdout_path = logs / f"{name}.stdout.log"
    stderr_path = logs / f"{name}.stderr.log"
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    receipt = {
        "command_id": name,
        "command": "uv run validation",
        "cwd": ".",
        "started_at": "2026-07-30T00:00:00+00:00",
        "finished_at": "2026-07-30T00:00:01+00:00",
        "duration_ms": 1000,
        "exit_code": exit_code,
        "stdout_tail": stdout.decode(),
        "stderr_tail": stderr.decode(),
        "environment": {"os": "test", "python": "3.11", "uv": "0.1", "git_sha": sha},
        "expected_exit_codes": expected_exit_codes,
        "result": "SUCCESS" if exit_code in expected_exit_codes else "FAILURE",
        "stdout_sha256": _sha(stdout),
        "stderr_sha256": _sha(stderr),
        "output_sha256": _sha(stdout + stderr),
        "log_paths": {
            "stdout_log": f"logs/{stdout_path.name}",
            "stderr_log": f"logs/{stderr_path.name}",
        },
    }
    path = receipt_dir / f"{name}.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return path


def read_receipt(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_receipt(path: Path, receipt: dict) -> None:
    path.write_text(json.dumps(receipt), encoding="utf-8")


def tree_snapshot(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def finalizer_args(mode: str, evidence_root: Path, *, output_dir: Path | None = None) -> list[str]:
    args = [
        mode,
        "--implementation-verified-sha",
        IMPLEMENTATION_SHA,
        "--verification-tooling-sha",
        TOOLING_SHA,
        "--source-evidence-index",
        str(evidence_root / "source-index.json"),
        "--ci-validation-receipt",
        str(evidence_root / "ci-validation.json"),
        "--branch-protection-receipt",
        str(evidence_root / "branch-protection.json"),
        "--schema-validation-receipt",
        str(evidence_root / "schema-validation.json"),
        "--hash-validation-receipt",
        str(evidence_root / "hash-validation.json"),
        "--evidence-root",
        str(evidence_root),
        "--repository-root",
        str(PHASE_ROOT.parents[2]),
    ]
    if mode == "verify":
        args.extend(
            [
                "--evidence-bundle-commit-sha",
                IMPLEMENTATION_SHA,
                "--attestation-commit-sha",
                TOOLING_SHA,
                "--authoritative-pointer-commit-sha",
                TOOLING_SHA,
            ]
        )
    if output_dir is not None:
        args.extend(["--output-dir", str(output_dir)])
    return args


def valid_ci(sha: str = TOOLING_SHA) -> dict:
    run_id = "123456"
    return {
        "run_id": run_id,
        "run_attempt": "1",
        "head_sha": sha,
        "workflow_url": "https://github.com/example/repo/actions/runs/123456",
        "aggregator_job": {"name": "final-evidence", "conclusion": "success", "job_id": 14},
        "producer_jobs": [
            {
                "name": name,
                "job_id": index + 1,
                "artifact_id": index + 101,
                "conclusion": "success",
                "run_id": run_id,
                "run_attempt": "1",
                "head_sha": sha,
                "artifact_name": f"{name}-evidence",
                "artifact_digest": "sha256:" + (f"{index:x}" * 64)[:64],
            }
            for index, name in enumerate(REQUIRED_PRODUCER_JOBS)
        ],
    }


def good_branch_report() -> dict:
    return {
        "repository": "WindFaculty/WindAgent",
        "branch": "main",
        "response_timestamp": "2026-07-30T00:00:00+00:00",
        "authenticated_principal": "redacted-installation[123]",
        "required_status_checks": {"strict": True, "contexts": list(REQUIRED_STATUS_CONTEXTS)},
        "enforce_admins": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "bypass_actors": [],
    }


def test_missing_receipt_fails(tmp_path: Path) -> None:
    with pytest.raises(Phase7ValidationError, match="missing"):
        validate_receipt(tmp_path / "receipts" / "absent.json", expected_sha=TOOLING_SHA)


def test_receipt_schema_failure_is_fail_closed(tmp_path: Path) -> None:
    receipt_path = write_receipt(tmp_path)
    receipt = read_receipt(receipt_path)
    del receipt["command"]
    save_receipt(receipt_path, receipt)
    with pytest.raises(Phase7ValidationError, match="schema"):
        validate_receipt(receipt_path, expected_sha=TOOLING_SHA)


def test_receipt_with_verified_logs_passes(tmp_path: Path) -> None:
    receipt_path = write_receipt(tmp_path)
    reference = validate_receipt(receipt_path, expected_sha=TOOLING_SHA)
    assert reference.command_id == "validation"
    assert reference.exit_code == 0


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("stdout_sha256", "0" * 64, "stdout log hash mismatch"),
        ("stderr_sha256", "0" * 64, "stderr log hash mismatch"),
        ("output_sha256", "0" * 64, "combined output hash mismatch"),
    ],
)
def test_receipt_hash_mismatch_fails(
    tmp_path: Path, field: str, replacement: str, message: str
) -> None:
    receipt_path = write_receipt(tmp_path)
    receipt = read_receipt(receipt_path)
    receipt[field] = replacement
    save_receipt(receipt_path, receipt)
    with pytest.raises(Phase7ValidationError, match=message):
        validate_receipt(receipt_path, expected_sha=TOOLING_SHA)


def test_receipt_path_traversal_and_absolute_path_fail(tmp_path: Path) -> None:
    receipt_path = write_receipt(tmp_path)
    receipt = read_receipt(receipt_path)
    receipt["log_paths"]["stdout_log"] = "../secrets.log"
    save_receipt(receipt_path, receipt)
    with pytest.raises(Phase7ValidationError, match="traversal"):
        validate_receipt(receipt_path, expected_sha=TOOLING_SHA)
    with pytest.raises(Phase7ValidationError, match="traversal"):
        resolve_evidence_path(tmp_path, "C:\\outside.log", label="test")


def test_receipt_symlink_escape_fails(tmp_path: Path) -> None:
    receipt_path = write_receipt(tmp_path)
    outside = tmp_path.parent / "outside.log"
    outside.write_text("not evidence", encoding="utf-8")
    link = tmp_path / "logs" / "escape.log"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation is unavailable in this environment")
    receipt = read_receipt(receipt_path)
    receipt["log_paths"]["stdout_log"] = "logs/escape.log"
    save_receipt(receipt_path, receipt)
    with pytest.raises(Phase7ValidationError, match="escapes evidence root"):
        validate_receipt(receipt_path, expected_sha=TOOLING_SHA)


def test_receipt_requires_matching_source_sha_and_result(tmp_path: Path) -> None:
    receipt_path = write_receipt(tmp_path, sha=IMPLEMENTATION_SHA)
    with pytest.raises(Phase7ValidationError, match="does not match"):
        validate_receipt(receipt_path, expected_sha=TOOLING_SHA)
    receipt = read_receipt(receipt_path)
    receipt["result"] = "FAILURE"
    save_receipt(receipt_path, receipt)
    with pytest.raises(Phase7ValidationError, match="does not match exit_code"):
        validate_receipt(receipt_path, expected_sha=IMPLEMENTATION_SHA)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("run_id", None, "run_id"),
        ("head_sha", IMPLEMENTATION_SHA, "head_sha"),
        ("workflow_url", "http://example.test", "workflow_url"),
    ],
)
def test_ci_identity_has_no_fallback(field: str, value: object, message: str) -> None:
    ci = valid_ci()
    if value is None:
        del ci[field]
    else:
        ci[field] = value
    with pytest.raises(Phase7ValidationError, match=message):
        validate_ci_section(ci, expected_sha=TOOLING_SHA, label="tooling CI")


def test_ci_rejects_12_of_13_and_duplicate_producers() -> None:
    ci = valid_ci()
    ci["producer_jobs"].pop()
    with pytest.raises(Phase7ValidationError, match="exactly 13"):
        validate_ci_section(ci, expected_sha=TOOLING_SHA, label="tooling CI")
    ci = valid_ci()
    ci["producer_jobs"][-1]["name"] = ci["producer_jobs"][0]["name"]
    with pytest.raises(Phase7ValidationError, match="duplicate"):
        validate_ci_section(ci, expected_sha=TOOLING_SHA, label="tooling CI")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda ci: ci.pop("aggregator_job"), "aggregator_job"),
        (lambda ci: ci["aggregator_job"].update({"conclusion": "failure"}), "conclusion"),
        (lambda ci: ci["producer_jobs"][0].pop("artifact_digest"), "artifact_digest"),
    ],
)
def test_ci_requires_aggregator_and_artifact_digest(mutation, message: str) -> None:
    ci = valid_ci()
    mutation(ci)
    with pytest.raises(Phase7ValidationError, match=message):
        validate_ci_section(ci, expected_sha=TOOLING_SHA, label="tooling CI")


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        (None, "missing"),
        ('<testsuite tests="0" failures="0" errors="0" skipped="0"/>', "zero tests"),
        ('<testsuite tests="2" failures="1" errors="0" skipped="0"/>', "failures/errors"),
    ],
)
def test_pytest_xml_must_exist_have_tests_and_pass(tmp_path: Path, xml: str | None, message: str) -> None:
    path = tmp_path / "pytest.xml"
    if xml:
        path.write_text(xml, encoding="utf-8")
    with pytest.raises(Phase7ValidationError, match=message):
        parse_pytest_xml(path)


def test_branch_protection_requires_all_controls() -> None:
    assert validate_branch_protection_report(good_branch_report())
    for field, value in (
        ("strict", False),
        ("enforce_admins", {"enabled": False}),
        ("allow_force_pushes", {"enabled": True}),
        ("allow_deletions", {"enabled": True}),
    ):
        report = good_branch_report()
        if field == "strict":
            report["required_status_checks"][field] = value
        else:
            report[field] = value
        assert not validate_branch_protection_report(report)
    report = good_branch_report()
    report["required_status_checks"]["contexts"].pop()
    assert not validate_branch_protection_report(report)
    report = good_branch_report()
    report["bypass_actors"] = ["unreviewed-admin"]
    assert not validate_branch_protection_report(report)
    assert validate_branch_protection_report(report, {"unreviewed-admin"})


def receipt_reference(name: str, exit_code: int = 0) -> ReceiptReference:
    return ReceiptReference(f"receipts/{name}.json", "c" * 64, name, exit_code, "SUCCESS")


def record(name: str, *, kind: str = "report", content: object = None, receipt: ReceiptReference | None = None) -> SourceRecord:
    suffix = ".xml" if kind == "pytest_xml" else ".json"
    return SourceRecord(name, Path(f"{name}{suffix}"), {"kind": kind}, content, receipt)


def complete_source_map() -> dict[str, list[SourceRecord]]:
    negative = [record(f"negative-{index}", kind="receipt", receipt=receipt_reference(f"negative-{index}", 1)) for index in range(9)]
    return {
        "artifact_protocol": [record("artifact", kind="receipt", receipt=receipt_reference("artifact")), record("artifact-report", content={"verdict": "PASS"})],
        "version_authority": [record("version", kind="receipt", receipt=receipt_reference("version")), record("version-report", content={"verdict": "PASS"})],
        "architecture_integrity": [record("architecture", kind="receipt", receipt=receipt_reference("architecture")), record("architecture-report", content={"verdict": "PASS", "violations": 0})],
        "cli_truthfulness": [record("cli", kind="receipt", receipt=receipt_reference("cli")), record("cli-tests", kind="pytest_xml", content={"tests": 2, "failures": 0, "errors": 0, "skipped": 0}), record("cli-report", content={"verdict": "PASS"})],
        "python_matrix": [record("python", kind="receipt", receipt=receipt_reference("python"))] + [record(f"python-{index}", kind="pytest_xml", content={"tests": 2, "failures": 0, "errors": 0, "skipped": 0}) for index in range(5)],
        "frontend_matrix": [record(f"frontend-{index}", kind="receipt", receipt=receipt_reference(f"frontend-{index}")) for index in range(16)],
        "database_matrix": [record(f"database-{index}", kind="receipt", receipt=receipt_reference(f"database-{index}")) for index in range(3)] + [record("database-report", content={"backend": "postgresql", "connection_url": "postgresql://db"})],
        "runtime_smoke": [record("runtime", kind="receipt", receipt=receipt_reference("runtime")), record("runtime-report", content={"verdict": "PASS"})],
        "negative_injections": negative,
        "branch_protection": [record("branch", kind="receipt", receipt=receipt_reference("branch")), record("branch-report", content=good_branch_report())],
    }


def test_source_gates_derive_negative_and_postgres_results_from_evidence() -> None:
    state = ValidationState()
    source_map = complete_source_map()
    evaluate_source_gates(source_map, state=state, allowed_bypass_actors=set())
    assert state.gates["negative_injections"]
    assert state.gates["database_matrix"]
    source_map["negative_injections"][0] = record("negative-0", kind="receipt", receipt=receipt_reference("negative-0", 0))
    source_map["database_matrix"][-1] = record("database-report", content={"backend": "postgresql", "connection_url": "sqlite://fallback"})
    state = ValidationState()
    evaluate_source_gates(source_map, state=state, allowed_bypass_actors=set())
    assert not state.gates["negative_injections"]
    assert not state.gates["database_matrix"]


def test_source_index_builder_requires_explicit_sources_and_hashes_bytes(tmp_path: Path) -> None:
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    source_specs: list[tuple[str, str, str]] = []
    provenance: dict[str, dict] = {}
    for index, gate in enumerate(complete_source_map()):
        raw_path = f"{gate}.json"
        artifact = evidence_root / raw_path
        artifact.write_text(json.dumps({"gate": gate}), encoding="utf-8")
        source_specs.append((gate, "report", raw_path))
        provenance[raw_path] = {
            "artifact_name": f"{gate}-evidence",
            "github_artifact_id": index + 1,
            "github_artifact_digest": "sha256:" + (f"{index:x}" * 64)[:64],
            "source_job": gate,
            "source_job_id": index + 11,
            "source_run_id": "123456",
            "source_head_sha": IMPLEMENTATION_SHA,
        }
    index = build_index(
        implementation_sha=IMPLEMENTATION_SHA,
        tooling_sha=TOOLING_SHA,
        implementation_ci=valid_ci(IMPLEMENTATION_SHA),
        tooling_ci=valid_ci(TOOLING_SHA),
        evidence_root=evidence_root,
        provenance=provenance,
        sources=source_specs,
        branch_protection_for="implementation",
    )
    assert index["sources"]["artifact_protocol"][0]["sha256"] == file_sha256(
        evidence_root / "artifact_protocol.json"
    )
    with pytest.raises(Phase7ValidationError, match="no source"):
        build_index(
            implementation_sha=IMPLEMENTATION_SHA,
            tooling_sha=TOOLING_SHA,
            implementation_ci=valid_ci(IMPLEMENTATION_SHA),
            tooling_ci=valid_ci(TOOLING_SHA),
            evidence_root=evidence_root,
            provenance=provenance,
            sources=source_specs[:-1],
            branch_protection_for="implementation",
        )


def test_artifact_manifest_rejects_self_hash_and_mismatch(tmp_path: Path) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "artifact_manifest.json"
    manifest.write_text(json.dumps({"artifact_hashes": {"report.json": "0" * 64}}), encoding="utf-8")
    with pytest.raises(Phase7ValidationError, match="mismatch"):
        validate_artifact_manifest(tmp_path)
    manifest.write_text(json.dumps({"artifact_hashes": {"artifact_manifest.json": file_sha256(manifest)}}), encoding="utf-8")
    with pytest.raises(Phase7ValidationError, match="self-hash"):
        validate_artifact_manifest(tmp_path)


def test_finalizer_receipt_must_match_real_exit_code(tmp_path: Path) -> None:
    receipt = write_receipt(tmp_path, name="finalize_phase7_verify")
    with pytest.raises(Phase7ValidationError, match="does not match"):
        validate_finalizer_receipt(receipt, expected_sha=TOOLING_SHA, actual_exit_code=1)


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def commit(root: Path, message: str) -> str:
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", message)
    return run_git(root, "rev-parse", "HEAD")


def test_publication_scope_ancestry_and_obsolete_values_are_fail_closed(tmp_path: Path) -> None:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.email", "test@example.invalid")
    run_git(tmp_path, "config", "user.name", "Phase 7 Test")
    (tmp_path / "README.md").write_text("initial", encoding="utf-8")
    tooling = commit(tmp_path, "tooling")
    final = tmp_path / "artifacts" / "architecture_v2_production_hardening" / "phase_07" / "final"
    final.mkdir(parents=True)
    (final / "report.json").write_text(json.dumps({"obsolete": "10e2260d5abae2660ddaa2d01becf65eedef1cbe"}), encoding="utf-8")
    evidence = commit(tmp_path, "evidence")
    assert git_commit_exists(tmp_path, tooling)
    assert is_ancestor(tmp_path, tooling, evidence)
    validate_commit_scope(tmp_path, evidence, prefix="artifacts/architecture_v2_production_hardening/phase_07/final/")
    with pytest.raises(Phase7ValidationError, match="obsolete"):
        validate_no_self_reference(tmp_path, evidence, "artifacts/architecture_v2_production_hardening/phase_07/final")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "unexpected.py").write_text("x = 1", encoding="utf-8")
    invalid_publication = commit(tmp_path, "bad publication")
    with pytest.raises(Phase7ValidationError, match="scope"):
        validate_commit_scope(tmp_path, invalid_publication, prefix="artifacts/architecture_v2_production_hardening/phase_07/final/")
    assert not git_commit_exists(tmp_path, "d" * 40)
    assert not is_ancestor(tmp_path, invalid_publication, tooling)


def test_every_require_flag_is_enforced_or_reported_not_required() -> None:
    args = build_parser().parse_args(
        [
            "verify",
            "--implementation-verified-sha", IMPLEMENTATION_SHA,
            "--verification-tooling-sha", TOOLING_SHA,
            "--source-evidence-index", "index.json",
            "--ci-validation-receipt", "ci.json",
            "--branch-protection-receipt", "bp.json",
            "--schema-validation-receipt", "schema.json",
            "--hash-validation-receipt", "hash.json",
            "--require-ci",
            "--require-python-matrix",
            "--require-frontend-matrix",
            "--require-postgresql",
            "--require-negative-injections",
            "--require-branch-protection",
            "--verify-artifact-hashes",
            "--verify-publication-ancestry",
            "--verify-publication-scope",
        ]
    )
    state = ValidationState(gates={})
    results = _require_flag_results(args, state)
    assert results["require_ci"] == "FAIL"
    assert results["require_tooling_ci"] == "NOT_REQUIRED"
    assert results["require_python_matrix"] == "FAIL"
    assert results["verify_publication_scope"] == "FAIL"
    assert state.errors


def test_finalizer_gate_evaluation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    canonical_final = PHASE_ROOT / "final"
    before = tree_snapshot(canonical_final)

    assert main(finalizer_args("verify", tmp_path / "evidence")) == 1
    capsys.readouterr()

    assert tree_snapshot(canonical_final) == before


def test_finalizer_build_writes_only_to_explicit_output_root(tmp_path: Path) -> None:
    output_dir = tmp_path / "finalized"
    canonical_final = PHASE_ROOT / "final"
    canonical_before = tree_snapshot(canonical_final)
    args = build_parser().parse_args(finalizer_args("build", tmp_path / "evidence", output_dir=output_dir))

    build_artifacts(args, ValidationState(source_index_sha256="c" * 64))

    assert {path.name for path in output_dir.glob("*.json")} == set(FINAL_JSON_ARTIFACTS)
    assert set(tree_snapshot(tmp_path)) == {
        f"finalized/{filename}" for filename in FINAL_JSON_ARTIFACTS
    }
    assert tree_snapshot(canonical_final) == canonical_before


def test_finalizer_build_requires_explicit_output_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    canonical_final = PHASE_ROOT / "final"
    before = tree_snapshot(canonical_final)

    assert main(finalizer_args("build", tmp_path / "evidence")) == 2
    capsys.readouterr()

    assert tree_snapshot(canonical_final) == before
