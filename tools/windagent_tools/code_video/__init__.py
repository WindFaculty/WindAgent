"""
Code Video Tools Package for WindAgent.

Provides workspace management, sandbox isolation, repository building,
incremental checkpoint tracking, and security scanning for code video creation.
"""

from __future__ import annotations

from windagent_tools.code_video.workspace.checkpoints import (
    CheckpointManager,
    CheckpointRecord,
)
from windagent_tools.code_video.workspace.repository_builder import (
    DEFAULT_ENV_EXAMPLE,
    DEFAULT_GITIGNORE,
    DEFAULT_PYPROJECT_TOML,
    DEFAULT_README_MD,
    TutorialRepositoryBuilder,
)
from windagent_tools.code_video.workspace.sandbox import TutorialWorkspace
from windagent_tools.code_video.workspace.security_scanner import (
    LEAK_PATTERNS,
    SecurityScanReport,
    SecurityViolation,
    WorkspaceSecretScanner,
)

__all__ = [
    # Sandbox & Workspace
    "TutorialWorkspace",
    # Repository Builder
    "TutorialRepositoryBuilder",
    "DEFAULT_GITIGNORE",
    "DEFAULT_ENV_EXAMPLE",
    "DEFAULT_PYPROJECT_TOML",
    "DEFAULT_README_MD",
    # Checkpoints
    "CheckpointRecord",
    "CheckpointManager",
    # Security Scanner
    "SecurityViolation",
    "SecurityScanReport",
    "WorkspaceSecretScanner",
    "LEAK_PATTERNS",
]
