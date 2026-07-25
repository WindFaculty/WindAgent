"""
WindAgent Intelligence Package (V2 Architecture — Phase 22).
Seven bounded components: task_classifier, planner, context_builder, model_router,
summarizer, reviewer, reporter.
"""

from windagent_intelligence.task_classifier import TaskClassifier, ClassificationResult, RiskLevel, WorkflowCandidate
from windagent_intelligence.planner import TaskPlanner, PlanRequest, PlanResult, PlanValidationResult
from windagent_intelligence.context_builder import IntelligenceContextBuilder, ContextAssemblyResult
from windagent_intelligence.model_router import RouteLock, ModelRouterPolicy, RoutingContext, RouterCache
from windagent_intelligence.summarizer import ContextSummarizer, SummarizationResult, SummarizationStrategy
from windagent_intelligence.reviewer import TaskReviewer, ReviewResult, ReviewVerdict, ReviewCheck
from windagent_intelligence.reporter import TaskReporter, ReportFormat, ReportSection, IntelligenceReport

__version__ = "0.4.0"

__all__ = [
    # task_classifier
    "TaskClassifier", "ClassificationResult", "RiskLevel", "WorkflowCandidate",
    # planner
    "TaskPlanner", "PlanRequest", "PlanResult", "PlanValidationResult",
    # context_builder
    "IntelligenceContextBuilder", "ContextAssemblyResult",
    # model_router
    "RouteLock", "ModelRouterPolicy", "RoutingContext", "RouterCache",
    # summarizer
    "ContextSummarizer", "SummarizationResult", "SummarizationStrategy",
    # reviewer
    "TaskReviewer", "ReviewResult", "ReviewVerdict", "ReviewCheck",
    # reporter
    "TaskReporter", "ReportFormat", "ReportSection", "IntelligenceReport",
]
