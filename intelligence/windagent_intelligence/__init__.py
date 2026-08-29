"""
WindAgent Intelligence Package (V2 Architecture — Phase 22).
Seven bounded components: task_classifier, planner, context_builder, model_router,
summarizer, reviewer, reporter.
"""

from windagent_core.version import PRODUCT_VERSION

from windagent_intelligence.task_classifier import TaskClassifier, ClassificationResult, RiskLevel, WorkflowCandidate
from windagent_intelligence.planner import TaskPlanner, PlanRequest, PlanResult, PlanValidationResult
from windagent_intelligence.context_builder import IntelligenceContextBuilder, ContextAssemblyResult
from windagent_intelligence.model_router import RouteLock, ModelRouterPolicy, RoutingContext, RouterCache
from windagent_intelligence.summarizer import ContextSummarizer, SummarizationResult, SummarizationStrategy
from windagent_intelligence.reviewer import TaskReviewer, ReviewResult, ReviewVerdict, ReviewCheck
from windagent_intelligence.reporter import TaskReporter, ReportFormat, ReportSection, IntelligenceReport
from windagent_intelligence.pipeline import IntelligencePipeline
from windagent_intelligence.experience import (
    Experience,
    ExperienceState,
    ExperienceDiagnostics,
    ExperienceStore,
)
from windagent_core.domain.candidate import (
    LearningCandidate,
    LearnedRule,
    CandidateKind,
    CandidateStatus,
    CandidateRiskLevel,
    CandidateScope,
    LearnedRuleState,
)
from windagent_intelligence.candidate import (
    CandidateGenerator,
    EligibilityGate,
    CandidateService,
    generate_candidate_id,
)

from windagent_core.domain.harness import (
    HarnessEntry,
    HarnessEntryKind,
    HarnessVersion,
    HarnessVersionStatus,
    RefinementProposal,
    RefinementStatus,
)
from windagent_intelligence.harness import (
    DiffEngine,
    HarnessAssembler,
    AssembledHarnessContext,
    HarnessService,
    ImmutableBaseGuard,
    ImmutableBaseViolationError,
    RefinementEngine,
)

__version__ = PRODUCT_VERSION
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
    # pipeline
    "IntelligencePipeline",
    # experience store (Phase 8)
    "Experience", "ExperienceState", "ExperienceDiagnostics", "ExperienceStore",
    # candidate learning (Phase 9)
    "LearningCandidate", "LearnedRule", "CandidateKind", "CandidateStatus",
    "CandidateRiskLevel", "CandidateScope", "LearnedRuleState",
    "CandidateGenerator", "EligibilityGate", "CandidateService", "generate_candidate_id",
    # continual harness (Phase 10)
    "HarnessEntry", "HarnessEntryKind", "HarnessVersion", "HarnessVersionStatus",
    "RefinementProposal", "RefinementStatus",
    "DiffEngine", "HarnessAssembler", "AssembledHarnessContext", "HarnessService",
    "ImmutableBaseGuard", "ImmutableBaseViolationError", "RefinementEngine",
]
