#!/usr/bin/env python3
"""Build and verify the Phase 7 publication chain from immutable evidence.

``build`` creates a candidate ``final/`` bundle before Commit E.  ``verify`` is
strictly read-only: it validates the source evidence, the T -> E -> A -> P
publication chain and the final artifacts.  Neither mode executes validation
commands, fabricates command receipts, calls the GitHub API, or supplies
defaults for evidence fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable, Mapping

from jsonschema import Draft7Validator, FormatChecker


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PHASE_ROOT = (
    REPOSITORY_ROOT
    / "artifacts"
    / "architecture_v2_production_hardening"
    / "phase_07"
)
RECEIPT_SCHEMA = REPOSITORY_ROOT / "scripts" / "schemas" / "command_receipt_v1.schema.json"
FINAL_ARTIFACT_SCHEMA = REPOSITORY_ROOT / "scripts" / "schemas" / "phase7_final_artifact_v1.schema.json"
SOURCE_INDEX_SCHEMA = REPOSITORY_ROOT / "scripts" / "schemas" / "phase7_source_evidence_index_v1.schema.json"

REQUIRED_PRODUCER_JOBS = (
    "artifact-protocol",
    "version-consistency",
    "architecture-boundaries",
    "python-unit-sqlite",
    "python-unit-windows",
    "python-integration-sqlite",
    "python-integration-postgres",
    "runtime-smoke",
    "cli-contract",
    "web-test",
    "web-test-windows",
    "desktop-test",
    "desktop-test-windows",
)
REQUIRED_STATUS_CONTEXTS = REQUIRED_PRODUCER_JOBS + ("final-evidence",)
REQUIRED_SOURCE_GATES = (
    "artifact_protocol",
    "version_authority",
    "architecture_integrity",
    "cli_truthfulness",
    "python_matrix",
    "frontend_matrix",
    "database_matrix",
    "runtime_smoke",
    "negative_injections",
    "branch_protection",
)
FINAL_JSON_ARTIFACTS = (
    "architecture_report.json",
    "artifact_manifest.json",
    "artifact_schema_report.json",
    "branch_protection_report.json",
    "ci_run_manifest.json",
    "cli_contract_report.json",
    "database_matrix.json",
    "environment_manifest.json",
    "final_verdict.json",
    "frontend_test_matrix.json",
    "negative_injection_report.json",
    "python_test_matrix.json",
    "runtime_smoke_report.json",
    "scaffold_report.json",
    "version_consistency_report.json",
    "version_manifest.json",
)
OBSOLETE_PUBLICATION_SHAS = (
    "10e2260d5abae2660ddaa2d01becf65eedef1cbe",
    "707009f",
    "ad7172ecbb86a5a43972649ae3c06891b25879b1",
    "bd2f99ce63da33256881e15cbd380258bd5de789",
    "cbf7257643d4a1705fa221ae37e9391b6ee3f40e",
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class Phase7ValidationError(ValueError):
    """Raised for any missing, malformed, or untraceable evidence."""


@dataclass(frozen=True)
class ReceiptReference:
    receipt_path: str
    receipt_sha256: str
    command_id: str
    exit_code: int
    result: str


@dataclass(frozen=True)
class SourceRecord:
    gate: str
    path: Path
    metadata: dict[str, Any]
    content: Any
    receipt: ReceiptReference | None = None


@dataclass
class ValidationState:
    errors: list[str] = field(default_factory=list)
    gates: dict[str, bool] = field(default_factory=dict)
    risks: dict[str, str] = field(default_factory=dict)
    receipt_references: list[ReceiptReference] = field(default_factory=list)
    source_index_sha256: str = ""
    implementation_ci: dict[str, Any] = field(default_factory=dict)
    tooling_ci: dict[str, Any] = field(default_factory=dict)
    publication: dict[str, bool] = field(default_factory=dict)

    def require(self, condition: bool, message: str) -> bool:
        if not condition:
            self.errors.append(message)
        return condition


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def load_json(path: Path, *, label: str | None = None) -> dict[str, Any]:
    """Load a JSON object; arrays and missing files are invalid evidence."""
    source = label or str(path)
    if not path.is_file():
        raise Phase7ValidationError(f"{source}: required JSON file is missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase7ValidationError(f"{source}: invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise Phase7ValidationError(f"{source}: JSON root must be an object")
    return value


def require_string(data: Mapping[str, Any], key: str, *, label: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise Phase7ValidationError(f"{label}: required non-empty string {key!r} is missing")
    return value


def require_sha(value: str, *, label: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise Phase7ValidationError(f"{label}: expected a 40-character lowercase SHA")
    return value


def _schema_validator(path: Path) -> Draft7Validator:
    schema = load_json(path, label=f"schema {path}")
    return Draft7Validator(schema, format_checker=FormatChecker())


def _validate_schema(value: Mapping[str, Any], schema: Draft7Validator, *, label: str) -> None:
    errors = sorted(schema.iter_errors(value), key=lambda error: list(error.absolute_path))
    if errors:
        details = "; ".join(
            f"{'.'.join(str(item) for item in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors
        )
        raise Phase7ValidationError(f"{label}: schema validation failed: {details}")


def resolve_evidence_path(root: Path, raw_path: str, *, label: str) -> Path:
    """Resolve a receipt/source relative path without traversal or symlink escape."""
    normalized = raw_path.replace("\\", "/")
    relative = Path(normalized)
    windows = PureWindowsPath(raw_path)
    if (
        not normalized
        or relative.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ".." in relative.parts
    ):
        raise Phase7ValidationError(f"{label}: path must be a traversal-free relative path")
    root_real = root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root_real)
    except ValueError as exc:
        raise Phase7ValidationError(f"{label}: path escapes evidence root") from exc
    return candidate


def _receipt_evidence_root(receipt_path: Path) -> Path:
    # run_command_receipt stores paths relative to the directory containing
    # ``receipts/``.  A receipt outside that layout is intentionally rejected.
    if receipt_path.parent.name != "receipts":
        raise Phase7ValidationError(
            f"{receipt_path}: receipt must be stored directly in a receipts directory"
        )
    return receipt_path.parent.parent


def validate_receipt(
    receipt_path: Path,
    *,
    expected_sha: str,
    receipt_schema: Draft7Validator | None = None,
) -> ReceiptReference:
    """Validate an immutable receipt and its persisted stdout/stderr bytes."""
    receipt_schema = receipt_schema or _schema_validator(RECEIPT_SCHEMA)
    receipt = load_json(receipt_path, label=f"receipt {receipt_path}")
    _validate_schema(receipt, receipt_schema, label=f"receipt {receipt_path}")

    command_id = require_string(receipt, "command_id", label=str(receipt_path))
    exit_code = receipt.get("exit_code")
    expected_codes = receipt.get("expected_exit_codes")
    result = require_string(receipt, "result", label=str(receipt_path))
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        raise Phase7ValidationError(f"receipt {receipt_path}: exit_code must be an integer")
    if not isinstance(expected_codes, list) or not expected_codes or not all(
        isinstance(code, int) and not isinstance(code, bool) for code in expected_codes
    ):
        raise Phase7ValidationError(f"receipt {receipt_path}: expected_exit_codes must be non-empty integers")
    expected_result = "SUCCESS" if exit_code in expected_codes else "FAILURE"
    if result != expected_result:
        raise Phase7ValidationError(
            f"receipt {receipt_path}: result {result!r} does not match exit_code {exit_code}"
        )
    if result != "SUCCESS":
        raise Phase7ValidationError(f"receipt {receipt_path}: command did not succeed")
    environment = receipt.get("environment")
    if not isinstance(environment, dict) or environment.get("git_sha") != expected_sha:
        raise Phase7ValidationError(
            f"receipt {receipt_path}: environment.git_sha does not match expected source SHA"
        )

    logs = receipt.get("log_paths")
    if not isinstance(logs, dict):
        raise Phase7ValidationError(f"receipt {receipt_path}: log_paths is required")
    root = _receipt_evidence_root(receipt_path)
    bytes_by_stream: dict[str, bytes] = {}
    for stream, log_field in (("stdout", "stdout_log"), ("stderr", "stderr_log")):
        raw = logs.get(log_field)
        if not isinstance(raw, str):
            raise Phase7ValidationError(f"receipt {receipt_path}: log_paths.{log_field} is required")
        log_path = resolve_evidence_path(root, raw, label=f"receipt {receipt_path} {log_field}")
        if not log_path.is_file():
            raise Phase7ValidationError(f"receipt {receipt_path}: {stream} log is missing")
        log_bytes = log_path.read_bytes()
        expected_hash = receipt.get(f"{stream}_sha256")
        if not isinstance(expected_hash, str) or file_sha256(log_path) != expected_hash:
            raise Phase7ValidationError(f"receipt {receipt_path}: {stream} log hash mismatch")
        bytes_by_stream[stream] = log_bytes
    combined = _sha256_bytes(bytes_by_stream["stdout"] + bytes_by_stream["stderr"])
    if receipt.get("output_sha256") != combined:
        raise Phase7ValidationError(f"receipt {receipt_path}: combined output hash mismatch")
    return ReceiptReference(
        receipt_path=str(receipt_path),
        receipt_sha256=file_sha256(receipt_path),
        command_id=command_id,
        exit_code=exit_code,
        result=result,
    )


def parse_pytest_xml(xml_path: Path) -> dict[str, int]:
    """Parse one real pytest XML report; absence and zero tests are failures."""
    if not xml_path.is_file():
        raise Phase7ValidationError(f"pytest XML is missing: {xml_path}")
    try:
        root = ET.parse(xml_path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise Phase7ValidationError(f"invalid pytest XML {xml_path}: {exc}") from exc
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise Phase7ValidationError(f"pytest XML has no testsuite: {xml_path}")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in totals:
            try:
                totals[key] += int(suite.attrib.get(key, 0))
            except ValueError as exc:
                raise Phase7ValidationError(f"pytest XML {xml_path}: {key} is not an integer") from exc
    if totals["tests"] <= 0:
        raise Phase7ValidationError(f"pytest XML has zero tests: {xml_path}")
    if totals["failures"] or totals["errors"]:
        raise Phase7ValidationError(
            f"pytest XML has failures/errors: {xml_path} ({totals['failures']}/{totals['errors']})"
        )
    return totals


def _source_kind(path: Path, metadata: Mapping[str, Any]) -> str:
    supplied = metadata.get("kind")
    if isinstance(supplied, str) and supplied:
        return supplied
    if path.suffix.lower() == ".xml":
        return "pytest_xml"
    if path.parent.name == "receipts" or "receipts" in path.parts:
        return "receipt"
    return "report"


def validate_source_entry(
    entry: Mapping[str, Any],
    *,
    gate: str,
    evidence_root: Path,
    expected_sha: str,
    expected_run_id: str,
    receipt_schema: Draft7Validator,
) -> SourceRecord:
    """Validate provenance, checksum and (where applicable) command receipt."""
    required = (
        "path",
        "sha256",
        "artifact_name",
        "github_artifact_id",
        "github_artifact_digest",
        "source_job",
        "source_job_id",
        "source_run_id",
        "source_head_sha",
    )
    missing = [name for name in required if name not in entry]
    if missing:
        raise Phase7ValidationError(f"source {gate}: missing fields {', '.join(missing)}")
    raw_path = require_string(entry, "path", label=f"source {gate}")
    path = resolve_evidence_path(evidence_root, raw_path, label=f"source {gate}")
    if not path.is_file():
        raise Phase7ValidationError(f"source {gate}: file is missing: {raw_path}")
    digest = require_string(entry, "sha256", label=f"source {gate}")
    if not SHA256_RE.fullmatch(digest) or file_sha256(path) != digest:
        raise Phase7ValidationError(f"source {gate}: SHA-256 mismatch for {raw_path}")
    require_string(entry, "artifact_name", label=f"source {gate}")
    artifact_digest = require_string(entry, "github_artifact_digest", label=f"source {gate}")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact_digest):
        raise Phase7ValidationError(f"source {gate}: github_artifact_digest is invalid")
    for identifier in ("github_artifact_id", "source_job_id"):
        value = entry.get(identifier)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise Phase7ValidationError(f"source {gate}: {identifier} must be a positive integer")
    require_string(entry, "source_job", label=f"source {gate}")
    if str(entry.get("source_run_id")) != expected_run_id:
        raise Phase7ValidationError(f"source {gate}: source_run_id does not match CI run")
    if entry.get("source_head_sha") != expected_sha:
        raise Phase7ValidationError(f"source {gate}: source_head_sha does not match expected SHA")

    kind = _source_kind(path, entry)
    content: Any = None
    receipt: ReceiptReference | None = None
    if kind == "receipt":
        receipt = validate_receipt(path, expected_sha=expected_sha, receipt_schema=receipt_schema)
    elif kind == "pytest_xml":
        content = parse_pytest_xml(path)
    elif path.suffix.lower() == ".json":
        content = load_json(path, label=f"source {gate} {raw_path}")
    else:
        content = {"path": raw_path}
    return SourceRecord(gate=gate, path=path, metadata=dict(entry), content=content, receipt=receipt)


def validate_ci_section(
    section: Mapping[str, Any],
    *,
    expected_sha: str,
    label: str,
) -> dict[str, Any]:
    """Require the explicit 13-producer plus final-evidence CI topology."""
    run_id = require_string(section, "run_id", label=label)
    run_attempt = require_string(section, "run_attempt", label=label)
    head_sha = require_sha(require_string(section, "head_sha", label=label), label=label)
    workflow_url = require_string(section, "workflow_url", label=label)
    if head_sha != expected_sha:
        raise Phase7ValidationError(f"{label}: head_sha does not match expected SHA")
    if not workflow_url.startswith("https://"):
        raise Phase7ValidationError(f"{label}: workflow_url must be HTTPS")
    aggregator = section.get("aggregator_job")
    if not isinstance(aggregator, dict):
        raise Phase7ValidationError(f"{label}: aggregator_job is required")
    if aggregator.get("name") != "final-evidence":
        raise Phase7ValidationError(f"{label}: aggregator_job must be final-evidence")
    if aggregator.get("conclusion") != "success":
        raise Phase7ValidationError(f"{label}: final-evidence conclusion is not success")
    if not isinstance(aggregator.get("job_id"), int) or aggregator["job_id"] <= 0:
        raise Phase7ValidationError(f"{label}: final-evidence job_id is invalid")
    producers = section.get("producer_jobs")
    if not isinstance(producers, list):
        raise Phase7ValidationError(f"{label}: producer_jobs is required")
    by_name: dict[str, Mapping[str, Any]] = {}
    for producer in producers:
        if not isinstance(producer, dict):
            raise Phase7ValidationError(f"{label}: producer_jobs entries must be objects")
        name = require_string(producer, "name", label=label)
        if name in by_name:
            raise Phase7ValidationError(f"{label}: duplicate producer job {name}")
        by_name[name] = producer
    if set(by_name) != set(REQUIRED_PRODUCER_JOBS):
        missing = sorted(set(REQUIRED_PRODUCER_JOBS) - set(by_name))
        unexpected = sorted(set(by_name) - set(REQUIRED_PRODUCER_JOBS))
        raise Phase7ValidationError(
            f"{label}: producer jobs must be exactly 13 canonical jobs; "
            f"missing={missing}, unexpected={unexpected}"
        )
    for name, producer in by_name.items():
        for field_name in ("job_id", "artifact_id"):
            value = producer.get(field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise Phase7ValidationError(f"{label}: {name}.{field_name} is invalid")
        if producer.get("conclusion") != "success":
            raise Phase7ValidationError(f"{label}: {name} conclusion is not success")
        if str(producer.get("run_id")) != run_id or str(producer.get("run_attempt")) != run_attempt:
            raise Phase7ValidationError(f"{label}: {name} run identity mismatch")
        if producer.get("head_sha") != expected_sha:
            raise Phase7ValidationError(f"{label}: {name} head SHA mismatch")
        require_string(producer, "artifact_name", label=f"{label} {name}")
        digest = require_string(producer, "artifact_digest", label=f"{label} {name}")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise Phase7ValidationError(f"{label}: {name} artifact_digest is invalid")
    return {
        "run_id": run_id,
        "run_attempt": run_attempt,
        "head_sha": head_sha,
        "workflow_url": workflow_url,
        "producer_jobs_passed": "13/13",
        "aggregator_job_status": "success",
    }


def _records_of_kind(records: Iterable[SourceRecord], kind: str) -> list[SourceRecord]:
    return [record for record in records if _source_kind(record.path, record.metadata) == kind]


def _report_passes(record: SourceRecord) -> bool:
    content = record.content
    if not isinstance(content, dict):
        return False
    if content.get("verdict") == "PASS" or content.get("status") in {"PASS", "SUCCESS"}:
        return True
    return content.get("checks_passed") is True or content.get("result") == "SUCCESS"


def _nested_values(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            if child_key == key:
                found.append(child_value)
            found.extend(_nested_values(child_value, key))
    elif isinstance(value, list):
        for item in value:
            found.extend(_nested_values(item, key))
    return found


def _gate_records_valid(records: list[SourceRecord]) -> bool:
    return bool(records) and all(
        record.receipt is not None or record.content is not None for record in records
    )


def evaluate_source_gates(
    source_map: Mapping[str, list[SourceRecord]],
    *,
    state: ValidationState,
    allowed_bypass_actors: set[str],
) -> None:
    """Derive every evidence gate from receipts, reports, and pytest XMLs."""
    for name in REQUIRED_SOURCE_GATES:
        if not _gate_records_valid(source_map.get(name, [])):
            state.errors.append(f"source gate {name}: no valid source evidence")

    artifact = source_map.get("artifact_protocol", [])
    neg = source_map.get("negative_injections", [])
    negative_receipts = [record for record in neg if record.receipt]
    negative_ok = len(negative_receipts) == 9
    if negative_ok:
        # A receipt for a negative test is successful only when the injected
        # command itself returned a non-zero expected exit code.
        negative_ok = all(record.receipt and record.receipt.exit_code != 0 for record in negative_receipts)
    state.gates["artifact_protocol"] = (
        _gate_records_valid(artifact)
        and any(record.receipt for record in artifact)
        and any(_report_passes(record) for record in artifact if record.content)
        and negative_ok
    )
    state.gates["negative_injections"] = negative_ok

    version = source_map.get("version_authority", [])
    state.gates["version_authority"] = (
        _gate_records_valid(version)
        and any(record.receipt for record in version)
        and any(_report_passes(record) for record in version if record.content)
    )

    architecture = source_map.get("architecture_integrity", [])
    architecture_reports = [record for record in architecture if isinstance(record.content, dict)]
    violations = [value for record in architecture_reports for value in _nested_values(record.content, "violations")]
    state.gates["architecture_integrity"] = (
        _gate_records_valid(architecture)
        and any(record.receipt for record in architecture)
        and any(_report_passes(record) for record in architecture_reports)
        and bool(violations)
        and all(value == 0 for value in violations)
    )

    cli = source_map.get("cli_truthfulness", [])
    cli_xml = _records_of_kind(cli, "pytest_xml")
    cli_reports = [record for record in cli if isinstance(record.content, dict)]
    state.gates["cli_truthfulness"] = (
        _gate_records_valid(cli)
        and bool(cli_xml)
        and any(record.receipt for record in cli)
        and any(_report_passes(record) for record in cli_reports)
    )

    python = source_map.get("python_matrix", [])
    python_xml = _records_of_kind(python, "pytest_xml")
    skip_reports = [record for record in python if "skip" in record.path.name.lower()]
    skipped = sum(int(record.content.get("skipped", 0)) for record in python_xml if isinstance(record.content, dict))
    state.gates["python_matrix"] = (
        _gate_records_valid(python)
        and len(python_xml) >= 5
        and any(record.receipt for record in python)
        and (skipped == 0 or any(_report_passes(record) for record in skip_reports))
    )

    frontend = source_map.get("frontend_matrix", [])
    frontend_receipts = [record for record in frontend if record.receipt]
    state.gates["frontend_matrix"] = _gate_records_valid(frontend) and len(frontend_receipts) >= 16

    database = source_map.get("database_matrix", [])
    database_reports = [record for record in database if isinstance(record.content, dict)]
    serialized_database = "\n".join(json.dumps(record.content, sort_keys=True) for record in database_reports).lower()
    state.gates["database_matrix"] = (
        _gate_records_valid(database)
        and len([record for record in database if record.receipt]) >= 3
        and "postgres" in serialized_database
        and "sqlite fallback" not in serialized_database
        and "sqlite://" not in serialized_database
    )

    runtime = source_map.get("runtime_smoke", [])
    state.gates["runtime_smoke"] = (
        _gate_records_valid(runtime)
        and any(record.receipt for record in runtime)
        and any(_report_passes(record) for record in runtime if record.content)
    )

    branch = source_map.get("branch_protection", [])
    branch_reports = [record for record in branch if isinstance(record.content, dict)]
    state.gates["branch_protection_verified"] = (
        _gate_records_valid(branch)
        and any(record.receipt for record in branch)
        and any(validate_branch_protection_report(record.content, allowed_bypass_actors) for record in branch_reports)
    )


def _enabled(value: Any) -> bool:
    return value is True or (isinstance(value, dict) and value.get("enabled") is True)


def validate_branch_protection_report(
    report: Mapping[str, Any], allowed_bypass_actors: set[str] | None = None
) -> bool:
    """Validate a persisted API response; this function never contacts GitHub."""
    allowed_bypass_actors = allowed_bypass_actors or set()
    payload = report.get("api_response", report)
    if not isinstance(payload, dict):
        return False
    repository = report.get("repository", payload.get("repository"))
    branch = report.get("branch", payload.get("branch"))
    timestamp = report.get("response_timestamp", payload.get("response_timestamp"))
    principal = report.get("authenticated_principal", payload.get("authenticated_principal"))
    checks = payload.get("required_status_checks", {})
    contexts = checks.get("contexts", []) if isinstance(checks, dict) else []
    bypass = payload.get("bypass_actors", report.get("bypass_actors", []))
    if not isinstance(contexts, list) or not isinstance(bypass, list):
        return False
    bypass_names = {
        actor if isinstance(actor, str) else actor.get("login")
        for actor in bypass
        if isinstance(actor, (str, dict))
    }
    bypass_names.discard(None)
    return bool(
        isinstance(repository, str)
        and repository
        and branch == "main"
        and isinstance(timestamp, str)
        and timestamp
        and isinstance(principal, str)
        and principal
        and checks.get("strict") is True
        and set(contexts) == set(REQUIRED_STATUS_CONTEXTS)
        and _enabled(payload.get("enforce_admins"))
        and not _enabled(payload.get("allow_force_pushes"))
        and not _enabled(payload.get("allow_deletions"))
        and bypass_names.issubset(allowed_bypass_actors)
    )


def _load_source_index(
    path: Path,
    *,
    evidence_root: Path,
    implementation_sha: str,
    tooling_sha: str,
    receipt_schema: Draft7Validator,
    source_index_schema: Draft7Validator,
    state: ValidationState,
) -> dict[str, list[SourceRecord]]:
    index = load_json(path, label="source evidence index")
    _validate_schema(index, source_index_schema, label="source evidence index")
    state.source_index_sha256 = file_sha256(path)
    if index.get("implementation_verified_sha") != implementation_sha:
        raise Phase7ValidationError("source evidence index: implementation_verified_sha mismatch")
    if index.get("verification_tooling_verified_sha") != tooling_sha:
        raise Phase7ValidationError("source evidence index: verification_tooling_verified_sha mismatch")
    implementation_ci = index.get("implementation_ci")
    tooling_ci = index.get("tooling_ci")
    if not isinstance(implementation_ci, dict) or not isinstance(tooling_ci, dict):
        raise Phase7ValidationError("source evidence index: implementation_ci and tooling_ci are required")
    state.implementation_ci = validate_ci_section(
        implementation_ci, expected_sha=implementation_sha, label="implementation CI"
    )
    state.tooling_ci = validate_ci_section(tooling_ci, expected_sha=tooling_sha, label="tooling CI")
    sources = index.get("sources")
    if not isinstance(sources, dict):
        raise Phase7ValidationError("source evidence index: sources is required")
    source_map: dict[str, list[SourceRecord]] = {}
    for gate in REQUIRED_SOURCE_GATES:
        entries = sources.get(gate)
        if not isinstance(entries, list) or not entries:
            raise Phase7ValidationError(f"source evidence index: sources.{gate} must be non-empty")
        # Source artifacts prove the implementation run unless they explicitly
        # prove the tooling CI job; neither run gets a hidden default.
        expected_sha = tooling_sha if gate == "branch_protection" and index.get("branch_protection_for") == "tooling" else implementation_sha
        expected_run_id = str(
            state.tooling_ci["run_id"] if expected_sha == tooling_sha else state.implementation_ci["run_id"]
        )
        source_map[gate] = [
            validate_source_entry(
                entry,
                gate=gate,
                evidence_root=evidence_root,
                expected_sha=expected_sha,
                expected_run_id=expected_run_id,
                receipt_schema=receipt_schema,
            )
            for entry in entries
            if isinstance(entry, dict)
        ]
        if len(source_map[gate]) != len(entries):
            raise Phase7ValidationError(f"source evidence index: sources.{gate} entries must be objects")
    return source_map


def validate_artifact_manifest(final_dir: Path) -> None:
    manifest_path = final_dir / "artifact_manifest.json"
    manifest = load_json(manifest_path, label="artifact manifest")
    hashes = manifest.get("artifact_hashes")
    if not isinstance(hashes, dict) or not hashes:
        raise Phase7ValidationError("artifact manifest: artifact_hashes is required")
    if "artifact_manifest.json" in hashes:
        raise Phase7ValidationError("artifact manifest must not self-hash")
    for raw_path, expected_hash in hashes.items():
        if not isinstance(raw_path, str) or not isinstance(expected_hash, str):
            raise Phase7ValidationError("artifact manifest: invalid hash entry")
        if not SHA256_RE.fullmatch(expected_hash):
            raise Phase7ValidationError(f"artifact manifest: invalid hash for {raw_path}")
        artifact = resolve_evidence_path(final_dir, raw_path, label="artifact manifest")
        if not artifact.is_file() or file_sha256(artifact) != expected_hash:
            raise Phase7ValidationError(f"artifact manifest hash mismatch: {raw_path}")


def validate_final_artifacts(final_dir: Path, *, schema: Draft7Validator) -> None:
    if not final_dir.is_dir():
        raise Phase7ValidationError(f"final artifact directory is missing: {final_dir}")
    for filename in FINAL_JSON_ARTIFACTS:
        artifact = final_dir / filename
        value = load_json(artifact, label=f"final artifact {filename}")
        _validate_schema(value, schema, label=f"final artifact {filename}")
    validate_artifact_manifest(final_dir)


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, timeout=15, check=False
        )
    except OSError as exc:
        raise Phase7ValidationError(f"git invocation failed: {exc}") from exc
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise Phase7ValidationError(f"git {' '.join(args)} failed: {message}")
    return result.stdout.strip()


def _git_bytes(root: Path, *args: str) -> bytes:
    """Read an exact Git object payload without newline normalization."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, timeout=15, check=False
        )
    except OSError as exc:
        raise Phase7ValidationError(f"git invocation failed: {exc}") from exc
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip() or "unknown git error"
        raise Phase7ValidationError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def git_commit_exists(root: Path, sha: str) -> bool:
    try:
        _git(root, "cat-file", "-e", f"{sha}^{{commit}}")
    except Phase7ValidationError:
        return False
    return True


