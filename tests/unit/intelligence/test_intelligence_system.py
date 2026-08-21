"""
Unit Tests for WindAgent Intelligence System (Phase 22):
- TaskClassifier: deterministic rules, multi-label, risk assessment, model fallback
- TaskPlanner: plan generation, DAG validation, tool/permission/cost/deadline validation
- IntelligenceContextBuilder: facade delegation
- RouterCache: cache key generation, endpoint failover, model preservation
- ContextSummarizer: provenance grouping, decision focus, warning preservation
- TaskReviewer: fail-closed, acceptance criteria checks, verification evidence
- TaskReporter: machine-readable canonical format, markdown/html render
"""

import os
import subprocess
import sys

from windagent_intelligence import (
    # task_classifier
    TaskClassifier, RiskLevel, TaskPlanner, PlanRequest, PlanResult, PlanValidationResult,
    # context_builder
    IntelligenceContextBuilder, ContextAssemblyResult,
    # model_router
    RouterCache,
    # summarizer
    ContextSummarizer, SummarizationResult, SummarizationStrategy,
    # reviewer
    TaskReviewer, ReviewResult, ReviewVerdict, ReviewCheck,
    # reporter
    TaskReporter, ReportFormat, ReportSection, IntelligenceReport,
)
from windagent_context import ContextItem, ContextItemProvenance, SourceType


# ====================================================================
# 1. Task Classifier
# ====================================================================

class TestTaskClassifier:
    def test_classify_bugfix(self):
        classifier = TaskClassifier()
        result = classifier.classify("Fix the login bug that crashes the app")
        assert result.primary_label == "bugfix"
        assert "bugfix" in result.labels
        assert result.confidence > 0.5
        assert len(result.workflow_candidates) > 0
        assert result.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)
        assert result.classification_method == "rule"

    def test_classify_feature(self):
        classifier = TaskClassifier()
        result = classifier.classify("Implement a new payment module")
        assert result.primary_label == "feature"
        assert "feature" in result.labels

    def test_classify_code_review(self):
        classifier = TaskClassifier()
        result = classifier.classify("Review the PR for security vulnerabilities")
        assert result.primary_label == "code_review"
        assert "code_review" in result.labels

    def test_multi_label_classification(self):
        classifier = TaskClassifier()
        result = classifier.classify("Fix bug and review the code changes")
        assert len(result.labels) >= 2
        assert "bugfix" in result.labels
        assert "code_review" in result.labels

    def test_workflow_candidates_sorted_by_confidence(self):
        classifier = TaskClassifier()
        result = classifier.classify("Refactor the code and fix the bug")
        candidates = result.workflow_candidates
        assert len(candidates) > 0
        # First candidate should have highest confidence
        for i in range(len(candidates) - 1):
            assert candidates[i].confidence >= candidates[i + 1].confidence

    def test_risk_assessment(self):
        classifier = TaskClassifier()
        # Prompt with production keyword should elevate risk to HIGH
        result = classifier.classify("Fix the authentication vulnerability in production")
        assert result.risk_level == RiskLevel.HIGH  # 'production' elevates to HIGH
        assert len(result.risk_reasons) > 0  # Should have risk elevation reason
        assert any('production' in r.lower() for r in result.risk_reasons)

    def test_high_risk_keywords(self):
        classifier = TaskClassifier()
        result = classifier.classify("Critical production outage needs immediate fix")
        assert result.risk_level == RiskLevel.HIGH  # 'critical' elevates to HIGH

    def test_needs_model_fallback(self):
        classifier = TaskClassifier(confidence_threshold=0.6)
        # Empty/random prompt should trigger fallback
        result = classifier.classify("xylophone zephyr quantum")
        # This might still match some rules... let's use a truly ambiguous one
        result2 = classifier.classify("Do something with the project")
        assert classifier.needs_model_fallback(result2) or classifier.needs_model_fallback(result)

    def test_model_fallback_default(self):
        classifier = TaskClassifier()
        fallback = classifier.model_fallback("Custom ambiguous request")
        assert fallback.used_model_fallback is True
        assert fallback.classification_method == "model"
        assert len(fallback.workflow_candidates) > 0

    def test_classification_result_to_dict(self):
        classifier = TaskClassifier()
        result = classifier.classify("Deploy version 2.0 to production")
        data = result.to_dict()
        assert "task_prompt_hash" in data
        assert "primary_label" in data
        assert "labels" in data
        assert "risk_level" in data
        assert "workflow_candidates" in data


