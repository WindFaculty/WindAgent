"""Rule Conflict Resolution Engine (Phase 14 — ban_ke_hoach_v1 §20, §23, §35).

Provides deterministic, multi-factor conflict resolution when competing learned rules
match the same context or domain condition.

Scoring factors:
1. Domain Match Precision (weight 0.25): Condition key-value overlap and specificity.
2. Scope Specificity (weight 0.20): PRIVATE_AGENT (1.0) > TASK (0.9) > SESSION (0.8) > ROLE (0.7) > PROJECT (0.6) > GLOBAL (0.5).
3. Evidence Strength (weight 0.25): Confidence * min(1.0, sample_size / 10.0).
4. Recency (weight 0.15): Recency of last_validated_at or created_at.
5. Harness Compatibility (weight 0.15): Compatibility with current active harness version.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from windagent_core.domain.organizational_learning import (
    ConflictResolutionRecord,
    KnowledgeVisibilityScope,
    LearnedRule,
    utc_now,
)

SCOPE_SPECIFICITY_WEIGHTS: Dict[KnowledgeVisibilityScope, float] = {
    KnowledgeVisibilityScope.PRIVATE_AGENT: 1.0,
    KnowledgeVisibilityScope.TASK: 0.9,
    KnowledgeVisibilityScope.SESSION: 0.8,
    KnowledgeVisibilityScope.ROLE: 0.7,
    KnowledgeVisibilityScope.PROJECT: 0.6,
    KnowledgeVisibilityScope.GLOBAL: 0.5,
}

WEIGHT_DOMAIN_MATCH = 0.25
WEIGHT_SCOPE_SPECIFICITY = 0.20
WEIGHT_EVIDENCE_STRENGTH = 0.25
WEIGHT_RECENCY = 0.15
WEIGHT_HARNESS_COMPATIBILITY = 0.15


class RuleConflictResolver:
    """Deterministic, transparent conflict resolver for competing learned rules."""

    def __init__(
        self,
        domain_weight: float = WEIGHT_DOMAIN_MATCH,
        scope_weight: float = WEIGHT_SCOPE_SPECIFICITY,
        evidence_weight: float = WEIGHT_EVIDENCE_STRENGTH,
        recency_weight: float = WEIGHT_RECENCY,
        harness_weight: float = WEIGHT_HARNESS_COMPATIBILITY,
    ) -> None:
        self.domain_weight = domain_weight
        self.scope_weight = scope_weight
        self.evidence_weight = evidence_weight
        self.recency_weight = recency_weight
        self.harness_weight = harness_weight

    def calculate_score(
        self,
        rule: LearnedRule,
        context_query: Dict[str, Any],
        active_harness_version: Optional[str] = None,
        reference_time: Optional[datetime] = None,
    ) -> Tuple[float, Dict[str, float]]:
        """Calculates multi-factor score and detailed breakdown for a single rule."""
        ref_time = reference_time or utc_now()

        # 1. Domain Match Score
        domain_match_score = self._compute_domain_match_score(rule.condition, context_query)

        # 2. Scope Specificity Score
        scope_score = SCOPE_SPECIFICITY_WEIGHTS.get(rule.scope, 0.5)

        # 3. Evidence Strength Score
        sample_factor = min(1.0, float(rule.sample_size) / 10.0) if rule.sample_size > 0 else 0.1
        evidence_score = float(rule.confidence) * sample_factor

        # 4. Recency Score
        val_time = rule.last_validated_at or rule.created_at
        if val_time:
            if val_time.tzinfo is None:
                val_time = val_time.replace(tzinfo=timezone.utc)
            days_elapsed = max(0.0, (ref_time - val_time).total_seconds() / 86400.0)
            recency_score = max(0.0, 1.0 - (days_elapsed / 365.0))
        else:
            recency_score = 0.5

        # 5. Harness Compatibility Score
        if active_harness_version and rule.harness_version:
            harness_score = 1.0 if rule.harness_version == active_harness_version else 0.4
        elif not rule.harness_version:
            harness_score = 0.7  # Universal / agnostic rule
        else:
            harness_score = 0.6

        total_score = (
            self.domain_weight * domain_match_score
            + self.scope_weight * scope_score
            + self.evidence_weight * evidence_score
            + self.recency_weight * recency_score
            + self.harness_weight * harness_score
        )

        breakdown = {
            "domain_match": round(domain_match_score, 4),
            "scope_specificity": round(scope_score, 4),
            "evidence_strength": round(evidence_score, 4),
            "recency": round(recency_score, 4),
            "harness_compatibility": round(harness_score, 4),
            "total_score": round(total_score, 4),
        }

        return total_score, breakdown

    def _compute_domain_match_score(
        self,
        condition: Dict[str, Any],
        context_query: Dict[str, Any],
    ) -> float:
        """Computes condition match precision."""
        if not condition:
            return 0.5  # Wildcard condition

        matched = 0
        for k, v in condition.items():
            if k in context_query and context_query[k] == v:
                matched += 1
            elif k not in context_query:
                # Partial match if key absent from query
                matched += 0.5
            else:
                return 0.0  # Explicit mismatch

        return matched / max(len(condition), 1)

    def resolve_conflict(
        self,
        competing_rules: List[LearnedRule],
        context_query: Dict[str, Any],
        domain: str = "youtube_studio",
        active_harness_version: Optional[str] = None,
        reference_time: Optional[datetime] = None,
    ) -> Tuple[LearnedRule, ConflictResolutionRecord]:
        """Resolves conflict among competing rules and produces an audit record.

        Raises ValueError if competing_rules is empty.
        """
        if not competing_rules:
            raise ValueError("Cannot resolve conflict for empty rules list.")

        if len(competing_rules) == 1:
            winner = competing_rules[0]
            score, breakdown = self.calculate_score(winner, context_query, active_harness_version, reference_time)
            rec = ConflictResolutionRecord(
                resolution_id=f"res_{uuid.uuid4().hex[:12]}",
                domain=domain,
                context_query=context_query,
                winning_rule_id=winner.rule_id,
                competing_rule_ids=[winner.rule_id],
                resolution_rationale=f"Single matching rule {winner.rule_id} selected directly (score={score:.4f}).",
                score_breakdown={winner.rule_id: breakdown},
                resolved_at=reference_time or utc_now(),
            )
            return winner, rec

        scored_rules: List[Tuple[float, int, str, LearnedRule, Dict[str, float]]] = []
        score_breakdowns: Dict[str, Dict[str, float]] = {}

        for rule in competing_rules:
            score, breakdown = self.calculate_score(rule, context_query, active_harness_version, reference_time)
            score_breakdowns[rule.rule_id] = breakdown
            # Tuple for sorting: (score DESC, version DESC, rule_id ASC)
            scored_rules.append((score, rule.version, rule.rule_id, rule, breakdown))

        # Sort by total_score desc, version desc, rule_id asc
        scored_rules.sort(key=lambda x: (x[0], x[1]), reverse=True)

        winner_tuple = scored_rules[0]
        winner = winner_tuple[3]
        winner_score = winner_tuple[0]

        competing_ids = [r.rule_id for r in competing_rules]
        runner_up = scored_rules[1][3]
        runner_up_score = scored_rules[1][0]

        rationale = (
            f"Rule {winner.rule_id} (scope={winner.scope.value}, version={winner.version}, score={winner_score:.4f}) "
            f"won against {runner_up.rule_id} (score={runner_up_score:.4f}) with breakdown: "
            f"domain_match={score_breakdowns[winner.rule_id]['domain_match']}, "
            f"scope={score_breakdowns[winner.rule_id]['scope_specificity']}, "
            f"evidence={score_breakdowns[winner.rule_id]['evidence_strength']}, "
            f"recency={score_breakdowns[winner.rule_id]['recency']}."
        )

        record = ConflictResolutionRecord(
            resolution_id=f"res_{uuid.uuid4().hex[:12]}",
            domain=domain,
            context_query=context_query,
            winning_rule_id=winner.rule_id,
            competing_rule_ids=competing_ids,
            resolution_rationale=rationale,
            score_breakdown=score_breakdowns,
            resolved_at=reference_time or utc_now(),
        )

        return winner, record

