"""
FacialAnimationCompilerPort — facial pipeline contract (VP3D Phase 18, Stage I).

A facial compiler turns Stage E alignment (phonemes + confidence) + a
Stage D facial rig profile into a `FacialAnimationTrack`: viseme curves,
emotion, blink, gaze and head motion. The port is implementation-neutral —
the Blender-side adapter maps semantic controls to shape keys / bones; the
domain never carries bpy data-block names (stage_i §3).

Guarantees:
  - the domain kernel (windagent_core...facial) normalizes timing, resolves
    visemes with explicit fallback rules, compiles deterministic curves and
    runs the stage_i §4 quality matrix (monotonic ordering, shot range,
    drift at line start/mid/end, silence, pop, idle, head joint limit);
  - low-confidence alignment or rig controls missing from the facial rig
    profile route to REQUIRES_HUMAN_REVIEW — never silently into render;
  - per-layer repair (lip-sync / gaze / emotion) invalidates only the
    affected layer + render/final downstream.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class FacialAnimationCompilerPort(Protocol):
    """Port a facial pipeline adapter implements (Blender, engine, etc.)."""

    def compile(self, request: object) -> object:
        """Compile one facial track from a compile request.

        `request` is a domain value object (phoneme track + viseme map +
        seed + head blend policy + optional emotion curves + rig controls).
        Returns a `FacialAnimationTrack` (domain object). Raises
        `FacialCompileError` / `VisemeMapMissingPhonemeError` when the input
        cannot compile — never silently skips.
        """
        ...

    def validate(self, track: object, *, phoneme_track: object = None,
                 facial_rig_controls: object = None,
                 body_head_turn_degrees: float = 0.0) -> object:
        """Run the stage_i §4 quality matrix over a compiled track.

        Returns a `FacialValidationReceipt` with status APPROVED /
        REQUIRES_HUMAN_REVIEW / REJECTED and per-line sync metrics.
        """
        ...

    def bake(self, track: object, *, action_id: object) -> object:
        """Bake an APPROVED track into a derived `BakedFacialAction`.

        Records compiler version + input hashes + frame range. Non-APPROVED
        tracks fail closed (`FacialBakeError`).
        """
        ...

    def repair(self, track: object, *, receipt_id: object,
               scope: object, seed: object = None,
               emotion_curves: object = None) -> object:
        """Repair ONE layer; returns a `FacialRepairReceipt` with the
        invalidation scope (layer only vs layer + render/final)."""
        ...

    def preview_manifest(self, track: object, **kwargs) -> dict:
        """Build the close-up / playblast preview manifest (backlog 9)."""
        ...


__all__ = ["FacialAnimationCompilerPort"]