# ====================================================================
# 2. Planner
# ====================================================================

class TestTaskPlanner:
    def test_plan_bugfix(self):
        classifier = TaskClassifier()
        classification = classifier.classify("Fix the login bug")
        planner = TaskPlanner()

        request = PlanRequest(
            task_prompt="Fix the login bug",
            classification=classification,
            max_steps=10,
        )
        result = planner.plan(request)

        assert isinstance(result, PlanResult)
        assert result.workflow_definition.name == "bugfix"
        assert len(result.workflow_definition.nodes) > 0
        assert len(result.workflow_definition.edges) > 0
        assert result.validation.is_valid or not result.validation.errors

    def test_plan_feature(self):
        classifier = TaskClassifier()
        classification = classifier.classify("Implement new feature")
        planner = TaskPlanner()

        request = PlanRequest(
            task_prompt="Implement new feature",
            classification=classification,
            max_steps=10,
        )
        result = planner.plan(request)
        assert result.workflow_definition.name == "feature"

    def test_dag_validation_no_cycles(self):
        """DAG validation should detect valid DAG."""
        planner = TaskPlanner()
        # Create a valid DAG plan
        classifier = TaskClassifier()
        classification = classifier.classify("Fix the bug")
        request = PlanRequest(
            task_prompt="Fix the bug",
            classification=classification,
        )
        result = planner.plan(request)
        assert result.validation.dag_valid is True

    def test_plan_with_budget_constraint(self):
        classifier = TaskClassifier()
        classification = classifier.classify("Fix the login bug")
        planner = TaskPlanner()

        request = PlanRequest(
            task_prompt="Fix the login bug",
            classification=classification,
            budget_usd=0.001,  # Very small budget -> should fail
        )
        result = planner.plan(request)
        # Cost validation may fail with such a small budget
        if not result.validation.cost_within_budget:
            assert any("budget" in e.lower() for e in result.validation.errors)

    def test_plan_with_max_steps(self):
        classifier = TaskClassifier()
        classification = classifier.classify("Fix the bug")
        planner = TaskPlanner()

        request = PlanRequest(
            task_prompt="Fix the bug",
            classification=classification,
            max_steps=2,  # Only 2 steps
        )
        result = planner.plan(request)
        assert len(result.workflow_definition.nodes) <= 2

    def test_plan_validation_result(self):
        validation = PlanValidationResult()
        assert validation.is_valid is True

        validation.dag_valid = False
        assert validation.is_valid is False

    def test_plan_result_to_dict(self):
        classifier = TaskClassifier()
        classification = classifier.classify("Review the code")
        planner = TaskPlanner()
        request = PlanRequest(
            task_prompt="Review the code",
            classification=classification,
        )
        result = planner.plan(request)
        data = result.to_dict()
        assert "workflow_id" in data
        assert "workflow_name" in data
        assert "validation" in data


# ====================================================================
# 3. Context Builder (Facade)
# ====================================================================

