"""Candidate Generator & Miner Engine (Phase 9 — ban_ke_hoach_v1 §14 & §22).

Analyzes diagnosed experiences, detects recurring patterns, anomalies, and attribution signals,
and synthesizes structured LearningCandidate instances.

Invariants:
- All generated candidates start in the PROPOSED state.
- Single failure / observation reflection generates PROPOSED candidate with sample_size=1.
- Candidate generation NEVER directly modifies active prompts, harness versions, or policies.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

from windagent_core.domain.candidate import (
    CandidateKind,
    CandidateRiskLevel,
    CandidateScope,
    CandidateStatus,
    LearningCandidate,
)
from windagent_core.domain.experience import Experience, ExperienceState


def generate_candidate_id() -> str:
    return f"cand_{uuid.uuid4().hex[:16]}"


class CandidateGenerator:
    """Synthesizes structured LearningCandidate instances from empirical experiences."""

    @staticmethod
    def generate_from_single_experience(
        experience: Experience,
        kind: Optional[CandidateKind] = None,
        scope: CandidateScope = CandidateScope.PROJECT,
    ) -> LearningCandidate:
        """Generates a single PROPOSED candidate (sample_size=1) from one diagnosed experience.

        Follows Hard Rule (§14): 1 failure/observation -> reflection -> candidate in PROPOSED state.
        """
        cand_id = generate_candidate_id()
        project_id = experience.project_id
        domain = experience.context.get("domain") or experience.context.get("topic_cluster") or "general"

        # Determine Kind
        inferred_kind = kind or CandidateKind.PROMPT_RULE
        if "tool" in experience.action or "tool_failures" in experience.metrics or experience.result.get("tool_error"):
            inferred_kind = CandidateKind.PROMPT_RULE
        elif "routing" in experience.decision or "model_route" in experience.provenance:
            inferred_kind = CandidateKind.ROUTING_POLICY

        # Determine condition and proposed change from diagnosis
        hypothesis = experience.hypothesis or "Diagnosed execution pattern requires behavioral adjustment."
        condition = experience.context.get("goal") or experience.context.get("topic_cluster") or f"domain == '{domain}'"

        # Formulate proposed change payload
        proposed_change: Dict[str, Any] = {
            "hypothesis": hypothesis,
            "recommended_action": f"Apply adjustment: {hypothesis}",
            "source_experience_id": experience.experience_id,
            "target_kind": inferred_kind.value,
        }

        # Calculate initial confidence (single observation confidence is capped at experience confidence)
        initial_confidence = round(min(0.75, experience.confidence), 4)

        # Risk assessment: single experience prompt mutation is medium risk, global is high risk
        risk_level = CandidateRiskLevel.HIGH if scope == CandidateScope.GLOBAL else CandidateRiskLevel.MEDIUM

        return LearningCandidate(
            candidate_id=cand_id,
            kind=inferred_kind,
            condition=str(condition),
            proposed_change=proposed_change,
            reasoning_summary=f"Derived from single diagnosed experience {experience.experience_id}: {hypothesis}",
            supporting_experiences=[experience.experience_id],
            counter_evidence=[],
            sample_size=1,
            confidence=initial_confidence,
            scope=scope,
            risk_level=risk_level,
            status=CandidateStatus.PROPOSED,
            project_id=project_id,
            domain=str(domain),
            metadata={
                "source": "single_experience_reflection",
                "execution_id": experience.execution_id,
            },
        )

    @classmethod
    def mine_candidates_from_experiences(
        cls,
        experiences: Sequence[Experience],
        min_cluster_size: int = 2,
        scope: CandidateScope = CandidateScope.PROJECT,
    ) -> List[LearningCandidate]:
        """Clusters diagnosed experiences to mine structured LearningCandidates with empirical sample sizes.

        Partitions experiences into specific diagnostic clusters:
        1. Tool correctness / failure anomaly patterns
        2. YouTube hook pattern / packaging attribution (§22)
        3. General topic/domain success patterns
        """
        candidates: List[LearningCandidate] = []
        diagnosed_exps = [e for e in experiences if e.state in (ExperienceState.DIAGNOSED, ExperienceState.EVALUATED)]

        if not diagnosed_exps:
            return candidates

        # Partition experiences to prevent duplicate candidates across specialized miners
        tool_exps: List[Experience] = []
        yt_exps: List[Experience] = []
        general_exps: List[Experience] = []

        for exp in diagnosed_exps:
            has_tool_error = bool(exp.metrics.get("tool_failures") or exp.result.get("tool_error"))
            has_yt_hook = bool(exp.context.get("hook_pattern"))

            if has_tool_error:
                tool_exps.append(exp)
            elif has_yt_hook:
                yt_exps.append(exp)
            else:
                general_exps.append(exp)

        # 1. Mine Tool correctness / failure anomalies
        if tool_exps:
            tool_candidates = cls._mine_tool_anomalies(tool_exps, min_cluster_size, scope)
            candidates.extend(tool_candidates)

        # 2. Mine YouTube hook pattern attribution
        if yt_exps:
            yt_candidates = cls._mine_youtube_patterns(yt_exps, min_cluster_size, scope)
            candidates.extend(yt_candidates)

        # 3. Mine General topic/domain success patterns
        if general_exps:
            domain_candidates = cls._mine_domain_patterns(general_exps, min_cluster_size, scope)
            candidates.extend(domain_candidates)

        return candidates

    @classmethod
    def _mine_youtube_patterns(
        cls,
        experiences: Sequence[Experience],
        min_cluster_size: int,
        scope: CandidateScope,
    ) -> List[LearningCandidate]:
        """Mines YouTube / Studio hook pattern and packaging retention candidates (§22)."""
        candidates: List[LearningCandidate] = []
        clusters: Dict[str, List[Experience]] = defaultdict(list)

        for exp in experiences:
            hook_pattern = exp.context.get("hook_pattern")
            topic = exp.context.get("topic_cluster") or exp.context.get("domain") or "general"
            if hook_pattern:
                cluster_key = f"yt_hook::{topic}::{hook_pattern}"
                clusters[cluster_key].append(exp)

        for key, exp_list in clusters.items():
            parts = key.split("::")
            topic = parts[1]
            hook_pattern = parts[2]

            supporting: List[str] = []
            counter: List[str] = []
            positive_confidences: List[float] = []

            for exp in exp_list:
                retention_delta = exp.metrics.get("diagnosis_details", {}).get("retention_delta_pp")
                if retention_delta is None and "retention_30s" in exp.metrics:
                    retention_30s = float(exp.metrics.get("retention_30s", 0.0))
                    baseline = 0.60
                    retention_delta = (retention_30s - baseline) * 100.0

                if retention_delta is not None and retention_delta >= 3.0:
                    supporting.append(exp.experience_id)
                    positive_confidences.append(exp.confidence)
                elif retention_delta is not None and retention_delta <= -3.0:
                    counter.append(exp.experience_id)
                elif exp.confidence >= 0.6:
                    supporting.append(exp.experience_id)
                    positive_confidences.append(exp.confidence)

            total_obs = len(supporting) + len(counter)
            if len(supporting) >= min_cluster_size:
                avg_conf = sum(positive_confidences) / len(positive_confidences) if positive_confidences else 0.65
                # Apply penalty for counter evidence
                counter_penalty = (len(counter) / total_obs) * 0.3 if total_obs > 0 else 0.0
                composite_conf = round(max(0.1, min(0.95, avg_conf - counter_penalty)), 4)

                cand_id = generate_candidate_id()
                condition = f"topic_cluster == '{topic}'"
                proposed_change = {
                    "hook_pattern": hook_pattern,
                    "recommendation": f"For topic cluster '{topic}', employ '{hook_pattern}' hook pattern to optimize 30s retention.",
                    "observed_support_count": len(supporting),
                    "counter_evidence_count": len(counter),
                }
                reasoning = (
                    f"Observed positive retention impact across {len(supporting)} experiences "
                    f"for hook pattern '{hook_pattern}' on topic '{topic}' (counter-evidence: {len(counter)})."
                )

                candidates.append(
                    LearningCandidate(
                        candidate_id=cand_id,
                        kind=CandidateKind.PROMPT_RULE,
                        condition=condition,
                        proposed_change=proposed_change,
                        reasoning_summary=reasoning,
                        supporting_experiences=supporting,
                        counter_evidence=counter,
                        sample_size=total_obs,
                        confidence=composite_conf,
                        scope=scope,
                        risk_level=CandidateRiskLevel.LOW,
                        status=CandidateStatus.PROPOSED,
                        project_id=exp_list[0].project_id,
                        domain="youtube",
                        metadata={"cluster_key": key, "hook_pattern": hook_pattern, "topic": topic},
                    )
                )

        return candidates

    @classmethod
    def _mine_tool_anomalies(
        cls,
        experiences: Sequence[Experience],
        min_cluster_size: int,
        scope: CandidateScope,
    ) -> List[LearningCandidate]:
        """Mines tool failure anomalies and synthesizes corrective prompt / skill candidates."""
        candidates: List[LearningCandidate] = []
        clusters: Dict[str, List[Experience]] = defaultdict(list)

        for exp in experiences:
            tool_name = exp.action.get("failed_tool") or exp.action.get("tool_name")
            if tool_name:
                cluster_key = f"tool_anomaly::{tool_name}"
                clusters[cluster_key].append(exp)

        for key, exp_list in clusters.items():
            tool_name = key.split("::")[1]
            if len(exp_list) >= min_cluster_size:
                supporting = [e.experience_id for e in exp_list]
                avg_conf = sum(e.confidence for e in exp_list) / len(exp_list)
                composite_conf = round(min(0.90, max(0.5, avg_conf)), 4)

                cand_id = generate_candidate_id()
                condition = f"invoking_tool == '{tool_name}'"
                proposed_change = {
                    "tool_name": tool_name,
                    "remedy": f"Enforce pre-invocation schema validation and argument sanity checks for tool '{tool_name}'.",
                }
                reasoning = (
                    f"Recurring failure anomaly detected on tool '{tool_name}' across {len(exp_list)} experiences. "
                    f"Requires schema safeguard rule."
                )

                candidates.append(
                    LearningCandidate(
                        candidate_id=cand_id,
                        kind=CandidateKind.SKILL if "skill" in tool_name else CandidateKind.PROMPT_RULE,
                        condition=condition,
                        proposed_change=proposed_change,
                        reasoning_summary=reasoning,
                        supporting_experiences=supporting,
                        counter_evidence=[],
                        sample_size=len(exp_list),
                        confidence=composite_conf,
                        scope=scope,
                        risk_level=CandidateRiskLevel.MEDIUM,
                        status=CandidateStatus.PROPOSED,
                        project_id=exp_list[0].project_id,
                        domain="tool_execution",
                        metadata={"cluster_key": key, "tool_name": tool_name},
                    )
                )

        return candidates

    @classmethod
    def _mine_domain_patterns(
        cls,
        experiences: Sequence[Experience],
        min_cluster_size: int,
        scope: CandidateScope,
    ) -> List[LearningCandidate]:
        """Mines general high-scoring domain pattern experiences."""
        candidates: List[LearningCandidate] = []
        clusters: Dict[str, List[Experience]] = defaultdict(list)

        for exp in experiences:
            domain = exp.context.get("domain") or exp.project_id or "general"
            if exp.confidence >= 0.70 and exp.hypothesis:
                # Extract normalized hypothesis signature
                sig = re.sub(r"[^a-zA-Z0-9 ]", "", exp.hypothesis.lower())[:40].strip()
                if sig:
                    cluster_key = f"domain::{domain}::{sig}"
                    clusters[cluster_key].append(exp)

        for key, exp_list in clusters.items():
            if len(exp_list) >= min_cluster_size:
                domain = key.split("::")[1]
                supporting = [e.experience_id for e in exp_list]
                avg_conf = sum(e.confidence for e in exp_list) / len(exp_list)

                cand_id = generate_candidate_id()
                condition = f"domain == '{domain}'"
                proposed_change = {
                    "domain": domain,
                    "rule": exp_list[0].hypothesis,
                }
                reasoning = (
                    f"Consistently validated pattern across {len(exp_list)} experiences in domain '{domain}'."
                )

                candidates.append(
                    LearningCandidate(
                        candidate_id=cand_id,
                        kind=CandidateKind.PROMPT_RULE,
                        condition=condition,
                        proposed_change=proposed_change,
                        reasoning_summary=reasoning,
                        supporting_experiences=supporting,
                        counter_evidence=[],
                        sample_size=len(exp_list),
                        confidence=round(min(0.95, avg_conf), 4),
                        scope=scope,
                        risk_level=CandidateRiskLevel.LOW,
                        status=CandidateStatus.PROPOSED,
                        project_id=exp_list[0].project_id,
                        domain=domain,
                        metadata={"cluster_key": key},
                    )
                )

        return candidates

