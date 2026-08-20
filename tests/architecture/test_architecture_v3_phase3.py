"""Phase 3 — dependency inversion across application and infrastructure boundaries.

Gate:
    application_direct_storage_import = 0
    storage_to_provider_import = 0
    infrastructure_to_application_import = 0
    intelligence -> windagent_providers imports = 0

These tests run the real V3 policy against the actual checkout and assert the
Phase 3 dependency-inversion gates are green.
"""

import re
import sys
from pathlib import Path

import yaml

import check_architecture_imports as checker  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def v3_policy() -> dict:
    return yaml.safe_load(
        (ROOT / "configs" / "architecture" / "scaffold_v3.yaml").read_text(
            encoding="utf-8"
        )
    )


def workspace_report():
    return checker.check(ROOT, v3_policy())


def _violations(report: dict, rule: str) -> list:
    return [item for item in report["violations"] if item["rule"] == rule]


def test_no_application_direct_storage_import():
    report, _ = workspace_report()
    assert _violations(report, "application_direct_storage_import") == []


def test_no_storage_to_provider_import():
    report, _ = workspace_report()
    assert _violations(report, "storage_to_provider_import") == []


def test_no_infrastructure_to_application_import():
    report, _ = workspace_report()
    assert _violations(report, "infrastructure_to_application_import") == []


def test_intelligence_never_imports_providers():
    intelligence_root = ROOT / "intelligence"
    pattern = re.compile(r"(from|import)\s+windagent_providers")
    offenders = []
    for path in intelligence_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for index, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{index}")
    assert offenders == []


def test_roadmap_provider_ports_are_core_owned():
    ports = (ROOT / "core" / "windagent_core" / "contracts" / "providers" / "ports.py").read_text(
        encoding="utf-8"
    )
    for name in (
        "ModelExecutionPort",
        "ModelRegistryPort",
        "ProviderHealthPort",
        "ProviderDiscoveryPort",
        "RoutingAuditPort",
    ):
        assert name in ports
    exported = (
        ROOT / "core" / "windagent_core" / "contracts" / "providers" / "__init__.py"
    ).read_text(encoding="utf-8")
    for name in (
        "ModelExecutionPort",
        "ModelRegistryPort",
        "ProviderHealthPort",
        "ProviderDiscoveryPort",
        "RoutingAuditPort",
    ):
        assert name in exported


def test_neutral_capability_types_are_core_owned():
    model_caps = (
        ROOT / "core" / "windagent_core" / "contracts" / "providers" / "model_capabilities.py"
    ).read_text(encoding="utf-8")
    for name in ("ModelCapability", "ModelCapabilityProfile", "KNOWN_MODEL_PROFILES"):
        assert name in model_caps
    # The intelligence policy must not import provider-owned capability types.
    policy = (
        ROOT / "intelligence" / "windagent_intelligence" / "model_router" / "policy.py"
    ).read_text(encoding="utf-8")
    assert "windagent_providers" not in policy
    assert "windagent_core.contracts.providers.model_capabilities" in policy
