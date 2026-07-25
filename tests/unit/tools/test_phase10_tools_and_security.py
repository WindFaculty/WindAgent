"""
Unit tests for WindAgent Tools and Security Policy Adoption (Phase 10).
Verifies canonical ToolInvocation & ToolResult models, fail-closed permission engine,
unknown action default DENY, destructive action approval, hard-deny rules, normalized path scope,
and shared decision_id in permission events & audit records.
"""

import pytest
import os
from windagent_core.domain.types import ToolInvocationId, SessionId, TaskId, DecisionId
from windagent_core.contracts.tools import ToolInvocation, ToolResult
from windagent_core.security.types import (
    PermissionEvaluationRequest, PermissionDecision, SecurityAuditContext, Principal, RiskLevel
)
from windagent_core.errors.exceptions import PermissionDeniedError, WindAgentError
from windagent_tools.security.permission_engine import PermissionEngine, normalize_and_validate_path
from windagent_tools.base import ToolDefinition, ToolExecutionContext, ToolRiskLevel


def test_canonical_tool_models():
    inv_id = ToolInvocationId.generate()
    sess_id = SessionId.generate()
    task_id = TaskId.generate()

    inv = ToolInvocation(
        id=inv_id,
        tool_name="view_file",
        params={"path": "src/main.py"},
    )
    assert inv.id == inv_id
    assert inv.tool_name == "view_file"
    assert inv.arguments == {"path": "src/main.py"}

    res = ToolResult(
        call_id=inv_id,
        success=True,
        data="file content",
        execution_time_ms=42.5
    )
    assert res.call_id == inv_id
    assert res.success is True
    assert res.execution_time_ms == 42.5


def test_unknown_action_defaults_to_deny():
    engine = PermissionEngine()
    req = PermissionEvaluationRequest(
        principal=Principal(id="agent_1"),
        action="unknown_action_xyz",
        target="some_target"
    )
    decision = engine.evaluate_request(req)
    assert decision.outcome == "DENY"
    assert decision.reason_code == "UNKNOWN_ACTION_DENY"
    assert decision.is_allowed is False


def test_destructive_action_not_auto_approved():
    engine = PermissionEngine()
    req = PermissionEvaluationRequest(
        principal=Principal(id="autonomous_agent"),
        action="delete_database",
        target="prod_db",
        risk_level=RiskLevel.HIGH,
        context={"user_approved": False, "is_destructive": True}
    )
    decision = engine.evaluate_request(req)
    assert decision.outcome == "REQUIRE_APPROVAL"
    assert decision.reason_code == "DESTRUCTIVE_APPROVAL_REQUIRED"
    assert decision.is_allowed is False


def test_autonomous_profile_cannot_bypass_hard_deny():
    engine = PermissionEngine()
    req = PermissionEvaluationRequest(
        principal=Principal(id="autonomous_agent", roles=["admin"]),
        action="drop_production_db",
        target="database"
    )
    decision = engine.evaluate_request(req)
    assert decision.outcome == "DENY"
    assert decision.reason_code == "HARD_DENY_RULE"
    assert decision.is_allowed is False


def test_permission_decision_and_audit_context_share_decision_id():
    engine = PermissionEngine()
    req = PermissionEvaluationRequest(
        principal=Principal(id="user_123"),
        action="view_file",
        target="README.md"
    )
    decision = engine.evaluate_request(req)
    assert decision.outcome == "ALLOW"
    assert isinstance(decision.decision_id, DecisionId)

    audit = SecurityAuditContext(
        audit_id="audit-1",
        principal_id="user_123",
        action="view_file",
        resource="README.md",
        decision_outcome=decision.outcome,
        timestamp_utc="2026-07-24T18:00:00Z",
        decision_id=decision.decision_id
    )
    assert audit.decision_id == decision.decision_id


def test_normalized_absolute_path_scope():
    workspace = os.path.abspath("d:/code_ca_nhan/WindAgent")

    # Inside workspace -> Valid
    assert normalize_and_validate_path(f"{workspace}/src/index.py", workspace) is True
    assert normalize_and_validate_path(f"{workspace}/../WindAgent/src/index.py", workspace) is True

    # Traversal escaping workspace -> Invalid
    assert normalize_and_validate_path(f"{workspace}/../../Windows/System32", workspace) is False
    assert normalize_and_validate_path("C:/Windows/System32", workspace) is False
