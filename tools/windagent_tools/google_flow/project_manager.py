"""
Phase 13 — Flow project mapping and verification (plan 04 §13.2).

WindAgent stores a durable mapping between its own project/revision and the
Google Flow project:

    project_id | production_revision_id | flow_project_id |
    flow_project_url_or_stable_locator | browser_session_id |
    last_verified_at | mapping_status

Rules:
- open an existing Flow project before creating a new one;
- confirm the correct project with at least TWO independent signals;
- the display name is never the sole identity;
- a missing/deleted project is a typed failure — WindAgent never creates a
  replacement project and silently continues.

The manager is deterministic and offline (no browser calls); verification
uses signals supplied by the caller or a fake in tests.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Sequence


class FlowProjectMappingStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    MISSING = "MISSING"
    STALE = "STALE"
    ERROR = "ERROR"


class FlowProjectManagerError(RuntimeError):
    """Base error for project mapping failures."""


class FlowProjectVerificationError(FlowProjectManagerError):
    """Raised when the open project cannot be confirmed by two signals."""


class FlowProjectMissingError(FlowProjectManagerError):
    """Typed failure for a missing/deleted Flow project (no auto-replace)."""


@dataclass(frozen=True)
class FlowProjectMapping:
    """Durable WindAgent ↔ Flow project mapping (plan 04 §13.2)."""

    project_id: str
    production_revision_id: str
    flow_project_id: str = ""
    flow_project_url: str = ""
    browser_session_id: str = ""
    last_verified_at: float = 0.0
    mapping_status: FlowProjectMappingStatus = FlowProjectMappingStatus.UNVERIFIED
    display_name: str = ""  # never used as the sole identity

    def __post_init__(self) -> None:
        # Coerce a string status (JSON reload / dict merge) back to the enum.
        if isinstance(self.mapping_status, str):
            object.__setattr__(
                self, "mapping_status", FlowProjectMappingStatus(self.mapping_status)
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "production_revision_id": self.production_revision_id,
            "flow_project_id": self.flow_project_id,
            "flow_project_url": self.flow_project_url,
            "browser_session_id": self.browser_session_id,
            "last_verified_at": self.last_verified_at,
            "mapping_status": self.mapping_status.value,
            "display_name": self.display_name,
        }


@dataclass(frozen=True)
class FlowProjectSignal:
    """One independent signal used to confirm the correct project."""

    kind: str  # e.g. flow_project_id | stable_url | title | canvas_marker
    value: str

    def matches(self, observed: Sequence[str]) -> bool:
        """Match this signal against the observed signals.

        - An exact element match always counts (tests pass ids/urls directly).
        - A `stable_url` signal must match the observed URL exactly.
        - An id-like signal (flow_project_id) must appear as a whole URL path
          segment (never a prefix of another id, e.g. fp_123 vs fp_12345).
        """
        if any(v == self.value for v in observed):
            return True
        url = next((v for v in observed if v.startswith("http")), "")
        if not url:
            return False
        if self.kind == "stable_url":
            return url == self.value
        segments = {seg for seg in url.rstrip("/").split("/") if seg}
        return self.value in segments


class FlowProjectManager:
    """Deterministic project mapping + two-signal verification (plan §13.2)."""

    def __init__(
        self,
        *,
        state_dir: str,
        clock: Optional[callable] = None,
    ) -> None:
        self._state_dir = Path(state_dir).resolve()
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._clock = clock or time.time
        self._registry_path = self._state_dir / "flow_project_mappings.json"
        self._mappings: dict[str, dict] = self._load()

    # ------------------------------------------------------------------
    def _load(self) -> dict[str, dict]:
        if not self._registry_path.exists():
            return {}
        try:
            data = json.loads(self._registry_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        self._registry_path.write_text(
            json.dumps(self._mappings, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    def create_mapping(
        self,
        *,
        project_id: str,
        production_revision_id: str,
        flow_project_id: str = "",
        flow_project_url: str = "",
        browser_session_id: str = "",
        display_name: str = "",
    ) -> FlowProjectMapping:
        mapping = FlowProjectMapping(
            project_id=project_id,
            production_revision_id=production_revision_id,
            flow_project_id=flow_project_id,
            flow_project_url=flow_project_url,
            browser_session_id=browser_session_id,
            last_verified_at=self._clock(),
            mapping_status=FlowProjectMappingStatus.UNVERIFIED,
            display_name=display_name,
        )
        self._mappings[project_id] = mapping.to_dict()
        self._save()
        return mapping

    def get_mapping(self, project_id: str) -> Optional[FlowProjectMapping]:
        raw = self._mappings.get(project_id)
        if raw is None:
            return None
        return FlowProjectMapping(**raw)

    def list_mappings(self) -> list[FlowProjectMapping]:
        return [
            FlowProjectMapping(**raw)
            for raw in sorted(
                self._mappings.values(), key=lambda r: r.get("last_verified_at", 0.0)
            )
        ]

    # ------------------------------------------------------------------
    def verify_two_signals(
        self,
        mapping: FlowProjectMapping,
        *,
        observed: Sequence[str],
    ) -> FlowProjectMapping:
        """Confirm the correct project with at least two independent signals.

        Raises `FlowProjectVerificationError` when fewer than two signals
        match (plan 04 §13.2: never rely on one signal / display name alone).
        """
        expected_signals = self._expected_signals(mapping)
        matched = [s for s in expected_signals if s.matches(observed)]
        if len(matched) < 2:
            raise FlowProjectVerificationError(
                f"project {mapping.project_id} confirmed by only "
                f"{len(matched)} signal(s); need >= 2"
            )
        updated = FlowProjectMapping(
            **{
                **mapping.to_dict(),
                "mapping_status": FlowProjectMappingStatus.VERIFIED.value,
                "last_verified_at": self._clock(),
            }
        )
        self._mappings[updated.project_id] = updated.to_dict()
        self._save()
        return updated

    @staticmethod
    def _expected_signals(mapping: FlowProjectMapping) -> list[FlowProjectSignal]:
        signals = []
        if mapping.flow_project_id:
            signals.append(FlowProjectSignal("flow_project_id", mapping.flow_project_id))
        if mapping.flow_project_url:
            signals.append(FlowProjectSignal("stable_url", mapping.flow_project_url))
        # display_name is deliberately NOT a signal — never the sole identity.
        return signals

    # ------------------------------------------------------------------
    def open_before_create(
        self,
        project_id: str,
        *,
        observed: Sequence[str],
    ) -> FlowProjectMapping:
        """Open an existing project when a mapping exists; else create.

        The observed signals are used to confirm the existing project; if the
        existing mapping is missing (project deleted in Flow), a typed
        `FlowProjectMissingError` is raised — WindAgent never auto-replaces
        and continues (plan 04 §13.2).
        """
        mapping = self.get_mapping(project_id)
        if mapping is None:
            return self.create_mapping(
                project_id=project_id,
                production_revision_id="unset",
            )
        if mapping.mapping_status == FlowProjectMappingStatus.MISSING:
            raise FlowProjectMissingError(
                f"Flow project for {project_id} is missing; do not auto-replace"
            )
        return self.verify_two_signals(mapping, observed=observed)

    def mark_missing(self, project_id: str) -> FlowProjectMapping:
        mapping = self.get_mapping(project_id)
        if mapping is None:
            raise FlowProjectManagerError(f"no mapping for {project_id}")
        updated = FlowProjectMapping(
            **{
                **mapping.to_dict(),
                "mapping_status": FlowProjectMappingStatus.MISSING.value,
            }
        )
        self._mappings[project_id] = updated.to_dict()
        self._save()
        return updated


__all__ = [
    "FlowProjectMapping",
    "FlowProjectMappingStatus",
    "FlowProjectManager",
    "FlowProjectManagerError",
    "FlowProjectMissingError",
    "FlowProjectSignal",
    "FlowProjectVerificationError",
]
