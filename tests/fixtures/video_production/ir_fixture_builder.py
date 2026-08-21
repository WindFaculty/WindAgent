"""
Deterministic fixture builders for the VP3D Phase 1 Production IR.

Provides a fully valid `ProductionIrDocument` plus a dict variant so tests
can exercise round-trip, canonical-hash stability, validation and the
engine port contract without hand-writing IR objects.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from windagent_core.domain.video_production.production_ir.enums import EngineJobStatus, IrAssetFormat
from windagent_core.domain.video_production.production_ir.models import (
    DEFAULT_RENDER_PROFILE_ID,
    DerivedArtifact,
    EngineJobReceipt,
    ProductionIrDocument,
    ShotExecutionIntent,
)


def sha256_hex(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_valid_ir_dict() -> Dict[str, Any]:
    """Build a fully valid ProductionIrDocument dict (schema 1.0.0)."""
    char_instance_id = "chr_hero_01"
    prop_instance_id = "prp_sword_01"
    env_instance_id = "env_forest_01"
    light_rig_id = "light_forest_01"
    scene_id = "scn_01"
    shot_id = "sht_010"
    profile_id = DEFAULT_RENDER_PROFILE_ID
    intent_id = shot_id

    return {
        "ir_id": "ir_vp_ir_0001_rev_0001",
        "schema_version": "1.0.0",
        "project_id": "vp_ir_0001",
        "revision_id": "rev_0001",
        "source_package_hash": sha256_hex("fixture-package"),
        "scenes": [
            {
                "scene_id": scene_id,
                "screenplay_scene_id": scene_id,
                "characters": [
                    {
                        "instance_id": char_instance_id,
                        "character_id": "chr_hero_01",
                        "display_name": "Hero",
                        "mesh": {
                            "asset_id": "ast_hero_glb",
                            "role": "CHARACTER_MESH",
                            "uri": "file:///assets/hero.glb",
                            "format": "GLTF",
                            "content_hash": sha256_hex("hero-gltf"),
                            "derived": False,
                        },
                        "rig_profile": "humanoid",
                    }
                ],
                "props": [
                    {
                        "instance_id": prop_instance_id,
                        "prop_id": "prp_sword",
                        "asset": {
                            "asset_id": "ast_sword_fbx",
                            "role": "PROP",
                            "uri": "file:///assets/sword.fbx",
                            "format": "FBX",
                            "content_hash": sha256_hex("sword-fbx"),
                            "derived": False,
                        },
                    }
                ],
                "environment": [
                    {
                        "instance_id": env_instance_id,
                        "location_id": "loc_forest_01",
                        "asset": {
                            "asset_id": "ast_forest_usd",
                            "role": "ENVIRONMENT",
                            "uri": "file:///assets/forest.usd",
                            "format": "USD",
                            "content_hash": sha256_hex("forest-usd"),
                            "derived": False,
                        },
                    }
                ],
                "light_rigs": [
                    {"rig_id": light_rig_id, "lighting_profile": "soft daylight"}
                ],
                "action": "The hero steps into the clearing.",
            }
        ],
        "shots": [
            {
                "intent_id": intent_id,
                "shot_id": shot_id,
                "scene_id": scene_id,
                "order": 1,
                "characters": [char_instance_id],
                "props": [prop_instance_id],
                "environment": [env_instance_id],
                "action": "hero walks to center",
                "camera": {
                    "track_id": "cam_sht_010",
                    "shot_type": "ESTABLISHING",
                    "angle": "EYE_LEVEL",
                    "movement": "DOLLY",
                    "duration_seconds": 5.0,
                    "frame_rate": 24,
                    "aspect_ratio": "16:9",
                    "transition_type": "CUT",
                },
                "animation_tracks": [
                    {
                        "track_id": "anim_sht_010",
                        "target_instance_ids": [char_instance_id],
                        "action": "walk_to center",
                    }
                ],
                "dialogue_tracks": [
                    {
                        "dialogue_line_ids": ["dlg_001"],
                        "audio_track_ids": ["dtk_001"],
                        "audio_asset_ids": ["tts_001"],
                        "target_start_seconds": 0.5,
                        "target_end_seconds": 3.5,
                    }
                ],
                "light_rig_ids": [light_rig_id],
                "simulation_tracks": [],
                "duration_seconds": 5.0,
                "render_profile_id": profile_id,
                "creative_prompt": "Wide view of the clearing, soft daylight.",
            }
        ],
        "render_profiles": [
            {
                "profile_id": profile_id,
                "quality": "HIGH",
                "engine_hint": "",
                "samples": 64,
                "resolution": {"width": 1920, "height": 1080},
                "denoise": True,
                "output_format": "PNG",
                "frame_rate": 24,
            }
        ],
        "render_intents": [
            {
                "intent_id": "ri_scn_01",
                "scene_id": scene_id,
                "shot_execution_intent_ids": [intent_id],
                "profile": {
                    "profile_id": profile_id,
                    "quality": "HIGH",
                    "engine_hint": "",
                    "samples": 64,
                    "resolution": {"width": 1920, "height": 1080},
                    "denoise": True,
                    "output_format": "PNG",
                    "frame_rate": 24,
                },
                "frame_start": 1,
                "frame_end": 0,
            }
        ],
        "locked": False,
        "approval_state_ref": "",
        "provenance": {"created_by": "ir-fixture-builder"},
    }


def build_valid_ir() -> ProductionIrDocument:
    return ProductionIrDocument.model_validate(build_valid_ir_dict())


def build_valid_shot_intent() -> ShotExecutionIntent:
    doc = build_valid_ir()
    return doc.shots[0]


def build_engine_receipt() -> EngineJobReceipt:
    return EngineJobReceipt(
        job_id="ej_0001",
        project_id="vp_ir_0001",
        revision_id="rev_0001",
        ir_hash=sha256_hex("fixture-ir"),
        status=EngineJobStatus.SUBMITTED,
        engine_name="fake-engine",
    )


def build_derived_artifact() -> DerivedArtifact:
    return DerivedArtifact(
        artifact_id="da_0001",
        job_id="ej_0001",
        kind="FRAME_SEQUENCE",
        uri="file:///out/sht_010/frame_0001.png",
        format=IrAssetFormat.PNG,
        content_hash=sha256_hex("frame-0001"),
        derived_from_ir_hash=sha256_hex("fixture-ir"),
        size_bytes=1024,
    )


__all__ = [
    "sha256_hex",
    "build_valid_ir_dict",
    "build_valid_ir",
    "build_valid_shot_intent",
    "build_engine_receipt",
    "build_derived_artifact",
]
