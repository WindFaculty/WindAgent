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

    # ------------------------------------------------------------------
    # Director layer (Phase 8) IDs
    # ------------------------------------------------------------------
    def cinematic_plan_id(self, project_id: str, revision_id: str) -> str:
        return self.entity_id("plan", f"{project_id}:{revision_id}")

    def shot_id(self, scene_id: str, order: int) -> str:
        return self.entity_id("sht", f"{scene_id}:{order}")

    def directorial_issue_id(self, seed_value: object, seq: int = 0) -> str:
        return self.entity_id("dri", seed_value, seq)

    def proposal_id(self, seed_value: object, seq: int = 0) -> str:
        return self.entity_id("prp_r", seed_value, seq)

    # ------------------------------------------------------------------
    # Shot graph layer (Phase 9) IDs
    # ------------------------------------------------------------------
    def shot_dependency_id(
        self, kind: str, from_shot_id: object, to_shot_id: object, seq: int = 0
    ) -> str:
        """Deterministic id for a typed dependency edge."""
        return self.entity_id("dep", f"{kind}:{from_shot_id}:{to_shot_id}", seq)

    def shot_spec_id(self, shot_id: object) -> str:
        """Deterministic id for a shot specification (one-to-one with shot)."""
        return self.entity_id("sps", shot_id)

    def shot_graph_issue_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for a shot-graph / camera issue."""
        return self.entity_id("sgi", seed_value, seq)

    # ------------------------------------------------------------------
    # Continuity ledger layer (Phase 10) IDs
    # ------------------------------------------------------------------
    def continuity_ledger_id(self, project_id: str, revision_id: str) -> str:
        """Deterministic id for the continuity ledger of a revision."""
        return self.entity_id("ledger", f"{project_id}:{revision_id}")

    def continuity_issue_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for a continuity issue."""
        return self.entity_id("ci", seed_value, seq)

    def continuity_override_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for a human continuity override."""
        return self.entity_id("cov", seed_value, seq)

    # ------------------------------------------------------------------
    # Reference binding + prompt compiler layer (Phase 11) IDs
    # ------------------------------------------------------------------
    def reference_binding_id(
        self, shot_id: object, asset_id: object, role: object, seq: int = 0
    ) -> str:
        """Deterministic id for a shot->asset binding edge."""
        return self.entity_id("rb", f"{shot_id}:{asset_id}:{role}", seq)

    def reference_binding_plan_id(self, project_id: str, revision_id: str) -> str:
        """Deterministic id for the reference binding plan of a revision."""
        return self.entity_id("rbp", f"{project_id}:{revision_id}")

    def reference_binding_issue_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for a reference binding issue."""
        return self.entity_id("rbi", seed_value, seq)

    def prompt_block_id(self, shot_id: object, block_type: object) -> str:
        """Deterministic id for a prompt block (one per shot+type)."""
        return self.entity_id("pb", f"{shot_id}:{block_type}")

    def compiled_prompt_id(self, shot_id: object) -> str:
        """Deterministic id for a compiled prompt (one per shot)."""
        return self.entity_id("cp", shot_id)

    def flow_spec_id(self, shot_id: object) -> str:
        """Deterministic id for a flow generation specification (one per shot)."""
        return self.entity_id("fs", shot_id)

    def prompt_issue_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for a prompt compiler issue."""
        return self.entity_id("pci", seed_value, seq)

    def security_finding_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for a prompt security finding."""
        return self.entity_id("psf", seed_value, seq)

    def generation_request_id(
        self, project_id: str, revision_id: str, shot_id: object
    ) -> str:
        """Deterministic id for a compiled GenerationRequest (one per shot)."""
        return self.entity_id("req", f"{project_id}:{revision_id}:{shot_id}")


__all__ = ["StableIdFactory"]