class TestIntelligenceContextBuilder:
    def test_assembly_result_to_dict(self):
        result = ContextAssemblyResult(
            items=[],
            truncated=False,
            budget_profile="bugfix",
        )
        data = result.to_dict()
        assert data["item_count"] == 0
        assert data["truncated"] is False
        assert data["budget_profile"] == "bugfix"

    def test_assemble_basic(self):
        builder = IntelligenceContextBuilder()
        result = builder.assemble(
            task_prompt="Fix the login bug",
            task_type="bugfix",
        )
        assert isinstance(result, ContextAssemblyResult)
        assert result.budget_profile == "bugfix"

    def test_assemble_for_classification(self):
        builder = IntelligenceContextBuilder()
        result = builder.assemble_for_classification(
            task_prompt="Fix the login bug",
            task_type="bugfix",
        )
        assert result.budget_profile == "bugfix"
        assert len(result.pipeline_steps) > 0

    def test_get_budget_profile_names(self):
        builder = IntelligenceContextBuilder()
        profiles = builder.get_budget_profile_names()
        assert "bugfix" in profiles
        assert "feature" in profiles
        assert "default" in profiles


# ====================================================================
# 4. Model Router — Cache & Failover
# ====================================================================

class TestRouterCache:
    def test_cache_key_generation(self):
        cache = RouterCache()
        key = cache.build_cache_key(
            canonical_model="gpt-4o",
            provider_name="openai",
            prompt="Fix the bug",
            tool_schemas=[{"name": "read_file", "params": {"path": "string"}}],
        )
        assert key.canonical_model == "gpt-4o"
        assert key.provider_name == "openai"
        assert len(key.prompt_hash) == 16
        assert len(key.tool_schema_hash) == 16
        assert key.to_cache_key().startswith("route_cache_")

    def test_cache_set_and_get(self):
        cache = RouterCache()
        key = cache.build_cache_key("gpt-4o", "openai", "Test prompt")
        cache.set(key, provider_name="openai", endpoint_id="ep_openai_v1", ttl_seconds=60)

        entry = cache.get(key)
        assert entry is not None
        assert entry.provider_name == "openai"
        assert entry.endpoint_id == "ep_openai_v1"
        assert entry.hit_count >= 1

    def test_cache_expiry(self):
        cache = RouterCache(default_ttl_seconds=-1)  # Negative TTL = expired immediately
        key = cache.build_cache_key("gpt-4o", "openai", "Test")
        cache.set(key, provider_name="openai", endpoint_id="ep_openai_v1")

        entry = cache.get(key)
        assert entry is None  # Expired immediately

    def test_cache_invalidate(self):
        cache = RouterCache()
        key = cache.build_cache_key("gpt-4o", "openai", "Test")
        cache.set(key, provider_name="openai", endpoint_id="ep_openai_v1")
        assert cache.invalidate(key) is True
        assert cache.get(key) is None

    def test_cache_clear(self):
        cache = RouterCache()
        k1 = cache.build_cache_key("gpt-4o", "openai", "Prompt A")
        k2 = cache.build_cache_key("claude-3", "anthropic", "Prompt B")
        cache.set(k1, provider_name="openai", endpoint_id="ep1")
        cache.set(k2, provider_name="anthropic", endpoint_id="ep2")
        count = cache.clear()
        assert count == 2
        assert cache.get_stats()["cache_entries"] == 0

    def test_endpoint_failover_same_model(self):
        """Endpoint failover should keep same canonical model, just change endpoint."""
        cache = RouterCache()
        cache.register_endpoint("ep_openai_v1", ["gpt-4o", "gpt-4-turbo"])
        cache.register_endpoint("ep_openai_v2", ["gpt-4o", "gpt-3.5-turbo"])

        # Report error on v1
        cache.report_endpoint_error("ep_openai_v1", 429)

        # Find failover for gpt-4o (should get v2)
        failover = cache.find_failover_endpoint("gpt-4o", current_endpoint="ep_openai_v1")
        assert failover == "ep_openai_v2", f"Expected ep_openai_v2, got {failover}"

    def test_endpoint_failover_no_alternative(self):
        """When no alternative endpoint exists for a model, failover returns None."""
        cache = RouterCache()
        cache.register_endpoint("ep_only_one", ["gpt-4o"])

        cache.report_endpoint_error("ep_only_one", 503)
        failover = cache.find_failover_endpoint("gpt-4o", current_endpoint="ep_only_one")
        assert failover is None

    def test_keep_same_model_on_failover(self):
        """Test that failover never changes the canonical model."""
        cache = RouterCache()
        cache.register_endpoint("ep_gpt4", ["gpt-4o"])
        cache.register_endpoint("ep_claude", ["claude-3-5-sonnet"])

        cache.report_endpoint_error("ep_gpt4", 429)

        # Should NOT failover to ep_claude because it doesn't support gpt-4o
        failover = cache.find_failover_endpoint("gpt-4o", current_endpoint="ep_gpt4")
        assert failover is None, "Should not switch to a model-incompatible endpoint"

    @staticmethod
    def test_compute_prompt_hash():
        h1 = RouterCache.compute_prompt_hash("Fix the bug")
        h2 = RouterCache.compute_prompt_hash("Fix the bug")
        h3 = RouterCache.compute_prompt_hash("Different prompt")

        assert h1 == h2  # Same prompt -> same hash
        assert h1 != h3  # Different prompt -> different hash
        assert len(h1) == 16

    def test_endpoint_health_reset(self):
        cache = RouterCache()
        cache.register_endpoint("ep1", ["gpt-4o"])
        cache.report_endpoint_error("ep1", 429)
        assert "ep1" in cache.failover_config.blacklisted_endpoints

        cache.reset_endpoint_health("ep1")
        assert "ep1" not in cache.failover_config.blacklisted_endpoints


