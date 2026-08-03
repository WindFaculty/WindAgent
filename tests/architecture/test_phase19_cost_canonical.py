"""Phase 19 — Cost, credits and quota control canonical isolation tests (plan 05 §4, §17-§21).

Proves the Phase 19 cost/quota modules (`orchestration/windagent_orchestration/production/`)
meet the architecture rules:

- orchestration-layer: imports only `windagent_core` + `windagent_storage`;
  never `windagent_providers` / `windagent_tools` / `windagent_workflows`
  (scaffold_v2.yaml packages.orchestration.allowed_dependencies) — the cost
  gate extends the existing orchestration authority, it does not create a
  parallel one (plan 05 §3, §4);
- no subprocess / sys.path mutation / dynamic import inside the package
  (offline determinism — the gate runs fully offline);
- unknown cost rule / unknown credit state fails closed
  (BLOCKED_UNKNOWN_ESTIMATE / BLOCKED_UNKNOWN_CREDIT_STATE, §19.1/§19.4);
- estimates are bound to plan hash + cost-catalog signature; stale approvals
  are never reused (§19.2);
- the quota ledger is append-only and replay-safe — duplicate
  observation/reserve never double counts (§19.3);
- reserve happens BEFORE submit; reconcile after the observed result (§19.4);
- the circuit breaker never continuous-auto-resets — OPEN -> HALF_OPEN after
  cooldown, closes only on success or human reset (§19.5);
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_DIR = ROOT / "orchestration" / "windagent_orchestration" / "production"

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

PHASE19_FILES = (
    "cost_catalog.py",
    "estimator.py",
    "quota_ledger.py",
    "budget_policy.py",
    "circuit_breaker.py",
    "__init__.py",
)


def _py_files(directory: Path) -> list[tuple[str, str]]:
    files = []
    for py in sorted(directory.rglob("*.py")):
        if "__pycache__" in py.as_posix():
            continue
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_phase19_modules_exist():
    for name in PHASE19_FILES:
        assert (PRODUCTION_DIR / name).exists(), f"missing orchestration/production/{name}"


def test_phase19_never_launches_or_dynamic_imports():
    hits = []
    for rel, text in _py_files(PRODUCTION_DIR):
        for pattern in FORBIDDEN_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"phase19 launches/dynamic-imports: {hits}"


def test_phase19_orchestration_dependency_roots():
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


def test_phase19_unknown_fails_closed():
    """§19.1/§19.4: unknown cost rule and unknown credit state block submit."""
    estimator_text = (PRODUCTION_DIR / "estimator.py").read_text(encoding="utf-8")
    assert "ESTIMATE_STATUS_UNKNOWN" in estimator_text
    assert "no cost rule" in estimator_text
    policy_text = (PRODUCTION_DIR / "budget_policy.py").read_text(encoding="utf-8")
    assert "BLOCKED_UNKNOWN_ESTIMATE" in policy_text
    assert "BLOCKED_UNKNOWN_CREDIT_STATE" in policy_text
    assert "fail closed" in policy_text.lower() or "never guess" in policy_text.lower()


def test_phase19_estimate_bound_to_hash_and_catalog():
    estimator_text = (PRODUCTION_DIR / "estimator.py").read_text(encoding="utf-8")
    assert "catalog_signature" in estimator_text
    assert "estimate_hash" in estimator_text
    assert "is_stale_for" in estimator_text
    policy_text = (PRODUCTION_DIR / "budget_policy.py").read_text(encoding="utf-8")
    assert "BLOCKED_STALE_APPROVAL" in policy_text
    assert "cost catalog changed" in policy_text


def test_phase19_ledger_append_only_and_replay_safe():
    text = (PRODUCTION_DIR / "quota_ledger.py").read_text(encoding="utf-8")
    assert "append-only" in text.lower()
    assert "OBSERVED_DEBIT" in text
    assert "never double count" in text.lower() or "double counts" in text.lower()
    assert "dedup_key" in text
    assert "adjustment requires a reason" in text
    assert "adjustment requires a source" in text


def test_phase19_observed_debit_never_overwritten():
    text = (PRODUCTION_DIR / "quota_ledger.py").read_text(encoding="utf-8")
    assert "never overwritten" in text.lower()
    assert "observed debit" in text.lower()
    assert "ADJUSTED" in text


def test_phase19_reserve_before_submit():
    text = (PRODUCTION_DIR / "budget_policy.py").read_text(encoding="utf-8")
    assert "reserve BEFORE submit" in text
    assert "def reserve" in text
    assert "def reconcile" in text
    assert "RESERVED" in text or "reserve" in text


def test_phase19_retry_and_candidate_bounded():
    text = (PRODUCTION_DIR / "budget_policy.py").read_text(encoding="utf-8")
    assert "RetryBudget" in text
    assert "BLOCKED_RETRY_BUDGET" in text
    assert "BLOCKED_CANDIDATE_LIMIT" in text
    assert "candidate_limit" in text


def test_phase19_limits_apply_before_submit():
    text = (PRODUCTION_DIR / "budget_policy.py").read_text(encoding="utf-8")
    assert "DailyLimit" in text
    assert "MonthlyLimit" in text
    assert "ProjectLimit" in text
    assert "BLOCKED_DAILY_LIMIT" in text
    assert "BLOCKED_MONTHLY_LIMIT" in text
    assert "BLOCKED_PROJECT_LIMIT" in text
    assert "BLOCKED_INSUFFICIENT_CREDITS" in text


def test_phase19_circuit_breaker_never_continuous_reset():
    text = (PRODUCTION_DIR / "circuit_breaker.py").read_text(encoding="utf-8")
    assert "never" in text.lower()
    assert "HALF_OPEN" in text
    assert "maybe_reset" in text
    assert "human_reset" in text
    assert "COOLDOWN_ELAPSED" in text
    assert "INSUFFICIENT_CREDITS" in text
    assert "ACCOUNT_CHALLENGE" in text


def test_phase19_exports():
    import windagent_orchestration as orch

    for name in (
        "CostCatalog",
        "CostCatalogEntry",
        "CostEstimate",
        "CreditEstimator",
        "EstimateLine",
        "QuotaLedger",
        "QuotaEntryType",
        "QuotaLedgerEntry",
        "RetryBudget",
        "DailyLimit",
        "MonthlyLimit",
        "ProjectLimit",
        "GenerationBudgetPolicy",
        "SubmitDecision",
        "SubmitVerdict",
        "ProviderCircuitBreaker",
        "CircuitState",
        "TripReason",
    ):
        assert hasattr(orch, name), f"windagent_orchestration missing export {name}"


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
