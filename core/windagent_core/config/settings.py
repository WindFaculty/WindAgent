"""
Typed Configuration Settings for WindAgent Architecture V2.
Enforces typed settings structures and secret redaction in string representations.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def redact_value(val: Optional[str]) -> str:
    if not val:
        return "<EMPTY>"
    return "***REDACTED***"


@dataclass
class CoreSettings:
    environment: str = "development"
    debug: bool = False
    app_name: str = "WindAgent"
    version: str = "0.3.0"


@dataclass
class DatabaseSettings:
    db_path: str = "windagent.db"
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False


@dataclass
class ProviderSettings:
    default_provider: str = "mock"
    default_model: str = "mock-gpt-4o"
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"ProviderSettings(default_provider={self.default_provider!r}, "
            f"default_model={self.default_model!r}, "
            f"openai_api_key={redact_value(self.openai_api_key)}, "
            f"anthropic_api_key={redact_value(self.anthropic_api_key)}, "
            f"google_api_key={redact_value(self.google_api_key)})"
        )


@dataclass
class ExecutionSettings:
    worktree_root: str = ".worktrees"
    max_concurrent_tasks: int = 5
    task_timeout_seconds: float = 300.0
    shell_enabled: bool = True


@dataclass
class SecuritySettings:
    secret_encryption_key: Optional[str] = None
    auth_enabled: bool = False
    allowed_hosts: List[str] = field(default_factory=lambda: ["localhost", "127.0.0.1"])

    def __repr__(self) -> str:
        return (
            f"SecuritySettings(secret_encryption_key={redact_value(self.secret_encryption_key)}, "
            f"auth_enabled={self.auth_enabled}, "
            f"allowed_hosts={self.allowed_hosts})"
        )


@dataclass
class ObservabilitySettings:
    log_level: str = "INFO"
    json_logs: bool = True
    audit_trail_enabled: bool = True
    cost_tracking_enabled: bool = True
