"""
Credit estimator for the Durable Production Workflow (plan 05 §19.2,
gate VP19_COST_AND_QUOTA_CONTROL_VERIFIED).

Estimate inputs:

- shot/mode/model/duration;
- number of candidates;
- image/reference generations;
- expected retry reserve;
- post-production when it has external cost;
- contingency.

Output (CostEstimate):

    estimated_credits, maximum_credits, candidate_count, retry_reserve,
    requires_approval

Fail-closed rules:

- a request with NO matching cost-catalog rule produces an estimate with
  status UNKNOWN and blocks submit (§19.1, §19.4);
- an estimate is bound to the plan/request hashes AND the cost-catalog
  signature; when the shot plan or the cost catalog changes, the estimate
  (and any approval bound to its estimate hash) becomes stale (§19.2).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from windagent_core.errors.exceptions import ValidationError

from windagent_orchestration.production.cost_catalog import CostCatalog

ESTIMATE_SCHEMA_VERSION = "1.0.0"

ESTIMATE_STATUS_KNOWN = "KNOWN"
ESTIMATE_STATUS_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EstimateLine:
    """One generation operation to be estimated (§19.2)."""

    provider: str
    model: str
    operation: str  # e.g. "video_generation"
    mode: str = "standard"
    duration_seconds: float = 0.0
    candidate_count: int = 1
    reference_generations: int = 0
    post_production_external: bool = False


@dataclass(frozen=True)
class CostEstimate:
    """Deterministic, hash-bound estimate for one plan/request set (§19.2)."""

    plan_hash: str
    request_hashes: Tuple[str, ...]
    catalog_signature: str
    estimated_credits: int
    maximum_credits: int
    candidate_count: int
    retry_reserve: int
    requires_approval: bool
    status: str = ESTIMATE_STATUS_KNOWN
    unknown_reasons: Tuple[str, ...] = ()

    def estimate_hash(self) -> str:
        """Hash binding the estimate to its plan/request hashes + catalog.

        An approval must target this exact hash; when the plan or catalog
        changes the hash changes and the old approval is stale (§19.2).
        """
        payload = json.dumps(
            {
                "schema_version": ESTIMATE_SCHEMA_VERSION,
                "plan_hash": self.plan_hash,
                "request_hashes": sorted(self.request_hashes),
                "catalog_signature": self.catalog_signature,
                "estimated_credits": self.estimated_credits,
                "maximum_credits": self.maximum_credits,
                "candidate_count": self.candidate_count,
                "retry_reserve": self.retry_reserve,
                "requires_approval": self.requires_approval,
                "status": self.status,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def is_stale_for(self, plan_hash: str, catalog_signature: str) -> bool:
        """True when the plan or the cost catalog changed after this estimate.

        An estimate is only valid for the exact plan/hash and catalog it was
        computed against; anything else means the old approval is stale and a
        fresh estimate + approval is required (§19.2).
        """
        return plan_hash != self.plan_hash or catalog_signature != self.catalog_signature

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": ESTIMATE_SCHEMA_VERSION,
            "plan_hash": self.plan_hash,
            "request_hashes": list(self.request_hashes),
            "catalog_signature": self.catalog_signature,
            "estimated_credits": self.estimated_credits,
            "maximum_credits": self.maximum_credits,
            "candidate_count": self.candidate_count,
            "retry_reserve": self.retry_reserve,
            "requires_approval": self.requires_approval,
            "status": self.status,
            "unknown_reasons": list(self.unknown_reasons),
            "estimate_hash": self.estimate_hash(),
        }


class CreditEstimator:
    """Computes a cost estimate from catalog rules + plan inputs (§19.2).

    Deterministic: the same catalog + lines + plan hash always produce the
    same estimate and the same estimate hash.
    """

    def __init__(
        self,
        catalog: CostCatalog,
        *,
        retry_reserve_ratio: float = 0.25,
        contingency_ratio: float = 1.2,
        approval_threshold: int = 100,
    ) -> None:
        if retry_reserve_ratio < 0:
            raise ValidationError(
                "retry_reserve_ratio must be >= 0",
                code="WINDAGENT_ERR_VALIDATION",
            )
        if contingency_ratio < 1.0:
            raise ValidationError(
                "contingency_ratio must be >= 1.0",
                code="WINDAGENT_ERR_VALIDATION",
            )
        self.catalog = catalog
        self.retry_reserve_ratio = retry_reserve_ratio
        self.contingency_ratio = contingency_ratio
        self.approval_threshold = approval_threshold

    def estimate(
        self,
        *,
        plan_hash: str,
        request_hashes: List[str],
        lines: List[EstimateLine],
        effective_at: str = "",
    ) -> CostEstimate:
        """Compute the estimate; UNKNOWN status when any rule is missing.

        An unknown rule never produces a numeric guess: the whole estimate is
        UNKNOWN and the budget policy blocks the submit (§19.1 fail closed).
        """
        if not plan_hash:
            raise ValidationError("plan_hash is required", code="WINDAGENT_ERR_VALIDATION")
        if not lines:
            raise ValidationError("at least one estimate line required", code="WINDAGENT_ERR_VALIDATION")

        unknown_reasons: List[str] = []
        estimated = 0
        candidate_count = 0

        for line in lines:
            if line.candidate_count < 1:
                raise ValidationError(
                    f"candidate_count must be >= 1 (line {line.operation})",
                    code="WINDAGENT_ERR_VALIDATION",
                )
            rule = self.catalog.rule_for(
                provider=line.provider,
                model=line.model,
                operation=line.operation,
                mode=line.mode,
                effective_at=effective_at,
            )
            if rule is None:
                unknown_reasons.append(
                    f"no cost rule for {line.provider}/{line.model}/{line.operation}@{line.mode}"
                )
                continue
            candidate_count += line.candidate_count
            base = rule.base_credits + int(round(rule.per_second_credits * line.duration_seconds))
            if rule.candidate_semantics == "per_candidate":
                base *= line.candidate_count
            elif rule.candidate_semantics != "per_request":
                raise ValidationError(
                    f"unknown candidate semantics {rule.candidate_semantics!r}",
                    code="WINDAGENT_ERR_VALIDATION",
                )
            base += rule.per_reference_credits * line.reference_generations
            if line.post_production_external:
                base += rule.post_production_credits
            estimated += base

        status = ESTIMATE_STATUS_UNKNOWN if unknown_reasons else ESTIMATE_STATUS_KNOWN
        retry_reserve = int(round(estimated * self.retry_reserve_ratio))
        maximum = int(round((estimated + retry_reserve) * self.contingency_ratio))
        requires_approval = maximum >= self.approval_threshold

        return CostEstimate(
            plan_hash=plan_hash,
            request_hashes=tuple(sorted(request_hashes)),
            catalog_signature=self.catalog.signature(),
            estimated_credits=estimated,
            maximum_credits=maximum,
            candidate_count=candidate_count,
            retry_reserve=retry_reserve,
            requires_approval=requires_approval,
            status=status,
            unknown_reasons=tuple(unknown_reasons),
        )


__all__ = [
    "ESTIMATE_SCHEMA_VERSION",
    "ESTIMATE_STATUS_KNOWN",
    "ESTIMATE_STATUS_UNKNOWN",
    "EstimateLine",
    "CostEstimate",
    "CreditEstimator",
]
