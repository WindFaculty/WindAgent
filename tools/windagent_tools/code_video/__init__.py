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
from windagent_tools.code_video.workspace.golden_builder import (
    CHECKPOINT_STEPS,
    CheckpointDefinition,
    GoldenTutorialBuilder,
    STEP_01_MESSAGE_CODE,
    STEP_02_CONFIG_CODE,
    STEP_03_PROTOCOL_CODE,
    STEP_04_FAKE_LLM_CODE,
    STEP_05_AGENT_CODE,
    STEP_06_TESTS_CODE,
    STEP_07_FINAL_AGENT_CODE,
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
    # Golden Tutorial Builder
    "GoldenTutorialBuilder",
    "CheckpointDefinition",
    "CHECKPOINT_STEPS",
    "STEP_01_MESSAGE_CODE",
    "STEP_02_CONFIG_CODE",
    "STEP_03_PROTOCOL_CODE",
    "STEP_04_FAKE_LLM_CODE",
    "STEP_05_AGENT_CODE",
    "STEP_06_TESTS_CODE",
    "STEP_07_FINAL_AGENT_CODE",
    # Security Scanner
    "SecurityViolation",
    "SecurityScanReport",
    "WorkspaceSecretScanner",
    "LEAK_PATTERNS",
]

