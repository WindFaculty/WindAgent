import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_architecture_imports.py"


def write_package(root: Path, name: str, imports: str = "", dependencies=()) -> None:
    namespace = f"windagent_{name}"
    package = root / name
    (package / namespace).mkdir(parents=True)
    (package / namespace / "__init__.py").write_text(imports, encoding="utf-8")
    deps = ", ".join(json.dumps(dep) for dep in dependencies)
    (package / "pyproject.toml").write_text(
        f'[project]\nname = "{namespace}"\nversion = "0.3.0"\ndependencies = [{deps}]\n',
        encoding="utf-8",
    )


def run_checker(tmp_path: Path, packages: dict, members=None):
    members = members or list(packages)
    config = {
        "version": "2.0",
        "workspace": {"members": members},
        "global_rules": {
            "forbid_cross_app_imports": True,
            "forbid_core_framework_imports": True,
            "require_declared_workspace_dependencies": True,
            "forbid_dependency_cycles": True,
            "forbid_public_api_leakage": True,
            "forbid_legacy_backend_imports": True,
        },
        "canonical_models": ["EventEnvelope"],
        "packages": packages,
    }
    config_path = tmp_path / "policy.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    report_path = tmp_path / "report.json"
    env = dict(os.environ)
    pythonpath = [str(ROOT), str(ROOT / "core"), str(ROOT / "providers"), str(ROOT / "workflows"), str(ROOT / "apps" / "cli"), str(ROOT / "apps" / "desktop")]
    if "PYTHONPATH" in env:
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path), "--config", str(config_path), "--report", str(report_path), "--skip-root-validation", "--skip-scaffold-check"],
        capture_output=True,
        text=True,
        env=env,
    )
    return result, json.loads(report_path.read_text(encoding="utf-8"))


def package(path: str, allowed=()):
    name = Path(path).name
    return {
        "path": path,
        "namespace": f"windagent_{name}",
        "layer": "platform",
        "legacy_source": f"legacy/{name}",
        "allowed_dependencies": list(allowed),
    }


@pytest.mark.parametrize(
    ("setup", "rule"),
    [
        (lambda root: (write_package(root, "api", "import windagent_worker\n"), write_package(root, "worker")), "cross_app_dependency"),
        (lambda root: (write_package(root, "providers", "import windagent_intelligence\n", ["windagent-intelligence"]), write_package(root, "intelligence")), "disallowed_dependency"),
        (lambda root: write_package(root, "core", "import sqlalchemy\n"), "core_framework_import"),
        (lambda root: (write_package(root, "api", "import windagent_core\n"), write_package(root, "core")), "undeclared_workspace_dependency"),
        (lambda root: (write_package(root, "api", "import windagent_worker\n", ["windagent-worker"]), write_package(root, "worker", "import windagent_api\n", ["windagent-api"])), "dependency_cycle"),
        (lambda root: write_package(root, "core"), "namespace_path_mismatch"),
    ],
)
def test_checker_rejects_architecture_violation(tmp_path, setup, rule):
    setup(tmp_path)
    names = [path.name for path in tmp_path.iterdir() if path.is_dir()]
    packages = {name: package(name, [other for other in names if other != name]) for name in names}
    if rule == "disallowed_dependency":
        packages["providers"]["allowed_dependencies"] = ["core"]
    if rule == "namespace_path_mismatch":
        packages["core"]["namespace"] = "wrong_namespace"
    result, report = run_checker(tmp_path, packages)
    assert result.returncode != 0
    assert rule in {violation["rule"] for violation in report["violations"]}


def test_checker_rejects_missing_workspace_package(tmp_path):
    write_package(tmp_path, "core")
    write_package(tmp_path, "skills")
    # Create root pyproject.toml with only core declared
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["core"]\n',
        encoding="utf-8",
    )
    result, report = run_checker(tmp_path, {"core": package("core"), "skills": package("skills")}, members=["core"])
    assert result.returncode != 0
    assert "workspace_member_missing" in {item["rule"] for item in report["violations"]}


def test_checker_rejects_duplicate_canonical_model(tmp_path):
    write_package(tmp_path, "core", "class EventEnvelope:\n    pass\n")
    write_package(tmp_path, "api", "class EventEnvelope:\n    pass\n")
    result, report = run_checker(tmp_path, {"core": package("core"), "api": package("api")})
    assert result.returncode != 0
    assert "duplicate_canonical_model" in {item["rule"] for item in report["violations"]}


def test_checker_requires_top_level_plugin_and_skill_packages(tmp_path):
    write_package(tmp_path, "core")
    packages = {"core": package("core")}
    run_checker(tmp_path, packages)
    config_path = tmp_path / "policy.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["required_top_level_packages"] = ["plugins", "skills"]
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    report_path = tmp_path / "required-report.json"
    env = dict(os.environ)
    pythonpath = [str(ROOT), str(ROOT / "core"), str(ROOT / "providers"), str(ROOT / "workflows"), str(ROOT / "apps" / "cli"), str(ROOT / "apps" / "desktop")]
    if "PYTHONPATH" in env:
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path), "--config", str(config_path), "--report", str(report_path), "--skip-root-validation", "--skip-scaffold-check"],
        capture_output=True,
        text=True,
        env=env,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert result.returncode != 0
    missing = {item["message"] for item in report["violations"] if item["rule"] == "missing_top_level_package"}
    assert missing == {"Top-level package missing: plugins", "Top-level package missing: skills"}


def test_checker_accepts_minimal_valid_repository(tmp_path):
    write_package(tmp_path, "core")
    write_package(tmp_path, "providers", "import windagent_core\n", ["windagent-core"])
    packages = {"core": package("core"), "providers": package("providers", ["core"])}
    result, report = run_checker(tmp_path, packages)
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["status"] == "PASS"
