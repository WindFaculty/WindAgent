"""Typed Worker runtime settings (Phase 8A).

``WorkerRuntimeSettings`` is the single frozen snapshot of every environment
value the Worker composition root may read.  ``from_environment`` is the ONLY
Worker composition location allowed to read environment variables; the
container and its helpers consume the frozen fields instead of re-reading the
process environment.

Boolean parsing is strict: unset -> default, accepted true ``1,true,yes,on``,
accepted false ``0,false,no,off``, any other non-empty value raises a clear
settings error.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})

CERTIFICATION_MODE_ENV = "WINDAGENT_CERTIFICATION_MODE"
LEGACY_CERTIFICATION_MODE_ENV = "WIND_STUDIO_CERTIFICATION"


class WorkerSettingsError(ValueError):
    """Raised when a Worker environment value cannot be parsed or validated."""


class CertificationPreflightError(RuntimeError):
    """Worker composition cannot satisfy the certification profile."""


def _parse_bool(name: str, value: str | None, default: bool) -> bool:
    """Strict boolean parsing: unset -> default, else 1/true/yes/on or
    0/false/no/off; any other non-empty value raises a clear settings error."""
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise WorkerSettingsError(
        f"Invalid boolean value for {name}: {value!r} "
        "(accepted: 1,true,yes,on / 0,false,no,off)"
    )


def _certification_enabled() -> bool:
    """Canonical certification flag with the legacy read-only alias fallback.

    An explicitly supplied canonical value always wins, including ``0``, so a
    stale legacy flag cannot override the launcher's manifest.
    """
    canonical = os.getenv(CERTIFICATION_MODE_ENV)
    if canonical is not None:
        return _parse_bool(CERTIFICATION_MODE_ENV, canonical, False)
    return _parse_bool(
        LEGACY_CERTIFICATION_MODE_ENV,
        os.getenv(LEGACY_CERTIFICATION_MODE_ENV),
        False,
    )


def _certification_conflict() -> bool:
    """Whether canonical and legacy flags are both present but disagree."""
    canonical = os.getenv(CERTIFICATION_MODE_ENV)
    legacy = os.getenv(LEGACY_CERTIFICATION_MODE_ENV)
    if canonical is None or legacy is None:
        return False
    return _parse_bool(
        CERTIFICATION_MODE_ENV, canonical, False
    ) != _parse_bool(LEGACY_CERTIFICATION_MODE_ENV, legacy, False)


@dataclass(frozen=True)
class WorkerRuntimeSettings:
    """Frozen typed snapshot of the Worker composition environment.

    PHASE 8A: the container owns exactly one settings instance; every
    ``os.getenv`` / ``_env_enabled`` / certification environment reread in the
    composition root is replaced by a field on this object.
    """

    database_url: str
    fake_runtime: bool
    studio_runtime: bool
    studio_model_route: bool
    studio_canonical_model: str
    blender_engine: bool
    asset_gateway: bool
    asset_normalizer: bool
    artifact_root: str
    asset_library_root: str
    blender_executable: str
    certification_enabled: bool
    certification_conflict: bool

    @property
    def provider_routing(self) -> bool:
        """Studio model/provider routing is active only under the Studio
        runtime (Plan A A6)."""
        return self.studio_runtime and self.studio_model_route

    @classmethod
    def from_environment(
        cls, default_db_url: str = "sqlite+aiosqlite:///windagent.db"
    ) -> "WorkerRuntimeSettings":
        """Build the frozen settings snapshot from the process environment.

        This is the only Worker composition location allowed to read
        environment variables.
        """
        return cls(
            database_url=os.getenv("WINDAGENT_DATABASE_URL", default_db_url),
            fake_runtime=_parse_bool(
                "WINDAGENT_FAKE_RUNTIME",
                os.getenv("WINDAGENT_FAKE_RUNTIME"),
                False,
            ),
            studio_runtime=_parse_bool(
                "WINDAGENT_STUDIO_RUNTIME",
                os.getenv("WINDAGENT_STUDIO_RUNTIME"),
                False,
            ),
            studio_model_route=_parse_bool(
                "WINDAGENT_STUDIO_MODEL_ROUTE",
                os.getenv("WINDAGENT_STUDIO_MODEL_ROUTE"),
                False,
            ),
            studio_canonical_model=os.getenv(
                "WINDAGENT_STUDIO_CANONICAL_MODEL", ""
            ),
            blender_engine=_parse_bool(
                "WINDAGENT_BLENDER_ENGINE",
                os.getenv("WINDAGENT_BLENDER_ENGINE"),
                False,
            ),
            asset_gateway=_parse_bool(
                "WINDAGENT_ASSET_GATEWAY",
                os.getenv("WINDAGENT_ASSET_GATEWAY"),
                False,
            ),
            asset_normalizer=_parse_bool(
                "WINDAGENT_ASSET_NORMALIZER",
                os.getenv("WINDAGENT_ASSET_NORMALIZER"),
                False,
            ),
            artifact_root=os.getenv("WINDAGENT_ARTIFACT_ROOT", "artifacts"),
            asset_library_root=os.getenv(
                "WINDAGENT_ASSET_LIBRARY_ROOT", "data/assets/library"
            ),
            blender_executable=os.getenv("WINDAGENT_BLENDER_EXECUTABLE", ""),
            certification_enabled=_certification_enabled(),
            certification_conflict=_certification_conflict(),
        )


def validate_settings(settings: WorkerRuntimeSettings) -> None:
    """Validate settings dependencies before any DB/background-task mutation.

    - Studio model/provider routing requires the Studio runtime.
    - The asset normalizer requires the asset gateway.
    """
    if settings.studio_model_route and not settings.studio_runtime:
        raise WorkerSettingsError(
            "WINDAGENT_STUDIO_MODEL_ROUTE=1 requires WINDAGENT_STUDIO_RUNTIME=1"
        )
    if settings.asset_normalizer and not settings.asset_gateway:
        raise WorkerSettingsError(
            "WINDAGENT_ASSET_NORMALIZER=1 requires WINDAGENT_ASSET_GATEWAY=1"
        )


__all__ = [
    "CertificationPreflightError",
    "WorkerRuntimeSettings",
    "WorkerSettingsError",
    "validate_settings",
]
