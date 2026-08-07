"""
VP3D Phase 4 — Typed deterministic smoke fixture (plan Stage B §4).

The plan requires a TYPED fixture describing: cube, ground, camera, THREE
lights, ONE material and keyframed animation. The fixture is a fixed,
auditable specification — the trusted compiler maps it (plus the Production IR)
onto `scene_plan.json` and the pinned bpy script. It is deliberately simple
(no asset AI, no rigs, no LLM-generated Python).
"""

from __future__ import annotations

from typing import Any, Dict

FIXTURE_VERSION = "1.0.0"

CUBE = {
    "name": "Cube",
    "kind": "CUBE",
    "location": [0.0, 0.0, 0.5],
    "rotation": [0.0, 0.0, 0.0],
    "scale": [1.0, 1.0, 1.0],
}

GROUND = {
    "name": "Ground",
    "kind": "PLANE",
    "location": [0.0, 0.0, 0.0],
    "rotation": [0.0, 0.0, 0.0],
    "scale": [4.0, 4.0, 1.0],
}

CAMERA = {
    "location": [7.0, -6.0, 4.5],
    "rotation": [1.1, 0.0, 0.7],
    "lens_mm": 35.0,
    "sensor_width_mm": 36.0,
}

THREE_LIGHTS = [
    {
        "name": "Key",
        "kind": "AREA",
        "energy": 800.0,
        "color": [1.0, 1.0, 1.0],
        "location": [5.0, -4.0, 6.0],
        "rotation": [0.0, 0.0, 0.0],
    },
    {
        "name": "Fill",
        "kind": "AREA",
        "energy": 200.0,
        "color": [1.0, 1.0, 1.0],
        "location": [-5.0, -4.0, 3.0],
        "rotation": [0.0, 0.0, 0.0],
    },
    {
        "name": "Rim",
        "kind": "AREA",
        "energy": 300.0,
        "color": [1.0, 1.0, 1.0],
        "location": [0.0, 6.0, 5.0],
        "rotation": [0.0, 0.0, 0.0],
    },
]

MATERIAL = {
    "name": "SmokeMaterial",
    "base_color": [0.8, 0.2, 0.2, 1.0],
    "roughness": 0.4,
    "metallic": 0.0,
}

ANIMATION = {
    "target_object": "Cube",
    "start_rotation_z": 0.0,
    "end_rotation_z": 6.283185307179586,  # one full turn
    "start_location": [0.0, 0.0, 0.5],
    "end_location": [0.0, 0.0, 0.5],
}


def build_smoke_fixture() -> Dict[str, Any]:
    """Return the canonical typed fixture (deterministic, immutable-by-convention)."""
    return {
        "fixture_version": FIXTURE_VERSION,
        "cube": CUBE,
        "ground": GROUND,
        "camera": CAMERA,
        "lights": THREE_LIGHTS,
        "material": MATERIAL,
        "animation": ANIMATION,
    }


def fixture_content_hash() -> str:
    """Content hash of the fixture (a fixture change must invalidate outputs)."""
    import hashlib
    import json

    canonical = json.dumps(
        build_smoke_fixture(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "FIXTURE_VERSION",
    "CUBE",
    "GROUND",
    "CAMERA",
    "THREE_LIGHTS",
    "MATERIAL",
    "ANIMATION",
    "build_smoke_fixture",
    "fixture_content_hash",
]