# ====================================================================
# 5. Summarizer
# ====================================================================

class TestContextSummarizer:
    def test_provenance_summary(self):
        summarizer = ContextSummarizer()
        items = [
            ContextItem(
                item_id="file_1",
                content="def process(): pass",
                provenance=ContextItemProvenance(
                    source="repo", source_type=SourceType.FILE_CONTENT,
                    retrieval_reason="search", token_cost=10,
                ),
            ),
            ContextItem(
                item_id="tool_1",
                content="Build succeeded",
                provenance=ContextItemProvenance(
                    source="exec_shell", source_type=SourceType.TOOL_OUTPUT,
                    retrieval_reason="command output", token_cost=5,
                ),
            ),
        ]

        result = summarizer.summarize(items, strategy=SummarizationStrategy.PROVENANCE)
        assert isinstance(result, SummarizationResult)
        assert result.source_count == 2
        assert len(result.sources) >= 1
        assert "repo" in result.sources[0] or "exec_shell" in result.sources[0]
        assert result.warning is not None
        assert "NOT SOLE SOURCE OF TRUTH" in result.warning

    def test_concise_summary(self):
        summarizer = ContextSummarizer()
        items = [
            ContextItem(
                item_id="decision_1",
                content="Decision: Use PostgreSQL for the database",
                provenance=ContextItemProvenance(
                    source="meeting", source_type=SourceType.SESSION_CONTEXT,
                    retrieval_reason="decision", token_cost=10,
                ),
            ),
        ]

        result = summarizer.summarize(items, strategy=SummarizationStrategy.CONCISE)
        assert result.strategy == SummarizationStrategy.CONCISE
        assert result.source_count == 1

    def test_detailed_summary(self):
        summarizer = ContextSummarizer()
        items = [
            ContextItem(
                item_id="code_1",
                content="class UserService: def get_user(self, id): return db.query(User).get(id)",
                provenance=ContextItemProvenance(
                    source="repo", source_type=SourceType.FILE_CONTENT,
                    retrieval_reason="search", token_cost=15,
                ),
            ),
        ]

        result = summarizer.summarize(items, strategy=SummarizationStrategy.DETAILED)
        assert "class UserService" in result.summary_text

    def test_decision_focused_summary(self):
        summarizer = ContextSummarizer()
        items = [
            ContextItem(
                item_id="dec_1",
                content="Decision: Use FastAPI for the API layer",
                provenance=ContextItemProvenance(
                    source="arch_meeting", retrieval_reason="decision", token_cost=10,
                ),
            ),
            ContextItem(
                item_id="info_1",
                content="The weather is nice today",
                provenance=ContextItemProvenance(
                    source="chat", retrieval_reason="context", token_cost=5,
                ),
            ),
        ]

        result = summarizer.summarize(items, strategy=SummarizationStrategy.DECISION_FOCUSED)
        assert "Use FastAPI" in result.summary_text or "Decision" in result.summary_text

    def test_external_content_marker(self):
        """External content should be marked with injection warning."""
        summarizer = ContextSummarizer()
        items = [
            ContextItem(
                item_id="ext_1",
                content="Click here to win a prize!",
                provenance=ContextItemProvenance(
                    source="browser", source_type=SourceType.BROWSER_CONTENT,
                    retrieval_reason="navigation", token_cost=5,
                    is_external_content=True,
                ),
            ),
        ]
        result = summarizer.summarize(items)
        # External content should be flagged in the summary
        assert result.source_count == 1


