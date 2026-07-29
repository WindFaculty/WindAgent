#!/usr/bin/env python3
"""Execute Phase 6 negative injections and persist one receipt per case.

Each case deliberately invokes a fail-closed gate and expects a non-zero exit
code.  A zero exit code therefore means that the injection was accepted and
causes this runner to fail.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .run_command_receipt import (
        generate_receipt,
        get_environment,
        persist_logs,
        run_command,
    )
except ImportError:  # Direct script execution from scripts/verification.
    from run_command_receipt import (
        generate_receipt,
        get_environment,
        persist_logs,
        run_command,
    )


@dataclass(frozen=True)
class InjectionCase:
    name: str
    command: list[str]
    expected_exit_codes: list[int]
    cwd: Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _python_case(code: str, *arguments: str) -> list[str]:
    return ["uv", "run", "python", "-c", code, *arguments]


def _workspace_product_version(repository_root: Path) -> str:
    with (repository_root / "pyproject.toml").open("rb") as source:
        data = tomllib.load(source)
    return str(data["project"]["version"])


def build_cases(repository_root: Path, workspace: Path) -> list[InjectionCase]:
    """Create isolated fixtures and return the required Phase 6 injections."""
    workspace.mkdir(parents=True, exist_ok=True)
    product_version = _workspace_product_version(repository_root)

    version_root = workspace / "version-mismatch"
    _write(
        version_root / "pyproject.toml",
        "[project]\nname = 'phase6-version-fixture'\n"
        f"version = '{product_version}'\n"
        "[tool.uv.workspace]\nmembers = ['core']\n",
    )
    _write(
        version_root / "core" / "pyproject.toml",
        "[project]\nname = 'windagent-core'\nversion = '0.0.0'\n",
    )
    version_code = (
        "from pathlib import Path\n"
        "import sys\n"
        "from scripts.check_version_consistency import VersionChecker\n"
        "checker = VersionChecker(Path(sys.argv[1]))\n"
        "ok = checker.check_package_versions()\n"
        "print('\\n'.join(checker.errors))\n"
        "raise SystemExit(1 if not ok else 0)\n"
    )

    root_code = (
        "from pathlib import Path\n"
        "import sys\n"
        "from windagent_core.config import repository_root\n"
        "from windagent_cli.main import architecture_check\n"
        "root = Path(sys.argv[1])\n"
        "(root / 'configs' / 'architecture').mkdir(parents=True)\n"
        "(root / 'pyproject.toml').write_text('[tool.uv.workspace]\\nmembers = []\\n')\n"
        "(root / 'configs' / 'architecture' / 'scaffold_v2.yaml').write_text('version: 2.0\\n')\n"
        "repository_root.find_repository_root = lambda: root\n"
        "raise SystemExit(architecture_check(json_mode=True))\n"
    )

    runtime_report = workspace / "api-worker-version-mismatch.json"
    runtime_code = (
        "from pathlib import Path\n"
        "import sys\n"
        "from scripts.verification import runtime_version_smoke as smoke\n"
        "real_version = smoke.version\n"
        "smoke.version = lambda name: '0.0.0' if name in {'windagent-api', 'windagent-worker'} else real_version(name)\n"
        "smoke.sys.argv = ['runtime_version_smoke.py', '--output', sys.argv[1]]\n"
        "raise SystemExit(smoke.main())\n"
    )

    desktop_root = workspace / "desktop-lockfile-mismatch"
    _write(
        desktop_root / "package.json",
        json.dumps(
            {
                "name": "phase6-negative-desktop-lockfile",
                "version": "1.0.0",
                "dependencies": {"left-pad": "1.3.0"},
            }
        ),
    )
    _write(
        desktop_root / "package-lock.json",
        json.dumps(
            {
                "name": "phase6-negative-desktop-lockfile",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {
                    "": {
                        "name": "phase6-negative-desktop-lockfile",
                        "version": "1.0.0",
                    }
                },
            }
        ),
    )
    npm = "npm.cmd" if os.name == "nt" else "npm"

    demo_code = (
        "import contextlib\n"
        "import io\n"
        "import json\n"
        "from windagent_cli.main import main\n"
        "stdout = io.StringIO()\n"
        "with contextlib.redirect_stdout(stdout):\n"
        "    code = main(['eval', '--json'])\n"
        "rendered = stdout.getvalue()\n"
        "print(rendered, end='')\n"
        "payload = json.loads(rendered)\n"
        "if code == 2 and payload.get('data_source') != 'DEMO' and payload.get('non_production') is False:\n"
        "    raise SystemExit(2)\n"
        "raise SystemExit(0)\n"
    )

    fixture = repository_root / "tests" / "fixtures" / "artifacts"
    return [
        InjectionCase(
            "version_mismatch",
            _python_case(version_code, str(version_root)),
            [1],
            repository_root,
        ),
        InjectionCase(
            "invalid_artifact_schema",
            [
                "uv",
                "run",
                "python",
                "scripts/validate_artifact_schema.py",
                str(fixture / "invalid_sha.json"),
            ],
            [1],
            repository_root,
        ),
        InjectionCase(
            "broken_artifact_hash",
            [
                "uv",
                "run",
                "python",
                "scripts/validate_artifact_schema.py",
                str(fixture / "wrong_hash.json"),
            ],
            [1],
            repository_root,
        ),
        InjectionCase(
            "missing_architecture_checker",
            _python_case(root_code, str(workspace / "missing-checker")),
            [3],
            repository_root,
        ),
        InjectionCase(
            "dirty_worktree",
            [
                "uv",
                "run",
                "python",
                "scripts/validate_artifact_schema.py",
                str(fixture / "dirty_worktree_pass.json"),
            ],
            [1],
            repository_root,
        ),
        InjectionCase(
            "api_worker_version_mismatch",
            _python_case(runtime_code, str(runtime_report)),
            [1],
            repository_root,
        ),
        InjectionCase(
            "postgresql_unavailable",
            [
                "uv",
                "run",
                "python",
                "scripts/verification/database_preflight.py",
                "--database-url",
                "postgresql+asyncpg://phase6:phase6@127.0.0.1:1/phase6",
                "--require-dialect",
                "postgresql",
                "--output",
                str(workspace / "postgresql-unavailable.json"),
            ],
            [1],
            repository_root,
        ),
        InjectionCase(
            "desktop_lockfile_mismatch",
            [npm, "ci", "--ignore-scripts"],
            [1],
            desktop_root,
        ),
        InjectionCase(
            "demo_fallback_in_production",
            _python_case(demo_code),
            [2],
            repository_root,
        ),
    ]


def _run_case(
    case: InjectionCase,
    receipts_dir: Path,
    environment: dict[str, str],
) -> tuple[dict[str, Any], bool]:
    started_at = datetime.now(timezone.utc)
    exit_code, stdout, stderr, duration_ms = run_command(
        case.command,
        cwd=case.cwd,
        timeout=180,
    )
    finished_at = datetime.now(timezone.utc)
    receipt = generate_receipt(
        name=case.name,
        command=case.command,
        cwd=case.cwd,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        started_at=started_at,
        finished_at=finished_at,
        expected_exit_codes=case.expected_exit_codes,
        environment=environment,
    )
    receipt["log_paths"] = persist_logs(
        receipts_dir / f"{case.name}.json",
        receipt["command_id"],
        stdout,
        stderr,
    )
    receipt_path = receipts_dir / f"{case.name}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    passed = exit_code in case.expected_exit_codes and exit_code != 0
    return receipt, passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the complete Phase 6 negative-injection matrix"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    repository_root = args.root.resolve()
    output_dir = args.output_dir.resolve()
    receipts_dir = output_dir / "receipts"
    workspace = output_dir / "work"
    if output_dir.exists() and any(output_dir.iterdir()):
        print(f"ERROR: output directory must be empty: {output_dir}", file=sys.stderr)
        return 1
    receipts_dir.mkdir(parents=True, exist_ok=True)

    environment = get_environment(repository_root)
    cases = build_cases(repository_root, workspace)
    results: list[dict[str, Any]] = []
    passed = True
    for case in cases:
        receipt, case_passed = _run_case(case, receipts_dir, environment)
        results.append(
            {
                "name": case.name,
                "receipt": f"receipts/{case.name}.json",
                "exit_code": receipt["exit_code"],
                "expected_exit_codes": case.expected_exit_codes,
                "passed": case_passed,
            }
        )
        passed = passed and case_passed

    report = {
        "report_version": "1.0.0",
        "verified_sha": environment["git_sha"],
        "cases": results,
        "verdict": "PASS" if passed else "FAIL",
    }
    (output_dir / "negative_injection_report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
