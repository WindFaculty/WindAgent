"""Rollback Coordinator & Post-Promotion Monitor (Phase 11 — ban_ke_hoach_v1 §17, §24, §25, §35).

Monitors post-promotion execution telemetry in production/staging environments.
Detects performance, safety, or reliability regressions, and automatically coordinates
an atomic rollback to the parent HarnessVersion, marking the PromotionDecision as ROLLED_BACK.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from windagent_core.contracts.repositories.harness_repository import (
    HarnessRepositoryProtocol,
)
from windagent_core.contracts.repositories.promotion_repository import (
    PromotionRepositoryProtocol,
)
from windagent_core.domain.harness import HarnessVersion, HarnessVersionStatus
from windagent_core.domain.promotion import (
    PostPromotionHealth,
    PromotionDecision,
)

logger = logging.getLogger("windagent.orchestration.learning.rollback_coordinator")


class RollbackCoordinator:
    """Monitors post-promotion performance and coordinates atomic rollbacks upon regression."""

    def __init__(
        self,
        harness_repo: Optional[HarnessRepositoryProtocol] = None,
        promotion_repo: Optional[PromotionRepositoryProtocol] = None,
        max_error_rate: float = 0.10,
        min_safety_score: float = 0.95,
        max_accuracy_drop: float = 0.08,
    ) -> None:
        self._harness_repo = harness_repo
        self._promotion_repo = promotion_repo
        self.max_error_rate = max_error_rate
        self.min_safety_score = min_safety_score
        self.max_accuracy_drop = max_accuracy_drop

    def evaluate_post_promotion_health(
        self,
        version_id: str,
        execution_runs: List[Dict[str, Any]],
        expected_accuracy: float = 0.85,
    ) -> PostPromotionHealth:
        """Evaluates telemetry of execution runs under the newly promoted version."""
        if not execution_runs:
            return PostPromotionHealth(version_id=version_id, observed_runs=0)

        n = len(execution_runs)
        errors = sum(1 for r in execution_runs if r.get("error"))
        safety_viols = sum(1 for r in execution_runs if r.get("safety_violation"))
        total_acc = sum(r.get("accuracy", 1.0 if r.get("success", False) else 0.0) for r in execution_runs)
        total_latency = sum(r.get("latency_ms", 0.0) for r in execution_runs)

        avg_acc = round(total_acc / n, 4)
        avg_lat = round(total_latency / n, 2)
        error_rate = errors / n

        is_reg = False
        reasons = []

        if safety_viols > 0:
            is_reg = True
            reasons.append(f"Detected {safety_viols} safety violations in production.")

        if error_rate > self.max_error_rate:
            is_reg = True
            reasons.append(f"Error rate {error_rate:.2%} exceeded threshold {self.max_error_rate:.2%}.")

        if avg_acc < (expected_accuracy - self.max_accuracy_drop):
            is_reg = True
            reasons.append(
                f"Accuracy {avg_acc:.2f} dropped below expected threshold ({expected_accuracy - self.max_accuracy_drop:.2f})."
            )

        return PostPromotionHealth(
            version_id=version_id,
            observed_runs=n,
            error_count=errors,
            safety_violations=safety_viols,
            avg_accuracy=avg_acc,
            avg_latency_ms=avg_lat,
            is_regression_detected=is_reg,
            regression_reason="; ".join(reasons) if reasons else None,
        )

    async def execute_rollback(
        self,
        current_version: HarnessVersion,
        promotion_decision: PromotionDecision,
        rollback_reason: str,
    ) -> tuple[HarnessVersion, Optional[HarnessVersion], PromotionDecision]:
        """Atomically rolls back the active harness version to its parent version.

        Returns:
            (rolled_back_version, parent_version_restored, updated_promotion_decision)
        """
        if not current_version.parent_version:
            raise ValueError(
                f"Cannot rollback harness version {current_version.version_id}: root baseline version has no parent."
            )

        logger.warning(
            "Executing harness rollback for version %s to parent %s due to: %s",
            current_version.version_id,
            current_version.parent_version,
            rollback_reason,
        )

        # 1. Rollback current version
        rolled_back_current = current_version.rollback(rollback_reason)
        if self._harness_repo:
            await self._harness_repo.save_version(rolled_back_current)

        # 2. Activate parent version
        restored_parent = None
        if self._harness_repo:
            parent = await self._harness_repo.get_version(current_version.parent_version)
            if parent:
                activated_parent = parent.activate()
                await self._harness_repo.save_version(activated_parent)
                await self._harness_repo.set_active_version(activated_parent.version_id)
                restored_parent = activated_parent
        else:
            # In-memory fallback
            restored_parent = HarnessVersion(
                version_id=current_version.parent_version,
                version_number=max(1, current_version.version_number - 1),
                status=HarnessVersionStatus.ACTIVE,
                is_active=True,
            )

        # 3. Update PromotionDecision
        updated_decision = promotion_decision.rollback(rollback_reason)
        if self._promotion_repo:
            await self._promotion_repo.save_decision(updated_decision)

        logger.info(
            "Rollback completed successfully: version %s deactivated, restored parent %s",
            current_version.version_id,
            current_version.parent_version,
        )

        return rolled_back_current, restored_parent, updated_decision