def is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    return result.returncode == 0


def changed_files(root: Path, commit: str) -> set[str]:
    parent = _git(root, "rev-parse", f"{commit}^")
    output = _git(root, "diff", "--name-only", parent, commit)
    return {line.replace("\\", "/") for line in output.splitlines() if line}


def validate_commit_scope(root: Path, commit: str, *, allowed: set[str] | None = None, prefix: str | None = None) -> None:
    files = changed_files(root, commit)
    if not files:
        raise Phase7ValidationError(f"commit {commit}: no changed files")
    valid = all(path in allowed for path in files) if allowed is not None else all(
        prefix is not None and path.startswith(prefix) for path in files
    )
    if not valid:
        raise Phase7ValidationError(f"commit {commit}: publication scope is invalid: {sorted(files)}")


def _contains_value(value: Any, needle: str) -> bool:
    if isinstance(value, dict):
        return any(_contains_value(child, needle) for child in value.values())
    if isinstance(value, list):
        return any(_contains_value(child, needle) for child in value)
    return value == needle


def _tree_json_values(root: Path, commit: str, prefix: str) -> list[tuple[str, Any]]:
    paths = _git(root, "ls-tree", "-r", "--name-only", commit, prefix).splitlines()
    values: list[tuple[str, Any]] = []
    for path in paths:
        if not path.endswith(".json"):
            continue
        raw = _git(root, "show", f"{commit}:{path}")
        try:
            values.append((path, json.loads(raw)))
        except json.JSONDecodeError as exc:
            raise Phase7ValidationError(f"{commit}:{path}: invalid JSON") from exc
    return values


