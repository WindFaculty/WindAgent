"""
VP3D Phase 3 — Blender version validation (plan Stage B §3 backlog item 2).

`BlenderVersionValidator` accepts ONLY the policy-pinned `4.5.x LTS` line and
returns a TYPED readiness failure for anything else (5.x, 4.6, unparseable,
missing binary). Jobs NEVER run on an unvalidated version — fail closed.

The policy is a fixed constant (road_map.md Phase 3 pins Blender 4.5 LTS); it
is intentionally NOT user-configurable at runtime, so a version regression is
an auditable policy change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from windagent_tools.production_engines.blender.runtime.detector import BlenderInstallationCandidate

# Policy pin (road_map.md Phase 3): Blender 4.5 LTS line only.
BLENDER_POLICY_MAJOR_MINOR = (4, 5)
BLENDER_POLICY_LABEL = "4.5.x LTS"

_VERSION_RE = re.compile(r"[Bb]lender\s+v?(\d+)\.(\d+)(?:\.(\d+))?")

# Typed readiness failure reasons.
REASON_READY = "READY"
REASON_VERSION_MISMATCH = "VERSION_MISMATCH"
REASON_UNPARSEABLE = "UNPARSEABLE_VERSION"
REASON_BINARY_MISSING = "BINARY_MISSING"


@dataclass(frozen=True)
class BlenderVersionPolicy:
    """Policy pin for accepted Blender versions (4.5.x LTS)."""

    major_minor: tuple = (4, 5)
    label: str = BLENDER_POLICY_LABEL

    def accepts(self, version: Optional[tuple]) -> bool:
        if not version or len(version) < 2:
            return False
        return (version[0], version[1]) == self.major_minor


@dataclass(frozen=True)
class BlenderVersionValidationResult:
    """Typed readiness result of validating one candidate."""

    executable_path: str
    version_line: str = ""
    major: Optional[int] = None
    minor: Optional[int] = None
    patch: Optional[int] = None
    accepted: bool = False
    reason_code: str = REASON_VERSION_MISMATCH
    reason: str = ""
    policy_label: str = BLENDER_POLICY_LABEL

    @property
    def is_ready(self) -> bool:
        return self.accepted

    def to_dict(self) -> dict:
        return {
            "executable_path": self.executable_path,
            "version_line": self.version_line,
            "version": (
                [self.major, self.minor, self.patch]
                if self.major is not None
                else None
            ),
            "accepted": self.accepted,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "policy_label": self.policy_label,
        }


def parse_blender_version(version_line: str) -> Optional[tuple]:
    """Parse 'Blender 4.5.3 (hash ...)' into (4, 5, 3); None when unparseable."""
    if not version_line:
        return None
    match = _VERSION_RE.search(version_line)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3)) if match.group(3) else 0
    return (major, minor, patch)


class BlenderVersionValidator:
    """Validates a detected candidate against the pinned 4.5.x LTS policy."""

    def __init__(self, policy: Optional[BlenderVersionPolicy] = None) -> None:
        self.policy = policy or BlenderVersionPolicy()

    def validate(self, candidate: BlenderInstallationCandidate) -> BlenderVersionValidationResult:
        if not candidate.executable_path:
            return BlenderVersionValidationResult(
                executable_path="",
                reason_code=REASON_BINARY_MISSING,
                reason="No blender executable path provided.",
            )
        version = parse_blender_version(candidate.version_line)
        if version is None:
            return BlenderVersionValidationResult(
                executable_path=candidate.executable_path,
                version_line=candidate.version_line,
                reason_code=REASON_UNPARSEABLE,
                reason=f"Cannot parse Blender version from {candidate.version_line!r}.",
            )
        major, minor, patch = version
        if not self.policy.accepts(version):
            return BlenderVersionValidationResult(
                executable_path=candidate.executable_path,
                version_line=candidate.version_line,
                major=major,
                minor=minor,
                patch=patch,
                accepted=False,
                reason_code=REASON_VERSION_MISMATCH,
                reason=(
                    f"Blender {major}.{minor} does not satisfy the pinned "
                    f"policy {self.policy.label}."
                ),
            )
        return BlenderVersionValidationResult(
            executable_path=candidate.executable_path,
            version_line=candidate.version_line,
            major=major,
            minor=minor,
            patch=patch,
            accepted=True,
            reason_code=REASON_READY,
            reason=f"Blender {major}.{minor}.{patch} satisfies {self.policy.label}.",
        )

    def first_ready(self, candidates: list) -> Optional[BlenderVersionValidationResult]:
        """Return the first candidate that satisfies the policy, or None."""
        for candidate in candidates:
            result = self.validate(candidate)
            if result.is_ready:
                return result
        return None


__all__ = [
    "BLENDER_POLICY_MAJOR_MINOR",
    "BLENDER_POLICY_LABEL",
    "REASON_READY",
    "REASON_VERSION_MISMATCH",
    "REASON_UNPARSEABLE",
    "REASON_BINARY_MISSING",
    "BlenderVersionPolicy",
    "BlenderVersionValidationResult",
    "parse_blender_version",
    "BlenderVersionValidator",
]
