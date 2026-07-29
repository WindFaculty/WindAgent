#!/usr/bin/env python3
"""Validate downloaded CI job evidence and write a fail-closed run manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _find_job_root(download_root: Path, job: str) -> Path:
    artifact_root = download_root / f"{job}-evidence"
    candidates = [
        artifact_root,
        artifact_root / "artifacts" / "ci" / job,
        download_root / job,
    ]
    for candidate in candidates:
        if (candidate / "receipts").is_dir():
            return candidate
    evidence_bundle_roots = [
        path.parent
        for path in artifact_root.rglob("evidence_bundle.json")
        if (path.parent / "receipts").is_dir()
    ] if artifact_root.is_dir() else []
    if len(evidence_bundle_roots) == 1:
        return evidence_bundle_roots[0]
    if len(evidence_bundle_roots) > 1:
        raise RuntimeError(
            f"Multiple evidence bundles found for required job {job!r}"
        )
    artifact_root = download_root / f"{job}-evidence"
    nested_receipts = (
        sorted(artifact_root.rglob("receipts"))
        if artifact_root.is_dir()
        else []
    )
    if len(nested_receipts) == 1:
        return nested_receipts[0].parent
    raise FileNotFoundError(
        f"No receipt directory found for required job {job!r}"
    )


def _validate_job(
    *,
    job: str,
    root: Path,
    expected_sha: str,
    receipt_validator: Draft202012Validator,
) -> dict[str, Any]:
    errors: list[str] = []
    environment_path = root / "environment.json"
    environment_hash_path = environment_path
    if not environment_path.is_file():
        bundle_path = root / "evidence_bundle.json"
        if bundle_path.is_file():
            try:
                bundle = _load_json(bundle_path)
                environment = bundle.get("environment", {})
                environment_hash_path = bundle_path
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"evidence bundle is invalid: {exc}")
                environment = {}
        else:
            errors.append("environment.json is missing")
            environment = {}
    else:
        try:
            environment = _load_json(environment_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"environment.json is invalid: {exc}")
            environment = {}
    environment_sha = environment.get("git_sha") or environment.get(
        "git", {}
    ).get("verified_sha")
    if environment_sha != expected_sha:
        errors.append(
            f"environment git_sha {environment_sha!r} != {expected_sha!r}"
        )

    receipts_dir = root / "receipts"
    receipt_paths = (
        sorted(receipts_dir.glob("*.json")) if receipts_dir.is_dir() else []
    )
    if not receipt_paths:
        errors.append("no command receipts found")

    receipt_summaries: list[dict[str, Any]] = []
    for receipt_path in receipt_paths:
        try:
            receipt = _load_json(receipt_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{receipt_path.name}: invalid JSON: {exc}")
            continue
        schema_errors = sorted(
            receipt_validator.iter_errors(receipt),
            key=lambda error: list(error.absolute_path),
        )
        for error in schema_errors:
            location = ".".join(str(item) for item in error.absolute_path)
            errors.append(
                f"{receipt_path.name}: schema {location or '<root>'}: "
                f"{error.message}"
            )

        if receipt.get("result") != "SUCCESS":
            errors.append(
                f"{receipt_path.name}: result is {receipt.get('result')!r}"
            )
        if receipt.get("exit_code") not in receipt.get(
            "expected_exit_codes", []
        ):
            errors.append(
                f"{receipt_path.name}: exit code is not expected"
            )
        receipt_sha = receipt.get("environment", {}).get("git_sha")
        if receipt_sha != expected_sha:
            errors.append(
                f"{receipt_path.name}: receipt git_sha "
                f"{receipt_sha!r} != {expected_sha!r}"
            )

        log_paths = receipt.get("log_paths", {})
        stdout_path = root / str(log_paths.get("stdout_log", ""))
        stderr_path = root / str(log_paths.get("stderr_log", ""))
        for stream, log_path, hash_field in (
            ("stdout", stdout_path, "stdout_sha256"),
            ("stderr", stderr_path, "stderr_sha256"),
        ):
            if not log_path.is_file():
                errors.append(
                    f"{receipt_path.name}: {stream} log is missing"
                )
            elif _sha256(log_path) != receipt.get(hash_field):
                errors.append(
                    f"{receipt_path.name}: {stream} log hash mismatch"
                )
        if stdout_path.is_file() and stderr_path.is_file():
            combined_hash = hashlib.sha256(
                stdout_path.read_bytes() + stderr_path.read_bytes()
            ).hexdigest()
            if combined_hash != receipt.get("output_sha256"):
                errors.append(
                    f"{receipt_path.name}: combined output hash mismatch"
                )

        receipt_summaries.append(
            {
                "command_id": receipt.get("command_id"),
                "receipt_sha256": _sha256(receipt_path),
                "exit_code": receipt.get("exit_code"),
                "result": receipt.get("result"),
            }
        )

    return {
        "job": job,
        "status": "PASS" if not errors else "FAIL",
        "environment_sha256": (
            _sha256(environment_hash_path)
            if environment_hash_path.is_file()
            else None
        ),
        "receipts": receipt_summaries,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate evidence uploaded by required CI jobs"
    )
    parser.add_argument("--download-root", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument(
        "--job-results-json",
        required=True,
        help="JSON object mapping required job names to GitHub conclusions",
    )
    parser.add_argument("--jobs", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    schema = _load_json(args.schema)
    receipt_validator = Draft202012Validator(schema)
    job_results: list[dict[str, Any]] = []
    top_errors: list[str] = []
    try:
        github_job_results = json.loads(args.job_results_json)
    except json.JSONDecodeError as exc:
        github_job_results = {}
        top_errors.append(f"GitHub job results JSON is invalid: {exc}")
    if not isinstance(github_job_results, dict):
        github_job_results = {}
        top_errors.append("GitHub job results must be a JSON object")
    for job in args.jobs:
        github_result = github_job_results.get(job)
        if github_result != "success":
            top_errors.append(
                f"{job}: GitHub job conclusion is {github_result!r}"
            )
        try:
            root = _find_job_root(args.download_root, job)
            result = _validate_job(
                job=job,
                root=root,
                expected_sha=args.sha,
                receipt_validator=receipt_validator,
            )
        except Exception as exc:
            result = {
                "job": job,
                "status": "FAIL",
                "environment_sha256": None,
                "receipts": [],
                "errors": [f"{type(exc).__name__}: {exc}"],
            }
        job_results.append(result)
        top_errors.extend(
            f"{job}: {error}" for error in result["errors"]
        )

    manifest = {
        "manifest_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verified_sha": args.sha,
        "ci": {
            "run_id": str(args.run_id),
            "run_attempt": str(args.run_attempt),
        },
        "required_jobs": list(args.jobs),
        "github_job_results": github_job_results,
        "jobs": job_results,
        "errors": top_errors,
        "verdict": "PASS" if not top_errors else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    if top_errors:
        for error in top_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"CI evidence validated for {len(job_results)} required jobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
