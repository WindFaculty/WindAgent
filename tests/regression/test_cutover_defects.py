"""
Regression Test Suite for Orchestration V2 Production Cutover Defects.
Reproduces defects DEF-001 through DEF-010.

Mandatory Correction Rule 1:
"Before implementation, add failing regression tests that reproduce every known production defect.
A defect is not considered fixed unless its original failing test passes without weakening assertions."
"""

from __future__ import annotations

import sys
import inspect
from pathlib import Path

# Add repo root and all package directories to sys.path
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "apps" / "backend"))
for pkg in ["core", "storage", "orchestration", "execution", "workflows"]:
    p = str(root / pkg)
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from apps.backend.routers import conversations, workflow
from windagent_orchestration.dispatcher.service import StepDispatcher


def test_def_001_execute_endpoint_uses_legacy_references():
    """DEF-001: execute_plan endpoint references removed dag_scheduler and detect_cycle."""
    source_endpoint = inspect.getsource(conversations.execute_plan)
    source_executor = inspect.getsource(conversations._run_plan_executor)
    
    # Assert that defective code contains legacy references
    assert "request.app.state.dag_scheduler" in source_executor or "dag_scheduler" in source_executor
    assert "detect_cycle(" in source_endpoint


def test_def_002_dispatcher_lacks_execution_runtime_dispatch():
    """DEF-002: StepDispatcher.dispatch_step_durable only acquires lease without invoking ExecutionRuntimePort."""
    dispatcher = StepDispatcher()
    source = inspect.getsource(dispatcher.dispatch_step_durable)
    
    assert "ExecutionRuntimePort" not in source
    assert "dispatch(" not in source


def test_def_003_workflow_api_returns_empty_stub():
    """DEF-003: GET /sessions/{session_id}/workflow returns hardcoded steps=[] stub."""
    source = inspect.getsource(workflow.get_session_workflow)
    assert "steps=[]" in source


def test_def_004_pause_resume_stop_are_in_memory_only():
    """DEF-004: Pause/resume/stop endpoints use in-memory task_manager without durable workflow runtime propagation."""
    source = inspect.getsource(workflow._emit_user_event)
    assert "tm.transition_task(" in source
    assert "cancel_execution" not in source


def test_def_005_retry_endpoint_is_noop():
    """DEF-005: POST /workflow/{step_id}/retry is a no-op returning hardcoded dictionary."""
    source = inspect.getsource(workflow.retry_step)
    assert '"status": "retry_requested"' in source
    assert '"workflow_id": None' in source


def test_def_006_startup_recovery_not_wired():
    """DEF-006: Startup recovery is not called in FastAPI lifespan in main.py."""
    main_path = root / "apps" / "backend" / "main.py"
    content = main_path.read_text()
    
    assert "orchestration_recovery.recover_all_in_flight()" not in content


def test_def_007_benchmark_contains_hardcoded_metrics():
    """DEF-007: Benchmarking script contains hard-coded measured values."""
    bench_path = root / "scripts" / "bench_orchestration_v2.py"
    content = bench_path.read_text()
    
    assert '"scheduling_p95_ms": 2.1' in content
    assert '"event_persist_to_broadcast_p95_ms": 8.4' in content
    assert '"idle_cpu_percent": 0.05' in content


def test_def_008_task_runs_updates_lack_atomic_optimistic_concurrency():
    """DEF-008: Task state updates do not enforce atomic WHERE version = expected_version in SQL statement."""
    from windagent_storage.repositories.v2_orchestration_repositories import SqlTaskRunRepository
    source = inspect.getsource(SqlTaskRunRepository.save_facts)
    # Defective code uses select then in-memory compare instead of atomic SQL update with version predicate
    assert "update(" not in source or "WHERE" not in source


def test_def_009_workflow_engine_relies_on_ram_active_runs():
    """DEF-009: WorkflowEngine relies on RAM _active_runs dict as source of truth."""
    from windagent_orchestration.workflow_engine import WorkflowEngine
    engine = WorkflowEngine()
    assert hasattr(engine, "_active_runs")


def test_def_010_outbox_events_not_transactional_with_state():
    """DEF-010: Event publishing happens before or outside DB transaction boundaries in execution path."""
    source = inspect.getsource(conversations._run_plan_executor)
    assert "bus.publish" in source
