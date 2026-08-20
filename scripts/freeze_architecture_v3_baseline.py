"""Freeze the Architecture V3 Phase 0 baseline.

The baseline is an observation, not a repair step.  Failing checks are retained
in the evidence and do not prevent ``ARCH_V3_BASELINE_FROZEN`` when every
required command ran and the source authority matches the Phase 0 contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EXPECTED_HEAD = "ac61c38cdca90100a14ec0ea26c4d19c35f7caa4"
EXPECTED_BRANCH = "refactor/architecture-v3-hardening"
GATE = "ARCH_V3_BASELINE_FROZEN"
SCHEMA_VERSION = 1

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "architecture_v3" / "baseline"
PHASE0_PATHS = {
    "scripts/freeze_architecture_v3_baseline.py",
    "artifacts/architecture_v3/baseline/",
}


@dataclass(frozen=True)
class CommandSpec:
    name: str
    display: str
    argv: tuple[str, ...]
    cwd: Path
    timeout_seconds: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_capture(
    argv: Iterable[str],
    *,
    cwd: Path = ROOT,
    timeout_seconds: int = 60,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    command = tuple(argv)
    started = time.perf_counter()
    try:
        process = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "argv": list(command),
            "cwd": cwd.relative_to(ROOT).as_posix() if cwd != ROOT else ".",
            "executed": True,
            "timed_out": False,
            "exit_code": process.returncode,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "stdout": process.stdout,
            "stderr": process.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "argv": list(command),
            "cwd": cwd.relative_to(ROOT).as_posix() if cwd != ROOT else ".",
            "executed": True,
            "timed_out": True,
            "exit_code": None,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "stdout": stdout,
            "stderr": stderr,
        }
    except OSError as exc:
        return {
            "argv": list(command),
            "cwd": cwd.relative_to(ROOT).as_posix() if cwd != ROOT else ".",
            "executed": False,
            "timed_out": False,
            "exit_code": None,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "stdout": "",
            "stderr": str(exc),
        }


def command_text(argv: Iterable[str], *, timeout_seconds: int = 60) -> str:
    result = run_capture(argv, timeout_seconds=timeout_seconds)
    if not result["executed"] or result["exit_code"] != 0:
        joined = " ".join(argv)
        raise RuntimeError(f"Command failed while collecting baseline: {joined}\n{result['stderr']}")
    # Preserve leading whitespace because Git porcelain and submodule status
    # encode state in their first columns.  Only line terminators are noise.
    return result["stdout"].rstrip("\r\n")


def parse_porcelain(status: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for line in status.splitlines():
        if not line:
            continue
        entries.append({"status": line[:2], "path": line[3:]})
    return entries


def collect_lockfiles() -> dict[str, dict[str, Any]]:
    candidates = [ROOT / "uv.lock"]
    candidates.extend(
        [
            ROOT / "frontend" / "package-lock.json",
            ROOT / "apps" / "web" / "package-lock.json",
            ROOT / "apps" / "desktop" / "package-lock.json",
        ]
    )
    result: dict[str, dict[str, Any]] = {}
    for path in candidates:
        relative = path.relative_to(ROOT).as_posix()
        result[relative] = {
            "exists": path.is_file(),
            "sha256": sha256_file(path) if path.is_file() else None,
            "size_bytes": path.stat().st_size if path.is_file() else None,
        }
    return result


def collect_git_state() -> dict[str, Any]:
    short_status = command_text(("git", "status", "--porcelain=v1", "--untracked-files=normal"))
    dirty_files = parse_porcelain(short_status)
    preexisting = [
        item
        for item in dirty_files
        if not any(item["path"].replace("\\", "/").startswith(path) for path in PHASE0_PATHS)
    ]
    return {
        "captured_at": utc_now(),
        "head_sha": command_text(("git", "rev-parse", "HEAD")),
        "branch": command_text(("git", "branch", "--show-current")),
        "status_porcelain": short_status,
        "dirty_files": dirty_files,
        "preexisting_dirty_files": preexisting,
        "submodules": command_text(("git", "submodule", "status", "--recursive")),
        "worktrees": command_text(("git", "worktree", "list", "--porcelain")),
        "remotes": command_text(("git", "remote", "-v")),
    }


def collect_environment() -> dict[str, Any]:
    npm_executable = "npm.cmd" if os.name == "nt" else "npm"
    return {
        "platform": platform.platform(),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": str(Path(sys.executable).resolve()),
        },
        "node_version": command_text(("node", "--version")),
        "npm_version": command_text((npm_executable, "--version")),
        "uv_version": command_text(("uv", "--version")),
        "lockfiles": collect_lockfiles(),
    }


def read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def python_package(path: Path) -> dict[str, Any]:
    data = read_toml(path / "pyproject.toml")
    project = data.get("project", {})
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "name": project.get("name"),
        "version": project.get("version"),
        "requires_python": project.get("requires-python"),
        "dependencies": project.get("dependencies", []),
        "optional_dependencies": project.get("optional-dependencies", {}),
    }


def node_package(path: Path) -> dict[str, Any]:
    manifest = json.loads((path / "package.json").read_text(encoding="utf-8"))
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "private": bool(manifest.get("private", False)),
        "workspaces": manifest.get("workspaces", []),
        "scripts": manifest.get("scripts", {}),
        "dependencies": manifest.get("dependencies", {}),
        "dev_dependencies": manifest.get("devDependencies", {}),
        "peer_dependencies": manifest.get("peerDependencies", {}),
    }


def collect_workspace_packages() -> dict[str, Any]:
    root_pyproject = read_toml(ROOT / "pyproject.toml")
    uv_members = root_pyproject["tool"]["uv"]["workspace"]["members"]
    python_packages = [python_package(ROOT / member) for member in uv_members]

    node_manifests = [ROOT / "apps" / "web", ROOT / "apps" / "desktop", ROOT / "frontend"]
    node_manifests.extend(sorted((ROOT / "frontend" / "app").parent.glob("app")))
    node_manifests.extend(sorted((ROOT / "frontend" / "packages").glob("*")))
    unique_node_manifests = sorted(
        {path.resolve() for path in node_manifests if (path / "package.json").is_file()},
        key=lambda path: path.as_posix(),
    )

    cargo_path = ROOT / "apps" / "desktop" / "src-tauri" / "Cargo.toml"
    cargo = read_toml(cargo_path)
    cargo_project = cargo.get("package", {})
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "uv_workspace": {
            "root_project": root_pyproject.get("project", {}),
            "member_count": len(python_packages),
            "members": python_packages,
        },
        "node_workspaces": {
            "package_count": len(unique_node_manifests),
            "packages": [node_package(path) for path in unique_node_manifests],
        },
        "rust_packages": [
            {
                "path": cargo_path.parent.relative_to(ROOT).as_posix(),
                "name": cargo_project.get("name"),
                "version": cargo_project.get("version"),
                "dependencies": cargo.get("dependencies", {}),
            }
        ],
        "lockfiles": collect_lockfiles(),
    }


def iter_runtime_routes(routes: Iterable[Any], prefix: str = "") -> Iterable[dict[str, Any]]:
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            context = getattr(route, "include_context", None)
            nested_prefix = prefix + (getattr(context, "prefix", "") or "")
            yield from iter_runtime_routes(original_router.routes, nested_prefix)
            continue

        route_path = getattr(route, "path", None)
        if route_path is None:
            continue
        endpoint = getattr(route, "endpoint", None)
        methods = getattr(route, "methods", None)
        kind = "websocket" if methods is None else "http"
        yield {
            "kind": kind,
            "path": prefix + route_path,
            "methods": ["WEBSOCKET"] if methods is None else sorted(methods),
            "name": getattr(route, "name", None),
            "operation_id": getattr(route, "operation_id", None),
            "include_in_schema": bool(getattr(route, "include_in_schema", False)),
            "tags": list(getattr(route, "tags", []) or []),
            "endpoint": (
                f"{endpoint.__module__}.{endpoint.__qualname__}"
                if endpoint is not None and hasattr(endpoint, "__module__")
                else None
            ),
        }


def collect_routes() -> dict[str, Any]:
    os.environ["ENABLE_V2_API"] = "false"
    from windagent_api.main import app

    routes = list(iter_runtime_routes(app.routes))
    routes.sort(key=lambda item: (item["path"], item["kind"], item["methods"], item["name"] or ""))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "source": "windagent_api.main.app runtime route graph",
        "environment": {"ENABLE_V2_API": "false"},
        "summary": {
            "total": len(routes),
            "http": sum(item["kind"] == "http" for item in routes),
            "websocket": sum(item["kind"] == "websocket" for item in routes),
            "schema_visible": sum(item["include_in_schema"] for item in routes),
        },
        "routes": routes,
    }


def execute_test(spec: CommandSpec, env: dict[str, str]) -> dict[str, Any]:
    print(f"[phase0] running {spec.name}: {spec.display}", flush=True)
    result = run_capture(
        spec.argv,
        cwd=spec.cwd,
        timeout_seconds=spec.timeout_seconds,
        env=env,
    )
    result["name"] = spec.name
    result["command"] = spec.display
    result["status"] = (
        "NOT_EXECUTED"
        if not result["executed"]
        else "TIMEOUT"
        if result["timed_out"]
        else "PASS"
        if result["exit_code"] == 0
        else "FAIL"
    )
    print(
        f"[phase0] {spec.name}: {result['status']} ({result['duration_seconds']}s)",
        flush=True,
    )
    return result


def test_specs() -> list[CommandSpec]:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    uv = "uv.exe" if os.name == "nt" else "uv"
    return [
        CommandSpec(
            name="architecture_checker",
            display="uv run python scripts/check_architecture_imports.py --root . --json",
            argv=(uv, "run", "--frozen", "python", "scripts/check_architecture_imports.py", "--root", ".", "--json"),
            cwd=ROOT,
            timeout_seconds=300,
        ),
        CommandSpec(
            name="python_pytest",
            display="uv run pytest",
            argv=(uv, "run", "--frozen", "pytest"),
            cwd=ROOT,
            timeout_seconds=3600,
        ),
        CommandSpec(
            name="frontend_workspace_tests",
            display="npm test (frontend)",
            argv=(npm, "test"),
            cwd=ROOT / "frontend",
            timeout_seconds=1200,
        ),
        CommandSpec(
            name="web_tests",
            display="npm test (apps/web)",
            argv=(npm, "test"),
            cwd=ROOT / "apps" / "web",
            timeout_seconds=1200,
        ),
        CommandSpec(
            name="desktop_tests",
            display="npm test (apps/desktop)",
            argv=(npm, "test"),
            cwd=ROOT / "apps" / "desktop",
            timeout_seconds=1200,
        ),
    ]


def dependency_report(architecture_result: dict[str, Any]) -> dict[str, Any]:
    parsed: Any = None
    parse_error: str | None = None
    try:
        parsed = json.loads(architecture_result["stdout"])
    except (json.JSONDecodeError, TypeError) as exc:
        parse_error = str(exc)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "command": architecture_result["command"],
        "executed": architecture_result["executed"],
        "exit_code": architecture_result["exit_code"],
        "duration_seconds": architecture_result["duration_seconds"],
        "status": architecture_result["status"],
        "report": parsed,
        "parse_error": parse_error,
        "stderr": architecture_result["stderr"],
    }


def git_state_text(git_state: dict[str, Any], environment: dict[str, Any]) -> str:
    lock_lines = [
        f"{path}: {item['sha256'] if item['exists'] else 'MISSING'}"
        for path, item in environment["lockfiles"].items()
    ]
    dirty = git_state["status_porcelain"] or "(clean)"
    submodules = git_state["submodules"] or "(none)"
    return "\n".join(
        [
            "WindAgent Architecture V3 Phase 0 Git State",
            f"Captured at: {git_state['captured_at']}",
            f"HEAD SHA: {git_state['head_sha']}",
            f"Branch: {git_state['branch']}",
            f"Python: {environment['python']['version']}",
            f"Node: {environment['node_version']}",
            f"npm: {environment['npm_version']}",
            f"uv: {environment['uv_version']}",
            "",
            "Lockfile SHA-256:",
            *lock_lines,
            "",
            "Git status (porcelain v1):",
            dirty,
            "",
            "Submodules:",
            submodules,
            "",
            "Worktrees:",
            git_state["worktrees"],
            "",
            "Remotes:",
            git_state["remotes"],
            "",
        ]
    )


def artifact_manifest() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name in (
        "dependency-report.json",
        "test-report.json",
        "workspace-packages.json",
        "route-inventory.json",
        "git-state.txt",
    ):
        path = OUTPUT_DIR / name
        result[name] = {
            "exists": path.is_file(),
            "sha256": sha256_file(path) if path.is_file() else None,
            "size_bytes": path.stat().st_size if path.is_file() else None,
        }
    return result


def freeze(*, run_tests: bool) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    captured_at = utc_now()
    git_state = collect_git_state()
    environment = collect_environment()

    write_json(OUTPUT_DIR / "workspace-packages.json", collect_workspace_packages())
    write_json(OUTPUT_DIR / "route-inventory.json", collect_routes())
    (OUTPUT_DIR / "git-state.txt").write_text(
        git_state_text(git_state, environment),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(ROOT / ".tmp" / "uv-cache")
    env["ENABLE_V2_API"] = "false"
    temp_root = ROOT / ".tmp" / "architecture-v3-phase0" / captured_at.replace(":", "-")
    temp_root.mkdir(parents=True, exist_ok=True)
    # The managed Windows sandbox does not permit pytest to create its default
    # directory under the user's AppData temp tree.  Keep temporary test data
    # inside the writable checkout so failures describe the code, not the host.
    env["TEMP"] = str(temp_root)
    env["TMP"] = str(temp_root)
    env["TMPDIR"] = str(temp_root)
    results = [execute_test(spec, env) for spec in test_specs()] if run_tests else []
    architecture_result = next(
        (result for result in results if result["name"] == "architecture_checker"),
        {
            "command": test_specs()[0].display,
            "executed": False,
            "exit_code": None,
            "duration_seconds": 0,
            "status": "NOT_EXECUTED",
            "stdout": "",
            "stderr": "tests were not requested",
        },
    )
    write_json(OUTPUT_DIR / "dependency-report.json", dependency_report(architecture_result))

    test_report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "required_commands": [spec.display for spec in test_specs()],
        "environment_overrides": {
            "ENABLE_V2_API": env["ENABLE_V2_API"],
            "TEMP": str(temp_root.relative_to(ROOT)),
            "TMP": str(temp_root.relative_to(ROOT)),
            "TMPDIR": str(temp_root.relative_to(ROOT)),
            "UV_CACHE_DIR": str((ROOT / ".tmp" / "uv-cache").relative_to(ROOT)),
        },
        "all_required_commands_executed": len(results) == len(test_specs())
        and all(result["executed"] for result in results),
        "all_required_commands_completed": len(results) == len(test_specs())
        and all(result["executed"] and not result["timed_out"] for result in results),
        "summary": {
            status: sum(result["status"] == status for result in results)
            for status in ("PASS", "FAIL", "TIMEOUT", "NOT_EXECUTED")
        },
        "results": results,
    }
    write_json(OUTPUT_DIR / "test-report.json", test_report)

    manifest = artifact_manifest()
    authority_matches = (
        git_state["head_sha"] == EXPECTED_HEAD and git_state["branch"] == EXPECTED_BRANCH
    )
    evidence_complete = (
        test_report["all_required_commands_completed"]
        and all(item["exists"] for item in manifest.values())
    )
    frozen = authority_matches and evidence_complete
    baseline = {
        "schema_version": SCHEMA_VERSION,
        "captured_at": captured_at,
        "source_authority": {
            "expected_head_sha": EXPECTED_HEAD,
            "actual_head_sha": git_state["head_sha"],
            "head_matches": git_state["head_sha"] == EXPECTED_HEAD,
            "expected_branch": EXPECTED_BRANCH,
            "actual_branch": git_state["branch"],
            "branch_matches": git_state["branch"] == EXPECTED_BRANCH,
            "main_merged_automatically": False,
        },
        "repository_state": {
            "dirty": bool(git_state["dirty_files"]),
            "dirty_file_count": len(git_state["dirty_files"]),
            "preexisting_dirty_file_count": len(git_state["preexisting_dirty_files"]),
            "dirty_files": git_state["dirty_files"],
            "preexisting_dirty_files": git_state["preexisting_dirty_files"],
            "submodules": git_state["submodules"],
        },
        "environment": environment,
        "test_baseline": {
            "all_required_commands_executed": test_report["all_required_commands_executed"],
            "all_required_commands_completed": test_report["all_required_commands_completed"],
            "summary": test_report["summary"],
            "all_checks_passed": bool(results) and all(result["status"] == "PASS" for result in results),
        },
        "artifacts": manifest,
        "gate": GATE if frozen else "ARCH_V3_BASELINE_NOT_FROZEN",
        "frozen": frozen,
        "note": "A frozen baseline may contain failing checks; Phase 0 records facts and does not repair later-phase architecture violations.",
    }
    write_json(OUTPUT_DIR / "baseline.json", baseline)
    print(f"[phase0] gate: {baseline['gate']}", flush=True)
    return 0 if frozen else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Generate inventory only; the Phase 0 gate will remain open.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(freeze(run_tests=not args.skip_tests))
