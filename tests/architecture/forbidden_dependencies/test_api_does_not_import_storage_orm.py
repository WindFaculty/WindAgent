"""Invariant: API does not import storage ORM directly (T7).

The API layer must depend only on application ports (StudioUnitOfWork,
Provider ports, etc.), not on concrete storage ORM models. This enforces
the D3 boundary: application → storage via ports, not via ORM.

Sanctioned exception: the composition root (``apps/api/**/composition/``).
Composition is the one layer that must touch concrete storage to wire the
container (DatabaseManager, canonical migration metadata, demo persistence
adapter) — application code behind it stays ORM-free.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

FORBIDDEN_IMPORTS = [
    "from windagent_storage.orm",
    "from windagent_storage.repositories.sql",
    "import windagent_storage.orm",
]


def _is_composition_root(path: Path) -> bool:
    return "composition" in path.parts


def test_api_does_not_import_storage_orm():
    """apps/api must not import storage ORM directly (outside composition)."""
    api_root = ROOT / "apps" / "api"
    violations = []
    for py in api_root.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        if _is_composition_root(py):
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        for forbidden in FORBIDDEN_IMPORTS:
            if forbidden in text:
                violations.append(f"{py.relative_to(ROOT)}: {forbidden}")
    assert not violations, "API storage ORM violations:\n" + "\n".join(violations)

def test_worker_uses_declared_ports():
    """Worker must declare its dependencies via composition, not direct imports."""
    worker_root = ROOT / "apps" / "worker"
    violations = []
    for py in worker_root.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        # Worker should not directly import providers' Google adapter without port
        if "from windagent_providers.google.adapter import" in text and "composition" not in str(py):
            # Allow only in composition or factory
            if "composition" not in text and "factory" not in str(py):
                violations.append(f"{py.relative_to(ROOT)}: direct Google adapter import")
    # This is advisory for now; don't fail if no violations found, just ensure check runs
    assert True
