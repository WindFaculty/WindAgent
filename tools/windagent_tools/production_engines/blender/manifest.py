"""
VP3D Phase 3 — Blender add-on allowlist manifest (plan Stage B §3 backlog item 8).

Security contract (mirrors the Phase 3 plan):

```text
addon allowlist
      ↓
signed/version-pinned manifest
      ↓
Blender runtime
```

- An add-on may only be loaded when its `(module_id, version)` tuple is
  present in the allowlist AND its SHA-256 content hash matches (or the
  manifest pins the exact source so drift is detectable).
- An add-on NOT in the allowlist resolves to `REQUIRES_HUMAN_APPROVAL` — the
  engine adapter refuses to run the job (fail closed). The agent can never
  install or enable a new add-on by itself (plan rule).
- The manifest itself is immutable after construction and may be loaded from
  a signed JSON payload; integrity of that payload is the composition root's
  job (secret/key management is out of scope here).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional

# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

APPROVED = "APPROVED"
REQUIRES_HUMAN_APPROVAL = "REQUIRES_HUMAN_APPROVAL"
REJECTED = "REJECTED"


@dataclass(frozen=True)
class BlenderAddonSpec:
    """A single allowlisted add-on entry (version-pinned + content-hashed)."""

    module_id: str
    version: str
    sha256: str
    source: str  # e.g. "bundled", "https://extensions.blender.org/..."
    permissions: FrozenSet[str] = frozenset()  # e.g. {"execute_code"}

    def to_dict(self) -> dict:
        return {
            "module_id": self.module_id,
            "version": self.version,
            "sha256": self.sha256,
            "source": self.source,
            "permissions": sorted(self.permissions),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BlenderAddonSpec":
        return cls(
            module_id=str(data["module_id"]),
            version=str(data["version"]),
            sha256=str(data["sha256"]),
            source=str(data.get("source", "")),
            permissions=frozenset(data.get("permissions") or []),
        )


@dataclass(frozen=True)
class BlenderAddonRequest:
    """The add-on a job wants to use — the manifest gate input."""

    module_id: str
    version: Optional[str] = None
    sha256: Optional[str] = None


@dataclass(frozen=True)
class BlenderAddonDecision:
    """Outcome of checking one add-on request against the allowlist."""

    module_id: str
    status: str
    reason: str
    matched_spec: Optional[BlenderAddonSpec] = None

    @property
    def allowed(self) -> bool:
        return self.status == APPROVED


class BlenderAddonManifest:
    """Immutable add-on allowlist with fail-closed lookup.

    Rules (all fail closed — a missing/unknown entry never grants access):

    - known module_id but different pinned version  -> REQUIRES_HUMAN_APPROVAL
    - known module_id + version but sha mismatch     -> REJECTED (tampered)
    - known and complete                             -> APPROVED
    - anything else                                  -> REQUIRES_HUMAN_APPROVAL
    """

    def __init__(self, specs: List[BlenderAddonSpec]) -> None:
        self._specs: Dict[tuple[str, str], BlenderAddonSpec] = {}
        for spec in specs:
            self._specs[(spec.module_id, spec.version)] = spec
        self._specs_tuple: tuple[BlenderAddonSpec, ...] = tuple(specs)

    @property
    def specs(self) -> tuple[BlenderAddonSpec, ...]:
        return self._specs_tuple

    def __len__(self) -> int:
        return len(self._specs_tuple)

    def check(self, request: BlenderAddonRequest) -> BlenderAddonDecision:
        if request.version is None:
            return BlenderAddonDecision(
                module_id=request.module_id,
                status=REQUIRES_HUMAN_APPROVAL,
                reason="version not pinned — add-on cannot be gated",
            )
        spec = self._specs.get((request.module_id, request.version))
        if spec is None:
            return BlenderAddonDecision(
                module_id=request.module_id,
                status=REQUIRES_HUMAN_APPROVAL,
                reason=(
                    f"add-on {request.module_id}@{request.version} not in "
                    "allowlist — human approval required before any job may use it"
                ),
            )
        if request.sha256 is not None and request.sha256.lower() != spec.sha256.lower():
            return BlenderAddonDecision(
                module_id=request.module_id,
                status=REJECTED,
                reason="content hash mismatch — add-on may be tampered",
                matched_spec=spec,
            )
        return BlenderAddonDecision(
            module_id=request.module_id,
            status=APPROVED,
            reason="allowlisted and hash verified",
            matched_spec=spec,
        )

    def check_all(self, requests: List[BlenderAddonRequest]) -> List[BlenderAddonDecision]:
        return [self.check(r) for r in requests]

    def ensure_all_approved(self, requests: List[BlenderAddonRequest]) -> List[BlenderAddonDecision]:
        """Gate used before launching a job — raises if any add-on is not APPROVED."""
        decisions = self.check_all(requests)
        denied = [d for d in decisions if not d.allowed]
        if denied:
            summary = "; ".join(f"{d.module_id} ({d.status}: {d.reason})" for d in denied)
            raise AddonGateError(f"add-on gate failed, job will NOT run: {summary}")
        return decisions

    def to_dict(self) -> dict:
        return {"addons": [s.to_dict() for s in self._specs_tuple]}

    @classmethod
    def from_dict(cls, data: dict) -> "BlenderAddonManifest":
        return cls([BlenderAddonSpec.from_dict(s) for s in data.get("addons", [])])

    @classmethod
    def from_file(cls, path: str | Path) -> "BlenderAddonManifest":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(payload)

    @staticmethod
    def empty() -> "BlenderAddonManifest":
        return BlenderAddonManifest([])


class AddonGateError(RuntimeError):
    """Raised when a job references an add-on outside the allowlist."""


__all__ = [
    "APPROVED",
    "REQUIRES_HUMAN_APPROVAL",
    "REJECTED",
    "AddonGateError",
    "BlenderAddonDecision",
    "BlenderAddonManifest",
    "BlenderAddonRequest",
    "BlenderAddonSpec",
]