def validate_no_self_reference(root: Path, commit: str, prefix: str) -> None:
    for path, value in _tree_json_values(root, commit, prefix):
        if _contains_value(value, commit):
            raise Phase7ValidationError(f"{commit}:{path}: contains a self-referential commit SHA")
        rendered = json.dumps(value, sort_keys=True)
        obsolete = [sha for sha in OBSOLETE_PUBLICATION_SHAS if sha in rendered]
        if obsolete:
            raise Phase7ValidationError(f"{commit}:{path}: contains obsolete publication SHA(s) {obsolete}")


def validate_finalizer_receipt(
    receipt_path: Path, *, expected_sha: str, actual_exit_code: int
) -> ReceiptReference:
    """Check the externally generated finalizer receipt against the real exit code.

    The receipt is intentionally not consumed by ``verify`` itself: it is
    generated *after* this process exits by ``run_command_receipt.py``.  This
    helper is used by the lightweight publication-integrity job.
    """
    reference = validate_receipt(receipt_path, expected_sha=expected_sha)
    if reference.exit_code != actual_exit_code:
        raise Phase7ValidationError(
            "finalizer receipt exit_code does not match the recorded execution exit code"
        )
    return reference


def validate_publication_chain(
    *,
    root: Path,
    implementation_sha: str,
    tooling_sha: str,
    evidence_sha: str,
    attestation_sha: str,
    pointer_sha: str,
    state: ValidationState,
) -> None:
    for label, sha in (("tooling", tooling_sha), ("evidence", evidence_sha), ("attestation", attestation_sha), ("pointer", pointer_sha)):
        if not git_commit_exists(root, sha):
            raise Phase7ValidationError(f"publication chain: {label} commit does not exist: {sha}")
    if not is_ancestor(root, tooling_sha, evidence_sha):
        raise Phase7ValidationError("publication chain: evidence commit is not a descendant of tooling commit")
    if not is_ancestor(root, evidence_sha, attestation_sha):
        raise Phase7ValidationError("publication chain: attestation commit is not a descendant of evidence commit")
    if not is_ancestor(root, attestation_sha, pointer_sha):
        raise Phase7ValidationError("publication chain: pointer commit is not a descendant of attestation commit")
    phase_prefix = "artifacts/architecture_v2_production_hardening/phase_07/"
    validate_commit_scope(root, evidence_sha, prefix=phase_prefix + "final/")
    validate_commit_scope(
        root,
        attestation_sha,
        allowed={
            phase_prefix + "attestation.json",
            phase_prefix + "phase_verdict.md",
            phase_prefix + "risk_register.md",
        },
    )
    validate_commit_scope(root, pointer_sha, allowed={phase_prefix + "AUTHORITATIVE_POINTER.json"})
    validate_no_self_reference(root, evidence_sha, phase_prefix + "final")
    validate_no_self_reference(root, attestation_sha, phase_prefix)
    validate_no_self_reference(root, pointer_sha, phase_prefix)

    attestation = json.loads(_git(root, "show", f"{attestation_sha}:{phase_prefix}attestation.json"))
    pointer = json.loads(_git(root, "show", f"{pointer_sha}:{phase_prefix}AUTHORITATIVE_POINTER.json"))
    if not isinstance(attestation, dict) or not isinstance(pointer, dict):
        raise Phase7ValidationError("publication chain: attestation and pointer must be JSON objects")
    expected_attestation = {
        "implementation_verified_sha": implementation_sha,
        "verification_tooling_verified_sha": tooling_sha,
        "evidence_bundle_commit_sha": evidence_sha,
        "verdict": "PHASE_7_VERSION_DOCUMENTATION_VERDICT_CONVERGED",
        "promotion_readiness": "READY_FOR_MAIN_PROMOTION",
        "manual_override": False,
    }
    for field_name, expected in expected_attestation.items():
        if attestation.get(field_name) != expected:
            raise Phase7ValidationError(f"publication chain: attestation {field_name} mismatch")
    if not isinstance(attestation.get("evidence_manifest_sha256"), str) or not SHA256_RE.fullmatch(attestation["evidence_manifest_sha256"]):
        raise Phase7ValidationError("publication chain: attestation evidence_manifest_sha256 is invalid")
    if pointer.get("attestation_commit_sha") != attestation_sha or pointer.get("evidence_bundle_commit_sha") != evidence_sha:
        raise Phase7ValidationError("publication chain: pointer does not reference attestation/evidence commit")
    if pointer.get("verification_tooling_verified_sha") != tooling_sha or pointer.get("implementation_verified_sha") != implementation_sha:
        raise Phase7ValidationError("publication chain: pointer source SHA mismatch")
    if pointer.get("status") != "AUTHORITATIVE_CURRENT":
        raise Phase7ValidationError("publication chain: pointer is not authoritative current")
    manifest_payload = _git_bytes(
        root, "show", f"{evidence_sha}:{phase_prefix}final/artifact_manifest.json"
    )
    manifest_hash = _sha256_bytes(manifest_payload)
    if attestation.get("evidence_manifest_sha256") != manifest_hash:
        raise Phase7ValidationError("publication chain: attestation manifest hash mismatch")
    if _git(root, "rev-parse", "HEAD") != pointer_sha:
        raise Phase7ValidationError("publication chain: verify must run from the authoritative pointer commit")
    state.publication = {"ancestry": True, "scope": True, "self_reference": False}


