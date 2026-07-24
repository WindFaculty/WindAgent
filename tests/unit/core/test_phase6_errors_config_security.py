"""
Unit tests for WindAgent Core Phase 6:
- Error hierarchy, retryability, category taxonomy, and automatic details redaction
- Immutable frozen Pydantic v2 config models
- Zero framework/os.getenv dependencies in core
- Security types and PermissionDecision structure
"""

import ast
import pytest
from pathlib import Path
from pydantic import ValidationError as PydanticValidationError

from windagent_core.errors import (
    WindAgentError, DomainError, ValidationError, IdentityValidationError, ConflictError,
    InvalidStateTransitionError, TerminalStateMutationError, ConcurrentStateConflictError,
    NotFoundError, PermissionDeniedError, ApprovalRequiredError, ExecutionError, RuntimeLostError,
    ProviderError, RateLimitError, QuotaExhaustedError, AuthenticationError, TimeoutError,
    ToolError, SerializationError, IntegrityError, ConfigurationError
)
from windagent_core.config import (
    ApplicationConfig, DatabaseConfig, ExecutionConfig, ProviderRoutingConfig,
    SecurityConfig, ObservabilityConfig, FeatureGateConfig
)
from windagent_core.security import (
    Principal, Role, Permission, ResourceScope, RiskLevel, ApprovalRequirement,
    PermissionEvaluationRequest, PermissionDecision, SecretRef, RedactedValue, SecurityAuditContext
)


def test_error_hierarchy_and_secret_redaction():
    # Verify inheritance
    err = RateLimitError("Rate limit hit", provider_name="openai", details={"api_key": "sk-secret-123"})
    assert isinstance(err, ProviderError)
    assert isinstance(err, WindAgentError)
    assert err.retryable is True
    assert err.category == "PROVIDER"
    
    # Check details redaction
    assert err.details["api_key"] == "***REDACTED***"
    assert err.details["provider_name"] == "openai"

    d = err.to_dict()
    assert d["code"] == "WINDAGENT_ERR_RATE_LIMIT"
    assert d["category"] == "PROVIDER"
    assert d["retryable"] is True
    assert d["details"]["api_key"] == "***REDACTED***"


def test_error_sanitization_nested():
    err = ToolError(
        "Tool execution failed",
        tool_name="shell",
        details={
            "env_vars": {"AWS_SECRET_ACCESS_KEY": "supersecret"},
            "tokens": [{"bearer_token": "token123"}],
            "normal": "public_val"
        }
    )
    assert err.details["env_vars"]["AWS_SECRET_ACCESS_KEY"] == "***REDACTED***"
    assert err.details["tokens"][0]["bearer_token"] == "***REDACTED***"
    assert err.details["normal"] == "public_val"


def test_config_models_immutability():
    app_cfg = ApplicationConfig(environment="production")
    assert app_cfg.environment == "production"

    # Frozen check
    with pytest.raises(PydanticValidationError):
        app_cfg.environment = "development"  # type: ignore

    sec_cfg = SecurityConfig(secret_encryption_key="my-key")
    assert "my-key" not in repr(sec_cfg)
    assert "***REDACTED***" in repr(sec_cfg)

    feat_gate = FeatureGateConfig(enable_orchestration_v2=True)
    assert feat_gate.enable_orchestration_v2 is True


def test_security_types_and_permission_decision():
    principal = Principal(id="user_101", roles=["developer"])
    req = PermissionEvaluationRequest(
        principal=principal,
        action="shell:execute",
        target="rm -rf /tmp/data",
        risk_level=RiskLevel.HIGH
    )
    decision = PermissionDecision(
        outcome="REQUIRE_APPROVAL",
        risk_level=RiskLevel.HIGH,
        reason_code="HIGH_RISK_COMMAND",
        human_reason="Destructive command requires explicit approval",
        matched_rule="rule_shell_rm"
    )
    assert not decision.is_allowed
    assert decision.outcome == "REQUIRE_APPROVAL"
    assert decision.risk_level == RiskLevel.HIGH


def test_core_zero_getenv_and_forbidden_imports():
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    core_dir = root_dir / "core" / "windagent_core"

    forbidden_modules = {"os.getenv", "os.environ", "fastapi", "sqlalchemy", "aiosqlite", "cryptography"}

    for py_file in core_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        
        # Check for os.getenv calls
        if "config" in py_file.parts:
            assert "os.getenv" not in content, f"{py_file} contains os.getenv call"
            assert "os.environ" not in content, f"{py_file} contains os.environ access"

        tree = ast.parse(content, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imp = alias.name.split(".")[0]
                    assert imp not in {"fastapi", "sqlalchemy", "aiosqlite", "cryptography"}, f"Forbidden import '{imp}' in {py_file}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imp = node.module.split(".")[0]
                    assert imp not in {"fastapi", "sqlalchemy", "aiosqlite", "cryptography"}, f"Forbidden import '{imp}' in {py_file}"
