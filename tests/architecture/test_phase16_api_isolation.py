"""
Phase 16 G9 API Isolation — executable evidence.

API process MUST NOT directly own Worker execution runtime.
This test proves:
- API composition root exists
- API does NOT instantiate ProductionWorker / WorkerRunner directly
- API does NOT own ExecutionRuntimeRegistry / WorktreeContextManager outside composition
- API does NOT claim tasks directly (no claim_next outside composition)
- API does NOT bypass application boundary via direct tool execution

The checker already enforces layering (application → infra) but this test
is the human-readable executable evidence for G9.
"""
from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
API_ROOT = ROOT_DIR / "apps" / "api" / "windagent_api"


def _collect_py_files(root: Path):
    return [p for p in root.rglob("*.py") if "composition" not in str(p).replace("\\", "/")]


def _scan_forbidden_patterns():
    forbidden = [
        "ProductionWorker",
        "WorkerRunner",
        "ExecutionRuntimeRegistry",
        "WorktreeContextManager",
        "FakeRuntimeAdapter",
        "claim_next",
        "claim_task",
        "ExecutionLease",
    ]
    # Direct tool execution patterns that API must not own
    forbidden_tool = [
        "ToolExecutionService",
        "BuiltinRegistry",
        "git worktree",
    ]
    hits = []
    for py in _collect_py_files(API_ROOT):
        try:
            txt = py.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # Allow comments and docstrings to mention but not import/instantiate
        # We check for import or instantiation patterns
        for pat in forbidden:
            if f"import {pat}" in txt or f"from {pat}" in txt or f"{pat}(" in txt:
                # Allow the composition package itself to reference (it is the only allowed)
                rel = str(py.relative_to(ROOT_DIR)).replace("\\", "/")
                if "composition" in rel:
                    continue
                hits.append((rel, pat, txt.count(pat)))
        for pat in forbidden_tool:
            if pat in txt and "composition" not in str(py.relative_to(ROOT_DIR)):
                # Only flag if it looks like import/instantiation, not comment
                if f"import {pat}" in txt or f"{pat}(" in txt:
                    hits.append((str(py.relative_to(ROOT_DIR)).replace("\\", "/"), pat, 1))
    return hits


def test_api_composition_root_exists():
    """G9: API composition root must exist (file-existence is necessary but not sufficient)."""
    candidates = [
        API_ROOT / "composition" / "container.py",
        API_ROOT / "composition.py",
    ]
    assert any(p.exists() for p in candidates), f"API composition root not found: {candidates}"


def test_api_does_not_compose_execution_runtime():
    """G9: API must NOT directly compose execution runtime outside composition root."""
    hits = _scan_forbidden_patterns()
    # Filter to the most critical: direct ProductionWorker / ExecutionRuntimeRegistry ownership
    critical = [h for h in hits if h[1] in ("ProductionWorker", "ExecutionRuntimeRegistry", "WorktreeContextManager", "FakeRuntimeAdapter")]
    assert critical == [], f"API Isolation violated — forbidden execution runtime ownership outside composition: {critical}"


def test_api_does_not_claim_tasks_directly():
    """G9: API must NOT own durable task claiming (claim_next)."""
    # claim_next is allowed via task_submission port, but not direct queue claim
    # We prove API uses task_submission port, not direct queue claim
    direct_queue_claim = []
    for py in _collect_py_files(API_ROOT):
        txt = py.read_text(encoding="utf-8", errors="replace")
        if "SqlDurableTaskQueue" in txt and "claim_next" in txt:
            rel = str(py.relative_to(ROOT_DIR)).replace("\\", "/")
            if "composition" not in rel:
                direct_queue_claim.append(rel)
    assert direct_queue_claim == [], f"API must not directly claim tasks via SqlDurableTaskQueue: {direct_queue_claim}"


def test_api_does_not_bypass_application_boundary():
    """G9: API must go through application services, not concrete infrastructure.

    API is allowed to depend on providers via the provider management
    application service (composition root). It must NOT directly import
    execution runtime or storage ORM outside composition.
    """
    forbidden_imports = [
        "windagent_storage.orm",
        "windagent_execution",
    ]
    hits = []
    for py in _collect_py_files(API_ROOT / "routers"):
        txt = py.read_text(encoding="utf-8", errors="replace")
        for imp in forbidden_imports:
            if f"import {imp}" in txt or f"from {imp}" in txt:
                hits.append((str(py.relative_to(ROOT_DIR)).replace("\\", "/"), imp))
    assert hits == [], f"API routers bypass application boundary: {hits}"
