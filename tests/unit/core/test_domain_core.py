"""
Unit Tests for WindAgent Core Domain (Phase 2):
- Typed Identifiers
- Domain Model Invariants
- Error Hierarchy
- Secret Redaction in Settings & Security Primitives
- Contract Protocols
- Legacy Compatibility Mappers
- Framework Boundary Verification
"""

import ast
import uuid
from pathlib import Path
import pytest

from windagent_core.domain.types import (
    SessionId, StepId, ToolCallId
)
from windagent_core.domain.models import (
    Session, SessionStatus, TaskRequest, WorkflowStep, WorkflowStatus,
)
from windagent_core.contracts.tools import ToolInvocation
from windagent_core.errors.exceptions import (
    NotFoundError, ProviderError, ToolError, IdentityValidationError
)
from windagent_core.config.settings import (
    ProviderSettings, SecuritySettings
)
from windagent_core.security.types import (
    Principal, Permission, RiskLevel, RedactedValue, SecretRef
)
from windagent_core.adapters.legacy_mappers import (
    legacy_session_dict_to_domain, domain_session_to_legacy_dict,
    legacy_workflow_dict_to_domain, domain_workflow_to_legacy_dict
)


def test_typed_identifiers():
    sid1 = SessionId.generate()
    sid2 = SessionId(str(sid1))
    assert sid1 == sid2
    assert str(sid1) == str(sid2)
    assert sid1.to_uuid() == sid2.to_uuid()
    assert hash(sid1) == hash(sid2)

    with pytest.raises(IdentityValidationError):
        SessionId("")

    with pytest.raises(IdentityValidationError):
        SessionId(12345)  # type: ignore


def test_domain_model_invariants():
    # Empty prompt prohibited
    with pytest.raises(ValueError, match="prompt cannot be empty"):
        TaskRequest(prompt="   ")

    # Step order must be >= 1
    with pytest.raises(ValueError, match="order must be >= 1"):
        WorkflowStep(id=StepId.generate(), order=0, name="invalid", tool_name="click_xy")

    # Tool invocation name cannot be empty
    with pytest.raises(ValueError, match="tool_name cannot be empty"):
        ToolInvocation(id=ToolCallId.generate(), tool_name="")

    # Session status transition
    session = Session(id=SessionId.generate())
    assert session.status == SessionStatus.IDLE
    session.transition_to(SessionStatus.RUNNING)
    assert session.status == SessionStatus.RUNNING


def test_error_hierarchy():
    err = NotFoundError("Session not found", code="WINDAGENT_001_NOT_FOUND")
    assert err.code == "WINDAGENT_001_NOT_FOUND"
    assert not err.retryable
    assert err.to_dict()["code"] == "WINDAGENT_001_NOT_FOUND"

    prov_err = ProviderError("Quota exceeded", provider_name="openai", status_code=429, retryable=True)
    assert prov_err.retryable
    assert prov_err.details["provider_name"] == "openai"
    assert prov_err.details["status_code"] == 429

    tool_err = ToolError("Execution timed out", tool_name="shell", retryable=False)
    assert not tool_err.retryable
    assert tool_err.details["tool_name"] == "shell"


def test_configuration_secret_redaction():
    prov = ProviderSettings(openai_api_key="sk-proj-secret123456789")
    repr_str = repr(prov)
    assert "sk-proj-secret123456789" not in repr_str
    assert "***REDACTED***" in repr_str

    sec = SecuritySettings(secret_encryption_key="super-secret-fernet-key")
    sec_repr = repr(sec)
    assert "super-secret-fernet-key" not in sec_repr
    assert "***REDACTED***" in sec_repr


def test_security_primitives():
    red = RedactedValue("my-raw-api-token")
    assert "my-raw-api-token" not in str(red)
    assert "my-raw-api-token" not in repr(red)
    assert str(red) == "***REDACTED***"
    assert red.get_secret_value() == "my-raw-api-token"

    sec_ref = SecretRef.create("anthropic_key", "sk-ant-12345")
    assert "sk-ant-12345" not in repr(sec_ref)
    assert sec_ref.get_secret() == "sk-ant-12345"

    perm = Permission(action="file:write", target="/etc/config", risk_level=RiskLevel.HIGH)
    principal = Principal(id="user_1", permissions=[perm])
    assert principal.has_permission("file:write", "/etc/config")
    assert not principal.has_permission("file:delete", "/etc/config")


def test_legacy_compatibility_mappers():
    raw_uid = str(uuid.uuid4())
    legacy_session = {
        "id": raw_uid,
        "created_at": "2026-07-23T05:00:00+00:00",
        "updated_at": "2026-07-23T05:00:00+00:00",
        "status": "running",
        "title": "Test Chat",
    }

    domain_session = legacy_session_dict_to_domain(legacy_session)
    assert str(domain_session.id) == raw_uid
    assert domain_session.status == SessionStatus.RUNNING

    back_to_legacy = domain_session_to_legacy_dict(domain_session)
    assert back_to_legacy["id"] == raw_uid
    assert back_to_legacy["status"] == "running"

    legacy_wf = {
        "workflow_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "created_at": "2026-07-23T05:00:00+00:00",
        "status": "pending",
        "steps": [
            {
                "id": str(uuid.uuid4()),
                "order": 1,
                "name": "Click Button",
                "tool_name": "click_xy",
                "params": {"x": 100, "y": 200},
                "status": "pending",
            }
        ]
    }

    domain_wf = legacy_workflow_dict_to_domain(legacy_wf)
    assert domain_wf.status == WorkflowStatus.PENDING
    assert len(domain_wf.steps) == 1
    assert domain_wf.steps[0].tool_name == "click_xy"

    exported = domain_workflow_to_legacy_dict(domain_wf)
    assert exported["workflow_id"] == str(domain_wf.workflow_id)
    assert len(exported["steps"]) == 1


def test_core_zero_framework_dependencies():
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    core_dir = root_dir / "core" / "windagent_core"
    
    forbidden = {"fastapi", "starlette", "sqlalchemy", "aiosqlite", "mcp", "langgraph"}

    for py_file in core_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imp_name = alias.name.split(".")[0]
                    assert imp_name not in forbidden, f"{py_file} imported forbidden framework '{imp_name}'"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imp_name = node.module.split(".")[0]
                    assert imp_name not in forbidden, f"{py_file} imported forbidden framework '{imp_name}'"