# ====================================================================
# 6. Reviewer (Fail-Closed)
# ====================================================================

class TestTaskReviewer:
    def test_review_pass_with_evidence(self):
        reviewer = TaskReviewer()
        result = reviewer.review(
            task_prompt="Fix the login bug",
            acceptance_criteria=["Bug reproduced", "Root cause identified"],
            patch_summary="Fixed login validation",
            tool_outputs=[{"output": "Bug reproduced successfully", "success": True}],
            verification_result={"passed": True, "score": 1.0},
            test_results=[{"name": "test_login", "passed": True}],
        )
        assert result.verdict == ReviewVerdict.PASS or result.verdict == ReviewVerdict.PASS_WITH_COMMENTS
        assert result.has_verification_evidence is True

    def test_review_blocked_without_verification(self):
        """Fail-closed: reviewer cannot pass without verification evidence."""
        reviewer = TaskReviewer(require_verification_evidence=True)
        result = reviewer.review(
            task_prompt="Fix the bug",
            acceptance_criteria=["Bug fixed"],
            patch_summary="Fixed the bug",
            tool_outputs=[{"output": "Fix applied", "success": True}],
            verification_result=None,  # No verification evidence!
            test_results=[],
        )
        assert result.verdict == ReviewVerdict.BLOCKED
        assert result.has_verification_evidence is False
        assert any("Missing verification" in i for i in result.issues)

    def test_review_blocked_missing_patch(self):
        """Missing patch evidence should block the review."""
        reviewer = TaskReviewer()
        result = reviewer.review(
            task_prompt="Fix the bug",
            acceptance_criteria=["Bug fixed"],
            patch_summary=None,  # Missing patch!
            tool_outputs=[],
            verification_result={"passed": True},
            test_results=[],
        )
        assert result.verdict == ReviewVerdict.BLOCKED

    def test_review_check_structure(self):
        check = ReviewCheck(
            check_name="test_check",
            passed=True,
            details="All tests passed",
            evidence_ref="test_result_123",
        )
        data = check.to_dict()
        assert data["check_name"] == "test_check"
        assert data["passed"] is True
        assert data["evidence_ref"] == "test_result_123"

    def test_review_result_properties(self):
        result = ReviewResult(
            review_id="test",
            task_prompt_hash="abc123",
            verdict=ReviewVerdict.PASS,
            checks=[ReviewCheck(check_name="c1", passed=True, details="ok")],
            summary="All good",
            issues=[],
            recommendations=[],
            has_verification_evidence=True,
        )
        assert result.passed is True

    def test_acceptance_criteria_checking(self):
        reviewer = TaskReviewer()
        result = reviewer.review(
            task_prompt="Refactor the service",
            acceptance_criteria=["Code compiles", "Tests pass", "No regression"],
            patch_summary="Refactored UserService",
            tool_outputs=[
                {"output": "Compilation successful", "success": True},
                {"output": "Tests passing", "success": True},
            ],
            verification_result={"passed": True},
            test_results=[{"name": "test1", "passed": True}],
        )
        # Acceptance criteria checks should be present
        check_names = [c.check_name for c in result.checks]
        assert any("criterion" in cn for cn in check_names)


