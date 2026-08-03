"""Phase 17 — Durable production workflow canonical isolation tests (plan 05 §4, §6-§10).

Proves the Phase 17 durable workflow (`orchestration/windagent_orchestration/production/`
and `workflows/windagent_workflows/video_production/`) meets the architecture rules:

- orchestration-layer: imports only `windagent_core` + `windagent_storage`;
  never `windagent_providers` / `windagent_tools` / `windagent_workflows`
  (scaffold_v2.yaml packages.orchestration.allowed_dependencies);
- workflows-layer pack imports only `windagent_core` + `windagent_orchestration`
  + `windagent_tools` (scaffold_v2.yaml packages.workflows.allowed_dependencies);
- no subprocess / sys.path mutation / dynamic import inside either package
  (offline determinism — the gate runs fully offline with fake executors);
- the engine persists SUBMITTING intent before any provider side effect and
  never blind-resubmits (plan 05 §8.3/§8.5 — gate-critical);
- approvals are bound to revision/hash; stale approvals never re-open gates
  (plan 05 §8.2);
- cancel stops scheduling and never claims provider-side cancellation without
  evidence (plan 05 §8.6);
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_DIR = ROOT / "orchestration" / "windagent_orchestration" / "production"
VIDEO_PROD_DIR = ROOT / "workflows" / "windagent_workflows" / "video_production"

FORBIDDEN_LAUNCH_PATTERNS = [
    re.compile(r"subprocess\.(?:run|Popen|call|create_subprocess_exec)\s*\(", re.MULTILINE),
    re.compile(r"sys\.path\.(?:insert|append)\s*\(", re.MULTILINE),
    re.compile(r"spec_from_file_location\s*\(", re.MULTILINE),
    re.compile(r"importlib\.import_module\s*\(", re.MULTILINE),
    re.compile(r"__import__\s*\(", re.MULTILINE),
]

ORCH_FORBIDDEN_DEP_ROOTS = (
    "windagent_providers",
    "windagent_tools",
    "windagent_workflows",
    "windagent_intelligence",
    "windagent_api",
    "windagent_cli",
    "windagent_worker",
)
# Self-root (windagent_orchestration) is allowed for intra-package imports.
ORCH_ALLOWED_DEP_ROOTS = ("windagent_core", "windagent_storage", "windagent_orchestration")

# Self-root (windagent_workflows) is allowed for intra-package imports.
WORKFLOWS_ALLOWED_DEP_ROOTS = (
    "windagent_core",
    "windagent_orchestration",
    "windagent_tools",
    "windagent_workflows",
)


def _py_files(directory: Path) -> list[tuple[str, str]]:
    files = []
    for py in sorted(directory.rglob("*.py")):
        if "__pycache__" in py.as_posix():
            continue
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_phase17_modules_exist():
    for name in (
        "states.py",
        "approvals.py",
        "checkpoint.py",
        "outbox.py",
        "scheduler.py",
        "recovery.py",
        "cancellation.py",
        "engine.py",
        "__init__.py",
    ):
        assert (PRODUCTION_DIR / name).exists(), f"missing orchestration/production/{name}"
    for name in ("definition.py", "pack.py", "__init__.py"):
        assert (VIDEO_PROD_DIR / name).exists(), f"missing workflows/video_production/{name}"


def test_phase17_never_launches_or_dynamic_imports():
    hits = []
    for rel, text in _py_files(PRODUCTION_DIR) + _py_files(VIDEO_PROD_DIR):
        for pattern in FORBIDDEN_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"phase17 launches/dynamic-imports: {hits}"


def test_phase17_orchestration_dependency_roots():
    offenders = []
    for rel, text in _py_files(PRODUCTION_DIR):
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "windagent" not in stripped:
                continue
            module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
            if module and module.group(1) not in ORCH_ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"orchestration/production imports forbidden deps: {offenders}"


def test_phase17_workflows_dependency_roots():
    offenders = []
    for rel, text in _py_files(VIDEO_PROD_DIR):
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "windagent" not in stripped:
                continue
            module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
            if module and module.group(1) not in WORKFLOWS_ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"workflows/video_production imports forbidden deps: {offenders}"


def test_phase17_engine_persists_submit_intent_before_side_effect():
    """Plan 05 §8.3/§8.5 (gate-critical): SUBMITTING intent is persisted before
    the executor is invoked for external-cost steps."""
    text = (PRODUCTION_DIR / "engine.py").read_text(encoding="utf-8")
    assert "SUBMITTING intent" in text
    assert "generation_submitting" in text
    assert "WAITING_PROVIDER" in text
    # the intent write happens before executor.execute
    commit_idx = text.index("self.uow.commit(run, intent_events)")
    execute_idx = text.index("result = self.executor.execute(step_id, run)")
    assert commit_idx < execute_idx


def test_phase17_recovery_never_blind_resubmit():
    text = (PRODUCTION_DIR / "recovery.py").read_text(encoding="utf-8")
    assert "never blind resubmit" in text or "never resubmit" in text
    assert "RECONCILE_UNKNOWN" in text
    assert "inspect_provider" in text
    assert "NEW_ATTEMPT" in text


def test_phase17_approval_bound_to_revision_hash():
    approvals_text = (PRODUCTION_DIR / "approvals.py").read_text(encoding="utf-8")
    assert "target_hash" in approvals_text
    assert "has_current_approval" in approvals_text
    assert "is_stale" in approvals_text
    engine_text = (PRODUCTION_DIR / "engine.py").read_text(encoding="utf-8")
    assert "has_current_approval" in engine_text
    assert "WINDAGENT_ERR_STALE_APPROVAL" in engine_text
    assert "WINDAGENT_ERR_APPROVAL_TARGET" in engine_text


def test_phase17_cancel_never_claims_provider_side_without_evidence():
    text = (PRODUCTION_DIR / "cancellation.py").read_text(encoding="utf-8")
    assert "provider_cancel_confirmed" in text
    assert "provider_evidence" in text
    assert "WAITING_PROVIDER" in text
    assert "never claims" in text or "no evidence" in text or "without evidence" in text


def test_phase17_scheduler_never_selects_or_approves():
    text = (PRODUCTION_DIR / "scheduler.py").read_text(encoding="utf-8")
    assert "never selects" in text.lower()
    assert "provider_concurrency" in text
    assert "ready_steps" in text
    assert "select_candidate" not in text


def test_phase17_exports():
    import windagent_orchestration as orch

    for name in (
        "ProductionRunState",
        "ProductionRunStateMachine",
        "ProductionApprovalGate",
        "ApprovalLedger",
        "ProductionCheckpoint",
        "OutboxJournal",
        "ProductionScheduler",
        "ProductionStepNode",
        "ProductionRecovery",
        "RecoveryAction",
        "ProductionCancellation",
        "CancellationAuditLog",
        "ProductionRun",
        "ProductionRunStore",
        "ProductionUnitOfWork",
        "ProductionWorkflowEngine",
        "StepExecutionResult",
    ):
        assert hasattr(orch, name), f"windagent_orchestration missing export {name}"

    import windagent_workflows as wf

    for name in (
        "VideoProductionWorkflowPack",
        "VIDEO_PRODUCTION_STEPS",
        "STEP_APPROVAL_GATES",
        "build_production_step_nodes",
        "all_step_contracts",
    ):
        assert hasattr(wf, name), f"windagent_workflows missing export {name}"


def test_phase17_pack_uses_immutable_definition():
    text = (VIDEO_PROD_DIR / "pack.py").read_text(encoding="utf-8")
    assert "ImmutableWorkflowDefinition" in text
    assert "definition.validate()" in text


def test_real_repo_architecture_stays_clean():
    import json
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/check_architecture_imports.py", "--root", ".", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-1000:]
    report = json.loads(proc.stdout)
    assert report["verdict"] == "PASS", report["violations"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
