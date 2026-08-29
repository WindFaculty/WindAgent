"""Experiment Runner (Phase 11 — ban_ke_hoach_v1 §17, §24, §25, §35).

Coordinates empirical replay and benchmark experiments comparing baseline harnesses
against candidate mutations. Evaluates statistical metrics, safety regressions,
and cost bounds, saving durable Experiment records.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from windagent_core.contracts.repositories.experiment_repository import (
    ExperimentRepositoryProtocol,
)
from windagent_core.domain.candidate import LearningCandidate
from windagent_core.domain.experiment import (
    Experiment,
    ExperimentMetrics,
    ExperimentStatus,
    ExperimentType,
    compute_statistical_comparison,
)

logger = logging.getLogger("windagent.orchestration.learning.experiment_runner")


class ExperimentRunner:
    """Coordinates and executes comparative candidate evaluation experiments."""

    def __init__(
        self,
        repository: Optional[ExperimentRepositoryProtocol] = None,
        significance_alpha: float = 0.05,
        min_win_margin: float = 0.02,
        max_allowed_cost_delta: float = 0.50,
        max_uncertainty_margin: float = 0.45,
    ) -> None:
        self._repo = repository
        self.significance_alpha = significance_alpha
        self.min_win_margin = min_win_margin
        self.max_allowed_cost_delta = max_allowed_cost_delta
        self.max_uncertainty_margin = max_uncertainty_margin

    def _aggregate_episodes(self, episodes: List[Dict[str, Any]]) -> ExperimentMetrics:
        """Aggregates a list of episode outcome dicts into an ExperimentMetrics model."""
        if not episodes:
            return ExperimentMetrics(sample_size=1)

        total_acc = sum(e.get("accuracy", 1.0 if e.get("success", False) else 0.0) for e in episodes)
        total_safety = sum(e.get("safety_score", 1.0) for e in episodes)
        total_rel = sum(e.get("reliability_score", 1.0 if not e.get("error") else 0.0) for e in episodes)
        total_latency = sum(e.get("latency_ms", 0.0) for e in episodes)
        total_cost = sum(e.get("cost_usd", 0.0) for e in episodes)
        error_count = sum(1 for e in episodes if e.get("error"))
        n = len(episodes)

        return ExperimentMetrics(
            accuracy=round(total_acc / n, 4),
            safety_score=round(total_safety / n, 4),
            reliability_score=round(total_rel / n, 4),
            latency_ms=round(total_latency / n, 2),
            cost_usd=round(total_cost, 4),
            sample_size=n,
            error_count=error_count,
            custom_metrics={"episode_count": n},
        )

    async def run_experiment(
        self,
        candidate: LearningCandidate,
        baseline_harness_version: str,
        baseline_episodes: List[Dict[str, Any]],
        candidate_episodes: List[Dict[str, Any]],
        experiment_type: ExperimentType = ExperimentType.REPLAY,
        dataset_id: Optional[str] = None,
        experiment_id: Optional[str] = None,
    ) -> Experiment:
        """Executes a comparative experiment and records the outcome."""
        expt_id = experiment_id or f"expt_{uuid.uuid4().hex[:12]}"

        # Initialize draft experiment
        draft_exp = Experiment(
            experiment_id=expt_id,
            candidate_id=candidate.candidate_id,
            baseline_harness_version=baseline_harness_version,
            experiment_type=experiment_type,
            status=ExperimentStatus.DRAFT,
            dataset_id=dataset_id,
            sample_size=max(1, len(candidate_episodes)),
            project_id=candidate.project_id,
            domain=candidate.domain,
            created_by="experiment_runner",
            metadata={"candidate_kind": candidate.kind.value},
        )

        running_exp = draft_exp.start()
        if self._repo:
            await self._repo.save_experiment(running_exp)

        # Aggregate metrics
        base_metrics = self._aggregate_episodes(baseline_episodes)
        cand_metrics = self._aggregate_episodes(candidate_episodes)

        # Run statistical comparison
        comp, safety_ok, rel_ok, verdict = compute_statistical_comparison(
            baseline=base_metrics,
            candidate=cand_metrics,
            significance_alpha=self.significance_alpha,
            min_win_margin=self.min_win_margin,
            max_allowed_cost_delta=self.max_allowed_cost_delta,
            max_uncertainty_margin=self.max_uncertainty_margin,
        )

        # Complete experiment
        completed_exp = running_exp.complete(
            baseline_metrics=base_metrics,
            candidate_metrics=cand_metrics,
            comparison=comp,
            safety_check_passed=safety_ok,
            reliability_check_passed=rel_ok,
            verdict=verdict,
        )

        if self._repo:
            await self._repo.save_experiment(completed_exp)

        logger.info(
            "Completed experiment %s for candidate %s: verdict=%s, acc_delta=%.4f",
            expt_id,
            candidate.candidate_id,
            verdict.value,
            comp.accuracy_delta,
        )

        return completed_exp

    async def run_synthetic_benchmark(
        self,
        candidate: LearningCandidate,
        baseline_harness_version: str,
        baseline_accuracy: float = 0.80,
        candidate_accuracy: float = 0.90,
        baseline_safety: float = 1.0,
        candidate_safety: float = 1.0,
        sample_size: int = 5,
        cost_usd: float = 0.05,
    ) -> Experiment:
        """Helper to create and evaluate benchmark runs from synthetic test aggregates."""
        base_episodes = [
            {"accuracy": baseline_accuracy, "safety_score": baseline_safety, "reliability_score": 0.95, "cost_usd": cost_usd}
            for _ in range(sample_size)
        ]
        cand_episodes = [
            {"accuracy": candidate_accuracy, "safety_score": candidate_safety, "reliability_score": 0.95, "cost_usd": cost_usd * 1.02}
            for _ in range(sample_size)
        ]

        return await self.run_experiment(
            candidate=candidate,
            baseline_harness_version=baseline_harness_version,
            baseline_episodes=base_episodes,
            candidate_episodes=cand_episodes,
            experiment_type=ExperimentType.BENCHMARK,
            dataset_id="synthetic_benchmark_v1",
        )