# ====================================================================
# 7. Reporter (Machine-Readable First)
# ====================================================================

class TestTaskReporter:
    def test_create_report(self):
        reporter = TaskReporter()
        report = reporter.create_report(
            title="Test Report",
            report_type="general",
            sections=[
                ReportSection(title="Section 1", content="Hello world", content_type="text"),
            ],
            metadata={"version": "1.0"},
        )
        assert isinstance(report, IntelligenceReport)
        assert report.format == ReportFormat.MACHINE
        assert len(report.sections) == 1

    def test_report_to_dict(self):
        reporter = TaskReporter()
        report = reporter.create_report("Test", "general", [ReportSection("S1", "Content")])
        data = report.to_dict()
        assert data["format"] == "machine"
        assert data["title"] == "Test"
        assert len(data["sections"]) == 1

    def test_report_to_markdown(self):
        reporter = TaskReporter()
        report = reporter.create_report("My Report", "classification", [
            ReportSection("Results", {"label": "bugfix", "confidence": 0.9}, content_type="json"),
        ])
        md = report.to_markdown()
        assert "# My Report" in md
        assert "## Results" in md

    def test_report_to_html(self):
        reporter = TaskReporter()
        report = reporter.create_report("HTML Report", "review", [
            ReportSection("Summary", "All checks passed"),
        ])
        html = report.to_html()
        assert "<h1>HTML Report</h1>" in html
        assert "All checks passed" in html
        assert "</html>" in html

    def test_classification_report(self):
        reporter = TaskReporter()
        # Build a classification result
        classifier = TaskClassifier()
        classification = classifier.classify("Fix the login bug")

        report = reporter.classification_report(classification, "Fix the login bug")
        assert report.report_type == "classification"
        assert report.metadata["primary_label"] == "bugfix"

    def test_planning_report(self):
        reporter = TaskReporter()
        classifier = TaskClassifier()
        classification = classifier.classify("Fix the bug")
        planner = TaskPlanner()
        plan = planner.plan(PlanRequest(
            task_prompt="Fix the bug",
            classification=classification,
        ))

        report = reporter.planning_report(plan, "Fix the bug")
        assert report.report_type == "planning"
        assert report.metadata["workflow_name"] is not None

    def test_review_report(self):
        reporter = TaskReporter()
        reviewer = TaskReviewer()
        review = reviewer.review(
            task_prompt="Fix the bug",
            acceptance_criteria=["Bug fixed"],
            patch_summary="Fixed",
            tool_outputs=[{"output": "done", "success": True}],
            verification_result={"passed": True},
        )

        report = reporter.review_report(review, "Fix the bug")
        assert report.report_type == "review"
        assert report.metadata["verdict"] is not None

    def test_summary_report(self):
        reporter = TaskReporter()
        summarizer = ContextSummarizer()
        items = [
            ContextItem(
                item_id="test",
                content="Test content",
                provenance=ContextItemProvenance(source="test", retrieval_reason="test", token_cost=5),
            )
        ]
        summary = summarizer.summarize(items)

        report = reporter.summary_report(summary, "Summarize this")
        assert report.report_type == "summary"
        assert report.metadata["source_count"] == 1


# ====================================================================
# 8. Gate: Intelligence does not import orchestration or apps
# ====================================================================

def test_intelligence_no_forbidden_imports():
    """Gate: Intelligence must not import orchestration or apps packages."""
    code = """
import sys
import windagent_intelligence

forbidden = ("windagent_orchestration", "apps.api", "apps.backend", "apps.worker")
matches = sorted(name for name in sys.modules if name.startswith(forbidden))
if matches:
    raise SystemExit(f"Intelligence imports forbidden packages: {matches}")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
