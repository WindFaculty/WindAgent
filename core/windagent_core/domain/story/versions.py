"""
Story artifact schema-version rules (frozen by B0 registry freeze).

- Every content artifact declares ``schema_version`` = ``studio.artifact/v1alpha1``
  and a stable content discriminator ``artifact_type``.
- Unknown MAJOR/alpha versions fail closed at parse time (reuse
  ``UnsupportedMajorVersionError`` semantics) — never silently interpreted.
- Canonical serialization is deterministic: sorted keys, ``ensure_ascii=False``,
  UTC ISO timestamps, no operational state in the content hash.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict

from windagent_core.domain.video_production.errors import UnsupportedMajorVersionError

ARTIFACT_SCHEMA_VERSION = "studio.artifact/v1alpha1"
SUPPORTED_ARTIFACT_SCHEMA_VERSIONS = frozenset({ARTIFACT_SCHEMA_VERSION})

_MAJOR_RE = re.compile(r"^studio\.artifact/v(\d+)(alpha\d+)?$")


def parse_artifact_schema_version(schema_version: str) -> tuple[int, str]:
    """Return ``(major, release_tag)`` for a schema version string."""
    if not schema_version or not isinstance(schema_version, str):
        raise UnsupportedMajorVersionError(
            f"schema_version must be a non-empty string; got {schema_version!r}.",
            details={"schema_version": schema_version},
        )
    match = _MAJOR_RE.match(schema_version.strip())
    if not match:
        raise UnsupportedMajorVersionError(
            f"Malformed story artifact schema_version {schema_version!r}; "
            f"expected 'studio.artifact/v<major>[alpha<n>]'.",
            details={"schema_version": schema_version},
        )
    return int(match.group(1)), match.group(2) or ""


def validate_artifact_schema_version(schema_version: str) -> str:
    """Fail closed on unknown artifact schema version (frozen rule 2)."""
    if schema_version not in SUPPORTED_ARTIFACT_SCHEMA_VERSIONS:
        major, release = parse_artifact_schema_version(schema_version)
        raise UnsupportedMajorVersionError(
            f"Unsupported story artifact schema version {schema_version!r}; "
            f"supported: {sorted(SUPPORTED_ARTIFACT_SCHEMA_VERSIONS)}.",
            details={
                "schema_version": schema_version,
                "supported": sorted(SUPPORTED_ARTIFACT_SCHEMA_VERSIONS),
                "major": major,
                "release": release,
            },
        )
    return schema_version


def canonical_json_bytes(data: Dict[str, Any]) -> bytes:
    """Stable canonical bytes: sorted keys, compact separators, UTF-8 kept."""
    canonical = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return canonical.encode("utf-8")


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "SUPPORTED_ARTIFACT_SCHEMA_VERSIONS",
    "parse_artifact_schema_version",
    "validate_artifact_schema_version",
    "canonical_json_bytes",
]
