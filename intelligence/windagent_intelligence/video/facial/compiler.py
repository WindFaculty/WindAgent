"""
Facial pipeline compiler layer (VP3D Phase 18, stage_i).

`FacialAnimationCompiler` implements the `FacialAnimationCompilerPort`: it
wires the core domain kernel (normalize -> map -> compile -> validate ->
bake -> repair -> preview manifest). The Blender-side adapter mapping
(semantic control -> shape key / bone) is a plain data table
(`FACIAL_BINDING_TABLE`) — no bpy import, no data-block names in the domain.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_core.contracts.video_production.facial_animation import (
    FacialAnimationCompilerPort,
)
from windagent_core.domain.video_production.enums import (
    FacialRepairScope,
    HeadBlendPolicy,
)
from windagent_core.domain.video_production.errors import (
    FacialCompileError,
    FacialRepairError,
)
from windagent_core.domain.video_production.facial import (
    ARTICULATION_CONTROLS,
    BLINK_CONTROLS,
    BROW_CONTROLS,
    GAZE_CONTROLS,
    HEAD_CONTROLS,
    BakedFacialAction,
    EmotionCurve,
    FacialAnimationTrack,
    FacialRepairReceipt,
    FacialValidationReceipt,
    PhonemeTrack,
    VisemeMap,
    bake_facial_track,
    build_preview_manifest,
    compile_facial_track,
    repair_facial_track,
    validate_facial_track,
)
from windagent_core.domain.video_production.ids import (
    BakedFacialActionId,
    FacialRepairReceiptId,
    FacialTrackId,
    FacialValidationReceiptId,
)

FACIAL_LAYER_VERSION = "facial-1.0"

# Semantic control -> adapter binding names. These are the ONLY place the
# facial pipeline knows shape-key / bone names; the domain stays clean.
# Keys are semantic controls; values are {shape_key, bone} names the
# Blender adapter resolves at bind time. No bpy import anywhere.
FACIAL_BINDING_TABLE: Dict[str, Dict[str, str]] = {
    "jaw_open": {"shape_key": "jawOpen", "bone": "jaw"},
    "lips_close": {"shape_key": "lipsClosed", "bone": "lips"},
    "mouth_corner_l": {"shape_key": "mouthCornerL", "bone": ""},
    "mouth_corner_r": {"shape_key": "mouthCornerR", "bone": ""},
    "tongue_up": {"shape_key": "tongueUp", "bone": ""},
    "blink_l": {"shape_key": "blinkLeft", "bone": ""},
    "blink_r": {"shape_key": "blinkRight", "bone": ""},
    "brow_raise_l": {"shape_key": "browRaiseL", "bone": ""},
    "brow_raise_r": {"shape_key": "browRaiseR", "bone": ""},
    "eye_target_x": {"shape_key": "", "bone": "eyeTargetX"},
    "eye_target_y": {"shape_key": "", "bone": "eyeTargetY"},
    "head_yaw": {"shape_key": "", "bone": "head"},
    "head_pitch": {"shape_key": "", "bone": "head"},
}


class FacialCompileRequest:
    """One compile request: normalized timing + viseme map + policy."""

    def __init__(
        self,
        *,
        track_id: FacialTrackId,
        character_id: str,
        shot_id: str,
        phoneme_track: PhonemeTrack,
        viseme_map: VisemeMap,
        seed: int,
        head_blend_policy: HeadBlendPolicy = HeadBlendPolicy.BLEND_LIMITED,
        emotion_curves: Optional[List[EmotionCurve]] = None,
        facial_rig_controls: Optional[List[str]] = None,
        idle: bool = False,
    ) -> None:
        self.track_id = track_id
        self.character_id = character_id
        self.shot_id = shot_id
        self.phoneme_track = phoneme_track
        self.viseme_map = viseme_map
        self.seed = seed
        self.head_blend_policy = head_blend_policy
        self.emotion_curves = emotion_curves
        self.facial_rig_controls = facial_rig_controls
        self.idle = idle


class FacialAnimationCompiler(FacialAnimationCompilerPort):
    """Pipeline facade over the core facial kernel (stage_i §3)."""

    def __init__(self) -> None:
        self.compiler_version = FACIAL_LAYER_VERSION

    def compile(self, request: FacialCompileRequest) -> FacialAnimationTrack:
        if not isinstance(request, FacialCompileRequest):
            raise FacialCompileError(
                "compile() requires a FacialCompileRequest",
                details={"got": type(request).__name__},
            )
        return compile_facial_track(
            track_id=request.track_id,
            character_id=request.character_id,
            shot_id=request.shot_id,
            phoneme_track=request.phoneme_track,
            viseme_map=request.viseme_map,
            seed=request.seed,
            head_blend_policy=request.head_blend_policy,
            emotion_curves=request.emotion_curves,
            facial_rig_controls=request.facial_rig_controls,
            idle=request.idle,
        )

    def validate(
        self,
        track: FacialAnimationTrack,
        *,
        phoneme_track: Optional[PhonemeTrack] = None,
        facial_rig_controls: Optional[List[str]] = None,
        body_head_turn_degrees: float = 0.0,
        receipt_id: Optional[FacialValidationReceiptId] = None,
    ) -> FacialValidationReceipt:
        rid = receipt_id or FacialValidationReceiptId(f"fvr-{track.track_id}")
        return validate_facial_track(
            receipt_id=rid,
            track=track,
            phoneme_track=phoneme_track,
            facial_rig_controls=facial_rig_controls,
            body_head_turn_degrees=body_head_turn_degrees,
        )

    def bake(self, track: FacialAnimationTrack, *,
             action_id: Optional[BakedFacialActionId] = None) -> BakedFacialAction:
        aid = action_id or BakedFacialActionId(f"bfa-{track.track_id}")
        return bake_facial_track(action_id=aid, track=track)

    def repair(
        self,
        track: FacialAnimationTrack,
        *,
        scope: FacialRepairScope,
        receipt_id: Optional[FacialRepairReceiptId] = None,
        seed: Optional[int] = None,
        emotion_curves: Optional[List[EmotionCurve]] = None,
    ) -> FacialRepairReceipt:
        if scope not in [s.value for s in FacialRepairScope] \
                and not isinstance(scope, FacialRepairScope):
            raise FacialRepairError(
                f"Unknown repair scope {scope!r}",
                details={"scope": str(scope)},
            )
        scope = FacialRepairScope(scope)
        rid = receipt_id or FacialRepairReceiptId(f"frr-{track.track_id}")
        return repair_facial_track(
            receipt_id=rid,
            track=track,
            scope=scope,
            seed=seed,
            emotion_curves=emotion_curves,
        )

    def preview_manifest(self, track: FacialAnimationTrack, **kwargs) -> dict:
        return build_preview_manifest(track=track, **kwargs)

    def binding_table(self) -> Dict[str, Dict[str, str]]:
        """Adapter binding table: semantic control -> shape key / bone."""
        return FACIAL_BINDING_TABLE

    def semantic_controls(self) -> List[str]:
        return sorted(set(ARTICULATION_CONTROLS) | set(BLINK_CONTROLS)
                      | set(BROW_CONTROLS) | set(GAZE_CONTROLS)
                      | set(HEAD_CONTROLS))


__all__ = [
    "FACIAL_LAYER_VERSION",
    "FACIAL_BINDING_TABLE",
    "FacialCompileRequest",
    "FacialAnimationCompiler",
]
