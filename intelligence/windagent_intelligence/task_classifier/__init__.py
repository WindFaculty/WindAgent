"""
Task Classifier Component for WindAgent Intelligence (Phase 22).
Deterministic rule matching first, multi-label classification, workflow candidate identification,
model fallback when confidence is low, and risk level assessment.
"""

from windagent_intelligence.task_classifier.classifier import (
    TaskClassifier, ClassificationResult, RiskLevel, WorkflowCandidate,
)

__all__ = ["TaskClassifier", "ClassificationResult", "RiskLevel", "WorkflowCandidate"]