def clean_worktree(root: Path) -> bool:
    return not _git(root, "status", "--porcelain").strip()


def derive_risks(state: ValidationState) -> dict[str, str]:
    gates = state.gates
    publication_ok = state.publication.get("ancestry", False) and state.publication.get("scope", False)
    risks = {
        "R11": "CLOSED" if gates.get("schema_validation") and gates.get("hash_validation") else "OPEN",
        "R12": "CLOSED" if publication_ok and gates.get("hash_validation") else "OPEN",
        "R13": "CLOSED" if gates.get("receipt_integrity") else "OPEN",
        "R14": "CLOSED" if gates.get("architecture_integrity") and gates.get("cli_truthfulness") else "OPEN",
        "R15": "CLOSED" if gates.get("cli_truthfulness") and gates.get("runtime_smoke") else "OPEN",
        "R16": "CLOSED" if gates.get("implementation_ci") and gates.get("tooling_ci") and gates.get("python_matrix") and gates.get("frontend_matrix") and gates.get("database_matrix") else "OPEN",
        "R17": "CLOSED" if publication_ok else "OPEN",
        "R18": "CLOSED" if gates.get("branch_protection_verified") else "OPEN",
    }
    state.risks = risks
    return risks


def _receipt_inputs(args: argparse.Namespace) -> tuple[Path, ...]:
    return (
        args.ci_validation_receipt,
        args.branch_protection_receipt,
        args.schema_validation_receipt,
        args.hash_validation_receipt,
    )


