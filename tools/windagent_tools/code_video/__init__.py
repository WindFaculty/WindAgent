"""
Code Video Tools Package for WindAgent.

Provides workspace management, sandbox isolation, repository building,
incremental checkpoint tracking, security scanning, and studio rendering for code video creation.
"""

from __future__ import annotations

from windagent_tools.code_video.renderer import (
    ChecklistItem,
    ChecklistItemStatus,
    ChecklistState,
    CodeEditorRenderer,
    CodeEditorState,
    CodeStudioRenderer,
    CodeToken,
    DiagramEdge,
    DiagramNode,
    DiagramRenderer,
    DiagramState,
    FileTreeItem,
    FileTreeState,
    NodeCategory,
    OutroCardState,
    PythonSyntaxHighlighter,
    PythonTokenType,
    StudioLayoutState,
    TerminalLine,
    TerminalLineType,
    TerminalRenderer,
    TerminalState,
    TitleCardState,
    TitleRenderer,
)
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
from windagent_tools.code_video.capture import (
    BrowserCaptureAdapter,
    CapturePort,
    CaptureStatus,
    FrameMetadata,
    FrameReport,
    MediaProbeReport,
    StudioCaptureEngine,
    TakeConfig,
    TakeReceipt,
)
from windagent_tools.code_video.media import (
    TakeAssembler,
    TakesManifest,
    TakeVerificationResult,
    TakeVerifier,
)
from windagent_tools.code_video.recording import (
    PassCatalog,
    PassDefinition,
    PassRecord,
    PassStatus,
    PassType,
    RecordingManifest,
    RecordingVerificationReport,
    RecordingVerifier,
    SecretExposureMatch,
    SecretPattern,
    SecretScanResult,
    SecretScanner,
    Video02RecordingEngine,
)

from windagent_tools.code_video.qc import (
    CodeCorrectnessVerifier,
    CodeQCReport,
    DOD_CRITERIA,
    MasterVisualQCEngine,
    MasterVisualQCReport,
    ReadabilityQCReport,
    ReadabilityQCVerifier,
    SecretFinding,
    SecretQCReport,
    SecretQCVerifier,
    StructuralQCReport,
    StructuralQCVerifier,
    TerminalCorrectnessVerifier,
    TerminalQCReport,
    TimingQCReport,
    TimingQCVerifier,
)

from windagent_tools.code_video.program import (
    DODMatrixItem,
    HandoffFileEntry,
    HandoffPackage,
    ProgramCertificationEngine,
    ProgramCertificationReport,
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
    # Renderer Subsystem
    "PythonTokenType",
    "CodeToken",
    "PythonSyntaxHighlighter",
    "CodeEditorState",
    "CodeEditorRenderer",
    "TerminalLineType",
    "TerminalLine",
    "TerminalState",
    "TerminalRenderer",
    "NodeCategory",
    "DiagramNode",
    "DiagramEdge",
    "DiagramState",
    "DiagramRenderer",
    "ChecklistItemStatus",
    "ChecklistItem",
    "TitleCardState",
    "ChecklistState",
    "OutroCardState",
    "TitleRenderer",
    "FileTreeItem",
    "FileTreeState",
    "StudioLayoutState",
    "CodeStudioRenderer",
    # Capture Subsystem
    "CaptureStatus",
    "TakeConfig",
    "CapturePort",
    "TakeReceipt",
    "FrameMetadata",
    "FrameReport",
    "MediaProbeReport",
    "StudioCaptureEngine",
    "BrowserCaptureAdapter",
    # Media Subsystem
    "TakesManifest",
    "TakeAssembler",
    "TakeVerificationResult",
    "TakeVerifier",
    # Recording Subsystem (Phase 9)
    "PassType",
    "PassStatus",
    "PassDefinition",
    "PassRecord",
    "PassCatalog",
    "SecretPattern",
    "SecretExposureMatch",
    "SecretScanResult",
    "SecretScanner",
    "RecordingManifest",
    "Video02RecordingEngine",
    "RecordingVerificationReport",
    "RecordingVerifier",
    # QC Subsystem (Phase 11)
    "StructuralQCReport",
    "StructuralQCVerifier",
    "CodeQCReport",
    "CodeCorrectnessVerifier",
    "TerminalQCReport",
    "TerminalCorrectnessVerifier",
    "SecretFinding",
    "SecretQCReport",
    "SecretQCVerifier",
    "ReadabilityQCReport",
    "ReadabilityQCVerifier",
    "TimingQCReport",
    "TimingQCVerifier",
    "DOD_CRITERIA",
    "MasterVisualQCReport",
    "MasterVisualQCEngine",
    # Program Certification (Phase 12)
    "DODMatrixItem",
    "HandoffFileEntry",
    "HandoffPackage",
    "ProgramCertificationEngine",
    "ProgramCertificationReport",
]




