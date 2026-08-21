"""
Stage G — Concurrent Edit & 3-Way Semantic Conflict Resolution Service (UI40).

Classifies changes between Base (starting revision), Local (base + local edits),
and Remote (latest server revision) into 8 conflict categories, auto-composes
safe merge candidates, and applies resolution commands.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from windagent_core.domain.video_production.screenplay_diff import (
    ScreenplayDiffEngine,
    EntityDiffSummary,
)
from windagent_core.errors.exceptions import ValidationError


class ConflictClassification(str, Enum):
    NO_CONFLICT = "NO_CONFLICT"
    LOCAL_ONLY_CHANGE = "LOCAL_ONLY_CHANGE"
    REMOTE_ONLY_CHANGE = "REMOTE_ONLY_CHANGE"
    NON_OVERLAPPING_MERGEABLE = "NON_OVERLAPPING_MERGEABLE"
    OVERLAPPING_REQUIRES_REVIEW = "OVERLAPPING_REQUIRES_REVIEW"
    ENTITY_DELETED = "ENTITY_DELETED"
    ORDER_CONFLICT = "ORDER_CONFLICT"
    UNSUPPORTED_UNKNOWN = "UNSUPPORTED_UNKNOWN"


class ResolutionStrategy(str, Enum):
    ACCEPT_LOCAL = "ACCEPT_LOCAL"
    ACCEPT_REMOTE = "ACCEPT_REMOTE"
    MERGE_CANDIDATE = "MERGE_CANDIDATE"
    CUSTOM = "CUSTOM"


class FieldConflict(BaseModel):
    field_name: str
    base_value: Any
    local_value: Any
    remote_value: Any
    is_overlapping: bool = False
    merged_value: Any = None


class EntityConflict(BaseModel):
    entity_type: str  # "SCREENPLAY" | "SCENE" | "DIALOGUE"
    entity_id: str
    classification: ConflictClassification
    title: str = ""
    field_conflicts: List[FieldConflict] = Field(default_factory=list)


class ThreeWayDiffResult(BaseModel):
    project_id: str
    base_revision_id: str
    latest_revision_id: str
    overall_classification: ConflictClassification
    can_auto_merge: bool = False
    entity_conflicts: List[EntityConflict] = Field(default_factory=list)
    auto_merged_payload: Optional[Dict[str, Any]] = None


class ConflictResolutionPayload(BaseModel):
    project_id: str
    base_revision_id: str
    latest_revision_id: str
    strategy: ResolutionStrategy
    custom_screenplay_payload: Optional[Dict[str, Any]] = None
    resolved_by: str = "user:editor"


class ThreeWayDiffEngine:
    """Computes entity & field 3-way semantic diff between Base, Local, and Remote screenplay models."""

    @staticmethod
    def compare(
        project_id: str,
        base_model: Dict[str, Any],
        local_model: Dict[str, Any],
        remote_model: Dict[str, Any],
    ) -> ThreeWayDiffResult:
        base_rev = base_model.get("revision_id", "base_rev")
        remote_rev = remote_model.get("revision_id", "remote_rev")

        diff_local = ScreenplayDiffEngine.compare(base_model, local_model)
        diff_remote = ScreenplayDiffEngine.compare(base_model, remote_model)

        local_entity_map: Dict[str, EntityDiffSummary] = {d.entity_id: d for d in diff_local.entity_diffs}
        remote_entity_map: Dict[str, EntityDiffSummary] = {d.entity_id: d for d in diff_remote.entity_diffs}

        all_entity_ids = list(dict.fromkeys(list(local_entity_map.keys()) + list(remote_entity_map.keys())))

        entity_conflicts: List[EntityConflict] = []
        has_overlap = False
        has_deleted_conflict = False
        has_order_conflict = False
        has_any_change = False

        for ent_id in all_entity_ids:
            l_diff = local_entity_map.get(ent_id)
            r_diff = remote_entity_map.get(ent_id)

            if l_diff and not r_diff:
                entity_conflicts.append(
                    EntityConflict(
                        entity_type=l_diff.entity_type,
                        entity_id=ent_id,
                        classification=ConflictClassification.LOCAL_ONLY_CHANGE,
                        title=l_diff.title,
                        field_conflicts=[
                            FieldConflict(field_name=fc.field_name, base_value=fc.old_value, local_value=fc.new_value, remote_value=fc.old_value, is_overlapping=False, merged_value=fc.new_value)
                            for fc in l_diff.changes
                        ],
                    )
                )
                has_any_change = True
            elif r_diff and not l_diff:
                entity_conflicts.append(
                    EntityConflict(
                        entity_type=r_diff.entity_type,
                        entity_id=ent_id,
                        classification=ConflictClassification.REMOTE_ONLY_CHANGE,
                        title=r_diff.title,
                        field_conflicts=[
                            FieldConflict(field_name=fc.field_name, base_value=fc.old_value, local_value=fc.old_value, remote_value=fc.new_value, is_overlapping=False, merged_value=fc.new_value)
                            for fc in r_diff.changes
                        ],
                    )
                )
                has_any_change = True
            elif l_diff and r_diff:
                has_any_change = True
                # Check for deletions
                if l_diff.change_type == "DELETED" or r_diff.change_type == "DELETED":
                    has_deleted_conflict = True
                    entity_conflicts.append(
                        EntityConflict(
                            entity_type=l_diff.entity_type,
                            entity_id=ent_id,
                            classification=ConflictClassification.ENTITY_DELETED,
                            title=l_diff.title or r_diff.title,
                        )
                    )
                    continue

                # Check field overlaps
                l_fields = {fc.field_name: fc for fc in l_diff.changes}
                r_fields = {fc.field_name: fc for fc in r_diff.changes}
                all_fields = list(dict.fromkeys(list(l_fields.keys()) + list(r_fields.keys())))

                f_conflicts: List[FieldConflict] = []
                ent_has_overlap = False

                for fname in all_fields:
                    lf = l_fields.get(fname)
                    rf = r_fields.get(fname)

                    if lf and not rf:
                        f_conflicts.append(
                            FieldConflict(field_name=fname, base_value=lf.old_value, local_value=lf.new_value, remote_value=lf.old_value, is_overlapping=False, merged_value=lf.new_value)
                        )
                    elif rf and not lf:
                        f_conflicts.append(
                            FieldConflict(field_name=fname, base_value=rf.old_value, local_value=rf.old_value, remote_value=rf.new_value, is_overlapping=False, merged_value=rf.new_value)
                        )
                    elif lf and rf:
                        # Same field modified
                        if fname == "order" and lf.new_value != rf.new_value:
                            has_order_conflict = True

                        if lf.new_value == rf.new_value:
                            # Both modified to identical value
                            f_conflicts.append(
                                FieldConflict(field_name=fname, base_value=lf.old_value, local_value=lf.new_value, remote_value=rf.new_value, is_overlapping=False, merged_value=lf.new_value)
                            )
                        else:
                            ent_has_overlap = True
                            has_overlap = True
                            f_conflicts.append(
                                FieldConflict(field_name=fname, base_value=lf.old_value, local_value=lf.new_value, remote_value=rf.new_value, is_overlapping=True, merged_value=None)
                            )

                classification = (
                    ConflictClassification.OVERLAPPING_REQUIRES_REVIEW
                    if ent_has_overlap
                    else (ConflictClassification.ORDER_CONFLICT if (fname == "order" and has_order_conflict) else ConflictClassification.NON_OVERLAPPING_MERGEABLE)
                )

                entity_conflicts.append(
                    EntityConflict(
                        entity_type=l_diff.entity_type,
                        entity_id=ent_id,
                        classification=classification,
                        title=l_diff.title,
                        field_conflicts=f_conflicts,
                    )
                )

        has_local = any(ec.classification == ConflictClassification.LOCAL_ONLY_CHANGE for ec in entity_conflicts)
        has_remote = any(ec.classification == ConflictClassification.REMOTE_ONLY_CHANGE for ec in entity_conflicts)

        if not has_any_change:
            overall = ConflictClassification.NO_CONFLICT
        elif has_deleted_conflict:
            overall = ConflictClassification.ENTITY_DELETED
        elif has_order_conflict:
            overall = ConflictClassification.ORDER_CONFLICT
        elif has_overlap:
            overall = ConflictClassification.OVERLAPPING_REQUIRES_REVIEW
        elif has_local and not has_remote:
            overall = ConflictClassification.LOCAL_ONLY_CHANGE
        elif has_remote and not has_local:
            overall = ConflictClassification.REMOTE_ONLY_CHANGE
        else:
            overall = ConflictClassification.NON_OVERLAPPING_MERGEABLE

        can_auto_merge = overall in [
            ConflictClassification.NO_CONFLICT,
            ConflictClassification.LOCAL_ONLY_CHANGE,
            ConflictClassification.REMOTE_ONLY_CHANGE,
            ConflictClassification.NON_OVERLAPPING_MERGEABLE,
        ]

        auto_merged_payload: Optional[Dict[str, Any]] = None
        if can_auto_merge:
            auto_merged_payload = ThreeWayDiffEngine._compose_auto_merge_payload(base_model, local_model, remote_model, entity_conflicts)

        return ThreeWayDiffResult(
            project_id=project_id,
            base_revision_id=base_rev,
            latest_revision_id=remote_rev,
            overall_classification=overall,
            can_auto_merge=can_auto_merge,
            entity_conflicts=entity_conflicts,
            auto_merged_payload=auto_merged_payload,
        )

    @staticmethod
    def _compose_auto_merge_payload(
        base_model: Dict[str, Any],
        local_model: Dict[str, Any],
        remote_model: Dict[str, Any],
        entity_conflicts: List[EntityConflict],
    ) -> Dict[str, Any]:
        """Composes merged screenplay dictionary payload starting from remote base and applying local non-overlapping edits."""
        merged = json.loads(json.dumps(remote_model))

        for ec in entity_conflicts:
            if ec.classification == ConflictClassification.LOCAL_ONLY_CHANGE:
                # Apply local only scene/dialogue edit to merged
                if ec.entity_type == "SCENE":
                    local_scene = next((s for s in local_model.get("scenes", []) if s["scene_id"] == ec.entity_id), None)
                    if local_scene:
                        existing_idx = next((i for i, s in enumerate(merged.get("scenes", [])) if s["scene_id"] == ec.entity_id), None)
                        if existing_idx is not None:
                            merged["scenes"][existing_idx] = local_scene
                        else:
                            merged.setdefault("scenes", []).append(local_scene)

                elif ec.entity_type == "DIALOGUE":
                    local_dlg = None
                    sc_id = None
                    for sc in local_model.get("scenes", []):
                        for d in sc.get("dialogue_lines", []):
                            if d["dialogue_id"] == ec.entity_id:
                                local_dlg = d
                                sc_id = sc["scene_id"]
                                break
                    if local_dlg and sc_id:
                        for sc in merged.get("scenes", []):
                            if sc["scene_id"] == sc_id:
                                d_idx = next((i for i, d in enumerate(sc.get("dialogue_lines", [])) if d["dialogue_id"] == ec.entity_id), None)
                                if d_idx is not None:
                                    sc["dialogue_lines"][d_idx] = local_dlg
                                else:
                                    sc.setdefault("dialogue_lines", []).append(local_dlg)

            elif ec.classification == ConflictClassification.NON_OVERLAPPING_MERGEABLE:
                # Apply non-overlapping field changes
                for fc in ec.field_conflicts:
                    if fc.merged_value is not None:
                        if ec.entity_type == "SCREENPLAY":
                            merged[fc.field_name] = fc.merged_value
                        elif ec.entity_type == "SCENE":
                            for sc in merged.get("scenes", []):
                                if sc["scene_id"] == ec.entity_id:
                                    sc[fc.field_name] = fc.merged_value
                        elif ec.entity_type == "DIALOGUE":
                            for sc in merged.get("scenes", []):
                                for d in sc.get("dialogue_lines", []):
                                    if d["dialogue_id"] == ec.entity_id:
                                        d[fc.field_name] = fc.merged_value

        return merged


class ConflictResolutionService:
    """Service to handle 3-way conflict diffing and resolution execution."""

    _in_memory_revisions: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def register_revision(cls, revision_id: str, screenplay_payload: Dict[str, Any]) -> None:
        cls._in_memory_revisions[revision_id] = screenplay_payload

    @classmethod
    def clear_store(cls) -> None:
        cls._in_memory_revisions.clear()

    @classmethod
    def compute_three_way_diff(
        cls,
        project_id: str,
        base_revision_id: str,
        local_payload: Dict[str, Any],
        latest_revision_id: str,
        latest_payload: Optional[Dict[str, Any]] = None,
    ) -> ThreeWayDiffResult:
        base_payload = cls._in_memory_revisions.get(base_revision_id, {"revision_id": base_revision_id, "title": "Base Screenplay", "scenes": []})
        remote_payload = latest_payload or cls._in_memory_revisions.get(
            latest_revision_id, {"revision_id": latest_revision_id, "title": "Remote Screenplay", "scenes": []}
        )

        return ThreeWayDiffEngine.compare(
            project_id=project_id,
            base_model=base_payload,
            local_model=local_payload,
            remote_model=remote_payload,
        )

    @classmethod
    def resolve_conflict(cls, payload: ConflictResolutionPayload) -> Dict[str, Any]:
        """Resolves conflict and issues a new revision on top of latest base."""
        diff_result = cls.compute_three_way_diff(
            project_id=payload.project_id,
            base_revision_id=payload.base_revision_id,
            local_payload=payload.custom_screenplay_payload or {},
            latest_revision_id=payload.latest_revision_id,
        )

        if payload.strategy == ResolutionStrategy.MERGE_CANDIDATE:
            if not diff_result.can_auto_merge or not diff_result.auto_merged_payload:
                raise ValidationError("Cannot auto-merge candidate due to overlapping field conflicts or entity deletions.")
            resolved_content = diff_result.auto_merged_payload
        elif payload.strategy == ResolutionStrategy.ACCEPT_LOCAL:
            resolved_content = payload.custom_screenplay_payload or {}
        elif payload.strategy == ResolutionStrategy.ACCEPT_REMOTE:
            resolved_content = cls._in_memory_revisions.get(payload.latest_revision_id, {})
        elif payload.strategy == ResolutionStrategy.CUSTOM:
            if not payload.custom_screenplay_payload:
                raise ValidationError("CUSTOM strategy requires custom_screenplay_payload.")
            resolved_content = payload.custom_screenplay_payload
        else:
            raise ValidationError(f"Unknown resolution strategy: {payload.strategy}")

        new_rev_id = f"rev_resolved_{payload.latest_revision_id}_{len(cls._in_memory_revisions) + 1}"
        resolved_content["revision_id"] = new_rev_id
        cls.register_revision(new_rev_id, resolved_content)

        return {
            "project_id": payload.project_id,
            "resulting_revision_id": new_rev_id,
            "base_revision_id": payload.base_revision_id,
            "latest_revision_id": payload.latest_revision_id,
            "strategy": payload.strategy.value,
            "resolved_by": payload.resolved_by,
            "resolved_payload": resolved_content,
        }
