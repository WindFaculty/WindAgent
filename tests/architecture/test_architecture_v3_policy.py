import sys
import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_architecture_imports as checker  # noqa: E402
import check_architecture_v3 as v3_entry  # noqa: E402


def write_package(
    root: Path,
    *,
    path: str,
    namespace: str,
    source: str = "",
) -> None:
    package_root = root / path
    source_root = package_root / namespace
    source_root.mkdir(parents=True)
    (source_root / "module.py").write_text(source, encoding="utf-8")
    (source_root / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "pyproject.toml").write_text(
        (
            "[project]\n"
            f'name = "{namespace.replace("_", "-")}"\n'
            'version = "0.1.0"\n'
            "dependencies = []\n"
        ),
        encoding="utf-8",
    )


def package(*, path: str, namespace: str, layer: str) -> dict:
    return {
        "path": path,
        "namespace": namespace,
        "layer": layer,
        "allowed_dependencies": [],
        "forbidden_dependencies": [],
    }


def policy(packages: dict) -> dict:
    return {
        "version": "3.0",
        "workspace": {
            "members": [item["path"] for item in packages.values()],
        },
        "global_rules": {
            "forbid_cross_app_imports": False,
            "forbid_core_framework_imports": False,
            "require_declared_workspace_dependencies": False,
            "forbid_dependency_cycles": False,
            "forbid_public_api_leakage": False,
            "forbid_legacy_backend_imports": False,
            "forbid_production_test_fallbacks": False,
            "enforce_legacy_quarantine": False,
            "enforce_videoclaw_quarantine": False,
            "forbid_canonical_to_legacy_imports": False,
            "forbid_legacy_runtime_authority": False,
            "forbid_dynamic_imports": False,
            "enforce_composition_root_rule": False,
            "forbid_application_direct_storage_import": False,
            "forbid_storage_to_provider_import": False,
            "forbid_infrastructure_to_application_import": False,
            "forbid_module_level_mutable_production_store": False,
            "forbid_concrete_adapter_outside_composition": False,
            "composition_roots": [
                "apps/api/windagent_api/composition.py",
                "apps/worker/windagent_worker/composition.py",
                "apps/cli/windagent_cli/composition.py",
            ],
        },
        "forbidden_patterns": {
            "production_fallback_regex": r"\b_fallback_[A-Za-z_][A-Za-z0-9_]*\b",
            "test_adapter_paths": ["tests/"],
            "module_level_store_patterns": [
                "_PROJECTS_STORE",
                "_TASKS_STORE",
                "_DEMO_",
            ],
            "concrete_adapter_instantiation_patterns": ["SqlUnitOfWork"],
            "legacy_quarantine": {
                "zone": "apps/backend",
                "allowlist": ["apps/backend/compat.py"],
                "runtime_authority_blocked_patterns": ["DatabaseManager"],
            },
        },
        "packages": packages,
    }


def rules(report: dict) -> list[str]:
    return [item["rule"] for item in report["violations"]]


def test_v3_application_cannot_import_concrete_storage(tmp_path):
    write_package(
        tmp_path,
        path="orchestration",
        namespace="windagent_orchestration",
        source="from sqlalchemy import select\n",
    )
    packages = {
        "orchestration": package(
            path="orchestration",
            namespace="windagent_orchestration",
            layer="application",
        )
    }
    config = policy(packages)
    config["global_rules"]["forbid_application_direct_storage_import"] = True

    report, _ = checker.check(tmp_path, config)

    assert "application_direct_storage_import" in rules(report)


def test_v3_storage_cannot_import_provider_implementation(tmp_path):
    write_package(
        tmp_path,
        path="storage",
        namespace="windagent_storage",
        source="from windagent_providers.base import Provider\n",
    )
    packages = {
        "storage": package(
            path="storage",
            namespace="windagent_storage",
            layer="infrastructure",
        )
    }
    config = policy(packages)
    config["global_rules"]["forbid_storage_to_provider_import"] = True

    report, _ = checker.check(tmp_path, config)

    assert "storage_to_provider_import" in rules(report)


def test_v3_infrastructure_cannot_import_application(tmp_path):
    write_package(
        tmp_path,
        path="tools",
        namespace="windagent_tools",
        source="from windagent_workflows.jobs import Job\n",
    )
    write_package(
        tmp_path,
        path="workflows",
        namespace="windagent_workflows",
    )
    packages = {
        "tools": package(
            path="tools", namespace="windagent_tools", layer="infrastructure"
        ),
        "workflows": package(
            path="workflows",
            namespace="windagent_workflows",
            layer="application",
        ),
    }
    config = policy(packages)
    config["global_rules"]["forbid_infrastructure_to_application_import"] = True

    report, _ = checker.check(tmp_path, config)

    assert "infrastructure_to_application_import" in rules(report)


