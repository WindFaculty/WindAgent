"""
Unit tests for WindAgent Observability subsystem (Phase 11):
- MetricsCollector tracking all 13 core metrics
- TraceChain and Span hierarchy management
- SecretSanitizer redaction of credentials and API keys
- AuditLogger correlated event logging and ordering verification
"""

from windagent_observability import (
    MetricsCollector, SpanKind, TraceChain,
    SecretSanitizer, AuditLogger
)


def test_metrics_collector_13_metrics_tracking():
    collector = MetricsCollector()

    # Record tasks
    collector.record_task_completion(
        success=True,
        accepted=True,
        first_pass=True,
        cost_usd=0.01,
        latency_sec=1.5,
        tokens=500,
        context_size=2000,
        retries=0,
        human_intervention=False
    )
    collector.record_task_completion(
        success=False,
        accepted=False,
        first_pass=False,
        cost_usd=0.02,
        latency_sec=2.5,
        tokens=800,
        context_size=3000,
        retries=2,
        human_intervention=True
    )

    collector.record_recovery(success=True)
    collector.record_tool_failure()
    collector.record_provider_failure()
    collector.record_verification_failure()

    snap = collector.get_snapshot()

    assert snap.total_tasks == 2
    assert snap.successful_tasks == 1
    assert snap.accepted_tasks == 1
    assert snap.first_pass_successes == 1
    assert snap.task_success_rate == 0.5
    assert snap.accepted_task_rate == 0.5
    assert snap.first_pass_success_rate == 0.5

    assert snap.recoveries_attempted == 1
    assert snap.recoveries_successful == 1
    assert snap.recovery_success_rate == 1.0

    assert snap.tool_failures == 1
    assert snap.provider_failures == 1
    assert snap.verification_failures == 1

    assert snap.total_tokens == 1300
    assert snap.total_cost_usd == 0.03
    assert snap.human_interventions == 1
    assert snap.total_retries == 2
    assert snap.average_context_size_tokens == 2500.0


def test_trace_chain_span_lifecycle_and_completeness():
    chain = TraceChain()

    task_span = chain.start_span("task_01", SpanKind.TASK)
    plan_span = chain.start_span("plan_01", SpanKind.PLAN, parent_span_id=task_span.span_id)
    wf_span = chain.start_span("workflow_01", SpanKind.WORKFLOW, parent_span_id=plan_span.span_id)
    step_span = chain.start_span("step_01", SpanKind.STEP, parent_span_id=wf_span.span_id)
    model_span = chain.start_span("model_01", SpanKind.MODEL_CALL, parent_span_id=step_span.span_id)
    tool_span = chain.start_span("tool_01", SpanKind.TOOL_CALL, parent_span_id=step_span.span_id)
    verif_span = chain.start_span("verif_01", SpanKind.VERIFICATION, parent_span_id=task_span.span_id)

    model_span.finish(status="OK")
    tool_span.finish(status="OK")
    step_span.finish(status="OK")
    wf_span.finish(status="OK")
    task_span.finish(status="OK")

    assert chain.validate_chain_completeness() is True
    assert task_span.duration_sec >= 0.0


def test_secret_sanitizer_redacts_keys_and_tokens():
    raw_str = "Authorization: Bearer sk-123456789012345678901234567890"
    clean_str = SecretSanitizer.sanitize_string(raw_str)
    assert "sk-123456789012345678901234567890" not in clean_str
    assert "[REDACTED_SECRET]" in clean_str

    raw_dict = {
        "api_key": "secret_value_123",
        "nested": {
            "password": "my_password",
            "normal_field": "public_data"
        }
    }
    clean_dict = SecretSanitizer.sanitize_payload(raw_dict)
    assert clean_dict["api_key"] == "[REDACTED_SECRET]"
    assert clean_dict["nested"]["password"] == "[REDACTED_SECRET]"
    assert clean_dict["nested"]["normal_field"] == "public_data"


def test_audit_logger_correlated_events():
    logger = AuditLogger()

    event1 = logger.log(
        actor="system",
        action="execute_tool",
        resource="filesystem:read",
        decision="ALLOWED",
        policy="default_policy",
        correlation_id="corr_100",
        result="Success",
        metadata={"api_key": "secret123", "target_file": "main.py"}
    )

    assert event1.metadata["api_key"] == "[REDACTED_SECRET]"
    assert event1.metadata["target_file"] == "main.py"

    events = logger.get_events_by_correlation("corr_100")
    assert len(events) == 1
    assert logger.verify_ordering() is True
