"""
ContinuityLedgerService (Phase 10) — turns a package + shot graph into a
traceable, reviewable continuity ledger (plan 03 §17-§21).

Responsibilities:
- build the INITIAL continuity state from screenplay/entity/style bibles and
  APPROVED references (plan §19.1); missing required fields become issues,
  immutable facts are distinguished from changeable state;
- walk shots in deterministic topological order (plan §19.2): outgoing state
  of a predecessor becomes the incoming state of its dependents; multi-scene
  boundaries reset location/weather/time per the new scene facts while
  identity continues across scenes;
- record allowed + planned changes per shot; changes outside the allowed set,
  unexplained prop changes, identity/reference hash mismatches and
  180-degree camera-side flips are BLOCKING (validator fail-closed);
- parallel shots planning the same canonical field raise a conflict issue
  until a merge rule exists (plan §19.2);
- human overrides are appended as auditable records (actor, reason, target
  revision, timestamp) and never rewrite retroactive evidence (plan §19.3);
- produce a deterministic, versioned ledger hash tied to the source
  graph/plan/package hashes.

The service is fully deterministic and never calls a provider.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from windagent_core.domain.video_production.continuity import (
    ContinuityAssertion,
    ContinuityChange,
    ContinuityFieldState,
    ContinuityLedger,
    ContinuityLedgerEntry,
    ContinuityLedgerValidator,
    HumanContinuityOverride,
    compute_ledger_hash,
)
from windagent_core.domain.video_production.enums import (
    CameraSide,
    ContinuityFieldSource,
)
from windagent_core.domain.video_production.ids import ContinuityLedgerId
from windagent_core.domain.video_production.package import VideoProductionPackage
from windagent_core.domain.video_production.shot import Shot
from windagent_core.domain.video_production.validation import (
    VideoProductionPackageValidator,
)

from windagent_intelligence.video.continuity.models import ContinuityLedgerReceipt
from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.shot_planner.models import ShotGraphReceipt

# Wardrobe / prop keywords scanned in screenplay action text to derive the
# fields a shot is ALLOWED to change (plan §19.2: change needs a screenplay
# fact or an explicit director decision; props need an action).
_WARDROBE_KEYWORDS = (
    "change", "changes", "changed", "put on", "takes off", "take off",
    "wears", "wear", "remove", "removes", "jacket", "coat", "dress",
    "costume", "clothing", "outfit", "hat", "shoes",
)
_PROP_KEYWORDS = (
    "takes", "take", "grab", "grabs", "holds", "hold", "picks up",
    "picks", "gives", "passes", "hands", "drops", "possesses",
)


class ContinuityLedgerService:
    """Deterministic continuity ledger builder over a package + shot graph."""

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        validator: Optional[ContinuityLedgerValidator] = None,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.validator = validator or ContinuityLedgerValidator(
            id_factory=self.id_factory,
        )

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def build(
        self,
        package: VideoProductionPackage,
        graph_receipt: ShotGraphReceipt,
        *,
        planned_changes: Optional[Dict[str, List[ContinuityChange]]] = None,
        allowed_changes: Optional[Dict[str, List[str]]] = None,
        overrides: Optional[List[HumanContinuityOverride]] = None,
        require_locked: bool = True,
    ) -> ContinuityLedgerReceipt:
        """Build the traceable continuity ledger for a revision.

        Raises `ValidationFailureError` for an invalid package or a graph
        with no shots. Blocking continuity defects are RETURNED as issues on
        the receipt (the ledger is a review artifact — it records defects
        instead of raising) so reviewers and workflows can resolve them via
        audited overrides or screenplay revisions.
        """
        package_issues = VideoProductionPackageValidator.validate(package)
        if package_issues:
            raise ValidationFailureError(
                "Cannot build a continuity ledger from an invalid package.",
                details={
                    "issue_count": len(package_issues),
                    "first": [i.code for i in package_issues[:5]],
                },
            )
        graph = graph_receipt.graph
        if not graph.shots:
            raise ValidationFailureError(
                "Continuity ledger requires a shot graph with at least one shot.",
            )
        if require_locked and not graph_receipt.source_plan_hash:
            # The plan lock is enforced upstream (Phase 8/9); if no plan hash
            # is present the ledger cannot be traced to a locked revision.
            raise ValidationFailureError(
                "Continuity ledger requires a traceable source plan hash.",
                details={"source_plan_hash": graph_receipt.source_plan_hash},
            )

        planned_changes = planned_changes or {}
        allowed_changes = allowed_changes or {}
        overrides = overrides or []

        # 1. Initial state from screenplay / bibles / approved references.
        initial = self._initial_state(package)

        # 2. Walk shots in deterministic topological order, threading state.
        scenes_by_id = _scenes_by_id(package)
        specs_by_shot = {str(s.shot_id): s for s in graph_receipt.specifications}

        current = dict(initial)
        entries: List[ContinuityLedgerEntry] = []
        ordered_shots = _ordered_shots(graph)
        override_by_shot: Dict[str, List[HumanContinuityOverride]] = {}
        for ov in overrides:
            # Overrides without a target shot apply from the FIRST shot of the
            # revision (deterministic policy, documented in the override doc).
            key = (
                str(ov.applied_at_shot_id)
                if ov.applied_at_shot_id
                else str(ordered_shots[0].shot_id)
            )
            override_by_shot.setdefault(key, []).append(ov)

        for shot in ordered_shots:
            scene = scenes_by_id.get(str(shot.scene_id))
            if scene is not None and _is_scene_boundary(entries, shot):
                current = self._scene_boundary_state(current, package, scene)

            spec = specs_by_shot.get(str(shot.shot_id))
            entry = self._build_entry(
                shot,
                current,
                package,
                scene,
                spec.camera.camera_side if spec else None,
                planned_changes.get(str(shot.shot_id), []),
                allowed_changes.get(str(shot.shot_id), []),
                override_by_shot.get(str(shot.shot_id), []),
            )
            entries.append(entry)
            current = dict(entry.outgoing_state)

        ledger = ContinuityLedger(
            ledger_id=ContinuityLedgerId(
                self.id_factory.continuity_ledger_id(
                    str(package.project_id), str(package.revision_id)
                )
            ),
            project_id=package.project_id,
            revision_id=package.revision_id,
            entries=entries,
            overrides=list(overrides),
            ledger_version="1.0.0",
        )

        # 3. Deterministic rule validation (blocking defects recorded).
        issues = self.validator.validate(ledger, graph=graph)
        ledger = ledger.model_copy(update={"issues": issues})

        # 4. Deterministic ledger hash tied to source hashes.
        ledger_hash = compute_ledger_hash(
            project_id=package.project_id,
            revision_id=package.revision_id,
            ledger_payload=json.loads(ledger.model_dump_json()),
            ledger_version=ledger.ledger_version,
            source_graph_hash=graph_receipt.graph_hash,
            source_plan_hash=graph_receipt.source_plan_hash,
            source_package_hash=graph_receipt.source_package_hash,
        )
        ledger = ledger.model_copy(update={"ledger_hash": ledger_hash})

        return ContinuityLedgerReceipt(
            ledger=ledger,
            issues=issues,
            ledger_hash=ledger_hash,
            source_graph_hash=graph_receipt.graph_hash,
            source_plan_hash=graph_receipt.source_plan_hash,
            source_package_hash=graph_receipt.source_package_hash,
            ledger_version=ledger.ledger_version,
        )

    # ------------------------------------------------------------------
    # Initial state (plan §19.1)
    # ------------------------------------------------------------------
    def _initial_state(self, package: VideoProductionPackage) -> Dict[str, ContinuityFieldState]:
        state: Dict[str, ContinuityFieldState] = {}
        # Character identity (approved portrait reference) + appearance.
        for char in package.characters:
            portrait = str(char.portrait_asset_ids[0]) if char.portrait_asset_ids else ""
            state[f"identity:{char.character_id}"] = ContinuityFieldState(
                field=f"identity:{char.character_id}",
                value=portrait,
                source=ContinuityFieldSource.APPROVED_REFERENCE,
            )
            for trait, value in (char.visual_traits or {}).items():
                state[f"appearance:{char.character_id}:{trait}"] = ContinuityFieldState(
                    field=f"appearance:{char.character_id}:{trait}",
                    value=value,
                    source=ContinuityFieldSource.BIBLE_FACT,
                )
            if char.costume_descriptions:
                state[f"appearance:{char.character_id}:clothing"] = ContinuityFieldState(
                    field=f"appearance:{char.character_id}:clothing",
                    value=char.costume_descriptions[0],
                    source=ContinuityFieldSource.BIBLE_FACT,
                )
        # Props: possession + state from bibles.
        for prop in package.props:
            state[f"prop:{prop.prop_id}:possessor"] = ContinuityFieldState(
                field=f"prop:{prop.prop_id}:possessor",
                value=None,
                source=ContinuityFieldSource.BIBLE_FACT,
            )
            state[f"prop:{prop.prop_id}:state"] = ContinuityFieldState(
                field=f"prop:{prop.prop_id}:state",
                value="intact",
                source=ContinuityFieldSource.BIBLE_FACT,
            )
        # Approved reference hashes (identity/reference binding).
        for asset in package.assets:
            state[f"reference:{asset.asset_id}"] = ContinuityFieldState(
                field=f"reference:{asset.asset_id}",
                value=asset.content_hash,
                source=ContinuityFieldSource.APPROVED_REFERENCE,
            )
        return state

    # ------------------------------------------------------------------
    # Scene boundary (plan §19.2 multi-scene policy)
    # ------------------------------------------------------------------
    def _scene_boundary_state(
        self,
        current: Dict[str, ContinuityFieldState],
        package: VideoProductionPackage,
        scene,
    ) -> Dict[str, ContinuityFieldState]:
        """Reset location/weather/time to the new scene facts; identity continues.

        Characters and props persist across scenes (continuation); the
        location's lighting/weather/time are re-derived from the new scene +
        location bible. Camera side resets to NEUTRAL (re-establish geography).
        """
        next_state = dict(current)
        location_by_id = {str(loc.location_id): loc for loc in package.locations}
        loc = location_by_id.get(str(scene.location_id))
        if loc is not None:
            next_state[f"location:{loc.location_id}:lighting"] = ContinuityFieldState(
                field=f"location:{loc.location_id}:lighting",
                value=loc.lighting_profile or "",
                source=ContinuityFieldSource.BIBLE_FACT,
            )
            next_state[f"location:{loc.location_id}:atmosphere"] = ContinuityFieldState(
                field=f"location:{loc.location_id}:atmosphere",
                value=", ".join(loc.atmosphere_tags),
                source=ContinuityFieldSource.BIBLE_FACT,
            )
        if scene.time_of_day is not None:
            next_state[f"time:{scene.scene_id}"] = ContinuityFieldState(
                field=f"time:{scene.scene_id}",
                value=scene.time_of_day.value,
                source=ContinuityFieldSource.SCREENPLAY_FACT,
            )
        next_state["camera_side"] = ContinuityFieldState(
            field="camera_side",
            value=CameraSide.NEUTRAL.value,
            source=ContinuityFieldSource.DIRECTOR_DECISION,
        )
        return next_state

    # ------------------------------------------------------------------
    # Per-shot entry (plan §18, §19.2)
    # ------------------------------------------------------------------
    def _build_entry(
        self,
        shot: Shot,
        current: Dict[str, ContinuityFieldState],
        package: VideoProductionPackage,
        scene,
        camera_side,
        planned: List[ContinuityChange],
        allowed_override: List[str],
        shot_overrides: List[HumanContinuityOverride],
    ) -> ContinuityLedgerEntry:
        # incoming = the threaded predecessor state (NOT the current shot's own
        # camera decision) so the 180-degree rule can compare across shots.
        incoming = dict(current)

        required = self._required_state(shot, package)
        allowed = self._allowed_changes(shot, scene, package, allowed_override)

        # Apply human overrides (audit records — appended, never retroactive).
        planned = list(planned)
        for ov in shot_overrides:
            planned = [c for c in planned if c.field != ov.field]
            planned.append(
                ContinuityChange(
                    field=ov.field,
                    before=ov.before,
                    after=ov.after,
                    source=ContinuityFieldSource.HUMAN_OVERRIDE,
                    reason=ov.reason,
                )
            )

        # The shot's own camera decision becomes a PLANNED CHANGE so the flip
        # from the threaded predecessor side is visible to the validator
        # (CAMERA_SIDE_VIOLATION fires only when incoming != outgoing).
        if camera_side is not None:
            threaded = incoming.get("camera_side")
            before = threaded.value if threaded else None
            after = camera_side.value
            if before != after:
                planned.append(
                    ContinuityChange(
                        field="camera_side",
                        before=before,
                        after=after,
                        source=ContinuityFieldSource.DIRECTOR_DECISION,
                        reason="camera plan for shot",
                    )
                )

        outgoing = dict(incoming)
        for change in planned:
            outgoing[change.field] = ContinuityFieldState(
                field=change.field,
                value=change.after,
                source=change.source,
            )

        assertions = self._continuity_assertions(shot, required, incoming)
        return ContinuityLedgerEntry(
            shot_id=shot.shot_id,
            scene_id=shot.scene_id,
            incoming_state=incoming,
            required_state=required,
            allowed_changes=sorted(set(allowed)),
            planned_changes=planned,
            outgoing_state=outgoing,
            continuity_assertions=assertions,
        )

    def _required_state(
        self, shot: Shot, package: VideoProductionPackage
    ) -> Dict[str, ContinuityFieldState]:
        required: Dict[str, ContinuityFieldState] = {}
        for asset_id in shot.reference_asset_ids:
            char = next(
                (c for c in package.characters if asset_id in c.portrait_asset_ids),
                None,
            )
            if char is not None:
                required[f"identity:{char.character_id}"] = ContinuityFieldState(
                    field=f"identity:{char.character_id}",
                    value=str(asset_id),
                    source=ContinuityFieldSource.APPROVED_REFERENCE,
                )
            asset = next(
                (a for a in package.assets if a.asset_id == asset_id), None
            )
            if asset is not None:
                required[f"reference:{asset_id}"] = ContinuityFieldState(
                    field=f"reference:{asset_id}",
                    value=asset.content_hash,
                    source=ContinuityFieldSource.APPROVED_REFERENCE,
                )
        return required

    def _allowed_changes(
        self,
        shot: Shot,
        scene,
        package: VideoProductionPackage,
        override: List[str],
    ) -> List[str]:
        if override:
            return list(override)
        allowed = ["camera_side"]
        # Emotion changes are director decisions.
        for char_id in _scene_character_ids(scene):
            allowed.append(f"appearance:{char_id}:emotion")
        action = " ".join(
            [
                scene.action_description if scene else "",
                shot.framing_description,
                " ".join(d.text for d in _shot_dialogue(shot, package)),
            ]
        ).lower()
        for char_id in _scene_character_ids(scene):
            if any(k in action for k in _WARDROBE_KEYWORDS):
                allowed.append(f"appearance:{char_id}:clothing")
        for prop in package.props:
            if any(k in action for k in _PROP_KEYWORDS):
                allowed.append(f"prop:{prop.prop_id}:possessor")
                allowed.append(f"prop:{prop.prop_id}:state")
        return allowed

    def _continuity_assertions(
        self,
        shot: Shot,
        required: Dict[str, ContinuityFieldState],
        incoming: Dict[str, ContinuityFieldState],
    ) -> List[ContinuityAssertion]:
        assertions: List[ContinuityAssertion] = []
        for field, state in required.items():
            incoming_value = incoming.get(field).value if incoming.get(field) else None
            if state.value is None or state.value == "":
                assertions.append(
                    ContinuityAssertion(
                        field=field,
                        expected=None,
                        source=state.source,
                        message="required state is missing",
                    )
                )
            elif incoming_value != state.value:
                assertions.append(
                    ContinuityAssertion(
                        field=field,
                        expected=state.value,
                        source=state.source,
                        message="incoming state does not match the approved reference",
                    )
                )
        return assertions


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------
def _scenes_by_id(package: VideoProductionPackage) -> Dict[str, object]:
    if package.screenplay is None:
        return {}
    return {str(s.scene_id): s for s in package.screenplay.scenes}


def _ordered_shots(graph) -> List[Shot]:
    ids = {str(s.shot_id): s for s in graph.shots}
    return [ids[str(sid)] for sid in graph.topological_order()]


def _is_scene_boundary(entries: List[ContinuityLedgerEntry], shot: Shot) -> bool:
    return not entries or str(entries[-1].scene_id) != str(shot.scene_id)


def _scene_character_ids(scene) -> List[str]:
    if scene is None:
        return []
    return [str(cid) for cid in getattr(scene, "character_ids", [])]


def _shot_dialogue(shot: Shot, package: VideoProductionPackage) -> list:
    dialogue_by_id = {str(d.dialogue_id): d for d in package.dialogue}
    return [
        dialogue_by_id[str(line_id)]
        for line_id in shot.dialogue_line_ids
        if str(line_id) in dialogue_by_id
    ]


__all__ = ["ContinuityLedgerService"]
