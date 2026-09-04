"""Unit tests for Quality grading evaluators."""

from windagent.modules.quality.domain.graders import (
    CodeCorrectnessGrader,
    CompositeGrader,
    CostLimitGrader,
    ExactMatchGrader,
    JsonSchemaGrader,
    LatencyGrader,
    NumericThresholdGrader,
    RegexGrader,
    SafetyRuleGrader,
)


def test_exact_match_grader() -> None:
    grader = ExactMatchGrader()
    score, passed, _ = grader.grade("hello", "hello")
    assert score == 1.0
    assert passed is True

    score2, passed2, _ = grader.grade("hello", "world")
    assert score2 == 0.0
    assert passed2 is False


def test_regex_grader() -> None:
    grader = RegexGrader(r"Scene\s+\d+:\s+EXT\.")
    score, passed, _ = grader.grade("Scene 1: EXT. CASTLE - DAY")
    assert score == 1.0
    assert passed is True

    score2, passed2, _ = grader.grade("Scene A: INT. ROOM")
    assert score2 == 0.0
    assert passed2 is False


def test_numeric_threshold_grader() -> None:
    grader = NumericThresholdGrader(min_val=10.0, max_val=20.0)
    score, passed, _ = grader.grade(15.0)
    assert score == 1.0
    assert passed is True

    score2, passed2, _ = grader.grade(5.0)
    assert score2 == 0.0
    assert passed2 is False


def test_json_schema_grader() -> None:
    grader = JsonSchemaGrader(required_keys=("title", "shots", "characters"))
    valid_payload = {"title": "Ep 1", "shots": [], "characters": []}
    score, passed, _ = grader.grade(valid_payload)
    assert score == 1.0
    assert passed is True

    invalid_payload = {"title": "Ep 1"}
    score2, passed2, details = grader.grade(invalid_payload)
    assert passed2 is False
    assert "shots" in details["missing_keys"]


def test_cost_and_latency_graders() -> None:
    cost_grader = CostLimitGrader(max_credits=5.0)
    s1, p1, _ = cost_grader.grade(3.5)
    assert p1 is True
    assert s1 == 1.0

    s2, p2, _ = cost_grader.grade(10.0)
    assert p2 is False

    lat_grader = LatencyGrader(max_seconds=2.0)
    s3, p3, _ = lat_grader.grade(1.2)
    assert p3 is True
    assert s3 == 1.0


def test_safety_rule_grader() -> None:
    grader = SafetyRuleGrader()
    safe_text = "The quick brown fox jumps over the lazy dog."
    s1, p1, _ = grader.grade(safe_text)
    assert s1 == 1.0
    assert p1 is True

    unsafe_text = "Here is my secret api_key = 'sk-1234567890abcdef1234567890'"
    s2, p2, d2 = grader.grade(unsafe_text)
    assert s2 == 0.0
    assert p2 is False
    assert "potential_secret_leakage" in d2["violations"]


def test_code_correctness_grader() -> None:
    grader = CodeCorrectnessGrader()
    valid_code = "def hello():\n    return 'world'\n"
    s1, p1, _ = grader.grade(valid_code)
    assert s1 == 1.0
    assert p1 is True

    invalid_code = "def syntax error !!!"
    s2, p2, _ = grader.grade(invalid_code)
    assert s2 == 0.0
    assert p2 is False


def test_composite_grader() -> None:
    g1 = ExactMatchGrader()
    g2 = SafetyRuleGrader()
    composite = CompositeGrader(graders=[(g1, 1.0), (g2, 1.0)])

    s, p, d = composite.grade("hello", "hello")
    assert s == 1.0
    assert p is True
    assert "exact_match" in d["sub_graders"]
    assert "safety_rules" in d["sub_graders"]
