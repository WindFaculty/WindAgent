"""Canonical Studio certification-mode configuration.

``WINDAGENT_CERTIFICATION_MODE`` is the process-wide authority.  The legacy
``WIND_STUDIO_CERTIFICATION`` name remains a read-only compatibility alias so
older launchers fail closed while they migrate.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

CERTIFICATION_MODE_ENV = "WINDAGENT_CERTIFICATION_MODE"
LEGACY_CERTIFICATION_MODE_ENV = "WIND_STUDIO_CERTIFICATION"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUE_VALUES


def certification_mode_enabled(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return the canonical certification mode, with a legacy fallback.

    An explicitly supplied canonical value always wins, including ``0``.
    This prevents a stale legacy flag from overriding the launcher's manifest.
    """

    env = os.environ if environ is None else environ
    if CERTIFICATION_MODE_ENV in env:
        return _enabled(env.get(CERTIFICATION_MODE_ENV))
    return _enabled(env.get(LEGACY_CERTIFICATION_MODE_ENV))


def certification_mode_conflict(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Whether canonical and legacy flags are both present but disagree."""

    env = os.environ if environ is None else environ
    if CERTIFICATION_MODE_ENV not in env or LEGACY_CERTIFICATION_MODE_ENV not in env:
        return False
    return _enabled(env.get(CERTIFICATION_MODE_ENV)) != _enabled(
        env.get(LEGACY_CERTIFICATION_MODE_ENV)
    )


__all__ = [
    "CERTIFICATION_MODE_ENV",
    "LEGACY_CERTIFICATION_MODE_ENV",
    "certification_mode_conflict",
    "certification_mode_enabled",
]
