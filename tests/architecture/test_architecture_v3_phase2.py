"""Phase 2 — break every dependency cycle in the workspace dependency graph.

Gate:
    dependency_cycles = 0
    undeclared_workspace_dependencies = 0

These tests run the real V3 policy against the actual checkout and assert the
workspace dependency graph is a DAG with no undeclared workspace edges.
"""

import re
import sys
import tomllib
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


def test_workspace_graph_has_no_dependency_cycles():
    report, _ = workspace_report()
    assert report["circular_dependency_cycles"] == 0
    cycles = [
        item for item in report["violations"] if item["rule"] == "dependency_cycle"
    ]
    assert cycles == []


def test_workspace_has_no_undeclared_dependencies():
    report, _ = workspace_report()
    undeclared = [
        item
        for item in report["violations"]
        if item["rule"] == "undeclared_workspace_dependency"
    ]
    assert undeclared == []


def test_tools_never_imports_workflows():
    tools_root = ROOT / "tools"
    pattern = re.compile(r"(from|import)\s+windagent_workflows")
    offenders = []
    for path in tools_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for index, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{index}")
    assert offenders == []


def test_code_video_contracts_live_in_core():
    contracts_init = ROOT / "core" / "windagent_core" / "contracts" / "code_video"
    assert (contracts_init / "__init__.py").is_file()
    source = (contracts_init / "models.py").read_text(encoding="utf-8")
    for name in ("Scene", "Resolution", "Action", "CodeVideoPlan"):
        assert name in source
    exported = (contracts_init / "__init__.py").read_text(encoding="utf-8")
    for name in ("Scene", "Resolution", "Action", "CodeVideoPlan"):
        assert name in exported


def test_workflows_code_video_contracts_is_core_shim():
    shim = ROOT / "workflows" / "windagent_workflows" / "code_video" / "contracts.py"
    source = shim.read_text(encoding="utf-8")
    assert "windagent_core.contracts.code_video" in source
    assert "compatibility shim" in source.lower()


def test_workflows_declares_tools_dependency():
    pyproject = tomllib.loads(
        (ROOT / "workflows" / "pyproject.toml").read_text(encoding="utf-8")
    )
    declared = set(pyproject["project"]["dependencies"])
    assert "windagent-tools" in declared


def test_workflows_to_tools_edge_is_gone():
    """V3 hardening removed the workflows → tools edge (Phase 2+ cleanup).

    All windagent_workflows imports of windagent_tools were retired, so the
    actual-import adjacency list no longer contains the edge even though a
    legacy declared dependency may remain in workflows/pyproject.toml.
    The gate stays strict: no undeclared edges, no cycles, and
    workflows must NOT import windagent_tools anywhere.
    """
    report, graph = workspace_report()
    adjacency = graph["adjacency_list"]
    assert "tools" not in adjacency.get("workflows", [])
    undeclared = [
        item for item in report["violations"] if "tools" in str(item.get("to", "")) or "windagent-tools" in str(item)
    ]
    assert undeclared == []
    assert "workflows" not in adjacency.get("tools", set())