def test_v3_composition_rule_reads_nested_policy_keys(tmp_path):
    write_package(
        tmp_path,
        path="orchestration",
        namespace="windagent_orchestration",
        source=(
            "class SqlUnitOfWork:\n"
            "    pass\n\n"
            "def build():\n"
            "    return SqlUnitOfWork()\n"
        ),
    )
    packages = {
        "orchestration": package(
            path="orchestration",
            namespace="windagent_orchestration",
            layer="application",
        )
    }
    config = policy(packages)
    config["global_rules"].update(
        {
            "enforce_composition_root_rule": True,
            "forbid_concrete_adapter_outside_composition": True,
        }
    )

    report, _ = checker.check(tmp_path, config)

    violations = [
        item
        for item in report["violations"]
        if item["rule"] == "concrete_adapter_outside_composition"
    ]
    assert len(violations) == 1
    assert violations[0]["line"] == 5


def test_v3_mutable_store_rule_only_checks_module_scope(tmp_path):
    write_package(
        tmp_path,
        path="apps/api",
        namespace="windagent_api",
        source=(
            "_TASKS_STORE: dict[str, object] = {}\n\n"
            "if True:\n"
            "    _DEMO_CACHE = []\n\n"
            "def request_scope():\n"
            "    _PROJECTS_STORE = {}\n"
            "    return _PROJECTS_STORE\n"
        ),
    )
    packages = {
        "api": package(
            path="apps/api", namespace="windagent_api", layer="app"
        )
    }
    config = policy(packages)
    config["global_rules"]["forbid_module_level_mutable_production_store"] = True

    report, _ = checker.check(tmp_path, config)

    violations = [
        item
        for item in report["violations"]
        if item["rule"] == "module_level_mutable_production_store"
    ]
    assert [item["line"] for item in violations] == [1, 4]


def test_v3_legacy_allowlist_cannot_restore_runtime_authority(tmp_path):
    legacy = tmp_path / "apps" / "backend"
    legacy.mkdir(parents=True)
    (legacy / "compat.py").write_text(
        "class DatabaseManager:\n    pass\n",
        encoding="utf-8",
    )
    config = policy({})
    config["global_rules"].update(
        {
            "enforce_legacy_quarantine": True,
            "forbid_legacy_runtime_authority": True,
        }
    )

    report, _ = checker.check(tmp_path, config)

    assert "legacy_runtime_authority" in rules(report)
    assert "legacy_backend_source_present" not in rules(report)


def test_v3_production_test_fallback_is_rejected(tmp_path):
    write_package(
        tmp_path,
        path="workflows",
        namespace="windagent_workflows",
        source="_fallback_database = object()\n",
    )
    packages = {
        "workflows": package(
            path="workflows",
            namespace="windagent_workflows",
            layer="application",
        )
    }
    config = policy(packages)
    config["global_rules"]["forbid_production_test_fallbacks"] = True

    report, _ = checker.check(tmp_path, config)

    assert "production_fallback_reference" in rules(report)


def test_v3_entrypoint_injects_policy_and_evidence_paths(monkeypatch):
    captured = {}

    def fake_main(argv):
        captured["argv"] = argv
        return 17

    monkeypatch.setattr(v3_entry.check_architecture_imports, "main", fake_main)

    assert v3_entry.main(["--json"]) == 17
    argv = captured["argv"]
    assert "--skip-scaffold-check" in argv
    assert str(ROOT / "configs" / "architecture" / "scaffold_v3.yaml") in argv
    assert str(
        ROOT / "artifacts" / "architecture_v3" / "phase_01" / "v3_boundary_report.json"
    ) in argv


def test_v3_policy_covers_every_workspace_member():
    root_config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    actual = set(root_config["tool"]["uv"]["workspace"]["members"])
    config = yaml.safe_load(
        (ROOT / "configs" / "architecture" / "scaffold_v3.yaml").read_text(
            encoding="utf-8"
        )
    )
    declared = set(config["workspace"]["members"])
    configured = {item["path"] for item in config["packages"].values()}

    assert declared == actual
    assert configured == actual


def test_v3_policy_enables_every_phase_1_checker_capability():
    config = yaml.safe_load(
        (ROOT / "configs" / "architecture" / "scaffold_v3.yaml").read_text(
            encoding="utf-8"
        )
    )
    rules_config = config["global_rules"]
    required = {
        "forbid_dependency_cycles",
        "require_declared_workspace_dependencies",
        "forbid_core_framework_imports",
        "forbid_application_direct_storage_import",
        "forbid_infrastructure_to_application_import",
        "forbid_cross_app_imports",
        "forbid_module_level_mutable_production_store",
        "forbid_production_test_fallbacks",
        "forbid_legacy_runtime_authority",
        "forbid_concrete_adapter_outside_composition",
    }

    assert {key for key in required if rules_config.get(key)} == required
    assert all(not path.endswith("apps/api/**") for path in rules_config["composition_roots"])
