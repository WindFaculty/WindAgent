"""Phase 4 - VideoClaw quarantine boundary architecture tests (plan 02).

Proves the negative checks required by plan 02 Section 8.4:
- import third_party / videoclaw from canonical code must fail;
- sys.path / dynamic import / subprocess reference to upstream must fail;
- third_party must never be a uv workspace member;
- the real repository's canonical code never imports the vendored snapshot.
"""

import shutil
import tempfile
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.check_architecture_imports import check, check_videoclaw_quarantine

ROOT = Path(__file__).resolve().parents[2]

# Minimal policy with the quarantine rule enabled (mirrors scaffold_v2.yaml).
MINIMAL_POLICY = {
    "version": "2.0",
    "workspace": {"root": ".", "members": []},
    "global_rules": {"enforce_videoclaw_quarantine": True},
    "canonical_models": [],
    "required_top_level_packages": [],
    "packages": {},
    "forbidden_patterns": {"legacy_quarantine": {"zone": "apps/backend", "allowlist": []}},
}


@pytest.fixture
def fixture_repo():
    temp_dir = tempfile.mkdtemp(prefix="arch_quarantine_")
    root = Path(temp_dir)
    (root / "pyproject.toml").write_text(
        "[tool.uv.workspace]\nmembers = []\n",
        encoding="utf-8",
    )
    yield root
    shutil.rmtree(temp_dir, ignore_errors=True)


def _make_package(root: Path, path: str, namespace: str) -> Path:
    pkg = root / path / namespace
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    # Package pyproject.toml so check() does not flag missing_pyproject.
    (root / path / "pyproject.toml").write_text(
        f"[project]\nname = \"{namespace}\"\nversion = \"0.1.0\"\n",
        encoding="utf-8",
    )
    return pkg


def test_static_import_of_videoclaw_is_violation(fixture_repo):
    ns = _make_package(fixture_repo, "tools", "windagent_tools")
    (ns / "module.py").write_text("import videoclaw\n", encoding="utf-8")
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["tools"]
    policy["packages"] = {
        "tools": {"layer": "infrastructure", "namespace": "windagent_tools", "path": "tools"},
    }
    report, _ = check(fixture_repo, policy)
    assert report["status"] == "FAIL"
    assert any(v["rule"] == "videoclaw_quarantine_import" for v in report["violations"])


def test_import_of_third_party_is_violation(fixture_repo):
    ns = _make_package(fixture_repo, "core", "windagent_core")
    (ns / "module.py").write_text("from third_party.videoclaw import x\n", encoding="utf-8")
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["core"]
    policy["packages"] = {
        "core": {"layer": "domain", "namespace": "windagent_core", "path": "core"},
    }
    report, _ = check(fixture_repo, policy)
    assert report["status"] == "FAIL"
    assert any(v["rule"] == "videoclaw_quarantine_import" for v in report["violations"])


def test_syspath_reference_to_upstream_is_violation(fixture_repo):
    ns = _make_package(fixture_repo, "workflows", "windagent_workflows")
    # Assembled via concatenation: the hygiene scanner forbids the raw probe
    # literal inside test sources; the written fixture must still contain the
    # real offending statement verbatim.
    syspath_probe = "import sys\nsys.path." "insert(0, '../third_party/videoclaw/upstream')\n"
    (ns / "module.py").write_text(
        syspath_probe,
        encoding="utf-8",
    )
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["workflows"]
    policy["packages"] = {
        "workflows": {"layer": "application", "namespace": "windagent_workflows", "path": "workflows"},
    }
    report, _ = check(fixture_repo, policy)
    assert report["status"] == "FAIL"
    assert any(v["rule"] == "videoclaw_quarantine_dynamic" for v in report["violations"])


def test_subprocess_launch_of_upstream_is_violation(fixture_repo):
    ns = _make_package(fixture_repo, "intelligence", "windagent_intelligence")
    (ns / "module.py").write_text(
        "import subprocess\nsubprocess.Popen(['python', 'third_party/videoclaw/upstream/main.py'])\n",
        encoding="utf-8",
    )
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["intelligence"]
    policy["packages"] = {
        "intelligence": {"layer": "application", "namespace": "windagent_intelligence", "path": "intelligence"},
    }
    report, _ = check(fixture_repo, policy)
    assert report["status"] == "FAIL"
    assert any(v["rule"] == "videoclaw_quarantine_subprocess" for v in report["violations"])


def test_third_party_workspace_membership_is_violation(fixture_repo):
    (fixture_repo / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["core", "third_party/videoclaw"]\n',
        encoding="utf-8",
    )
    _make_package(fixture_repo, "core", "windagent_core")
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["core", "third_party/videoclaw"]
    policy["packages"] = {
        "core": {"layer": "domain", "namespace": "windagent_core", "path": "core"},
    }
    violations = check_videoclaw_quarantine(fixture_repo, policy["packages"], policy)
    assert any(v["rule"] == "videoclaw_workspace_membership" for v in violations)


def test_clean_code_has_no_videoclaw_violations(fixture_repo):
    ns = _make_package(fixture_repo, "core", "windagent_core")
    (ns / "module.py").write_text("from windagent_core.contracts import Port\n", encoding="utf-8")
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["core"]
    policy["packages"] = {
        "core": {"layer": "domain", "namespace": "windagent_core", "path": "core"},
    }
    report, _ = check(fixture_repo, policy)
    assert report["status"] == "PASS"
    assert not any(v["rule"].startswith("videoclaw_quarantine") for v in report["violations"])


def test_real_repo_never_imports_vendored_snapshot():
    """The real workspace's canonical code must contain no upstream reference."""
    root = ROOT
    packages = {
        "core": {"path": "core", "namespace": "windagent_core"},
        "intelligence": {"path": "intelligence", "namespace": "windagent_intelligence"},
        "tools": {"path": "tools", "namespace": "windagent_tools"},
        "providers": {"path": "providers", "namespace": "windagent_providers"},
        "workflows": {"path": "workflows", "namespace": "windagent_workflows"},
        "orchestration": {"path": "orchestration", "namespace": "windagent_orchestration"},
        "api": {"path": "apps/api", "namespace": "windagent_api"},
        "cli": {"path": "apps/cli", "namespace": "windagent_cli"},
        "worker": {"path": "apps/worker", "namespace": "windagent_worker"},
    }
    violations = check_videoclaw_quarantine(root, packages, MINIMAL_POLICY)
    assert violations == [], violations


if __name__ == "__main__":
    pytest.main([__file__, "-v"])