def evaluate(
    args: argparse.Namespace,
    *,
    require_publication: bool,
) -> ValidationState:
    """Evaluate all inputs, collecting every independently discoverable error."""
    state = ValidationState()
    implementation_sha = require_sha(args.implementation_verified_sha, label="implementation SHA")
    tooling_sha = require_sha(args.verification_tooling_sha, label="tooling SHA")
    receipt_schema = _schema_validator(args.receipt_schema)
    final_schema = _schema_validator(args.final_artifact_schema)
    source_index_schema = _schema_validator(args.source_index_schema)

    for receipt_path in _receipt_inputs(args):
        try:
            reference = validate_receipt(receipt_path, expected_sha=tooling_sha, receipt_schema=receipt_schema)
            state.receipt_references.append(reference)
        except Phase7ValidationError as exc:
            state.errors.append(str(exc))
    state.gates["receipt_integrity"] = len(state.receipt_references) == 4
    state.gates["schema_validation"] = any(
        reference.command_id.startswith("schema") or "schema" in reference.command_id
        for reference in state.receipt_references
    )
    state.gates["hash_validation"] = any(
        reference.command_id.startswith("hash") or "hash" in reference.command_id
        for reference in state.receipt_references
    )
    # The explicit input path, not a command-id convention, remains authoritative.
    state.gates["schema_validation"] = state.gates["schema_validation"] or any(
        path == args.schema_validation_receipt for path in _receipt_inputs(args) if path.is_file()
    ) and state.gates["receipt_integrity"]
    state.gates["hash_validation"] = state.gates["hash_validation"] or any(
        path == args.hash_validation_receipt for path in _receipt_inputs(args) if path.is_file()
    ) and state.gates["receipt_integrity"]

    try:
        source_map = _load_source_index(
            args.source_evidence_index,
            evidence_root=args.evidence_root,
            implementation_sha=implementation_sha,
            tooling_sha=tooling_sha,
            receipt_schema=receipt_schema,
            source_index_schema=source_index_schema,
            state=state,
        )
        evaluate_source_gates(
            source_map,
            state=state,
            allowed_bypass_actors=set(args.allow_bypass_actor),
        )
        state.gates["implementation_ci"] = True
        state.gates["tooling_ci"] = True
    except Phase7ValidationError as exc:
        state.errors.append(str(exc))
        for gate in REQUIRED_SOURCE_GATES:
            state.gates.setdefault(gate, False)
        state.gates["implementation_ci"] = False
        state.gates["tooling_ci"] = False

    if require_publication:
        try:
            validate_publication_chain(
                root=args.repository_root,
                implementation_sha=implementation_sha,
                tooling_sha=tooling_sha,
                evidence_sha=args.evidence_bundle_commit_sha,
                attestation_sha=args.attestation_commit_sha,
                pointer_sha=args.authoritative_pointer_commit_sha,
                state=state,
            )
            final_dir = args.repository_root / "artifacts" / "architecture_v2_production_hardening" / "phase_07" / "final"
            validate_final_artifacts(final_dir, schema=final_schema)
            state.gates["publication_ancestry"] = True
            state.gates["publication_scope"] = True
            state.gates["artifact_hashes"] = True
            state.gates["final_artifact_schema"] = True
        except Phase7ValidationError as exc:
            state.errors.append(str(exc))
            for gate in ("publication_ancestry", "publication_scope", "artifact_hashes", "final_artifact_schema"):
                state.gates[gate] = False
    else:
        state.gates.update(
            {
                "publication_ancestry": False,
                "publication_scope": False,
                "artifact_hashes": False,
                "final_artifact_schema": False,
            }
        )
    if args.require_clean_worktree and not clean_worktree(args.repository_root):
        state.errors.append("worktree is not clean")
    derive_risks(state)
    return state


