"""
Screenplay Semantic Diff Engine (Stage C — UI12 & UI15).

Calculates entity-based semantic differences between two screenplay revisions (base vs target).
Distinguishes between entity reordering (moves) vs actual additions/deletions, preventing false delete+add reports.
"""

from __future__ import annotations

from typing import Any, Dict, List
from pydantic import BaseModel, Field


class FieldChange(BaseModel):
    field_name: str
    old_value: Any
    new_value: Any


class EntityDiffSummary(BaseModel):
    entity_type: str  # "SCREENPLAY" | "SCENE" | "DIALOGUE" | "CHARACTER" | "LOCATION"
    entity_id: str
    change_type: str  # "ADDED" | "DELETED" | "MODIFIED" | "MOVED" | "UNCHANGED"
    title: str = ""
    changes: List[FieldChange] = Field(default_factory=list)


class ScreenplayDiffResult(BaseModel):
    base_revision_id: str
    target_revision_id: str
    has_changes: bool
    total_added: int = 0
    total_deleted: int = 0
    total_modified: int = 0
    total_moved: int = 0
    entity_diffs: List[EntityDiffSummary] = Field(default_factory=list)


class ScreenplayDiffEngine:
    """Semantic diff comparator for Screenplay models."""

    @staticmethod
    def compare(base_model: Dict[str, Any], target_model: Dict[str, Any]) -> ScreenplayDiffResult:
        entity_diffs: List[EntityDiffSummary] = []

        base_rev = base_model.get("revision_id", "base_rev")
        target_rev = target_model.get("revision_id", "target_rev")

        # Compare Screenplay level metadata
        metadata_changes: List[FieldChange] = []
        if base_model.get("title") != target_model.get("title"):
            metadata_changes.append(FieldChange(field_name="title", old_value=base_model.get("title"), new_value=target_model.get("title")))
        if base_model.get("logline") != target_model.get("logline"):
            metadata_changes.append(FieldChange(field_name="logline", old_value=base_model.get("logline"), new_value=target_model.get("logline")))

        if metadata_changes:
            entity_diffs.append(
                EntityDiffSummary(
                    entity_type="SCREENPLAY",
                    entity_id=target_model.get("screenplay_id", "sp_01"),
                    change_type="MODIFIED",
                    title="Screenplay Metadata",
                    changes=metadata_changes,
                )
            )

        # Compare Scenes
        base_scenes: Dict[str, Dict[str, Any]] = {s["scene_id"]: s for s in base_model.get("scenes", [])}
        target_scenes: Dict[str, Dict[str, Any]] = {s["scene_id"]: s for s in target_model.get("scenes", [])}

        added_cnt = 0
        deleted_cnt = 0
        modified_cnt = 0
        moved_cnt = 0

        all_scene_ids = list(dict.fromkeys(list(base_scenes.keys()) + list(target_scenes.keys())))

        for sc_id in all_scene_ids:
            b_sc = base_scenes.get(sc_id)
            t_sc = target_scenes.get(sc_id)

            if b_sc is None and t_sc is not None:
                added_cnt += 1
                entity_diffs.append(
                    EntityDiffSummary(
                        entity_type="SCENE",
                        entity_id=sc_id,
                        change_type="ADDED",
                        title=t_sc.get("title", "NEW SCENE"),
                        changes=[FieldChange(field_name="scene", old_value=None, new_value=t_sc.get("title"))],
                    )
                )
            elif b_sc is not None and t_sc is None:
                deleted_cnt += 1
                entity_diffs.append(
                    EntityDiffSummary(
                        entity_type="SCENE",
                        entity_id=sc_id,
                        change_type="DELETED",
                        title=b_sc.get("title", "DELETED SCENE"),
                        changes=[FieldChange(field_name="scene", old_value=b_sc.get("title"), new_value=None)],
                    )
                )
            elif b_sc is not None and t_sc is not None:
                sc_changes: List[FieldChange] = []
                is_moved = b_sc.get("order") != t_sc.get("order")
                if is_moved:
                    sc_changes.append(FieldChange(field_name="order", old_value=b_sc.get("order"), new_value=t_sc.get("order")))
                    moved_cnt += 1

                if b_sc.get("title") != t_sc.get("title"):
                    sc_changes.append(FieldChange(field_name="title", old_value=b_sc.get("title"), new_value=t_sc.get("title")))
                if b_sc.get("action_description") != t_sc.get("action_description"):
                    sc_changes.append(FieldChange(field_name="action_description", old_value=b_sc.get("action_description"), new_value=t_sc.get("action_description")))

                if sc_changes:
                    modified_cnt += 1 if not is_moved else 0
                    entity_diffs.append(
                        EntityDiffSummary(
                            entity_type="SCENE",
                            entity_id=sc_id,
                            change_type="MOVED" if (is_moved and len(sc_changes) == 1) else "MODIFIED",
                            title=t_sc.get("title", "SCENE"),
                            changes=sc_changes,
                        )
                    )

                # Compare Dialogue lines within scene
                base_dlgs = {d["dialogue_id"]: d for d in b_sc.get("dialogue_lines", [])}
                target_dlgs = {d["dialogue_id"]: d for d in t_sc.get("dialogue_lines", [])}

                all_dlg_ids = list(dict.fromkeys(list(base_dlgs.keys()) + list(target_dlgs.keys())))
                for d_id in all_dlg_ids:
                    b_d = base_dlgs.get(d_id)
                    t_d = target_dlgs.get(d_id)

                    if b_d is None and t_d is not None:
                        added_cnt += 1
                        entity_diffs.append(
                            EntityDiffSummary(
                                entity_type="DIALOGUE",
                                entity_id=d_id,
                                change_type="ADDED",
                                title=f"Dialogue by {t_d.get('character_name')}",
                                changes=[FieldChange(field_name="text", old_value=None, new_value=t_d.get("text"))],
                            )
                        )
                    elif b_d is not None and t_d is None:
                        deleted_cnt += 1
                        entity_diffs.append(
                            EntityDiffSummary(
                                entity_type="DIALOGUE",
                                entity_id=d_id,
                                change_type="DELETED",
                                title=f"Dialogue by {b_d.get('character_name')}",
                                changes=[FieldChange(field_name="text", old_value=b_d.get("text"), new_value=None)],
                            )
                        )
                    elif b_d is not None and t_d is not None:
                        dlg_changes: List[FieldChange] = []
                        if b_d.get("text") != t_d.get("text"):
                            dlg_changes.append(FieldChange(field_name="text", old_value=b_d.get("text"), new_value=t_d.get("text")))
                        if b_d.get("delivery") != t_d.get("delivery"):
                            dlg_changes.append(FieldChange(field_name="delivery", old_value=b_d.get("delivery"), new_value=t_d.get("delivery")))

                        if dlg_changes:
                            modified_cnt += 1
                            entity_diffs.append(
                                EntityDiffSummary(
                                    entity_type="DIALOGUE",
                                    entity_id=d_id,
                                    change_type="MODIFIED",
                                    title=f"Dialogue by {t_d.get('character_name')}",
                                    changes=dlg_changes,
                                )
                            )

        has_changes = len(entity_diffs) > 0

        return ScreenplayDiffResult(
            base_revision_id=base_rev,
            target_revision_id=target_rev,
            has_changes=has_changes,
            total_added=added_cnt,
            total_deleted=deleted_cnt,
            total_modified=modified_cnt,
            total_moved=moved_cnt,
            entity_diffs=entity_diffs,
        )
