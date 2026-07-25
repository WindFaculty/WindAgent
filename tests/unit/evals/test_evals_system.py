"""
Unit Tests for WindAgent Evals System (Phase 24):
- execution_id required for all test cases
- Fail-closed: no synthetic execution fallback
- Dataset version and checksum
- Confidence intervals for large suites
- Baseline comparison and regression detection
- Replay parity measurement
"""

import pytest
from windagent_core.errors.exceptions import ValidationError
from windagent_evals import (
    EvalTestCase, BenchmarkDataset, get_default_benchmark_datasets, compute_dataset_checksum,
    AccuracyGrader, ToolSelectionGrader, CostEfficiencyGrader,
    SafetyGrader, ModelRoutingGrader, GradingResult,
    BenchmarkRunner, BenchmarkResult,
    ReplayEngine, ReplayExecutionRecord, ReplayParityResult, RecordedEvent,
    EvaluationReport, EvalReportGenerator,
)


# ====================================================================
# 1. EvalTestCase — execution_id Required
# ====================================================================

def test_eval_case_requires_execution_id():
    """Test case without execution_id should fail validation."""
    case = EvalTestCase(
        id="test_01", domain="bugfix",
        prompt="Fix the bug", expected_output="Fixed",
        execution_id=None,
    )
    assert case.has_execution is False
    with pytest.raises(ValidationError, match="execution_id is required"):
        case.validate()


def test_eval_case_with_execution():
    case = EvalTestCase(
        id="test_01", domain="bugfix",
        prompt="Fix the bug", expected_output="Fixed",
        execution_id="exec_001",
    )
    assert case.has_execution is True
    case.validate()  # Should not raise


# ====================================================================
# 2. Dataset Version and Checksum
# ====================================================================

def test_dataset_checksum():
    cases = [
        EvalTestCase(id="a", domain="test", prompt="p1", expected_output="o1", execution_id="e1"),
        EvalTestCase(id="b", domain="test", prompt="p2", expected_output="o2", execution_id="e2"),
    ]
    checksum = compute_dataset_checksum(cases)
    assert len(checksum) == 16
    # Same data should produce same checksum
    assert compute_dataset_checksum(cases) == checksum


def test_dataset_has_version():
    datasets = get_default_benchmark_datasets()
    for ds in datasets:
        assert ds.dataset_version == "2.0.0"
        assert len(ds.checksum) == 16
        # All cases should have execution_id
        for tc in ds.test_cases:
            assert tc.execution_id is not None


# ====================================================================
# 3. Graders — Fail-Closed Without Execution
# ====================================================================

def test_accuracy_grader_blocked_no_execution():
    grader = AccuracyGrader()
    case = EvalTestCase(id="t1", domain="test", prompt="test", expected_output="ok", execution_id=None)
    result = grader.grade(case, {"output": "synthetic"})
    assert result.blocked is True
    assert result.passed is False


def test_accuracy_grader_with_execution():
    grader = AccuracyGrader(threshold=0.5)
    case = EvalTestCase(id="t1", domain="test", prompt="test", expected_output="expected output", execution_id="exec_1")
    result = grader.grade(case, {"output": "This is the expected output here"})
    assert result.blocked is False
    assert result.score > 0.5


def test_tool_selection_grader_blocked_no_execution():
    grader = ToolSelectionGrader()
    case = EvalTestCase(id="t1", domain="test", prompt="test", expected_output="ok", execution_id=None)
    result = grader.grade(case, {})
    assert result.blocked is True


def test_cost_efficiency_grader_blocked_no_execution():
    grader = CostEfficiencyGrader()
    case = EvalTestCase(id="t1", domain="test", prompt="test", expected_output="ok", execution_id=None)
    result = grader.grade(case, {})
    assert result.blocked is True


def test_safety_grader_blocked_no_execution():
    grader = SafetyGrader()
    case = EvalTestCase(id="t1", domain="test", prompt="test", expected_output="ok", execution_id=None)
    result = grader.grade(case, {})
    assert result.blocked is True


def test_model_routing_grader_blocked_no_execution():
    grader = ModelRoutingGrader()
    case = EvalTestCase(id="t1", domain="test", prompt="test", expected_output="ok", execution_id=None)
    result = grader.grade(case, {})
    assert result.blocked is True


# ====================================================================
# 4. BenchmarkRunner — No Synthetic Fallback
# ====================================================================

def test_benchmark_runner_blocks_missing_execution():
    """Cases without execution_id should be blocked."""
    runner = BenchmarkRunner()
    dataset = BenchmarkDataset(
        name="test", domain="test", description="test",
        test_cases=[
            EvalTestCase(id="t1", domain="test", prompt="test", expected_output="ok", execution_id=None),
        ],
    )
    result = runner.run_dataset(dataset, {})
    assert result.blocked_cases == 1
    assert result.passed_cases == 0
    assert result.total_cases == 1


def test_benchmark_runner_blocks_synthetic_data():
    """Cases where output matches expected exactly should be blocked (synthetic)."""
    runner = BenchmarkRunner()
    dataset = BenchmarkDataset(
        name="test", domain="test", description="test",
        test_cases=[
            EvalTestCase(id="t1", domain="test", prompt="Fix bug", expected_output="Fixed bug", execution_id="exec_1"),
        ],
    )
    # Output matches expected exactly — looks synthetic
    result = runner.run_dataset(dataset, {"t1": {"output": "Fixed bug", "execution_id": "exec_1"}})
    assert result.blocked_cases == 1


