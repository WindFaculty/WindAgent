"""
Unit tests for Phase 24 — Controlled E2E Video Production PoC (VP24_E2E_POC_PASSED).
"""

from __future__ import annotations

import pytest
from windagent_core.domain.video_production.e2e_poc import (
    AutomationRateMetric,
    CostReport,
    PocRunManifest,
)
from windagent_core.domain.video_production.ids import (
    ProductionRevisionId,
    VideoProjectId,
)
from windagent_intelligence.video.e2e_poc import (
    AutomationCalculator,
    PocRunner,
    RecoveryAuditor,
    TraceabilityAuditor,
)


@pytest.fixture
def sample_manifest() -> PocRunManifest:
    return PocRunManifest(
        run_id="run_poc_e2e_01",
        project_id=VideoProjectId("vp_poc"),
        revision_id=ProductionRevisionId("rev_poc_01"),
        planned_scenes=2,
        planned_shots=6,
        planned_duration_seconds=35.0,
    )


def test_14_step_runbook_execution(sample_manifest: PocRunManifest):
    """PocRunner executes all 14 runbook steps sequentially."""
    runner = PocRunner()
    receipts = runner.execute_runbook(sample_manifest)
    assert len(receipts) == 14
    assert receipts[0].step_number == 1
    assert receipts[-1].step_number == 14
    assert all(r.status == "COMPLETED" for r in receipts)


def test_traceability_graph_auditing(sample_manifest: PocRunManifest):
    """TraceabilityAuditor builds complete DAG from final deliverable back to screenplay."""
    auditor = TraceabilityAuditor()
    graph = auditor.build_traceability_graph(
        run_id=sample_manifest.run_id,
        deliverable_hash="hash_final_mp4_123",
        edl_hash="hash_edl_456",
        shot_hashes=("hash_shot_1", "hash_shot_2"),
        audio_hash="hash_audio_789",
        script_hash="hash_script_rev_01",
    )
    assert graph.is_complete is True
    assert len(graph.nodes) >= 6
    assert graph.deliverable_hash == "hash_final_mp4_123"


def test_browser_recovery_zero_duplicate_submits(sample_manifest: PocRunManifest):
    """RecoveryAuditor verifies disconnect simulation, reattach, and zero duplicate submits."""
    auditor = RecoveryAuditor()
    receipt = auditor.audit_session_recovery(run_id=sample_manifest.run_id)
    assert receipt.is_passed is True
    assert receipt.duplicate_submits_count == 0


def test_automation_rate_calculator():
    """AutomationCalculator calculates automation rate and checks 80% threshold."""
    calc = AutomationCalculator()

    # 100% automation (0 manual edits out of 6 shots)
    metric_100 = calc.calculate_automation_rate(total_planned_shots=6, manual_edits_count=0)
    assert metric_100.automation_rate == 1.0
    assert metric_100.satisfies_threshold is True

    # 83.3% automation (1 manual edit out of 6 shots)
    metric_83 = calc.calculate_automation_rate(total_planned_shots=6, manual_edits_count=1)
    assert metric_83.automation_rate > 0.80
    assert metric_83.satisfies_threshold is True

    # 66.7% automation (2 manual edits out of 6 shots) -> FAILS threshold
    metric_66 = calc.calculate_automation_rate(total_planned_shots=6, manual_edits_count=2)
    assert metric_66.automation_rate < 0.80
    assert metric_66.satisfies_threshold is False


def test_cost_report_satisfies_budget():
    """CostReport verifies observed debits <= max approved credits."""
    cost_ok = CostReport(
        run_id="run_poc_e2e_01",
        max_approved_credits=50.0,
        estimated_credits=25.0,
        debited_credits=22.5,
        remaining_credits=27.5,
        ledger_reconciled=True,
    )
    assert cost_ok.satisfies_budget is True

    cost_over = CostReport(
        run_id="run_poc_e2e_01",
        max_approved_credits=50.0,
        estimated_credits=25.0,
        debited_credits=55.0,  # Exceeded budget
        remaining_credits=-5.0,
        ledger_reconciled=True,
    )
    assert cost_over.satisfies_budget is False
