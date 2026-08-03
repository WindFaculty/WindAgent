"""
Task Classifier for WindAgent Intelligence (Phase 22).
Applies deterministic rule matching first. Uses model fallback when confidence is below threshold.
Supports multi-label classification, workflow candidate identification, and risk assessment.
"""

from __future__ import annotations
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List


logger = logging.getLogger("windagent.intelligence.task_classifier")


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class WorkflowCandidate:
    """A candidate workflow for a classified task."""
    workflow_name: str
    confidence: float  # 0.0 to 1.0
    match_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_name": self.workflow_name,
            "confidence": self.confidence,
            "match_reason": self.match_reason,
        }


@dataclass
class ClassificationResult:
    """Result of task classification."""
    task_prompt_hash: str
    primary_label: str
    labels: List[str]
    confidence: float
    workflow_candidates: List[WorkflowCandidate]
    risk_level: RiskLevel
    risk_reasons: List[str]
    classification_method: str  # "rule" or "model"
    used_model_fallback: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_prompt_hash": self.task_prompt_hash,
            "primary_label": self.primary_label,
            "labels": self.labels,
            "confidence": self.confidence,
            "workflow_candidates": [c.to_dict() for c in self.workflow_candidates],
            "risk_level": self.risk_level.value,
            "risk_reasons": self.risk_reasons,
            "classification_method": self.classification_method,
            "used_model_fallback": self.used_model_fallback,
            "created_at": self.created_at,
        }


# Deterministic classification rules
# Each rule maps a regex pattern -> (label, workflow_name, risk_level)
CLASSIFICATION_RULES: List[Dict[str, Any]] = [
    # Bugfix
    {"pattern": r"(fix|bug|crash|error|broken|fail|issue|defect|bugfix)", "label": "bugfix", "workflow": "bugfix", "risk": RiskLevel.MEDIUM},
    # CI Fix
    {"pattern": r"(ci|pipeline|github actions|build fail|test fail|ci/cd)", "label": "ci_fix", "workflow": "ci_fix", "risk": RiskLevel.MEDIUM},
    # Code Review
    {"pattern": r"(review|audit|pr|pull request|code review|inspect)", "label": "code_review", "workflow": "code_review", "risk": RiskLevel.LOW},
    # Feature
    {"pattern": r"(feature|implement|add|create|new|enhance|build|develop)", "label": "feature", "workflow": "feature", "risk": RiskLevel.MEDIUM},
    # Refactor
    {"pattern": r"(refactor|clean|restructure|modernize|improve|optimize|deduplicate)", "label": "refactor", "workflow": "refactor", "risk": RiskLevel.LOW},
    # Research
    {"pattern": r"(research|explore|investigate|find out|learn|analyze|study)", "label": "research", "workflow": "research", "risk": RiskLevel.LOW},
    # Scientific Evaluation
    {"pattern": r"(eval|benchmark|evaluate|grade|score|scientific)", "label": "scientific_eval", "workflow": "scientific_eval", "risk": RiskLevel.LOW},
    # Release
    {"pattern": r"(release|deploy|ship|publish|version|tag)", "label": "release", "workflow": "release", "risk": RiskLevel.HIGH},
    # Security-sensitive
    {"pattern": r"(password|secret|token|credential|api key|ssh|encrypt|decrypt)", "label": "security", "workflow": "code_review", "risk": RiskLevel.CRITICAL},
    # Destructive
    {"pattern": r"(delete|remove|destroy|drop|format|clean all|erase)", "label": "destructive", "workflow": "bugfix", "risk": RiskLevel.CRITICAL},
]

# Risk keywords that elevate the classification risk level
RISK_ELEVATION_KEYWORDS = {
    RiskLevel.HIGH: ["production", "critical", "urgent", "asap", "security", "vulnerability", "exploit"],
    RiskLevel.CRITICAL: ["password", "secret", "credential", "database drop", "data loss", "rm -rf"],
}