def quality_gates(state: ValidationState) -> dict[str, bool]:
    return {
        "G7.1": state.gates.get("final_artifact_schema", False),
        "G7.2": state.gates.get("artifact_hashes", False) and state.gates.get("receipt_integrity", False),
        "G7.3": state.gates.get("implementation_ci", False) and state.gates.get("tooling_ci", False),
        "G7.4": state.gates.get("implementation_ci", False) and state.gates.get("tooling_ci", False),
        "G7.5": state.gates.get("publication_ancestry", False) and state.gates.get("publication_scope", False),
        "G7.6": state.gates.get("receipt_integrity", False) and not state.errors,
        "G7.7": all(status == "CLOSED" for status in state.risks.values()),
    }


def _require_flag_results(args: argparse.Namespace, state: ValidationState) -> dict[str, str]:
    checks = {
        "require_ci": (args.require_ci, state.gates.get("implementation_ci") and state.gates.get("tooling_ci")),
        "require_tooling_ci": (args.require_tooling_ci, state.gates.get("tooling_ci")),
        "require_python_matrix": (args.require_python_matrix, state.gates.get("python_matrix")),
        "require_frontend_matrix": (args.require_frontend_matrix, state.gates.get("frontend_matrix")),
        "require_postgresql": (args.require_postgresql, state.gates.get("database_matrix")),
        "require_negative_injections": (args.require_negative_injections, state.gates.get("negative_injections")),
        "require_branch_protection": (args.require_branch_protection, state.gates.get("branch_protection_verified")),
        "verify_artifact_hashes": (args.verify_artifact_hashes, state.gates.get("artifact_hashes")),
        "verify_publication_ancestry": (args.verify_publication_ancestry, state.gates.get("publication_ancestry")),
        "verify_publication_scope": (args.verify_publication_scope, state.gates.get("publication_scope")),
    }
    outcome: dict[str, str] = {}
    for name, (required, passed) in checks.items():
        if not required:
            outcome[name] = "NOT_REQUIRED"
        elif passed:
            outcome[name] = "PASS"
        else:
            outcome[name] = "FAIL"
            state.errors.append(f"required flag --{name.replace('_', '-')} was not satisfied")
    for priority in args.fail_on_open_risk:
        for risk, status in state.risks.items():
            if status != "CLOSED" and risk in {"R11", "R12", "R13", "R17"} and priority == "P0":
                state.errors.append(f"open P0 risk: {risk}")
            if status != "CLOSED" and risk in {"R14", "R15", "R16", "R18"} and priority == "P1":
                state.errors.append(f"open P1 risk: {risk}")
    return outcome


