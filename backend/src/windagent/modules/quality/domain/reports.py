"""Quality certification and scorecard report generators."""

from __future__ import annotations

from .evals import EvaluationRunAggregate
from .regression import BaselineComparison
from .verification import VerificationSuiteReport


class QualityReportGenerator:
    """Produces structured markdown and JSON summary reports for quality certification."""

    @staticmethod
    def generate_markdown_certificate(
        run: EvaluationRunAggregate,
        verification: VerificationSuiteReport | None = None,
        comparison: BaselineComparison | None = None,
    ) -> str:
        lines: list[str] = [
            "# WindAgent Quality Certification Report",
            "",
            f"- **Execution ID:** `{run.execution_id}`",
            f"- **Evaluator Version:** `{run.evaluator_version}`",
            f"- **Run Status:** `{run.status.value}`",
            f"- **Composite Score:** **{run.composite_score:.2%}**",
            f"- **Overall Verdict:** {'✅ PASSED' if run.passed else '❌ FAILED'}",
            "",
            "## Dimension Breakdown",
            "",
            "| Dimension | Metric | Score | Threshold | Status | Evidence |",
            "|---|---|---|---|---|---|",
        ]

        for r in run.records:
            status_emoji = "✅" if r.passed else ("🚫 BLOCKED" if r.blocked else "❌")
            lines.append(
                f"| {r.dimension.value} | {r.metric_name} | {r.score:.2f} | {r.threshold:.2f} | {status_emoji} | {len(r.evidence_refs)} refs |"
            )

        if verification:
            lines.extend(
                [
                    "",
                    "## Verification Gates",
                    "",
                    f"- **Overall Status:** `{verification.overall_status.value}`",
                    f"- **Passed Gates:** {len(verification.passed_gates)}",
                    f"- **Failed Gates:** {len(verification.failed_gates)}",
                    f"- **Blocked Gates:** {len(verification.blocked_gates)}",
                ]
            )

        if comparison:
            lines.extend(
                [
                    "",
                    "## Baseline Comparison",
                    "",
                    f"- **Baseline ID:** `{comparison.baseline_id}`",
                    f"- **Candidate Composite:** `{comparison.composite_candidate_score:.2%}`",
                    f"- **Baseline Composite:** `{comparison.composite_baseline_score:.2%}`",
                    f"- **Composite Delta:** `+{comparison.composite_delta:.2%}`" if comparison.composite_delta >= 0 else f"- **Composite Delta:** `{comparison.composite_delta:.2%}`",
                    f"- **Regression Detected:** {'⚠️ YES' if comparison.regression_detected else '✅ NONE'}",
                ]
            )

        return "\n".join(lines)
