"""
Typed Immutable Configuration Models for WindAgent Architecture V2 (Phase 6).
Pure Pydantic v2 frozen configuration schemas without environment loaders or side-effects.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from windagent_core.version import PRODUCT_VERSION


def redact_value(val: Optional[str]) -> str:
    if not val:
        return "<EMPTY>"
    return "***REDACTED***"


class ApplicationConfig(BaseModel):
    environment: str = "development"
    debug: bool = False
    app_name: str = "WindAgent"
    version: str = PRODUCT_VERSION

    model_config = ConfigDict(frozen=True, extra="forbid", validate_assignment=True)


class DatabaseConfig(BaseModel):
    db_path: str = "windagent.db"
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False

    model_config = ConfigDict(frozen=True, extra="forbid", validate_assignment=True)


class ExecutionConfig(BaseModel):
    worktree_root: str = ".worktrees"
    max_concurrent_tasks: int = 5
    task_timeout_seconds: float = 300.0
    shell_enabled: bool = True

    model_config = ConfigDict(frozen=True, extra="forbid", validate_assignment=True)


class ProviderRoutingConfig(BaseModel):
    default_provider: str = "mock"
    default_model: str = "mock-gpt-4o"
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None

    model_config = ConfigDict(frozen=True, extra="forbid", validate_assignment=True)

    def __repr__(self) -> str:
        return (
            f"ProviderRoutingConfig(default_provider={self.default_provider!r}, "
            f"default_model={self.default_model!r}, "
            f"openai_api_key={redact_value(self.openai_api_key)}, "
            f"anthropic_api_key={redact_value(self.anthropic_api_key)}, "
            f"google_api_key={redact_value(self.google_api_key)})"
        )


class SecurityConfig(BaseModel):
    secret_encryption_key: Optional[str] = None
    auth_enabled: bool = False
    allowed_hosts: List[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])

    model_config = ConfigDict(frozen=True, extra="forbid", validate_assignment=True)

    def __repr__(self) -> str:
        return (
            f"SecurityConfig(secret_encryption_key={redact_value(self.secret_encryption_key)}, "
            f"auth_enabled={self.auth_enabled}, "
            f"allowed_hosts={self.allowed_hosts})"
        )


class ObservabilityConfig(BaseModel):
    log_level: str = "INFO"
    json_logs: bool = True
    audit_trail_enabled: bool = True
    cost_tracking_enabled: bool = True

    model_config = ConfigDict(frozen=True, extra="forbid", validate_assignment=True)


class FeatureGateConfig(BaseModel):
    enable_orchestration_v2: bool = True
    enable_provider_v3_routing: bool = True
    enable_shadow_comparator: bool = False
    enable_agent_s3: bool = False
    custom_gates: Dict[str, bool] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True, extra="forbid", validate_assignment=True)


# Backward compatibility aliases
CoreSettings = ApplicationConfig
DatabaseSettings = DatabaseConfig
ExecutionSettings = ExecutionConfig
ProviderSettings = ProviderRoutingConfig
SecuritySettings = SecurityConfig
ObservabilitySettings = ObservabilityConfig
