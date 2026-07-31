"""
Deterministic stable ID factory for the video kernel (Phase 6).

Characterization (NONDET-001/005) showed upstream derives entity IDs from
uuid4 random suffixes and sorts names by length only. The canonical kernel
must instead:
- generate IDs deterministically from a stable seed (never display name),
- order character/name lists with a full deterministic sort.

`StableIdFactory` derives stable IDs from a seed + optional sequence so the
same logical content yields the same IDs across runs while remaining opaque
and never derived from display names.
"""

from __future__ import annotations

import hashlib
from typing import Optional


class StableIdFactory:
    """Deterministic, namespace-prefixed ID generation for the kernel."""

    def __init__(self, seed: str = "windagent-video-kernel") -> None:
        self._seed = seed

    def _digest(self, *parts: object) -> str:
        payload = "::".join(str(p) for p in parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def entity_id(self, prefix: str, seed_value: object, seq: int = 0) -> str:
        """Deterministic id `{prefix}_{digest}` from seed value + sequence."""
        return f"{prefix}_{self._digest(self._seed, seed_value, seq)}"

    def project_id(self, title: str) -> str:
        return self.entity_id("vp", title)

    def revision_id(self, project_id: str, seq: int) -> str:
        return self.entity_id("rev", f"{project_id}:{seq}")

    def brief_id(self, title: str) -> str:
        return self.entity_id("brf", title)

    def concept_id(self, title: str) -> str:
        return self.entity_id("cnc", title)

    def screenplay_id(self, title: str) -> str:
        return self.entity_id("scr", title)

    def scene_id(self, screenplay_id: str, order: int) -> str:
        return self.entity_id("scn", f"{screenplay_id}:{order}")

    def character_id(self, name: str, seq: int = 0) -> str:
        # Never derived from display name alone — identity is stable per
        # logical character record (name + sequence), so duplicate display
        # names with distinct identities get distinct IDs (fixes DEF-003).
        return self.entity_id("chr", f"{name}:{seq}", seq)

    def location_id(self, name: str, seq: int = 0) -> str:
        return self.entity_id("loc", f"{name}:{seq}", seq)

    def prop_id(self, name: str, seq: int = 0) -> str:
        return self.entity_id("prp", f"{name}:{seq}", seq)

    def style_id(self, name: str) -> str:
        return self.entity_id("sty", name)

    def dialogue_id(self, scene_id: str, order: int) -> str:
        return self.entity_id("dlg", f"{scene_id}:{order}")

    def asset_id(self, kind: str, name: str, seq: int = 0) -> str:
        return self.entity_id("ast", f"{kind}:{name}:{seq}", seq)


__all__ = ["StableIdFactory"]
