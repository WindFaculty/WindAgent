"""
Deterministic fixture builders for VideoProductionPackage v1.

Golden valid fixtures exercise the full package surface; invalid fixtures
cover the six required invalid cases:
- missing ID
- duplicate ID
- broken reference
- unordered shot
- asset without hash
- mutation after lock
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from windagent_core.domain.video_production.package import (
    VideoProductionPackage,
)

SCHEMA_VERSION = "1.0.0"


def sha256_hex(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def stable_hash(value: str) -> str:
    """Deterministic 64-char pseudo-hash for fixture purposes."""
    return sha256_hex(f"fixture::{value}")


# ----------------------------------------------------------------------
# Golden valid fixture
# ----------------------------------------------------------------------
def build_valid_package_dict() -> Dict[str, Any]:
    """Build a fully valid VideoProductionPackage v1 dict."""
    char_id = "chr_hero_01"
    loc_id = "loc_forest_01"
    scene_id = "scn_01"
    shot_id = "sht_010"
    asset_id = "ast_hero_portrait"
    dialogue_id = "dlg_001"

    package_dict: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "project_id": "vp_fixture_0001",
        "revision_id": "rev_0003",
        "creative_brief": {
            "brief_id": "brf_0001",
            "title": "Forest Guardian",
            "genre": "fantasy",
            "logline": "A guardian defends the forest.",
            "tone": "heroic",
            "target_duration_seconds": 45,
            "aspect_ratio": "16:9",
            "production_constraints": {"max_shots": 7},
        },
        "story_concept": {
            "concept_id": "cnc_0001",
            "title": "Forest Guardian",
            "premise": "A lone guardian protects the last forest.",
            "synopsis": "The guardian faces the encroaching darkness.",
            "themes": ["sacrifice", "nature"],
        },
        "screenplay": {
            "screenplay_id": "scr_0001",
            "title": "Forest Guardian",
            "logline": "A guardian defends the forest.",
            "status": "LOCKED",
            "scenes": [
                {
                    "scene_id": scene_id,
                    "order": 1,
                    "title": "The Clearing",
                    "location_id": loc_id,
                    "character_ids": [char_id],
                    "dialogue_line_ids": [dialogue_id],
                    "action_description": "The hero steps into the clearing.",
                    "time_of_day": "DAY",
                }
            ],
        },
        "characters": [
            {
                "character_id": char_id,
                "name": "Hero",
                "role": "LEAD",
                "visual_traits": {"age": "young", "build": "athletic"},
                "costume_descriptions": ["green cloak"],
                "portrait_asset_ids": [asset_id],
            }
        ],
        "locations": [
            {
                "location_id": loc_id,
                "name": "Forest Clearing",
                "visual_description": "Sun-dappled clearing",
                "lighting_profile": "soft daylight",
                "atmosphere_tags": ["peaceful"],
                "reference_asset_ids": [asset_id],
            }
        ],
        "props": [
            {
                "prop_id": "prp_sword",
                "name": "Guardian Sword",
                "description": "Ancient blade",
                "reference_asset_ids": [],
            }
        ],
        "style_bible": {
            "style_id": "sty_painterly",
            "name": "Painterly Fantasy",
            "visual_style": "soft painterly",
            "color_palette": ["green", "gold"],
            "lighting_rules": ["warm rim light"],
            "reference_asset_ids": [],
        },
        "dialogue": [
            {
                "dialogue_id": dialogue_id,
                "scene_id": scene_id,
                "character_id": char_id,
                "order": 1,
                "text": "The forest will not fall today.",
            }
        ],
        "cinematic_plan": {
            "plan_id": "plan_0001",
            "project_id": "vp_fixture_0001",
            "revision_id": "rev_0003",
            "graph": {
                "shots": [
                    {
                        "shot_id": shot_id,
                        "scene_id": scene_id,
                        "order": 1,
                        "shot_type": "ESTABLISHING",
                        "camera_movement": "STATIC",
                        "duration_seconds": 5.0,
                        "framing_description": "Wide view of the clearing",
                        "transition_type": "CUT",
                        "generation_mode": "TEXT_TO_VIDEO",
                        "dialogue_line_ids": [],
                        "reference_asset_ids": [asset_id],
                    }
                ],
                "dependencies": [],
            },
            "locked": True,
        },
        "continuity": [
            {
                "state_id": "ctn_0001",
                "shot_id": shot_id,
                "character_states": {"hero": {"position": "center"}},
                "location_state": {"lighting": "daylight"},
                "prop_states": {"sword": {"held_by": "hero"}},
                "camera_state": {"side": "A"},
                "must_preserve": ["character.hero.position"],
                "allowed_changes": [],
            }
        ],
        "assets": [
            {
                "asset_id": asset_id,
                "content_hash": stable_hash("hero_portrait"),
                "media_type": "image",
                "mime_type": "image/png",
                "size_bytes": 1024,
                "source_type": "GENERATED",
                "license_state": "LICENSED",
                "acquisition": {
                    "source_type": "GENERATED",
                    "source_url": None,
                    "license_state": "LICENSED",
                    "acquired_at": "2026-07-31T00:00:00+00:00",
                    "notes": "generated by test provider",
                },
            }
        ],
        "approvals": {
            "approvals": [
                {
                    "approval_id": "appr_0001",
                    "project_id": "vp_fixture_0001",
                    "revision_id": "rev_0003",
                    "target_hash": stable_hash("content_v3"),
                    "actor": "reviewer-1",
                    "role": "DIRECTOR",
                    "decision": "APPROVED",
                    "reason": "Looks good",
                }
            ],
            "locked": True,
        },
        "final_deliverable": {
            "deliverable_id": "delv_0001",
            "project_id": "vp_fixture_0001",
            "revision_id": "rev_0003",
            "content_hash": stable_hash("final_cut"),
            "mime_type": "video/mp4",
            "duration_seconds": 45.0,
            "uri": "s3://artifacts/final.mp4",
        },
        "provenance": {
            "created_by": "fixture-builder",
            "generator": "windagent-video-production-protocol",
        },
    }
    # The approval target hash must equal the package's actual content hash
    # (approvals/provenance are excluded from the hash, so no circularity).
    pkg = VideoProductionPackage.model_validate(package_dict)
    actual_hash = pkg.content_hash()
    package_dict["approvals"]["approvals"][0]["target_hash"] = actual_hash
    return package_dict


def build_valid_package() -> VideoProductionPackage:
    """Build a fully valid parsed package."""
    return VideoProductionPackage.model_validate(build_valid_package_dict())


# ----------------------------------------------------------------------
# Invalid fixtures
# ----------------------------------------------------------------------
def build_invalid_missing_id() -> Dict[str, Any]:
    """Invalid: scene_id missing from the embedded scene."""
    data = build_valid_package_dict()
    data["screenplay"]["scenes"][0]["scene_id"] = ""
    return data


def build_invalid_duplicate_id() -> Dict[str, Any]:
    """Invalid: duplicate asset_id in assets."""
    data = build_valid_package_dict()
    asset = data["assets"][0]
    data["assets"].append(dict(asset, asset_id=asset["asset_id"]))
    return data


def build_invalid_broken_reference() -> Dict[str, Any]:
    """Invalid: dialogue references a character that does not exist."""
    data = build_valid_package_dict()
    data["dialogue"][0]["character_id"] = "chr_does_not_exist"
    return data


def build_invalid_unordered_shot() -> Dict[str, Any]:
    """Invalid: shot order not increasing (shot 2 before shot 1)."""
    data = build_valid_package_dict()
    shots = data["cinematic_plan"]["graph"]["shots"]
    shots[0]["order"] = 2  # single shot with order 2 is fine, add a second unordered
    shots.append(
        {
            "shot_id": "sht_020",
            "scene_id": "scn_01",
            "order": 1,
            "shot_type": "MEDIUM",
            "camera_movement": "PAN",
            "duration_seconds": 3.0,
            "framing_description": "Close on hero",
            "transition_type": "CUT",
            "generation_mode": "TEXT_TO_VIDEO",
            "dialogue_line_ids": [],
            "reference_asset_ids": [],
        }
    )
    return data


def build_invalid_asset_missing_hash() -> Dict[str, Any]:
    """Invalid: asset with an empty content hash."""
    data = build_valid_package_dict()
    data["assets"][0]["content_hash"] = ""
    return data


def build_invalid_mutation_after_lock() -> Dict[str, Any]:
    """Invalid: locked revision whose content hash no longer matches approval target."""
    data = build_valid_package_dict()
    # Locked with approval target hash matching an OLD content hash
    data["approvals"]["locked"] = True
    data["approvals"]["approvals"][0]["target_hash"] = stable_hash("older_content")
    return data


INVALID_FIXTURE_BUILDERS = {
    "missing_id": build_invalid_missing_id,
    "duplicate_id": build_invalid_duplicate_id,
    "broken_reference": build_invalid_broken_reference,
    "unordered_shot": build_invalid_unordered_shot,
    "asset_missing_hash": build_invalid_asset_missing_hash,
    "mutation_after_lock": build_invalid_mutation_after_lock,
}

__all__ = [
    "SCHEMA_VERSION",
    "sha256_hex",
    "stable_hash",
    "build_valid_package_dict",
    "build_valid_package",
    "build_invalid_missing_id",
    "build_invalid_duplicate_id",
    "build_invalid_broken_reference",
    "build_invalid_unordered_shot",
    "build_invalid_asset_missing_hash",
    "build_invalid_mutation_after_lock",
    "INVALID_FIXTURE_BUILDERS",
]
