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

    def set_dressing_plan_id(self, scene_id: object) -> str:
        """Deterministic id for a compiled set-dressing scene plan (VP3D Phase 12)."""
        return self.entity_id("sd", str(scene_id))

    def spatial_finding_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for a spatial finding (VP3D Phase 12)."""
        return self.entity_id("sf", seed_value, seq)

    # ------------------------------------------------------------------
    # Camera compiler layer (Phase 13) IDs
    # ------------------------------------------------------------------
    def camera_rig_plan_id(self, shot_id: object) -> str:
        """Deterministic id for a compiled camera rig plan (VP3D Phase 13)."""
        return self.entity_id("crp", str(shot_id))

    def camera_finding_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for a camera finding (VP3D Phase 13)."""
        return self.entity_id("cf", seed_value, seq)

    def camera_override_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for a manual camera override (VP3D Phase 13)."""
        return self.entity_id("covr", seed_value, seq)

    def camera_path_manifest_id(self, shot_id: object) -> str:
        """Deterministic id for a camera path/playblast manifest (VP3D Phase 13)."""
        return self.entity_id("cpm", str(shot_id))

    # ------------------------------------------------------------------
    # Lighting compiler layer (Phase 14) IDs
    # ------------------------------------------------------------------
    def light_rig_plan_id(self, shot_id: object) -> str:
        """Deterministic id for a compiled light rig plan (VP3D Phase 14)."""
        return self.entity_id("lrp", str(shot_id))

    def lighting_finding_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for a lighting finding (VP3D Phase 14)."""
        return self.entity_id("lf", seed_value, seq)

    def light_override_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for a bounded lighting override (VP3D Phase 14)."""
        return self.entity_id("lovr", seed_value, seq)

    def lighting_contact_sheet_id(self, shot_id: object) -> str:
        """Deterministic id for a lighting contact sheet manifest (VP3D Phase 14)."""
        return self.entity_id("lcs", str(shot_id))

    # ------------------------------------------------------------------
    # Animation compiler layer (Phase 15) IDs
    # ------------------------------------------------------------------
    def animation_clip_id(self, action: object, emotion: object,
                          version: str) -> str:
        """Deterministic id for a library clip entry (VP3D Phase 15).

        Content-based: same action+emotion+version -> same clip id, so the
        library is deterministic and never keyed by display name.
        """
        return self.entity_id("acl", f"{action}:{emotion}:{version}")

    def animation_track_id(self, actor_id: object,
                           start_frame: object, seq: int = 0) -> str:
        """Deterministic id for a compiled animation track (VP3D Phase 15)."""
        return self.entity_id("atk", f"{actor_id}:{start_frame}", seq)

    def animation_finding_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for an animation finding (VP3D Phase 15)."""
        return self.entity_id("anf", seed_value, seq)

    def retarget_receipt_id(self, clip_id: object) -> str:
        """Deterministic id for a clip retarget receipt (VP3D Phase 15)."""
        return self.entity_id("rtr", str(clip_id))

    def episode_pin_id(self, episode_id: object, actor_id: object) -> str:
        """Deterministic id for an episode clip-revision pin (VP3D Phase 15)."""
        return self.entity_id("epn", f"{episode_id}:{actor_id}")

    def blend_transition_id(self, actor_id: object,
                            boundary_frame: object) -> str:
        """Deterministic id for a blend transition (VP3D Phase 15)."""
        return self.entity_id("bln", f"{actor_id}:{boundary_frame}")

    # ------------------------------------------------------------------
    # Procedural animation layer (Phase 16) IDs
    # ------------------------------------------------------------------
    def procedural_recipe_id(self, track_id: object) -> str:
        """Deterministic id for a procedural recipe (VP3D Phase 16)."""
        return self.entity_id("prc", str(track_id))

    def procedural_layer_id(self, kind: object, seed_value: object,
                            seq: int = 0) -> str:
        """Deterministic id for one procedural layer spec (VP3D Phase 16)."""
        return self.entity_id("plr", f"{kind}:{seed_value}", seq)

    def procedural_finding_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for a procedural finding (VP3D Phase 16)."""
        return self.entity_id("pfd", seed_value, seq)

    def baked_action_id(self, track_id: object) -> str:
        """Deterministic id for a baked derived action (VP3D Phase 16)."""
        return self.entity_id("bka", str(track_id))

    # ------------------------------------------------------------------
    # AI motion adapter (Phase 17) IDs
    # ------------------------------------------------------------------
    def motion_capability_id(self, provider: object, model: object,
                             version: object) -> str:
        """Deterministic id for a capability contract (VP3D Phase 17)."""
        return self.entity_id("moc", f"{provider}:{model}:{version}")

    def motion_request_id(self, actor_id: object,
                          prompt_hash: object, seed: object) -> str:
        """Deterministic id for a generation request (VP3D Phase 17)."""
        return self.entity_id("mor", f"{actor_id}:{prompt_hash}:{seed}")

    def raw_motion_artifact_id(self, request_id: object,
                               seed: object) -> str:
        """Deterministic id for a raw artifact (VP3D Phase 17)."""
        return self.entity_id("rma", f"{request_id}:{seed}")

    def motion_candidate_id(self, request_id: object,
                            seed: object) -> str:
        """Deterministic id for one candidate (VP3D Phase 17)."""
        return self.entity_id("mcd", f"{request_id}:{seed}")

    def motion_finding_id(self, seed_value: object, seq: int = 0) -> str:
        """Deterministic id for an AI motion finding (VP3D Phase 17)."""
        return self.entity_id("mfd", seed_value, seq)

    def skeleton_remap_receipt_id(self, artifact_id: object) -> str:
        """Deterministic id for a skeleton remap receipt (VP3D Phase 17)."""
        return self.entity_id("smr", str(artifact_id))


__all__ = ["StableIdFactory"]
