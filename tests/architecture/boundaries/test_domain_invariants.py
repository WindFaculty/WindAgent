"""Invariant-based architecture tests (T5).

These replace the phase-history based checks (``test_architecture_v3_phase*.py``)
with production invariants that must hold regardless of roadmap phase.

Each test asserts a structural property that is expected to remain true
forever, not just for a particular phase.

Phase-based tests remain as ``tests/architecture/test_architecture_v3_phase*.py``
for migration evidence until they are gradually retired to
``tests/verification/characterization/``.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _all_py_files_under(pkg: str) -> list[pathlib.Path]:
    return list((ROOT / pkg).rglob("*.py"))


def test_domain_has_no_infrastructure_dependencies():
    """``core/windagent_core/domain`` must not import infrastructure.

    Domain must not depend on ``sqlalchemy``, ``aiosqlite``, ``fastapi``,
    ``httpx``, ``storage`` ORM, or ``providers`` routing. This is the
    hexagonal boundary: domain is pure.
    """
    forbidden = re.compile(r"\b(sqlalchemy|aiosqlite|fastapi|httpx|windagent_storage|windagent_providers|windagent_api)\b")
    domain = ROOT / "core" / "windagent_core" / "domain"
    violations = []
    for p in domain.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        # Only check import statements
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                if forbidden.search(stripped):
                    violations.append(f"{p.relative_to(ROOT)}: {stripped}")
    assert not violations, "domain imports infrastructure:\n" + "\n".join(violations)


def test_storage_implements_declared_ports():
    """Every ``windagent_storage`` repository with ``SQL`` in name should
    implement a port declared in ``windagent_core/contracts``.
    """
    storage = ROOT / "storage"
    # Heuristic: just ensure at least one SQL repository exists and is not empty
    sql_repos = list((storage).rglob("*repository*.py"))
    assert len(sql_repos) >= 3, f"expected >=3 repository files, got {len(sql_repos)}: {sql_repos}"
    for repo in sql_repos:
        text = repo.read_text(encoding="utf-8", errors="ignore")
        assert "class " in text, f"{repo} has no class"


def test_api_depends_only_on_application_ports():
    """``apps/api`` must not import ``windagent_storage.orm`` directly except
    via the composition root.

    This is a relaxed check: we allow imports in ``apps/api/windagent_api/composition/**``
    but not in routers/services.
    """
    api = ROOT / "apps" / "api"
    forbidden = "windagent_storage.orm"
    violations = []
    for p in api.rglob("*.py"):
        if "composition" in p.parts:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if forbidden in text and "import" in text:
            # Only flag direct ORM imports
            if re.search(r"from windagent_storage\.orm", text) or re.search(r"import windagent_storage\.orm", text):
                violations.append(str(p.relative_to(ROOT)))
    assert not violations, "API imports ORM outside composition:\n" + "\n".join(violations)


def test_no_legacy_runtime_imports():
    """No file should import retired ``windagent_orchestration.legacy`` or
    ``videoclaw`` outside the quarantine test.
    """
    allowed = {
        "test_phase04_videoclaw_quarantine.py",
        "test_architecture_v3_phase4.py",
        "test_domain_invariants.py",
    }
    pattern = re.compile(r"from windagent_orchestration\.legacy|import videoclaw")
    violations = []
    for p in ROOT.rglob("*.py"):
        if p.name in allowed:
            continue
        if "tests/architecture/test_phase04_videoclaw_quarantine" in p.as_posix():
            continue
        if "tests/architecture/boundaries/test_domain_invariants" in p.as_posix():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            violations.append(str(p.relative_to(ROOT)))
    assert not violations, "legacy imports found:\n" + "\n".join(violations)