class TaskClassifier:
    """Classifies task prompts into workflow candidates with risk assessment.
    Uses deterministic rules first, with model fallback capability when confidence is low.
    """

    def __init__(self, confidence_threshold: float = 0.6):
        self.confidence_threshold = confidence_threshold

    def classify(self, task_prompt: str) -> ClassificationResult:
        """Classifies a task prompt using deterministic rules.
        Returns ClassificationResult with labels, workflow candidates, and risk level.
        """
        prompt_lower = task_prompt.lower()
        prompt_hash = hashlib.sha256(task_prompt.encode("utf-8")).hexdigest()[:16]

        # 1. Apply deterministic rules
        matched_labels: List[str] = []
        matched_workflows: Dict[str, float] = {}
        matched_risks: List[RiskLevel] = []
        match_reasons: List[str] = []
        unmatched_rules = 0

        for rule in CLASSIFICATION_RULES:
            if re.search(rule["pattern"], prompt_lower):
                label = rule["label"]
                if label not in matched_labels:
                    matched_labels.append(label)

                wf_name = rule["workflow"]
                if wf_name not in matched_workflows:
                    matched_workflows[wf_name] = 0.0
                matched_workflows[wf_name] = max(matched_workflows.get(wf_name, 0.0), 0.8)
                matched_risks.append(rule["risk"])
                match_reasons.append(f"Matched rule pattern '{rule['pattern']}' -> {label}")
            else:
                unmatched_rules += 1

        # 2. Risk elevation based on keyword presence
        risk_reasons: List[str] = []
        final_risk = self._assess_risk(prompt_lower, matched_risks, risk_reasons)

        # 3. Build workflow candidates sorted by confidence
        workflow_candidates = [
            WorkflowCandidate(
                workflow_name=wf,
                confidence=conf,
                match_reason=match_reasons[0] if match_reasons else "rule_match",
            )
            for wf, conf in sorted(matched_workflows.items(), key=lambda x: x[1], reverse=True)
        ]

        # 4. Determine classification
        if matched_labels:
            primary_label = matched_labels[0]
            confidence = min(0.9, 0.5 + 0.1 * len(matched_labels))
            classification_method = "rule"
            used_fallback = False
        else:
            # No rules matched — model fallback would be used in production
            primary_label = "unclassified"
            confidence = 0.0
            classification_method = "model"  # Would use model in production
            used_fallback = True
            # Default to general workflow
            workflow_candidates.append(
                WorkflowCandidate(workflow_name="feature", confidence=0.4, match_reason="Model fallback: default to feature")
            )

        return ClassificationResult(
            task_prompt_hash=prompt_hash,
            primary_label=primary_label,
            labels=matched_labels if matched_labels else ["unclassified"],
            confidence=confidence,
            workflow_candidates=workflow_candidates,
            risk_level=final_risk,
            risk_reasons=risk_reasons,
            classification_method=classification_method,
            used_model_fallback=used_fallback,
        )

    def needs_model_fallback(self, result: ClassificationResult) -> bool:
        """Returns True if the classification confidence is below threshold and model fallback is needed."""
        return result.confidence < self.confidence_threshold or not result.labels or result.primary_label == "unclassified"

    def _assess_risk(self, prompt_lower: str, matched_risks: List[RiskLevel], risk_reasons: List[str]) -> RiskLevel:
        """Assesses the final risk level based on matched rules and keywords."""
        # Start from matched rule risks
        if matched_risks:
            risk_order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
            base_risk = max(matched_risks, key=lambda r: risk_order.index(r))
        else:
            base_risk = RiskLevel.LOW

        # Elevate for high/critical keywords
        for level, keywords in RISK_ELEVATION_KEYWORDS.items():
            for kw in keywords:
                if kw in prompt_lower:
                    risk_order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
                    if risk_order.index(level) > risk_order.index(base_risk):
                        base_risk = level
                        risk_reasons.append(f"Risk elevated due to keyword '{kw}'")
                    break

        return base_risk

    def model_fallback(self, task_prompt: str) -> ClassificationResult:
        """Placeholder for model-based fallback classification.
        In production, this would call an LLM for classification when rules are insufficient.
        """
        logger.info(f"Model fallback called for prompt hash [{hashlib.sha256(task_prompt.encode()).hexdigest()[:16]}]")
        # Default fallback: classify as feature with low confidence
        return ClassificationResult(
            task_prompt_hash=hashlib.sha256(task_prompt.encode("utf-8")).hexdigest()[:16],
            primary_label="feature",
            labels=["feature"],
            confidence=0.4,
            workflow_candidates=[
                WorkflowCandidate(workflow_name="feature", confidence=0.4, match_reason="Model fallback: generic classification"),
                WorkflowCandidate(workflow_name="bugfix", confidence=0.3, match_reason="Model fallback: secondary candidate"),
            ],
            risk_level=RiskLevel.MEDIUM,
            risk_reasons=["Model fallback: default medium risk for unclassified tasks"],
            classification_method="model",
            used_model_fallback=True,
        )
