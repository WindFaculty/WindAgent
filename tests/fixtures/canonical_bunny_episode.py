"""
Canonical Fixture Builder for Bunny Episode 01.

Provides deterministic data structures for Stage H testing:
- Screenplays with locked ancestor + active draft
- Scenes (dialogue, locations, props)
- Asset Taxonomy (3D GLB Bunny, Location Park, missing Ball asset)
- License states (LICENSED, UNKNOWN, INCOMPATIBLE)
- Job pipelines (SUCCESS, RETRYABLE_FAILURE, TERMINAL_FAILURE)
- Collaboration Proposals (PENDING, STALE, APPROVED, REJECTED)
- Event histories (replay, duplicate, gap scenarios)
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

BUNNY_PROJECT_ID = "prj_bunny_ep01"
BUNNY_LOCKED_REV = "rev_ep01_v1_locked"
BUNNY_ACTIVE_DRAFT_REV = "rev_ep01_v2_draft"


def sha256_hex(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_canonical_bunny_episode() -> Dict[str, Any]:
    """Returns full canonical fixture dictionary for Bunny Episode 01."""
    return {
        "project_id": BUNNY_PROJECT_ID,
        "title": "Bunny Episode 01 - The Great Park Chase",
        "description": "Bunny loses a golden ball in the park and encounters unexpected challenges.",
        "revisions": {
            "locked_ancestor": {
                "revision_id": BUNNY_LOCKED_REV,
                "project_id": BUNNY_PROJECT_ID,
                "version_number": 1,
                "parent_revision_id": None,
                "locked": True,
                "locked_at": "2026-08-01T10:00:00Z",
                "locked_hash": sha256_hex("bunny_locked_ancestor_v1"),
                "screenplay_id": "scr_bunny_v1",
            },
            "active_draft": {
                "revision_id": BUNNY_ACTIVE_DRAFT_REV,
                "project_id": BUNNY_PROJECT_ID,
                "version_number": 2,
                "parent_revision_id": BUNNY_LOCKED_REV,
                "locked": False,
                "locked_at": None,
                "locked_hash": None,
                "screenplay_id": "scr_bunny_v2",
            },
        },
        "screenplay": {
            "screenplay_id": "scr_bunny_v2",
            "title": "Bunny Episode 01 - The Great Park Chase",
            "logline": "Bunny loses a golden ball in the park.",
            "status": "DRAFT",
            "scenes": [
                {
                    "scene_id": "scn_park_01",
                    "order": 1,
                    "title": "Sunlit Meadow",
                    "location_id": "loc_park_meadow",
                    "character_ids": ["chr_bunny", "chr_squirrel"],
                    "action_description": "Bunny bounces into the meadow holding a shimmering golden ball.",
                    "time_of_day": "DAY",
                    "dialogue_line_ids": ["dlg_b1_01", "dlg_b1_02"],
                },
                {
                    "scene_id": "scn_park_02",
                    "order": 2,
                    "title": "Near the Old Oak Tree",
                    "location_id": "loc_oak_tree",
                    "character_ids": ["chr_bunny"],
                    "action_description": "The ball rolls down into a deep hollow between roots.",
                    "time_of_day": "DAY",
                    "dialogue_line_ids": ["dlg_b1_03"],
                },
            ],
            "dialogue": [
                {
                    "dialogue_id": "dlg_b1_01",
                    "scene_id": "scn_park_01",
                    "character_id": "chr_bunny",
                    "order": 1,
                    "text": "Look at how shiny this golden ball is!",
                },
                {
                    "dialogue_id": "dlg_b1_02",
                    "scene_id": "scn_park_01",
                    "character_id": "chr_squirrel",
                    "order": 2,
                    "text": "Be careful, Bunny! Don't let it drop near the old oak tree!",
                },
                {
                    "dialogue_id": "dlg_b1_03",
                    "scene_id": "scn_park_02",
                    "character_id": "chr_bunny",
                    "order": 1,
                    "text": "Oh no! It slipped right into the roots!",
                },
            ],
        },
        "assets": [
            {
                "asset_id": "ast_bunny_3d",
                "name": "Bunny Character Rig",
                "asset_type": "CHARACTER_MODEL",
                "format": "GLB",
                "content_hash": sha256_hex("ast_bunny_3d_content"),
                "license_state": "LICENSED",
                "processing_state": "COMPLETED",
                "uri": "s3://assets/bunny_rig_v1.glb",
                "provenance": {"author": "Studio3D", "license_type": "CC-BY-4.0"},
            },
            {
                "asset_id": "ast_park_bg",
                "name": "Sunlit Park Background",
                "asset_type": "LOCATION_SET",
                "format": "PNG",
                "content_hash": sha256_hex("ast_park_bg_content"),
                "license_state": "UNKNOWN",
                "processing_state": "COMPLETED",
                "uri": "s3://assets/park_meadow.png",
                "provenance": {"author": "StockPhotos", "license_type": "UNKNOWN"},
            },
            {
                "asset_id": "ast_missing_ball",
                "name": "Golden Ball Prop",
                "asset_type": "PROP",
                "format": "GLB",
                "content_hash": sha256_hex("ast_missing_ball_content"),
                "license_state": "INCOMPATIBLE",
                "processing_state": "FAILED",
                "uri": "s3://assets/golden_ball_missing.glb",
                "provenance": {"author": "UnlicensedStore", "license_type": "PROPRIETARY_RESTRICTED"},
            },
        ],
        "jobs": [
            {
                "job_id": "job_success_01",
                "asset_id": "ast_bunny_3d",
                "status": "COMPLETED",
                "retry_count": 0,
                "max_retries": 3,
                "error": None,
            },
            {
                "job_id": "job_retryable_01",
                "asset_id": "ast_park_bg",
                "status": "RETRYABLE_FAILURE",
                "retry_count": 1,
                "max_retries": 3,
                "error": "Transient network timeout connecting to storage provider.",
            },
            {
                "job_id": "job_terminal_01",
                "asset_id": "ast_missing_ball",
                "status": "TERMINAL_FAILURE",
                "retry_count": 3,
                "max_retries": 3,
                "error": "Asset license verification failed: PROPRIETARY_RESTRICTED.",
            },
        ],
        "proposals": [
            {
                "proposal_id": "prop_pending_01",
                "project_id": BUNNY_PROJECT_ID,
                "revision_id": BUNNY_ACTIVE_DRAFT_REV,
                "target_entity_type": "SCREENPLAY",
                "target_entity_id": "scn_park_01",
                "agent_id": "agent_script_assistant",
                "status": "PENDING",
                "summary": "Add background sound effects to Sunlit Meadow scene.",
                "payload": {"action": "ADD_SFX", "sfx_tag": "birds_chirping"},
            },
            {
                "proposal_id": "prop_stale_01",
                "project_id": BUNNY_PROJECT_ID,
                "revision_id": BUNNY_LOCKED_REV,
                "target_entity_type": "SCREENPLAY",
                "target_entity_id": "scn_park_02",
                "agent_id": "agent_cinematographer",
                "status": "STALE",
                "summary": "Adjust camera angle in locked ancestor.",
                "payload": {"action": "SET_CAMERA", "angle": "LOW_ANGLE"},
            },
            {
                "proposal_id": "prop_approved_01",
                "project_id": BUNNY_PROJECT_ID,
                "revision_id": BUNNY_ACTIVE_DRAFT_REV,
                "target_entity_type": "SCREENPLAY",
                "target_entity_id": "dlg_b1_02",
                "agent_id": "agent_dialogue_tuner",
                "status": "APPROVED",
                "summary": "Emphasize squirrel warning dialogue.",
                "payload": {"action": "UPDATE_DIALOGUE", "new_text": "Be careful, Bunny! Don't let it drop!"},
            },
            {
                "proposal_id": "prop_rejected_01",
                "project_id": BUNNY_PROJECT_ID,
                "revision_id": BUNNY_ACTIVE_DRAFT_REV,
                "target_entity_type": "ASSET",
                "target_entity_id": "ast_missing_ball",
                "agent_id": "agent_asset_generator",
                "status": "REJECTED",
                "summary": "Force assign unlicensed golden ball asset.",
                "payload": {"action": "FORCE_BIND"},
            },
        ],
        "events": [
            {
                "event_id": "evt_001",
                "sequence": 1,
                "project_id": BUNNY_PROJECT_ID,
                "event_type": "PROJECT_CREATED",
                "timestamp": "2026-08-01T09:00:00Z",
                "data": {"title": "Bunny Episode 01"},
            },
            {
                "event_id": "evt_002",
                "sequence": 2,
                "project_id": BUNNY_PROJECT_ID,
                "event_type": "REVISION_LOCKED",
                "timestamp": "2026-08-01T10:00:00Z",
                "data": {"revision_id": BUNNY_LOCKED_REV},
            },
            {
                "event_id": "evt_003",
                "sequence": 3,
                "project_id": BUNNY_PROJECT_ID,
                "event_type": "DRAFT_SAVED",
                "timestamp": "2026-08-02T11:00:00Z",
                "data": {"revision_id": BUNNY_ACTIVE_DRAFT_REV},
            },
        ],
    }
