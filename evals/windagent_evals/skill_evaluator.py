"""Skill Evaluator & Benchmark Engine (Phase 12 — ban_ke_hoach_v1 §18, §27).

Evaluates skill candidates against functional verification test cases and benchmarks:
- Executes functional validation suites (template rendering, context variable binding).
- Measures accuracy score, token budget efficiency, latency delta, and cost delta.
- Computes safety score (must satisfy safety_score >= 0.95).
- Produces immutable SkillEvaluationResult entities.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from windagent_core.domain.skill_evolution import (
    SkillCandidate,
    SkillEvaluationResult,
)


class SkillTestCase:
    """A functional test case for evaluating skill prompt rendering or execution."""

    def __init__(
        self,
        name: str,
        context_vars: Dict[str, Any],
        expected_substrings: Optional[List[str]] = None,
        validator_fn: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self.name = name
        self.context_vars = context_vars
        self.expected_substrings = expected_substrings or []
        self.validator_fn = validator_fn


class SkillEvaluator:
    """Evaluates SkillCandidate quality, safety, and functional conformance."""

    def evaluate(
        self,
        candidate: SkillCandidate,
        test_cases: Optional[List[SkillTestCase]] = None,
        baseline_token_usage: int = 2000,
        baseline_latency_ms: float = 150.0,
    ) -> SkillEvaluationResult:
        """Runs the functional test suite and benchmark on a SkillCandidate."""
        eval_id = f"skeval_{uuid.uuid4().hex[:12]}"
        manifest_dict = candidate.proposed_manifest
        prompt_template = manifest_dict.get("prompt_template", "")
        token_budget = int(manifest_dict.get("token_budget", 2000))

        tests_run = 0
        tests_passed = 0
        tests_failed = 0
        details: Dict[str, Any] = {"test_results": []}

        start_time = time.perf_counter()

        # If custom test cases provided, run them
        if test_cases:
            for tc in test_cases:
                tests_run += 1
                try:
                    rendered = prompt_template.format(**tc.context_vars) if prompt_template else ""
                    passed = True

                    for sub in tc.expected_substrings:
                        if sub.lower() not in rendered.lower():
                            passed = False
                            break

                    if passed and tc.validator_fn:
                        passed = tc.validator_fn(rendered)

                    if passed:
                        tests_passed += 1
                        details["test_results"].append({"name": tc.name, "status": "PASS"})
                    else:
                        tests_failed += 1
                        details["test_results"].append({"name": tc.name, "status": "FAIL"})
                except Exception as e:
                    tests_failed += 1
                    details["test_results"].append({"name": tc.name, "status": "ERROR", "error": str(e)})
        else:
            # Default smoke test case
            tests_run = 1
            if prompt_template or candidate.proposed_code:
                tests_passed = 1
                details["test_results"].append({"name": "default_manifest_smoke", "status": "PASS"})
            else:
                tests_failed = 1
                details["test_results"].append({"name": "default_manifest_smoke", "status": "FAIL", "error": "Empty prompt template and code"})

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Accuracy score from test pass rate
        accuracy_score = float(tests_passed) / float(tests_run) if tests_run > 0 else 0.0

        # Safety score evaluation: check for dangerous trigger keywords in prompt
        safety_score = 1.0
        dangerous_keywords = ["ignore previous instructions", "bypass security", "sudo", "eval(", "drop table"]
        for kw in dangerous_keywords:
            if kw in prompt_template.lower():
                safety_score -= 0.3
        safety_score = max(0.0, safety_score)

        # Token efficiency ratio: declared token_budget vs benchmark baseline
        token_efficiency = float(baseline_token_usage) / float(max(1, token_budget))

        # Latency delta
        latency_delta_ms = elapsed_ms - baseline_latency_ms

        # Cost delta estimate ($0.002 per 1000 tokens difference)
        token_delta = token_budget - baseline_token_usage
        cost_delta_usd = (token_delta / 1000.0) * 0.002

        test_suite_passed = (tests_failed == 0 and tests_passed > 0)
        benchmark_passed = (test_suite_passed and accuracy_score >= 0.8 and safety_score >= 0.95)

        return SkillEvaluationResult(
            evaluation_id=eval_id,
            skill_candidate_id=candidate.candidate_id,
            benchmark_passed=benchmark_passed,
            test_suite_passed=test_suite_passed,
            tests_run=tests_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            accuracy_score=accuracy_score,
            safety_score=safety_score,
            token_efficiency_score=token_efficiency,
            cost_delta_usd=cost_delta_usd,
            latency_delta_ms=latency_delta_ms,
            details=details,
        )


__all__ = ["SkillEvaluator", "SkillTestCase"]

