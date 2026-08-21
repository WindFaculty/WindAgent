"""Canonical Studio certification-mode configuration.

``WINDAGENT_CERTIFICATION_MODE`` is the process-wide authority.  The legacy
``WIND_STUDIO_CERTIFICATION`` name remains a read-only compatibility alias so
older launchers fail closed while they migrate.

Core purity: this module never reads the process environment itself.
The environment mapping is injected by the caller (composition root).
"""

from __future__ import annotations

from collections.abc import Mapping

CERTIFICATION_MODE_ENV = "WINDAGENT_CERTIFICATION_MODE"
LEGACY_CERTIFICATION_MODE_ENV = "WIND_STUDIO_CERTIFICATION"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUE_VALUES


def certification_mode_enabled(environ: Mapping[str, str]) -> bool:
    """Return the canonical certification mode, with a legacy fallback.

    An explicitly supplied canonical value always wins, including ``0``.
    This prevents a stale legacy flag from overriding the launcher's manifest.
    """

    if CERTIFICATION_MODE_ENV in environ:
        return _enabled(environ.get(CERTIFICATION_MODE_ENV))
    return _enabled(environ.get(LEGACY_CERTIFICATION_MODE_ENV))


def certification_mode_conflict(environ: Mapping[str, str]) -> bool:
    """Whether canonical and legacy flags are both present but disagree."""

    has_canonical = CERTIFICATION_MODE_ENV in environ
    has_legacy = LEGACY_CERTIFICATION_MODE_ENV in environ
    if not has_canonical or not has_legacy:
        return False
    canonical = _enabled(environ.get(CERTIFICATION_MODE_ENV))
    legacy = _enabled(environ.get(LEGACY_CERTIFICATION_MODE_ENV))
    return canonical != legacy


__all__ = [
    "CERTIFICATION_MODE_ENV",
    "LEGACY_CERTIFICATION_MODE_ENV",
    "certification_mode_conflict",
    "certification_mode_enabled",
]
