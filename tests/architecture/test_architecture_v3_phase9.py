"""Phase 9 — Production Worker execution pipeline decomposition.

Strong source/runtime guards proving:
- the ``pipeline`` package exists with the required stage modules;
- ``TaskExecutionContext`` carries the full normalized per-task state
  (canonical/raw ids, worker id, fencing token, exact lease id + generation,
  attempt, tool/prompt/parameters, handle/result slots, timestamps, metric);
- only ``finalizer.py`` references the terminal UoW/finalize APIs
  (``SqlUnitOfWork``, ``FinalizeTaskExecutionRequest``,
  ``finalize_task_execution``);
- the executor stage has no commit/UoW imports;
- ``poll_and_execute_tick`` is a small delegate (target <= 15 source lines)
  that routes through ``TaskExecutionPipeline``.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKER_PACKAGE = ROOT / "apps" / "worker" / "windagent_worker"
PIPELINE_DIR = WORKER_PACKAGE / "pipeline"

REQUIRED_PIPELINE_MODULES = {
    "__init__.py",
    "context.py",
    "claim.py",
    "lease_guard.py",
    "executor.py",
    "result_validator.py",
    "finalizer.py",
    "reconciler.py",
    "pipeline.py",
}

# Terminal UoW/finalize API tokens that only finalizer.py may reference.
TERMINAL_FINALIZE_TOKENS = (
    "SqlUnitOfWork",
    "FinalizeTaskExecutionRequest",
    "finalize_task_execution",
)

# Required TaskExecutionContext fields (Architecture V3 Phase 9 contract).
REQUIRED_CONTEXT_FIELDS = {
    "task_id",
    "raw_task_id",
    "worker_id",
    "fencing_token",
    "lease_id",
    "lease_generation",
    "attempt",
    "attempt_id",
    "tool_name",
    "prompt",
    "parameters",
    "handle",
    "result",
    "claimed_at",
    "started_at",
    "execution_finished_at",
    "finalized_at",
    "metric",
}


def _pipeline_source_files() -> list[Path]:
    return sorted(PIPELINE_DIR.rglob("*.py"))


def _pipeline_source_text() -> str:
    parts = []
    for path in _pipeline_source_files():
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


# ── package structure ───────────────────────────────────────────────────────


def test_pipeline_package_modules_exist():
    assert PIPELINE_DIR.is_dir(), "pipeline package directory missing"
    present = {p.name for p in PIPELINE_DIR.rglob("*.py")}
    missing = REQUIRED_PIPELINE_MODULES - present
    assert not missing, f"required pipeline modules missing: {sorted(missing)}"


def test_pipeline_public_imports_work():
    from windagent_worker.pipeline import (
        ClaimStage,
        ExecutorStage,
        FinalizerStage,
        LeaseGuardStage,
        ReconcilerStage,
        ResultValidatorStage,
        TaskExecutionContext,
        TaskExecutionPipeline,
    )

    assert TaskExecutionContext.__name__ == "TaskExecutionContext"
    assert TaskExecutionPipeline.__name__ == "TaskExecutionPipeline"
    assert ClaimStage.__name__ == "ClaimStage"
    assert LeaseGuardStage.__name__ == "LeaseGuardStage"
    assert ExecutorStage.__name__ == "ExecutorStage"
    assert ResultValidatorStage.__name__ == "ResultValidatorStage"
    assert FinalizerStage.__name__ == "FinalizerStage"
    assert ReconcilerStage.__name__ == "ReconcilerStage"


# ── TaskExecutionContext contract ───────────────────────────────────────────


def test_task_execution_context_fields():
    from windagent_worker.pipeline import TaskExecutionContext

    fields = set(TaskExecutionContext.__dataclass_fields__)
    missing = REQUIRED_CONTEXT_FIELDS - fields
    assert not missing, f"TaskExecutionContext missing fields: {sorted(missing)}"


def test_task_execution_context_normalizes_object_and_dict_claims():
    from types import SimpleNamespace

    from windagent_worker.pipeline import TaskExecutionContext

    obj = SimpleNamespace(
        task_id="task_obj",
        fencing_token="fence_obj",
        lease_id="lease_obj",
        lease_generation=2,
        tool_name="code_search",
        prompt="p",
        parameters={"attempt": 4},
        acquired_at=None,
    )
    ctx_obj = TaskExecutionContext.from_claim(obj, worker_id="wkr_1")
    assert ctx_obj.task_id == "task_obj"
    assert ctx_obj.lease_id == "lease_obj"
    assert ctx_obj.lease_generation == 2
    assert ctx_obj.attempt == 4

    legacy = {"task_id": "task_dict", "prompt": "p"}
    ctx_dict = TaskExecutionContext.from_claim(legacy, worker_id="wkr_1")
    assert ctx_dict.task_id == "task_dict"
    assert ctx_dict.lease_id == "lease_task_dict"
    assert ctx_dict.lease_generation == 1
    assert ctx_dict.fencing_token == "fence_task_dict_gen_1"


# ── terminal authority: only finalizer.py ───────────────────────────────────


def test_only_finalizer_references_terminal_uow_finalize_apis():
    for path in _pipeline_source_files():
        source = path.read_text(encoding="utf-8")
        for token in TERMINAL_FINALIZE_TOKENS:
            if token in source and path.name != "finalizer.py":
                raise AssertionError(
                    f"{path.name} references terminal finalize API '{token}'"
                )


def test_finalizer_owns_terminal_finalize_apis():
    finalizer_source = (PIPELINE_DIR / "finalizer.py").read_text(encoding="utf-8")
    for token in TERMINAL_FINALIZE_TOKENS:
        assert token in finalizer_source, f"finalizer.py must reference {token}"


def test_executor_has_no_commit_or_uow_imports():
    executor_source = (PIPELINE_DIR / "executor.py").read_text(encoding="utf-8")
    tree = ast.parse(executor_source, filename=str(PIPELINE_DIR / "executor.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("windagent_storage"), (
                f"executor.py imports storage: {module}"
            )
            assert not module.startswith("sqlalchemy"), (
                f"executor.py imports sqlalchemy: {module}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("windagent_storage"), (
                    f"executor.py imports storage: {alias.name}"
                )
    assert "SqlUnitOfWork" not in executor_source
    assert "finalize_task_execution" not in executor_source
    assert "commit" not in executor_source


def test_other_stages_do_not_import_storage():
    """Only finalizer.py may import concrete storage (UoW) in the pipeline."""
    for path in _pipeline_source_files():
        if path.name == "finalizer.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert "windagent_storage" not in source, (
            f"{path.name} imports concrete storage"
        )


# ── runner tick is a small delegate ─────────────────────────────────────────


def _poll_and_execute_tick_body_lines() -> list[ast.stmt]:
    runner_source = (WORKER_PACKAGE / "runner.py").read_text(encoding="utf-8")
    tree = ast.parse(runner_source, filename=str(WORKER_PACKAGE / "runner.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "poll_and_execute_tick":
            return [
                n
                for n in node.body
                if not (
                    isinstance(n, ast.Expr)
                    and isinstance(n.value, ast.Constant)
                    and isinstance(n.value.value, str)
                )
            ]
    raise AssertionError("poll_and_execute_tick not found in runner.py")


def test_poll_and_execute_tick_is_a_small_delegate():
    body = _poll_and_execute_tick_body_lines()
    assert len(body) <= 15, (
        f"poll_and_execute_tick must be a small delegate, got {len(body)} statements"
    )


def test_poll_and_execute_tick_routes_through_pipeline():
    runner_source = (WORKER_PACKAGE / "runner.py").read_text(encoding="utf-8")
    assert "self._pipeline().run_tick()" in runner_source
    assert "from windagent_worker.pipeline import TaskExecutionPipeline" in runner_source


def test_runner_keeps_legacy_worker_state_attributes():
    """The runner still owns the mutable current-task/cancellation state that
    heartbeat/stop/tests rely on; the pipeline drives it via callbacks."""
    runner_source = (WORKER_PACKAGE / "runner.py").read_text(encoding="utf-8")
    assert "self._current_task_id" in runner_source
    assert "self._current_fencing_token" in runner_source
    assert "self._cancellation_requested" in runner_source
    assert "def _set_current_task" in runner_source
    assert "def _clear_current_task" in runner_source
    assert "def _reset_cancellation" in runner_source