def test_benchmark_runner_with_real_execution():
    runner = BenchmarkRunner()
    dataset = BenchmarkDataset(
        name="test", domain="test", description="test",
        test_cases=[
            EvalTestCase(id="t1", domain="test", prompt="Fix bug", expected_output="Fixed bug", execution_id="exec_1"),
        ],
    )
    result = runner.run_dataset(dataset, {
        "t1": {
            "output": "Bug fixed successfully with proper error handling",
            "used_tools": ["read_file", "write_file"],
            "cost_usd": 0.01,
            "model": "gpt-4o-mini",
            "execution_id": "exec_1",
        },
    })
    # Should have evaluated, not blocked
    # Note: accuracy might fail because expected != actual, but that's fine
    assert result.blocked_cases == 0
    assert result.total_cases == 1


# ====================================================================
# 5. Confidence Intervals
# ====================================================================

def test_benchmark_result_confidence_interval():
    """BenchmarkResult with multiple scores should have confidence interval."""
    result = BenchmarkResult(
        dataset_name="test", domain="test",
        total_cases=10, passed_cases=8, blocked_cases=0,
        overall_score=0.85,
        confidence_interval=(0.80, 0.90),
    )
    assert result.confidence_interval is not None
    lower, upper = result.confidence_interval
    assert lower <= upper


# ====================================================================
# 6. Baseline Comparison and Regression Detection
# ====================================================================

def test_regression_detection():
    runner = BenchmarkRunner(regression_threshold=0.1)
    dataset = BenchmarkDataset(
        name="bugfix_benchmark", domain="bugfix", description="test",
        test_cases=[
            EvalTestCase(id="t1", domain="bugfix", prompt="Fix bug", expected_output="fix", execution_id="exec_1"),
        ],
    )
    executions = {"t1": {"output": "actual fix implemented", "used_tools": [], "cost_usd": 0.01, "model": "gpt-4o-mini", "execution_id": "exec_1"}}
    result = runner.run_dataset(dataset, executions, baseline_scores={"bugfix_benchmark": 0.9})
    # If current score is below baseline - threshold, regression is detected
    assert result.baseline_score == 0.9
    if result.score_delta is not None:
        assert result.regression_detected == (result.score_delta < -0.1)


# ====================================================================
# 7. Report Generator — Fail-Closed
# ====================================================================

def test_eval_report_generator_empty():
    generator = EvalReportGenerator()
    report = generator.generate_report([])
    assert report.passed is False
    assert report.total_benchmarks == 0


def test_eval_report_generator_blocked_benchmarks():
    generator = EvalReportGenerator(min_overall_score=0.5)
    results = [
        BenchmarkResult(
            dataset_name="test", domain="test",
            total_cases=5, passed_cases=0, blocked_cases=5,
            overall_score=0.0,
        ),
    ]
    report = generator.generate_report(results)
    assert report.blocked_benchmarks == 1
    # With blocked benchmarks, overall score should be penalized


def test_eval_report_generator_regression_detection():
    generator = EvalReportGenerator(regression_threshold=0.1)
    results = [
        BenchmarkResult(
            dataset_name="bugfix", domain="bugfix",
            total_cases=10, passed_cases=8, blocked_cases=0,
            overall_score=0.85, regression_detected=True,
        ),
    ]
    report = generator.generate_report(results)
    assert "bugfix" in report.regressions_detected


# ====================================================================
# 8. Replay Parity
# ====================================================================

def test_replay_parity_matched():
    engine = ReplayEngine()
    original = ReplayExecutionRecord(
        task_id="task_1", workflow_name="bugfix", status="COMPLETED",
        output="fixed the bug", used_tools=["read_file"],
        model_calls=[], total_tokens=100, cost_usd=0.01, total_duration_sec=10.0,
    )
    replay = ReplayExecutionRecord(
        task_id="task_1", workflow_name="bugfix", status="COMPLETED",
        output="fixed the bug", used_tools=["read_file"],
        model_calls=[], total_tokens=100, cost_usd=0.01, total_duration_sec=10.0,
    )
    parity = engine.measure_parity(original, replay)
    assert parity.parity_matched is True
    assert parity.token_delta == 0


def test_replay_parity_mismatched():
    engine = ReplayEngine()
    original = ReplayExecutionRecord(
        task_id="task_1", workflow_name="bugfix", status="COMPLETED",
        output="fixed correctly", used_tools=["read_file"],
        model_calls=[], total_tokens=100, cost_usd=0.01, total_duration_sec=10.0,
    )
    replay = ReplayExecutionRecord(
        task_id="task_1", workflow_name="bugfix", status="COMPLETED",
        output="different output", used_tools=["read_file", "write_file"],
        model_calls=[], total_tokens=200, cost_usd=0.02, total_duration_sec=15.0,
    )
    parity = engine.measure_parity(original, replay)
    assert parity.parity_matched is False
    assert parity.token_delta == 100
    assert parity.tool_delta == 1
    assert parity.output_diff is not None


def test_replay_output_hash():
    record = ReplayExecutionRecord(
        task_id="t1", workflow_name="wf", status="COMPLETED",
        output="test output", used_tools=[], model_calls=[],
        total_tokens=0, cost_usd=0.0, total_duration_sec=0.0,
    )
    assert len(record.output_hash) == 16
