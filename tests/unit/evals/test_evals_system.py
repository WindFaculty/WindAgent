"""
Unit tests for WindAgent Evals subsystem (Phase 11):
- Benchmark dataset initialization (10 core domains)
- Objective Graders (AccuracyGrader, ToolSelectionGrader, CostEfficiencyGrader, SafetyGrader, ModelRoutingGrader)
- BenchmarkRunner execution
- Deterministic ReplayEngine history reconstruction
- EvalReportGenerator score aggregation
"""

from windagent_evals import (
    get_default_benchmark_datasets, EvalTestCase,
    AccuracyGrader, ToolSelectionGrader, CostEfficiencyGrader, SafetyGrader, ModelRoutingGrader,
    BenchmarkRunner, ReplayEngine, EvalReportGenerator
)


def test_default_benchmark_datasets_cover_all_10_domains():
    datasets = get_default_benchmark_datasets()
    assert len(datasets) == 10

    expected_domains = {
        "bugfix", "feature", "ci_repair", "code_review", "research",
        "tool_selection", "model_routing", "recovery", "permission_safety", "cost"
    }

    actual_domains = {d.domain for d in datasets}
    assert actual_domains == expected_domains


def test_graders_evaluation():
    test_case = EvalTestCase(
        id="test_01",
        domain="bugfix",
        prompt="Fix calculation",
        expected_output="return a + b",
        expected_tools=["read_file", "write_to_file"],
        max_cost_usd=0.05,
        allowed_models=["gpt-4o-mini"]
    )

    exec_data = {
        "output": "def sum(a, b): return a + b",
        "used_tools": ["read_file", "write_to_file"],
        "cost_usd": 0.02,
        "model": "gpt-4o-mini"
    }

    acc = AccuracyGrader().grade(test_case, exec_data)
    assert acc.passed is True

    tool = ToolSelectionGrader().grade(test_case, exec_data)
    assert tool.passed is True

    cost = CostEfficiencyGrader().grade(test_case, exec_data)
    assert cost.passed is True

    safety = SafetyGrader().grade(test_case, exec_data)
    assert safety.passed is True

    mr = ModelRoutingGrader().grade(test_case, exec_data)
    assert mr.passed is True


def test_benchmark_runner_and_report_generator():
    datasets = get_default_benchmark_datasets()
    runner = BenchmarkRunner()

    benchmark_results = []
    for ds in datasets:
        res = runner.run_dataset(ds, {})
        benchmark_results.append(res)

    assert len(benchmark_results) == 10

    report_gen = EvalReportGenerator(min_overall_score=0.7)
    report = report_gen.generate_report(benchmark_results)

    assert report.total_benchmarks == 10
    assert report.overall_accuracy_score > 0.7
    assert report.passed is True


def test_replay_engine_deterministic_reconstruction():
    events = [
        {"step_id": "step_0", "event_type": "task_started", "payload": {"task_id": "task_99", "workflow_name": "bugfix"}, "timestamp": 100.0},
        {"step_id": "step_1", "event_type": "model_call", "payload": {"tokens": 150, "cost_usd": 0.002}, "timestamp": 101.0},
        {"step_id": "step_2", "event_type": "tool_call", "payload": {"tool_name": "read_file"}, "timestamp": 102.0},
        {"step_id": "step_3", "event_type": "task_completed", "payload": {"output": "def sum(a, b): return a + b"}, "timestamp": 103.0},
    ]

    engine = ReplayEngine()
    record = engine.replay_trace(events)

    assert record.task_id == "task_99"
    assert record.status == "COMPLETED"
    assert record.total_tokens == 150
    assert record.cost_usd == 0.002
    assert record.used_tools == ["read_file"]
    assert record.total_duration_sec == 3.0
