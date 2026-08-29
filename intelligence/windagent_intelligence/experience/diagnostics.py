"""Experience Diagnostics & Attribution Engine (Phase 8 — ban_ke_hoach_v1 §13 & §22).

Analyzes empirical experiences, correlates multidimensional evaluation results,
and computes attributed learning hypotheses (e.g. YouTube attribution, tool usage patterns).

Invariants:
- Strictly observational: produces candidate hypotheses, NOT binding behavioral mutations.
- Confidence is bounded in [0.0, 1.0] and mathematically backed by evaluation scores.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from windagent_core.domain.experience import Experience


class ExperienceDiagnostics:
    """Diagnostic analyzer converting evaluated experiences into diagnosed learning hypotheses."""

    @staticmethod
    def attribute_experience(
        experience: Experience,
        custom_hypothesis: Optional[str] = None,
        baseline_metrics: Optional[Dict[str, float]] = None,
    ) -> Experience:
        """Attributes outcome drivers, calculates confidence, and produces diagnosed experience."""
        evals = experience.evaluator_results
        metrics = experience.metrics

        # Compute composite evaluation score and confidence
        if evals:
            passed_count = sum(1 for e in evals if e.get("passed", False))
            avg_score = sum(float(e.get("score", 0.0)) for e in evals) / len(evals)
            eval_confidence = sum(float(e.get("confidence", 1.0)) for e in evals) / len(evals)
            has_safety_block = any(e.get("blocked", False) or e.get("dimension") == "safety" and not e.get("passed", False) for e in evals)
        else:
            passed_count = 0
            avg_score = 0.0
            eval_confidence = 0.5
            has_safety_block = False

        details: Dict[str, Any] = {
            "evaluation_count": len(evals),
            "passed_count": passed_count,
            "avg_eval_score": round(avg_score, 4),
            "has_safety_block": has_safety_block,
        }

        # If custom hypothesis is provided, validate and apply
        if custom_hypothesis and custom_hypothesis.strip():
            hypothesis = custom_hypothesis.strip()
            # Confidence derives from evaluation quality and baseline delta
            confidence = min(1.0, max(0.0, avg_score * eval_confidence))
            if has_safety_block:
                confidence = 0.0
                details["safety_penalty"] = "Safety blocked or zero-tolerance violation detected."
            return experience.with_diagnosis(hypothesis=hypothesis, confidence=confidence, details=details)

        # Domain attribution: YouTube / Studio metrics attribution (§22)
        if "retention_30s" in metrics or "hook_pattern" in experience.context:
            retention_30s = float(metrics.get("retention_30s", 0.0))
            base_retention = float(baseline_metrics.get("retention_30s", 0.60)) if baseline_metrics else 0.60
            hook_pattern = experience.context.get("hook_pattern", "standard")
            topic = experience.context.get("topic_cluster", "general")

            delta_pct = (retention_30s - base_retention) * 100.0
            details["retention_delta_pp"] = round(delta_pct, 2)

            if delta_pct >= 5.0:
                hypothesis = (
                    f"Hook pattern '{hook_pattern}' on topic '{topic}' improved 30s retention by "
                    f"+{delta_pct:.1f}pp (observed: {retention_30s:.2f} vs baseline: {base_retention:.2f})."
                )
                confidence = min(0.95, max(0.5, 0.6 + (delta_pct / 100.0) * 0.5))
            elif delta_pct <= -5.0:
                hypothesis = (
                    f"Hook pattern '{hook_pattern}' on topic '{topic}' regressed 30s retention by "
                    f"{delta_pct:.1f}pp (observed: {retention_30s:.2f} vs baseline: {base_retention:.2f})."
                )
                confidence = min(0.90, max(0.5, 0.6 + abs(delta_pct / 100.0) * 0.5))
            else:
                hypothesis = f"Hook pattern '{hook_pattern}' showed neutral retention effect ({delta_pct:+.1f}pp)."
                confidence = 0.50

            return experience.with_diagnosis(hypothesis=hypothesis, confidence=confidence, details=details)

        # General task success / error diagnosis
        if has_safety_block:
            hypothesis = "Execution blocked due to safety policy invariant violation or secret exposure."
            confidence = 0.0
        elif avg_score >= 0.85 and passed_count == len(evals):
            hypothesis = (
                f"Execution succeeded with high dimensional quality ({avg_score:.2f}) "
                f"and zero safety regressions across {len(evals)} evaluation checks."
            )
            confidence = round(min(1.0, avg_score * eval_confidence), 4)
        elif avg_score < 0.5:
            hypothesis = (
                f"Execution degraded across evaluations (average score {avg_score:.2f}). "
                f"Requires root cause inspection on tool correctness and error handling."
            )
            confidence = round(min(0.8, (1.0 - avg_score) * 0.8), 4)
        else:
            hypothesis = f"Execution achieved acceptable performance (score: {avg_score:.2f})."
            confidence = round(avg_score * 0.8, 4)

        return experience.with_diagnosis(hypothesis=hypothesis, confidence=confidence, details=details)