def build_artifacts(args: argparse.Namespace, state: ValidationState) -> None:
    """Write a pre-Commit-E evidence bundle; never writes a commit SHA of itself."""
    output_dir = args.output_dir
    if output_dir.exists() and any(output_dir.iterdir()):
        raise Phase7ValidationError(f"build output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "phase7_artifact_version": "1.0.0",
        "implementation_verified_sha": args.implementation_verified_sha,
        "verification_tooling_verified_sha": args.verification_tooling_sha,
        "publication_model": "external_commit_attestation",
        "source_evidence_index_sha256": state.source_index_sha256,
        "receipt_references": [reference.__dict__ for reference in state.receipt_references],
        "gates": state.gates,
        "risks": state.risks,
    }
    for filename in FINAL_JSON_ARTIFACTS:
        if filename == "artifact_manifest.json":
            continue
        artifact_type = filename.removesuffix(".json")
        payload = {
            **base,
            "artifact_type": artifact_type,
            "results": {"source_backed": True, "gate": state.gates.get(artifact_type, None)},
            "verdict": "PASS" if not state.errors else "BLOCKED",
        }
        if filename == "final_verdict.json":
            payload["results"] = {
                "verdict_name": "PHASE_7_FINAL_EVIDENCE_BLOCKED",
                "promotion_readiness": "NOT_READY_FOR_MAIN_PROMOTION",
                "manual_override": False,
                "quality_gates": quality_gates(state),
            }
        (output_dir / filename).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    hashes = {
        path.name: file_sha256(path)
        for path in sorted(output_dir.glob("*.json"))
        if path.name != "artifact_manifest.json"
    }
    manifest = {
        **base,
        "artifact_type": "artifact_manifest",
        "artifact_hashes": hashes,
        "results": {"total_files": len(hashes)},
        "verdict": "PASS" if not state.errors else "BLOCKED",
    }
    (output_dir / "artifact_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def render_report(args: argparse.Namespace, state: ValidationState, flag_results: Mapping[str, str]) -> dict[str, Any]:
    quality = quality_gates(state)
    successful = not state.errors and all(quality.values())
    return {
        "branch": _git(args.repository_root, "branch", "--show-current"),
        "worktree_clean": clean_worktree(args.repository_root),
        "implementation_verified_sha": args.implementation_verified_sha,
        "implementation_ci_run_id": state.implementation_ci.get("run_id"),
        "implementation_ci_url": state.implementation_ci.get("workflow_url"),
        "verification_tooling_verified_sha": args.verification_tooling_sha,
        "tooling_ci_run_id": state.tooling_ci.get("run_id"),
        "tooling_ci_url": state.tooling_ci.get("workflow_url"),
        "evidence_bundle_commit_sha": getattr(args, "evidence_bundle_commit_sha", None),
        "attestation_commit_sha": getattr(args, "attestation_commit_sha", None),
        "authoritative_pointer_commit_sha": getattr(args, "authoritative_pointer_commit_sha", None),
        "authoritative_tag": None,
        "publication_ancestry_verified": state.gates.get("publication_ancestry", False),
        "publication_scope_verified": state.gates.get("publication_scope", False),
        "self_reference_detected": state.publication.get("self_reference", True),
        "producer_jobs_passed": {
            "implementation": state.implementation_ci.get("producer_jobs_passed"),
            "tooling": state.tooling_ci.get("producer_jobs_passed"),
        },
        "aggregator_job_status": {
            "implementation": state.implementation_ci.get("aggregator_job_status"),
            "tooling": state.tooling_ci.get("aggregator_job_status"),
        },
        "branch_protection_verified": state.gates.get("branch_protection_verified", False),
        "finalizer_verify_receipt_path": None,
        "finalizer_verify_receipt_sha256": None,
        "finalizer_exit_code": 0 if successful else 1,
        "schema_validation": state.gates.get("schema_validation", False),
        "hash_validation": state.gates.get("hash_validation", False),
        "required_flags": dict(flag_results),
        "gates": quality,
        "risks": state.risks,
        "errors": state.errors,
        "final_verdict": (
            "PHASE_7_VERSION_DOCUMENTATION_VERDICT_CONVERGED"
            if successful
            else "PHASE_7_FINAL_EVIDENCE_BLOCKED"
        ),
        "promotion_status": "READY_FOR_MAIN_PROMOTION" if successful else "NOT_READY_FOR_MAIN_PROMOTION",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or verify Phase 7 source-backed evidence")
    parser.add_argument("mode", choices=("build", "verify"), nargs="?", default="verify")
    parser.add_argument("--implementation-verified-sha", required=True)
    parser.add_argument("--verification-tooling-sha", required=True)
    parser.add_argument("--evidence-bundle-commit-sha")
    parser.add_argument("--attestation-commit-sha")
    parser.add_argument("--authoritative-pointer-commit-sha")
    parser.add_argument("--source-evidence-index", type=Path, required=True)
    parser.add_argument("--ci-validation-receipt", type=Path, required=True)
    parser.add_argument("--branch-protection-receipt", type=Path, required=True)
    parser.add_argument("--schema-validation-receipt", type=Path, required=True)
    parser.add_argument("--hash-validation-receipt", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--receipt-schema", type=Path, default=RECEIPT_SCHEMA)
    parser.add_argument("--final-artifact-schema", type=Path, default=FINAL_ARTIFACT_SCHEMA)
    parser.add_argument("--source-index-schema", type=Path, default=SOURCE_INDEX_SCHEMA)
    parser.add_argument("--allow-bypass-actor", action="append", default=[])
    parser.add_argument("--require-clean-worktree", action="store_true")
    parser.add_argument("--require-ci", action="store_true")
    parser.add_argument("--require-tooling-ci", action="store_true")
    parser.add_argument("--require-python-matrix", action="store_true")
    parser.add_argument("--require-frontend-matrix", action="store_true")
    parser.add_argument("--require-postgresql", action="store_true")
    parser.add_argument("--require-negative-injections", action="store_true")
    parser.add_argument("--require-branch-protection", action="store_true")
    parser.add_argument("--verify-artifact-hashes", action="store_true")
    parser.add_argument("--verify-publication-ancestry", action="store_true")
    parser.add_argument("--verify-publication-scope", action="store_true")
    parser.add_argument("--fail-on-open-risk", choices=("P0", "P1"), action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.evidence_root = args.evidence_root.resolve()
    args.repository_root = args.repository_root.resolve()
    if args.mode == "build" and args.output_dir is None:
        print("ERROR: build mode requires --output-dir", file=sys.stderr)
        return 2
    if args.mode == "verify":
        required = {
            "--evidence-bundle-commit-sha": args.evidence_bundle_commit_sha,
            "--attestation-commit-sha": args.attestation_commit_sha,
            "--authoritative-pointer-commit-sha": args.authoritative_pointer_commit_sha,
        }
        missing = [flag for flag, value in required.items() if not value]
        if missing:
            print(f"ERROR: verify mode requires {', '.join(missing)}", file=sys.stderr)
            return 2
    try:
        state = evaluate(args, require_publication=args.mode == "verify")
        flags = _require_flag_results(args, state)
        if args.mode == "build" and not state.errors:
            build_artifacts(args, state)
        report = render_report(args, state, flags)
    except Phase7ValidationError as exc:
        report = {
            "errors": [str(exc)],
            "final_verdict": "PHASE_7_FINAL_EVIDENCE_BLOCKED",
            "promotion_status": "NOT_READY_FOR_MAIN_PROMOTION",
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["final_verdict"] == "PHASE_7_VERSION_DOCUMENTATION_VERDICT_CONVERGED":
        print("PHASE_7_VERSION_DOCUMENTATION_VERDICT_CONVERGED")
        print("READY_FOR_MAIN_PROMOTION")
        return 0
    print("PHASE_7_FINAL_EVIDENCE_BLOCKED")
    print("NOT_READY_FOR_MAIN_PROMOTION")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
