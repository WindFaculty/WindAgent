#!/usr/bin/env python3
"""Validate and freeze the Architecture V3 Phase 1 policy gate.

The architecture checker is expected to return FAIL while later-phase boundary
violations still exist. Phase 1 passes when the V3 policy is complete, the
checker executes without an internal error, its evidence is internally
consistent, and the focused policy tests pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import tomllib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "artifacts" / "architecture_v3" / "phase_01"
CONFIG_PATH = ROOT / "configs" / "architecture" / "scaffold_v3.yaml"
CHECKER_ENTRY_PATH = ROOT / "scripts" / "check_architecture_v3.py"
CHECKER_CORE_PATH = ROOT / "scripts" / "check_architecture_imports.py"
PRODUCER_PATH = ROOT / "scripts" / "freeze_architecture_v3_policy.py"
BASELINE_PATH = ROOT / "artifacts" / "architecture_v3" / "baseline" / "baseline.json"
REPORT_PATH = OUTPUT_DIR / "v3_boundary_report.json"
GRAPH_PATH = OUTPUT_DIR / "v3_import_graph.json"
TEST_RECEIPT_PATH = OUTPUT_DIR / "test_receipt.json"
POLICY_RECEIPT_PATH = OUTPUT_DIR / "policy_frozen.json"
GATE = "ARCH_V3_POLICY_FROZEN"

POLICY_TESTS = (
    "tests/architecture/test_architecture_policy.py",
    "tests/architecture/test_architecture_v3_policy.py",
)

REQUIRED_CAPABILITIES = {
    "dependency_cycle": "forbid_dependency_cycles",
    "undeclared_dependency": "require_declared_workspace_dependencies",
    "core_framework_import": "forbid_core_framework_imports",
    "application_to_infrastructure": "forbid_application_direct_storage_import",
    "infrastructure_to_application": "forbid_infrastructure_to_application_import",
    "cross_app_import": "forbid_cross_app_imports",
    "module_level_mutable_production_store": "forbid_module_level_mutable_production_store",
    "production_test_fallback": "forbid_production_test_fallbacks",
    "legacy_runtime_authority": "forbid_legacy_runtime_authority",
    "concrete_adapter_outside_composition": "forbid_concrete_adapter_outside_composition",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run(argv: Iterable[str], *, timeout: int) -> dict[str, Any]:
    command = list(argv)
    started_at = utc_now()
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "argv": command,
            "started_at": started_at,
            "executed": True,
            "completed": True,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "argv": command,
            "started_at": started_at,
            "executed": True,
            "completed": False,
            "exit_code": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "error": f"timeout after {timeout}s",
        }


def git_text(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def workspace_members() -> set[str]:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return set(payload.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", []))


def checked_source_files(config: dict[str, Any]) -> list[Path]:
    files = {
        ROOT / "pyproject.toml",
        CONFIG_PATH,
        CHECKER_ENTRY_PATH,
        CHECKER_CORE_PATH,
    }
    for item in config.get("packages", {}).values():
        package_root = ROOT / item["path"]
        namespace_root = package_root / item["namespace"]
        pyproject = package_root / "pyproject.toml"
        if pyproject.is_file():
            files.add(pyproject)
        if namespace_root.is_dir():
            files.update(
                path
                for path in namespace_root.rglob("*.py")
                if "__pycache__" not in path.parts
            )
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def tree_fingerprint(paths: Iterable[Path]) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\0")
        count += 1
    return digest.hexdigest(), count


def run_policy_tests(timeout: int) -> dict[str, Any]:
    temp_root = ROOT / ".tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase1-policy-", dir=temp_root) as temp:
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(Path(temp) / "pytest"),
            *POLICY_TESTS,
        ]
        result = run(command, timeout=timeout)
    result["status"] = "PASS" if result.get("exit_code") == 0 else "FAIL"
    return result


def freeze(*, test_timeout: int, checker_timeout: int) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Architecture V3 policy must be a YAML mapping")

    test_result = run_policy_tests(test_timeout)
    write_json(TEST_RECEIPT_PATH, test_result)

    checker_result = run(
        [
            sys.executable,
            str(CHECKER_ENTRY_PATH),
            "--json",
            "--report",
            str(REPORT_PATH),
            "--graph",
            str(GRAPH_PATH),
        ],
        timeout=checker_timeout,
    )

    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    actual_members = workspace_members()
    declared_members = set(config.get("workspace", {}).get("members", []))
    configured_members = {
        item.get("path") for item in config.get("packages", {}).values()
    }
    rules = config.get("global_rules", {})
    capability_status = {
        capability: bool(rules.get(config_key))
        for capability, config_key in REQUIRED_CAPABILITIES.items()
    }
    violation_counts = Counter(
        item.get("rule", "unknown") for item in report.get("violations", [])
    )
    source_hash, source_file_count = tree_fingerprint(checked_source_files(config))
    status_text = git_text("status", "--porcelain=v1", "--untracked-files=all")

    validation = {
        "baseline_frozen": (
            baseline.get("frozen") is True
            and baseline.get("gate") == "ARCH_V3_BASELINE_FROZEN"
        ),
        "workspace_matrix_matches": (
            actual_members == declared_members == configured_members
        ),
        "all_required_capabilities_enabled": all(capability_status.values()),
        "composition_roots_are_scoped": bool(rules.get("composition_roots"))
        and all(
            path not in {"apps/api/**", "apps/worker/**", "apps/cli/**"}
            for path in rules["composition_roots"]
        ),
        "policy_tests_pass": test_result.get("exit_code") == 0,
        "checker_completed": checker_result.get("completed") is True,
        "checker_returned_policy_result": checker_result.get("exit_code") in (0, 1),
        "report_status_valid": report.get("status") in {"PASS", "FAIL"},
        "report_count_consistent": report.get("total_violations")
        == len(report.get("violations", [])),
        "graph_covers_workspace": len(graph.get("nodes", [])) == len(actual_members),
    }
    frozen = all(validation.values())

    receipt = {
        "schema_version": 2,
        "phase": "phase_01",
        "generated_at": utc_now(),
        "gate": GATE if frozen else "ARCH_V3_POLICY_NOT_FROZEN",
        "gate_verdict": "PASS" if frozen else "FAIL",
        "frozen": frozen,
        "architecture_verdict": report.get("status"),
        "zero_violations_required": False,
        "baseline_commit": git_text("rev-parse", "HEAD"),
        "baseline_branch": git_text("branch", "--show-current"),
        "source_snapshot": {
            "mode": "content_addressed_worktree",
            "checked_source_sha256": source_hash,
            "checked_source_file_count": source_file_count,
            "worktree_dirty": bool(status_text),
            "dirty_entry_count": len(status_text.splitlines()) if status_text else 0,
            "git_status_sha256": hashlib.sha256(status_text.encode("utf-8")).hexdigest(),
        },
        "inputs": {
            "policy": {
                "path": CONFIG_PATH.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(CONFIG_PATH),
            },
            "checker_entry": {
                "path": CHECKER_ENTRY_PATH.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(CHECKER_ENTRY_PATH),
            },
            "checker_core": {
                "path": CHECKER_CORE_PATH.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(CHECKER_CORE_PATH),
            },
            "producer": {
                "path": PRODUCER_PATH.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(PRODUCER_PATH),
            },
            "policy_tests": [
                {
                    "path": path,
                    "sha256": sha256_file(ROOT / path),
                }
                for path in POLICY_TESTS
            ],
        },
        "artifacts": {
            "boundary_report": {
                "path": REPORT_PATH.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(REPORT_PATH),
            },
            "import_graph": {
                "path": GRAPH_PATH.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(GRAPH_PATH),
            },
            "test_receipt": {
                "path": TEST_RECEIPT_PATH.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(TEST_RECEIPT_PATH),
            },
        },
        "checker": {
            "executed": checker_result.get("executed"),
            "completed": checker_result.get("completed"),
            "exit_code": checker_result.get("exit_code"),
        },
        "tests": {
            "status": test_result.get("status"),
            "exit_code": test_result.get("exit_code"),
            "files": list(POLICY_TESTS),
        },
        "required_capabilities": capability_status,
        "validation": validation,
        "total_violations": report.get("total_violations"),
        "violations_by_rule": [
            {"rule": rule, "count": count}
            for rule, count in sorted(
                violation_counts.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "v3_new_rules_reporting": {
            rule: violation_counts.get(rule, 0)
            for rule in (
                "application_direct_storage_import",
                "storage_to_provider_import",
                "infrastructure_to_application_import",
                "module_level_mutable_production_store",
                "concrete_adapter_outside_composition",
                "legacy_runtime_authority",
            )
        },
        "note": (
            "Phase 1 freezes policy and the content-addressed violation inventory. "
            "Zero violations are intentionally deferred to their owning repair phases."
        ),
    }
    write_json(POLICY_RECEIPT_PATH, receipt)
    print(f"[phase1] gate: {receipt['gate']}")
    print(f"[phase1] policy tests: {test_result['status']}")
    print(
        "[phase1] architecture verdict: "
        f"{report['status']} ({report['total_violations']} violations)"
    )
    return 0 if frozen else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-timeout", type=int, default=120)
    parser.add_argument("--checker-timeout", type=int, default=120)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return freeze(
        test_timeout=args.test_timeout,
        checker_timeout=args.checker_timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
