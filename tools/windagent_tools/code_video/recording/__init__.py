"""
WindAgent Code Video Recording Package (Phase 9).

Provides pass catalog definitions, automated secret scanning, deterministic
master recording coordination, and Phase 9 gate verification.
"""

from __future__ import annotations

from windagent_tools.code_video.recording.passes import (
    PassCatalog,
    PassDefinition,
    PassRecord,
    PassStatus,
    PassType,
)
from windagent_tools.code_video.recording.recorder import (
    RecordingManifest,
    Video02RecordingEngine,
)
from windagent_tools.code_video.recording.secret_scanner import (
    SecretExposureMatch,
    SecretPattern,
    SecretScanResult,
    SecretScanner,
)
from windagent_tools.code_video.recording.verifier import (
    RecordingVerificationReport,
    RecordingVerifier,
)

__all__ = [
    # Passes
    "PassType",
    "PassStatus",
    "PassDefinition",
    "PassRecord",
    "PassCatalog",
    # Secret Scanner
    "SecretPattern",
    "SecretExposureMatch",
    "SecretScanResult",
    "SecretScanner",
    # Recorder
    "RecordingManifest",
    "Video02RecordingEngine",
    # Verifier
    "RecordingVerificationReport",
    "RecordingVerifier",
]
