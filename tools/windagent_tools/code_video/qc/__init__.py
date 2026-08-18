"""
Visual Quality Control (QC) and Final Gate Certification Module for Code Video Production.
"""

from __future__ import annotations

from windagent_tools.code_video.qc.code_qc import (
    ASTNormalizer,
    CodeCorrectnessVerifier,
    CodeQCReport,
    FORBIDDEN_CORE_IMPORTS,
    REQUIRED_CLASSES,
    REQUIRED_TEST_FUNCTIONS,
)
from windagent_tools.code_video.qc.engine import (
    DOD_CRITERIA,
    MasterVisualQCEngine,
    MasterVisualQCReport,
)
from windagent_tools.code_video.qc.readability_qc import (
    ReadabilityQCReport,
    ReadabilityQCVerifier,
    contrast_ratio,
    hex_to_rgb,
    relative_luminance,
)
from windagent_tools.code_video.qc.secret_qc import (
    ALLOWED_PLACEHOLDERS,
    DANGEROUS_SECRET_PATTERNS,
    SecretFinding,
    SecretQCReport,
    SecretQCVerifier,
)
from windagent_tools.code_video.qc.structural_qc import (
    EXPECTED_SCENE_IDS,
    REQUIRED_CODE_SCENES,
    REQUIRED_GRAPHIC_ASSETS,
    StructuralQCReport,
    StructuralQCVerifier,
)
from windagent_tools.code_video.qc.terminal_qc import (
    MANDATORY_COMMAND_PATTERNS,
    TerminalCorrectnessVerifier,
    TerminalQCReport,
)
from windagent_tools.code_video.qc.timing_qc import (
    TimingQCReport,
    TimingQCVerifier,
)


__all__ = [
    "ALLOWED_PLACEHOLDERS",
    "ASTNormalizer",
    "CodeCorrectnessVerifier",
    "CodeQCReport",
    "contrast_ratio",
    "DANGEROUS_SECRET_PATTERNS",
    "DOD_CRITERIA",
    "EXPECTED_SCENE_IDS",
    "FORBIDDEN_CORE_IMPORTS",
    "hex_to_rgb",
    "MANDATORY_COMMAND_PATTERNS",
    "MasterVisualQCEngine",
    "MasterVisualQCReport",
    "ReadabilityQCReport",
    "ReadabilityQCVerifier",
    "relative_luminance",
    "REQUIRED_CLASSES",
    "REQUIRED_CODE_SCENES",
    "REQUIRED_GRAPHIC_ASSETS",
    "REQUIRED_TEST_FUNCTIONS",
    "SecretFinding",
    "SecretQCReport",
    "SecretQCVerifier",
    "StructuralQCReport",
    "StructuralQCVerifier",
    "TerminalCorrectnessVerifier",
    "TerminalQCReport",
    "TimingQCReport",
    "TimingQCVerifier",
]
