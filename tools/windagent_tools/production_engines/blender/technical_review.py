"""VP3D Phase 22 - 3D technical reviewer (plan Stage K §3).

Engine-neutral quality-review kernel at the Blender adapter boundary (no
``bpy`` import, mirroring Phase 19 ``rendering``, Phase 20 ``vram_budget``
and Phase 21 ``render_jobs``).  It turns typed scene/render manifests and
per-frame media signals into structured findings and a single verdict:

```text
blocking finding exists           -> REJECT
no blocking, low confidence       -> REQUIRES_HUMAN
every required dimension passes   -> APPROVE
```

Components:

```text
PreRenderReviewer        deterministic pre-render gates: missing object /
                         texture, broken rig, frame range, camera/character
                         collision, lighting, audio timing, unapproved
                         asset/add-on, VRAM budget.  A BLOCKING finding
                         stops render submission.
FrameIntegrityReviewer   post-render frame gate: expected count, decode,
                         dimension, black/corrupt frames, missing ranges.
TemporalReviewer         flicker / noise / exposure discontinuity over
                         sliding temporal windows; sustained violations
                         escalate to BLOCKING.
ContentReviewer          identity, lip-sync, occlusion, continuity, motion
                         quality, lighting, camera compliance.  Deterministic
                         metrics first; an optional VLM port runs after and
                         NEVER turns a timeout into a PASS (fail closed ->
                         REQUIRES_HUMAN).
CrossShotReviewer        continuity across shots: every comparison pins
                         character / location / lighting references.
decide_verdict           the Stage K §3 verdict rule.
```

Every finding carries: code, severity, affected entity, frame range,
evidence (raw measurements), confidence (0..1), suggested repair scope and
- for ambiguous defects - the candidate causes instead of a single
auto-picked repair (Stage K §5: keep uncertainty below the confidence
threshold).

All models are immutable frozen dataclasses; services never mutate input.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from windagent_tools.production_engines.blender.vram_budget import (
    SceneResourceManifest,
    VramBudgetPolicy,
    VramMitigationPlanner,
)

TECHNICAL_REVIEW_SCHEMA_VERSION = "technical-review-1.0.0"

# ---------------------------------------------------------------------------
# Severity / verdict constants
# ---------------------------------------------------------------------------
SEVERITY_BLOCKING = "BLOCKING"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"
SEVERITIES = (SEVERITY_BLOCKING, SEVERITY_WARNING, SEVERITY_INFO)

VERDICT_REJECT = "REJECT"
VERDICT_REQUIRES_HUMAN = "REQUIRES_HUMAN"
VERDICT_APPROVE = "APPROVE"

DEFAULT_CONFIDENCE_THRESHOLD = 0.6

# Repair scopes the retry planner (Phase 23) can consume directly.
REPAIR_ASSET_REVISION = "asset_revision"
REPAIR_CAMERA_RECOMPILE = "camera_recompile"
REPAIR_FACIAL_ONLY = "facial_only"
REPAIR_AFFECTED_FRAMES = "affected_frames"
REPAIR_AUDIO_MIX = "audio_mix"
REPAIR_RIG_REPAIR = "rig_repair"
REPAIR_FRAME_RANGE_ADJUST = "frame_range_adjust"
REPAIR_LIGHTING_FIX = "lighting_fix"
REPAIR_ASSET_APPROVAL = "asset_approval"
REPAIR_VRAM_MITIGATION = "vram_mitigation"
REPAIR_HUMAN_REVIEW = "human_review"

# Content-review dimensions (Stage K §3 post-render item 3).
DIM_IDENTITY = "identity"
DIM_LIP_SYNC = "lip_sync"
DIM_OCCLUSION = "occlusion"
DIM_CONTINUITY = "continuity"
DIM_MOTION_QUALITY = "motion_quality"
DIM_LIGHTING = "lighting"
DIM_CAMERA_COMPLIANCE = "camera_compliance"
REQUIRED_DIMENSIONS = (
    DIM_IDENTITY,
    DIM_LIP_SYNC,
    DIM_OCCLUSION,
    DIM_CONTINUITY,
    DIM_MOTION_QUALITY,
    DIM_LIGHTING,
    DIM_CAMERA_COMPLIANCE,
)

# Pre-render gate finding codes.
FINDING_MISSING_OBJECT = "MISSING_OBJECT"
FINDING_MISSING_TEXTURE = "MISSING_TEXTURE"
FINDING_BROKEN_RIG = "BROKEN_RIG"
FINDING_FRAME_RANGE = "FRAME_RANGE_INVALID"
FINDING_CAMERA_COLLISION = "CAMERA_CHARACTER_COLLISION"
FINDING_LIGHTING = "LIGHTING_INVALID"
FINDING_AUDIO_TIMING = "AUDIO_TIMING"
FINDING_UNAPPROVED_ASSET = "UNAPPROVED_ASSET"
FINDING_UNAPPROVED_ADDON = "UNAPPROVED_ADDON"
FINDING_VRAM_BUDGET = "VRAM_BUDGET_EXCEEDED"

# Post-render gate finding codes.
FINDING_FRAME_COUNT = "FRAME_COUNT_MISMATCH"
FINDING_FRAME_UNDECODABLE = "FRAME_UNDECODABLE"
FINDING_FRAME_DIMENSION = "FRAME_DIMENSION_MISMATCH"
FINDING_FRAME_BLACK = "FRAME_BLACK_OR_CORRUPT"
FINDING_FRAME_MISSING_RANGE = "FRAME_MISSING_RANGE"
FINDING_FLICKER = "FLICKER_DETECTED"
FINDING_NOISE = "NOISE_BURST"
FINDING_EXPOSURE_DISCONTINUITY = "EXPOSURE_DISCONTINUITY"
FINDING_VLM_TIMEOUT = "VLM_REVIEW_TIMEOUT"
FINDING_LIP_SYNC = "LIP_SYNC_MISMATCH"
FINDING_IDENTITY = "IDENTITY_DRIFT"
FINDING_OCCLUSION = "OCCLUSION_ANOMALY"
FINDING_CONTINUITY = "CONTINUITY_BREAK"
FINDING_MOTION_QUALITY = "MOTION_QUALITY_DEGRADED"
FINDING_LIGHTING_DRIFT = "LIGHTING_DRIFT"
FINDING_CAMERA_COMPLIANCE = "CAMERA_NON_COMPLIANT"
FINDING_CROSS_SHOT_IDENTITY = "CROSS_SHOT_IDENTITY_MISMATCH"
FINDING_CROSS_SHOT_LOCATION = "CROSS_SHOT_LOCATION_MISMATCH"
FINDING_CROSS_SHOT_LIGHTING = "CROSS_SHOT_LIGHTING_MISMATCH"

# Pre-render defaults.
DEFAULT_AUDIO_TIMING_TOLERANCE = 0.25  # seconds of slack
DEFAULT_LIGHT_INTENSITY_MIN = 0.05
DEFAULT_LIGHT_INTENSITY_MAX = 100.0
DEFAULT_COLLISION_MARGIN = 0.1  # meters around character bounds
REQUIRED_RIG_JOINTS = ("root", "spine", "head")

# Post-render defaults.
DEFAULT_BLACK_LUMA_MEAN = 2.0  # average pixel luma below this = black frame
DEFAULT_TEMPORAL_WINDOW = 8  # frames per temporal window
DEFAULT_EXPOSURE_JUMP = 12.0  # |window mean delta| above this = discontinuity
DEFAULT_FLICKER_SIGN_FLIPS = 4  # delta sign flips inside one window = flicker
DEFAULT_NOISE_MEAN = 25.0  # window noise metric above this = noise burst
DEFAULT_SUSTAINED_FRACTION = 0.25  # affected windows / total -> BLOCKING

# Content-metric thresholds (deterministic pass/fail, Stage K §3 item 3).
LIP_SYNC_MIN_CORRELATION = 0.5
IDENTITY_MAX_DRIFT = 0.15
OCCLUSION_MAX_MEAN = 0.85
CONTINUITY_MAX_BREAKS = 2
MOTION_MAX_JITTER = 0.35  # std of frame-to-frame motion deltas
LIGHTING_MAX_EXCURSION = 12.0  # mean luma excursion across shot
CAMERA_MAX_SPEED = 1.5  # scene units per frame


@dataclass(frozen=True)
class ReviewFinding:
    """One structured finding (Stage K §3 post-render item 5)."""

    code: str
    severity: str
    entity: str
    frame_range: Optional[Tuple[int, int]] = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    suggested_repair: str = ""
    causes: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "entity": self.entity,
            "frame_range": list(self.frame_range) if self.frame_range else None,
            "evidence": dict(self.evidence),
            "confidence": self.confidence,
            "suggested_repair": self.suggested_repair,
            "causes": list(self.causes),
        }


@dataclass(frozen=True)
class TechnicalReviewPolicy:
    """Gate thresholds + reviewer wiring for one engine boundary."""

    vram_budget_policy: Optional[VramBudgetPolicy] = None
    approved_addons: frozenset = frozenset()
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    required_dimensions: Tuple[str, ...] = REQUIRED_DIMENSIONS
    temporal_window: int = DEFAULT_TEMPORAL_WINDOW
    sustained_fraction: float = DEFAULT_SUSTAINED_FRACTION
    black_luma_mean: float = DEFAULT_BLACK_LUMA_MEAN
    exposure_jump: float = DEFAULT_EXPOSURE_JUMP
    flicker_sign_flips: int = DEFAULT_FLICKER_SIGN_FLIPS
    noise_mean: float = DEFAULT_NOISE_MEAN


# ---------------------------------------------------------------------------
# Pre-render gates (Stage K §3 pre-render)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PreRenderReviewResult:
    """Outcome of the deterministic pre-render gate bundle."""

    findings: Tuple[ReviewFinding, ...]
    blocked: bool = False

    def to_dict(self) -> dict:
        return {
            "blocked": self.blocked,
            "findings": [f.to_dict() for f in self.findings],
        }


class PreRenderReviewer:
    """Runs the deterministic pre-render checks; BLOCKING stops submission."""

    def __init__(self, policy: Optional[TechnicalReviewPolicy] = None) -> None:
        self._policy = policy or TechnicalReviewPolicy()

    # ------------------------------------------------------------------
    def _missing_object(self, manifest: Mapping[str, Any]) -> List[ReviewFinding]:
        findings = []
        registry = set(manifest.get("object_registry") or [])
        rig_ids = {
            str(rig.get("id") or "")
            for rig in (manifest.get("rigs") or [])
            if isinstance(rig, dict)
        }
        for obj in manifest.get("objects") or []:
            obj_id = str(obj.get("id") or "")
            rig_id = str(obj.get("rig") or "")
            if obj_id and obj_id not in registry:
                findings.append(
                    ReviewFinding(
                        code=FINDING_MISSING_OBJECT,
                        severity=SEVERITY_BLOCKING,
                        entity=obj_id,
                        evidence={"registry_members": len(registry)},
                        confidence=1.0,
                        suggested_repair=REPAIR_ASSET_REVISION,
                    )
                )
            if rig_id and rig_id not in rig_ids:
                findings.append(
                    ReviewFinding(
                        code=FINDING_MISSING_OBJECT,
                        severity=SEVERITY_BLOCKING,
                        entity=rig_id,
                        evidence={"kind": "rig"},
                        confidence=1.0,
                        suggested_repair=REPAIR_RIG_REPAIR,
                    )
                )
        return findings

    def _missing_texture(self, manifest: Mapping[str, Any]) -> List[ReviewFinding]:
        findings = []
        registry = set(manifest.get("texture_registry") or [])
        for tex in manifest.get("textures") or []:
            tex_id = str(tex.get("id") or "")
            if tex_id and tex_id not in registry:
                findings.append(
                    ReviewFinding(
                        code=FINDING_MISSING_TEXTURE,
                        severity=SEVERITY_BLOCKING,
                        entity=tex_id,
                        evidence={"registry_members": len(registry)},
                        confidence=1.0,
                        suggested_repair=REPAIR_ASSET_REVISION,
                    )
                )
        return findings

    def _broken_rig(self, manifest: Mapping[str, Any]) -> List[ReviewFinding]:
        findings = []
        for rig in manifest.get("rigs") or []:
            rig_id = str(rig.get("id") or "")
            joints = set(rig.get("joints") or [])
            skinned = bool(rig.get("skinned", True))
            missing = [j for j in REQUIRED_RIG_JOINTS if j not in joints]
            if missing or not skinned:
                findings.append(
                    ReviewFinding(
                        code=FINDING_BROKEN_RIG,
                        severity=SEVERITY_BLOCKING,
                        entity=rig_id,
                        evidence={
                            "missing_joints": missing,
                            "skinned": skinned,
                        },
                        confidence=1.0,
                        suggested_repair=REPAIR_RIG_REPAIR,
                    )
                )
        return findings

    def _frame_range(self, manifest: Mapping[str, Any]) -> List[ReviewFinding]:
        frame_range = manifest.get("frame_range") or []
        if len(frame_range) != 2:
            return []
        start, end = int(frame_range[0]), int(frame_range[1])
        if start < 1 or end < start:
            return [
                ReviewFinding(
                    code=FINDING_FRAME_RANGE,
                    severity=SEVERITY_BLOCKING,
                    entity="render",
                    evidence={"frame_range": [start, end]},
                    confidence=1.0,
                    suggested_repair=REPAIR_FRAME_RANGE_ADJUST,
                )
            ]
        return []

    def _camera_collision(self, manifest: Mapping[str, Any]) -> List[ReviewFinding]:
        camera = manifest.get("camera") or {}
        path = camera.get("path") or []
        characters = manifest.get("characters") or []
        bounds = []
        for char in characters:
            b = char.get("bounds") or {}
            bounds.append(
                {
                    "id": str(char.get("id") or ""),
                    "min_x": float(b.get("min_x", 0)),
                    "max_x": float(b.get("max_x", 0)),
                    "min_y": float(b.get("min_y", 0)),
                    "max_y": float(b.get("max_y", 0)),
                    "min_z": float(b.get("min_z", 0)),
                    "max_z": float(b.get("max_z", 0)),
                }
            )
        margin = float((camera.get("collision_margin") or DEFAULT_COLLISION_MARGIN))
        findings = []
        for point in path:
            frame = int(point.get("frame") or 0)
            x = float(point.get("x") or 0.0)
            y = float(point.get("y") or 0.0)
            z = float(point.get("z") or 0.0)
            for b in bounds:
                if (
                    b["min_x"] - margin <= x <= b["max_x"] + margin
                    and b["min_y"] - margin <= y <= b["max_y"] + margin
                    and b["min_z"] - margin <= z <= b["max_z"] + margin
                ):
                    findings.append(
                        ReviewFinding(
                            code=FINDING_CAMERA_COLLISION,
                            severity=SEVERITY_BLOCKING,
                            entity=str(b["id"]),
                            frame_range=(frame, frame),
                            evidence={
                                "camera_position": [x, y, z],
                                "character_bounds": {
                                    "min_x": b["min_x"],
                                    "max_x": b["max_x"],
                                    "min_y": b["min_y"],
                                    "max_y": b["max_y"],
                                    "min_z": b["min_z"],
                                    "max_z": b["max_z"],
                                },
                                "margin": margin,
                            },
                            confidence=1.0,
                            suggested_repair=REPAIR_CAMERA_RECOMPILE,
                        )
                    )
        return findings

    def _lighting(self, manifest: Mapping[str, Any]) -> List[ReviewFinding]:
        lights = manifest.get("lights") or []
        if not lights:
            return [
                ReviewFinding(
                    code=FINDING_LIGHTING,
                    severity=SEVERITY_BLOCKING,
                    entity="scene",
                    evidence={"light_count": 0},
                    confidence=1.0,
                    suggested_repair=REPAIR_LIGHTING_FIX,
                )
            ]
        findings = []
        for light in lights:
            intensity = float(light.get("intensity") or 0.0)
            if intensity < DEFAULT_LIGHT_INTENSITY_MIN:
                findings.append(
                    ReviewFinding(
                        code=FINDING_LIGHTING,
                        severity=SEVERITY_WARNING,
                        entity=str(light.get("id") or ""),
                        evidence={
                            "intensity": intensity,
                            "min_intensity": DEFAULT_LIGHT_INTENSITY_MIN,
                        },
                        confidence=0.9,
                        suggested_repair=REPAIR_LIGHTING_FIX,
                    )
                )
        return findings

    def _audio_timing(self, manifest: Mapping[str, Any]) -> List[ReviewFinding]:
        audio = manifest.get("audio") or {}
        frame_range = manifest.get("frame_range") or []
        frame_rate = float(audio.get("frame_rate") or 0.0)
        duration = float(audio.get("duration_seconds") or 0.0)
        if len(frame_range) != 2 or frame_rate <= 0:
            return []
        frames = int(frame_range[1]) - int(frame_range[0]) + 1
        required = frames / frame_rate
        if duration < required - DEFAULT_AUDIO_TIMING_TOLERANCE:
            return [
                ReviewFinding(
                    code=FINDING_AUDIO_TIMING,
                    severity=SEVERITY_BLOCKING,
                    entity="audio",
                    evidence={
                        "duration_seconds": duration,
                        "required_seconds": round(required, 3),
                        "frame_rate": frame_rate,
                        "frames": frames,
                    },
                    confidence=1.0,
                    suggested_repair=REPAIR_AUDIO_MIX,
                )
            ]
        return []

    def _approvals(self, manifest: Mapping[str, Any]) -> List[ReviewFinding]:
        findings = []
        for asset in manifest.get("assets") or []:
            asset_id = str(asset.get("id") or "")
            if not bool(asset.get("approved", True)):
                findings.append(
                    ReviewFinding(
                        code=FINDING_UNAPPROVED_ASSET,
                        severity=SEVERITY_BLOCKING,
                        entity=asset_id,
                        evidence={"approved": False},
                        confidence=1.0,
                        suggested_repair=REPAIR_ASSET_APPROVAL,
                    )
                )
        for addon in manifest.get("addons") or []:
            module_id = str(addon.get("module_id") or "")
            if module_id and module_id not in self._policy.approved_addons:
                findings.append(
                    ReviewFinding(
                        code=FINDING_UNAPPROVED_ADDON,
                        severity=SEVERITY_BLOCKING,
                        entity=module_id,
                        evidence={"approved_addons": sorted(self._policy.approved_addons)},
                        confidence=1.0,
                        suggested_repair=REPAIR_ASSET_APPROVAL,
                    )
                )
        return findings

    def _vram(self, manifest: Mapping[str, Any]) -> List[ReviewFinding]:
        vram_manifest = manifest.get("vram") or {}
        if not vram_manifest or self._policy.vram_budget_policy is None:
            return []
        try:
            resource = SceneResourceManifest.from_dict(vram_manifest)
        except (KeyError, TypeError, ValueError):
            return []
        decision = VramMitigationPlanner().plan(resource, self._policy.vram_budget_policy)
        if not decision.blocked:
            return []
        return [
            ReviewFinding(
                code=FINDING_VRAM_BUDGET,
                severity=SEVERITY_BLOCKING,
                entity="render",
                evidence={
                    "decision": decision.to_dict(),
                    "recommendation": decision.recommendation,
                },
                confidence=1.0,
                suggested_repair=REPAIR_VRAM_MITIGATION,
            )
        ]

    # ------------------------------------------------------------------
    def review(self, manifest: Mapping[str, Any]) -> PreRenderReviewResult:
        """Run every pre-render gate over one neutral scene/render manifest."""
        findings: List[ReviewFinding] = []
        for check in (
            self._missing_object,
            self._missing_texture,
            self._broken_rig,
            self._frame_range,
            self._camera_collision,
            self._lighting,
            self._audio_timing,
            self._approvals,
            self._vram,
        ):
            findings.extend(check(manifest))
        blocked = any(f.severity == SEVERITY_BLOCKING for f in findings)
        return PreRenderReviewResult(findings=tuple(findings), blocked=blocked)


# ---------------------------------------------------------------------------
# Post-render: frame integrity (Stage K §3 item 1)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FrameProbe:
    """Per-frame media probe (decode + dimension + black-frame signal)."""

    frame: int
    decodable: bool = True
    width: int = 0
    height: int = 0
    luma_mean: Optional[float] = None


class FrameIntegrityReviewer:
    """Frame count / decode / dimension / black / missing-range gate."""

    def __init__(self, policy: Optional[TechnicalReviewPolicy] = None) -> None:
        self._policy = policy or TechnicalReviewPolicy()

    def review(
        self,
        *,
        expected_start: int,
        expected_end: int,
        probes: Sequence[FrameProbe],
        expected_dimensions: Optional[Tuple[int, int]] = None,
    ) -> Tuple[ReviewFinding, ...]:
        findings: List[ReviewFinding] = []
        by_frame = {p.frame: p for p in probes}
        expected_frames = set(range(expected_start, expected_end + 1))
        present_frames = set(by_frame)

        # Missing ranges first (concrete frame list for the repair scope).
        missing = sorted(expected_frames - present_frames)
        if missing:
            findings.append(
                ReviewFinding(
                    code=FINDING_FRAME_MISSING_RANGE,
                    severity=SEVERITY_BLOCKING,
                    entity="render",
                    frame_range=(missing[0], missing[-1]),
                    evidence={"missing_frames": missing},
                    confidence=1.0,
                    suggested_repair=REPAIR_AFFECTED_FRAMES,
                )
            )

        # Count mismatch (redundant with missing ranges but explicit for gate).
        if len(present_frames) != len(expected_frames):
            findings.append(
                ReviewFinding(
                    code=FINDING_FRAME_COUNT,
                    severity=SEVERITY_BLOCKING,
                    entity="render",
                    evidence={
                        "expected": len(expected_frames),
                        "actual": len(present_frames),
                    },
                    confidence=1.0,
                    suggested_repair=REPAIR_AFFECTED_FRAMES,
                )
            )

        for frame in sorted(expected_frames & present_frames):
            probe = by_frame[frame]
            if not probe.decodable:
                findings.append(
                    ReviewFinding(
                        code=FINDING_FRAME_UNDECODABLE,
                        severity=SEVERITY_BLOCKING,
                        entity="render",
                        frame_range=(frame, frame),
                        evidence={"frame": frame},
                        confidence=1.0,
                        suggested_repair=REPAIR_AFFECTED_FRAMES,
                    )
                )
                continue
            if expected_dimensions and (probe.width, probe.height) != expected_dimensions:
                findings.append(
                    ReviewFinding(
                        code=FINDING_FRAME_DIMENSION,
                        severity=SEVERITY_BLOCKING,
                        entity="render",
                        frame_range=(frame, frame),
                        evidence={
                            "expected": list(expected_dimensions),
                            "actual": [probe.width, probe.height],
                        },
                        confidence=1.0,
                        suggested_repair=REPAIR_AFFECTED_FRAMES,
                    )
                )
            if (
                probe.luma_mean is not None
                and probe.luma_mean < self._policy.black_luma_mean
            ):
                findings.append(
                    ReviewFinding(
                        code=FINDING_FRAME_BLACK,
                        severity=SEVERITY_BLOCKING,
                        entity="render",
                        frame_range=(frame, frame),
                        evidence={
                            "frame": frame,
                            "luma_mean": probe.luma_mean,
                            "black_threshold": self._policy.black_luma_mean,
                        },
                        confidence=1.0,
                        suggested_repair=REPAIR_AFFECTED_FRAMES,
                    )
                )
        return tuple(findings)


# ---------------------------------------------------------------------------
# Post-render: temporal review (Stage K §3 item 2)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TemporalWindow:
    """One sliding temporal window over per-frame signals."""

    start: int
    end: int
    luma_mean: float
    luma_std: float
    sign_flips: int
    noise_mean: float


class TemporalReviewer:
    """Flicker / noise / exposure discontinuity over temporal windows."""

    def __init__(self, policy: Optional[TechnicalReviewPolicy] = None) -> None:
        self._policy = policy or TechnicalReviewPolicy()

    def _windows(
        self,
        luma: Mapping[int, float],
        noise: Mapping[int, float],
        window: int,
    ) -> List[TemporalWindow]:
        frames = sorted(luma)
        out: List[TemporalWindow] = []
        for i in range(0, max(1, len(frames) - window + 1), window):
            chunk = frames[i : i + window]
            if len(chunk) < 2:
                continue
            values = [luma[f] for f in chunk]
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            flips = sum(
                1
                for j in range(1, len(values) - 1)
                if (values[j] - values[j - 1]) * (values[j + 1] - values[j]) < 0
            )
            noise_vals = [noise.get(f, 0.0) for f in chunk]
            out.append(
                TemporalWindow(
                    start=chunk[0],
                    end=chunk[-1],
                    luma_mean=mean,
                    luma_std=math.sqrt(variance),
                    sign_flips=flips,
                    noise_mean=sum(noise_vals) / len(noise_vals),
                )
            )
        return out

    def review(
        self,
        *,
        luma: Mapping[int, float],
        noise: Optional[Mapping[int, float]] = None,
        window: Optional[int] = None,
    ) -> Tuple[ReviewFinding, ...]:
        """Detect flicker / noise / exposure discontinuity per window.

        A violation is BLOCKING when it is SUSTAINED (affected windows /
        total >= policy.sustained_fraction); transient violations stay
        WARNING so a single glitch frame does not kill a shot.
        """
        if not luma:
            return ()
        win = window or self._policy.temporal_window
        noise = noise or {}
        windows = self._windows(luma, noise, win)
        if not windows:
            return ()

        flicker_windows = [w for w in windows if w.sign_flips >= self._policy.flicker_sign_flips]
        noise_windows = [w for w in windows if w.noise_mean >= self._policy.noise_mean]
        exposure_windows = []
        for a, b in zip(windows, windows[1:]):
            if abs(b.luma_mean - a.luma_mean) >= self._policy.exposure_jump:
                exposure_windows.append(b)

        findings: List[ReviewFinding] = []
        total = len(windows)

        def _escalate(affected: int) -> str:
            return (
                SEVERITY_BLOCKING
                if affected / total >= self._policy.sustained_fraction
                else SEVERITY_WARNING
            )

        if flicker_windows:
            findings.append(
                ReviewFinding(
                    code=FINDING_FLICKER,
                    severity=_escalate(len(flicker_windows)),
                    entity="render",
                    frame_range=(
                        flicker_windows[0].start,
                        flicker_windows[-1].end,
                    ),
                    evidence={
                        "affected_windows": [
                            [w.start, w.end] for w in flicker_windows
                        ],
                        "window_size": win,
                        "sign_flips_threshold": self._policy.flicker_sign_flips,
                    },
                    confidence=round(
                        min(1.0, len(flicker_windows) / total + 0.5), 4
                    ),
                    suggested_repair=REPAIR_AFFECTED_FRAMES,
                )
            )
        if noise_windows:
            findings.append(
                ReviewFinding(
                    code=FINDING_NOISE,
                    severity=_escalate(len(noise_windows)),
                    entity="render",
                    frame_range=(noise_windows[0].start, noise_windows[-1].end),
                    evidence={
                        "affected_windows": [
                            [w.start, w.end] for w in noise_windows
                        ],
                        "noise_threshold": self._policy.noise_mean,
                    },
                    confidence=round(min(1.0, len(noise_windows) / total + 0.5), 4),
                    suggested_repair=REPAIR_AFFECTED_FRAMES,
                )
            )
        if exposure_windows:
            findings.append(
                ReviewFinding(
                    code=FINDING_EXPOSURE_DISCONTINUITY,
                    severity=_escalate(len(exposure_windows)),
                    entity="render",
                    frame_range=(
                        exposure_windows[0].start,
                        exposure_windows[-1].end,
                    ),
                    evidence={
                        "affected_windows": [
                            [w.start, w.end] for w in exposure_windows
                        ],
                        "jump_threshold": self._policy.exposure_jump,
                        "window_means": [
                            round(w.luma_mean, 3) for w in windows
                        ],
                    },
                    confidence=round(
                        min(1.0, len(exposure_windows) / total + 0.5), 4
                    ),
                    suggested_repair=REPAIR_LIGHTING_FIX,
                )
            )
        return tuple(findings)


# ---------------------------------------------------------------------------
# Post-render: content review (Stage K §3 item 3) - deterministic first,
# optional VLM port after; a VLM timeout is NEVER a PASS.
# ---------------------------------------------------------------------------
class VlmReviewError(Exception):
    """VLM port failed or timed out; must fail closed (never auto-pass)."""


@dataclass(frozen=True)
class ContentReviewResult:
    """Findings + the set of dimensions with deterministic coverage."""

    findings: Tuple[ReviewFinding, ...]
    covered_dimensions: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "covered_dimensions": list(self.covered_dimensions),
        }


class ContentReviewer:
    """Deterministic metrics per required dimension + optional VLM port."""

    def __init__(self, policy: Optional[TechnicalReviewPolicy] = None) -> None:
        self._policy = policy or TechnicalReviewPolicy()

    # -- deterministic metrics -----------------------------------------
    @staticmethod
    def _correlation(a: Sequence[float], b: Sequence[float]) -> float:
        if len(a) < 3 or len(a) != len(b):
            return 0.0
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        den = math.sqrt(
            sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)
        )
        return num / den if den else 0.0

    @staticmethod
    def _std(values: Sequence[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))

    def review(
        self,
        *,
        signals: Mapping[str, Sequence[float]],
        vlm_outcome: Optional[dict] = None,
    ) -> ContentReviewResult:
        """Run deterministic metrics; merge an optional VLM outcome.

        ``signals`` keys (per dimension, deterministic metric first):
        - lip_sync:   audio_envelope, mouth_open  -> correlation
        - identity:   identity_score              -> drift (std)
        - occlusion:  occlusion_score             -> mean
        - continuity: continuity_breaks           -> count
        - motion:     motion_magnitude            -> jitter (std of deltas)
        - lighting:   luma_mean                   -> max excursion
        - camera:     camera_speed                -> max speed

        Returns findings + the dimensions that actually had deterministic
        signal coverage; dimensions without coverage can NOT be approved
        (decide_verdict treats them as REQUIRES_HUMAN).
        """
        findings: List[ReviewFinding] = []
        covered: set[str] = set()

        # Lip-sync: facial-only repair scope, never a whole-shot retake.
        if "audio_envelope" in signals and "mouth_open" in signals:
            covered.add(DIM_LIP_SYNC)
            corr = self._correlation(
                signals["audio_envelope"], signals["mouth_open"]
            )
            if corr < LIP_SYNC_MIN_CORRELATION:
                findings.append(
                    ReviewFinding(
                        code=FINDING_LIP_SYNC,
                        severity=SEVERITY_BLOCKING,
                        entity="facial",
                        evidence={
                            "correlation": round(corr, 4),
                            "min_correlation": LIP_SYNC_MIN_CORRELATION,
                        },
                        confidence=round(min(1.0, 1.0 - corr + 0.5), 4),
                        suggested_repair=REPAIR_FACIAL_ONLY,
                        causes=("audio_alignment", "facial_animation"),
                    )
                )

        if "identity_score" in signals:
            covered.add(DIM_IDENTITY)
            drift = self._std(list(signals["identity_score"]))
            if drift > IDENTITY_MAX_DRIFT:
                findings.append(
                    ReviewFinding(
                        code=FINDING_IDENTITY,
                        severity=SEVERITY_BLOCKING,
                        entity="character",
                        evidence={
                            "identity_drift": round(drift, 4),
                            "max_drift": IDENTITY_MAX_DRIFT,
                        },
                        confidence=round(min(1.0, drift / IDENTITY_MAX_DRIFT), 4),
                        suggested_repair=REPAIR_ASSET_REVISION,
                        causes=("asset_revision", "lighting_change", "facial_animation"),
                    )
                )

        if "occlusion_score" in signals:
            covered.add(DIM_OCCLUSION)
            mean_occ = sum(signals["occlusion_score"]) / len(signals["occlusion_score"])
            if mean_occ > OCCLUSION_MAX_MEAN:
                findings.append(
                    ReviewFinding(
                        code=FINDING_OCCLUSION,
                        severity=SEVERITY_BLOCKING,
                        entity="camera",
                        evidence={
                            "mean_occlusion": round(mean_occ, 4),
                            "max_mean": OCCLUSION_MAX_MEAN,
                        },
                        confidence=round(min(1.0, mean_occ / OCCLUSION_MAX_MEAN), 4),
                        suggested_repair=REPAIR_CAMERA_RECOMPILE,
                        causes=("camera_angle", "prop_placement", "character_blocking"),
                    )
                )

        if "continuity_breaks" in signals:
            covered.add(DIM_CONTINUITY)
            breaks = sum(1 for v in signals["continuity_breaks"] if v > 0)
            if breaks > CONTINUITY_MAX_BREAKS:
                findings.append(
                    ReviewFinding(
                        code=FINDING_CONTINUITY,
                        severity=SEVERITY_BLOCKING,
                        entity="scene",
                        evidence={
                            "break_count": breaks,
                            "max_breaks": CONTINUITY_MAX_BREAKS,
                        },
                        confidence=0.9,
                        suggested_repair=REPAIR_HUMAN_REVIEW,
                        causes=("prop_state", "character_blocking", "camera_angle"),
                    )
                )

        if "motion_magnitude" in signals:
            covered.add(DIM_MOTION_QUALITY)
            deltas = [
                abs(b - a)
                for a, b in zip(signals["motion_magnitude"], signals["motion_magnitude"][1:])
            ]
            jitter = self._std(deltas) if deltas else 0.0
            if jitter > MOTION_MAX_JITTER:
                findings.append(
                    ReviewFinding(
                        code=FINDING_MOTION_QUALITY,
                        severity=SEVERITY_BLOCKING,
                        entity="animation",
                        evidence={
                            "jitter": round(jitter, 4),
                            "max_jitter": MOTION_MAX_JITTER,
                        },
                        confidence=round(min(1.0, jitter / MOTION_MAX_JITTER), 4),
                        suggested_repair=REPAIR_AFFECTED_FRAMES,
                        causes=("animation_layer", "retarget_error", "constraint_drift"),
                    )
                )

        if "luma_mean" in signals:
            covered.add(DIM_LIGHTING)
            excursion = max(signals["luma_mean"]) - min(signals["luma_mean"])
            if excursion > LIGHTING_MAX_EXCURSION:
                findings.append(
                    ReviewFinding(
                        code=FINDING_LIGHTING_DRIFT,
                        severity=SEVERITY_BLOCKING,
                        entity="lighting",
                        evidence={
                            "excursion": round(excursion, 4),
                            "max_excursion": LIGHTING_MAX_EXCURSION,
                        },
                        confidence=round(min(1.0, excursion / LIGHTING_MAX_EXCURSION), 4),
                        suggested_repair=REPAIR_LIGHTING_FIX,
                    )
                )

        if "camera_speed" in signals:
            covered.add(DIM_CAMERA_COMPLIANCE)
            top = max(signals["camera_speed"])
            if top > CAMERA_MAX_SPEED:
                findings.append(
                    ReviewFinding(
                        code=FINDING_CAMERA_COMPLIANCE,
                        severity=SEVERITY_BLOCKING,
                        entity="camera",
                        evidence={
                            "max_speed": top,
                            "limit": CAMERA_MAX_SPEED,
                        },
                        confidence=round(min(1.0, top / CAMERA_MAX_SPEED), 4),
                        suggested_repair=REPAIR_CAMERA_RECOMPILE,
                    )
                )

        # Optional VLM port: merge a structured outcome. A timeout/error is
        # represented by the CALLER as vlm_outcome={"timed_out": True}; the
        # reviewer converts it to a low-confidence finding so the verdict is
        # REQUIRES_HUMAN, never APPROVE (Stage K test matrix: reviewer/VLM
        # timeout must not become PASS).
        if vlm_outcome:
            if vlm_outcome.get("timed_out") or vlm_outcome.get("error"):
                findings.append(
                    ReviewFinding(
                        code=FINDING_VLM_TIMEOUT,
                        severity=SEVERITY_WARNING,
                        entity="render",
                        evidence={
                            "error": str(vlm_outcome.get("error") or "timeout"),
                            "dimension": str(vlm_outcome.get("dimension") or "all"),
                        },
                        confidence=0.0,
                        suggested_repair=REPAIR_HUMAN_REVIEW,
                    )
                )
            else:
                findings.append(
                    ReviewFinding(
                        code=str(vlm_outcome.get("code") or "VLM_FINDING"),
                        severity=str(
                            vlm_outcome.get("severity") or SEVERITY_WARNING
                        ),
                        entity=str(vlm_outcome.get("entity") or "render"),
                        evidence=dict(vlm_outcome.get("evidence") or {}),
                        confidence=float(vlm_outcome.get("confidence") or 0.0),
                        suggested_repair=str(
                            vlm_outcome.get("suggested_repair") or REPAIR_HUMAN_REVIEW
                        ),
                    )
                )
        return ContentReviewResult(
            findings=tuple(findings), covered_dimensions=tuple(sorted(covered))
        )


# ---------------------------------------------------------------------------
# Post-render: cross-shot continuity (Stage K §3 item 4) - comparisons ALWAYS
# pin character / location / lighting references.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ShotReviewContext:
    """One reviewed shot's pinned continuity references."""

    shot_id: str
    character_ref: str = ""
    location_ref: str = ""
    lighting_ref: str = ""
    identity_score: float = 1.0
    luma_mean: Optional[float] = None


class CrossShotReviewer:
    """Cross-shot comparison pinned to continuity references."""

    def review(
        self, shots: Sequence[ShotReviewContext]
    ) -> Tuple[ReviewFinding, ...]:
        findings: List[ReviewFinding] = []
        by_character: Dict[str, List[ShotReviewContext]] = {}
        by_location: Dict[str, List[ShotReviewContext]] = {}
        for shot in shots:
            if shot.character_ref:
                by_character.setdefault(shot.character_ref, []).append(shot)
            if shot.location_ref:
                by_location.setdefault(shot.location_ref, []).append(shot)

        # Identity continuity: same pinned character across shots must keep
        # a stable identity score (visual identity drift -> human review,
        # never auto-pass: creative conflict).
        for character, group in sorted(by_character.items()):
            if len(group) < 2:
                continue
            scores = [s.identity_score for s in group]
            drift = max(scores) - min(scores)
            if drift > IDENTITY_MAX_DRIFT:
                findings.append(
                    ReviewFinding(
                        code=FINDING_CROSS_SHOT_IDENTITY,
                        severity=SEVERITY_WARNING,
                        entity=character,
                        evidence={
                            "pinned_character_ref": character,
                            "shots": [s.shot_id for s in group],
                            "identity_scores": scores,
                            "drift": round(drift, 4),
                            "max_drift": IDENTITY_MAX_DRIFT,
                        },
                        confidence=round(min(1.0, drift / IDENTITY_MAX_DRIFT), 4),
                        suggested_repair=REPAIR_HUMAN_REVIEW,
                        causes=("asset_revision", "lighting_change", "facial_animation"),
                    )
                )

        # Location + lighting continuity: same pinned location must keep the
        # same lighting reference; a lighting-ref mismatch or mean-luma jump
        # is a creative/technical conflict -> human review.
        for location, group in sorted(by_location.items()):
            if len(group) < 2:
                continue
            refs = {s.lighting_ref for s in group}
            if len(refs) > 1:
                findings.append(
                    ReviewFinding(
                        code=FINDING_CROSS_SHOT_LIGHTING,
                        severity=SEVERITY_WARNING,
                        entity=location,
                        evidence={
                            "pinned_location_ref": location,
                            "shots": [s.shot_id for s in group],
                            "lighting_refs": sorted(refs),
                        },
                        confidence=0.8,
                        suggested_repair=REPAIR_LIGHTING_FIX,
                    )
                )
            lumas = [s.luma_mean for s in group if s.luma_mean is not None]
            if len(lumas) >= 2 and max(lumas) - min(lumas) > LIGHTING_MAX_EXCURSION:
                findings.append(
                    ReviewFinding(
                        code=FINDING_CROSS_SHOT_LOCATION,
                        severity=SEVERITY_WARNING,
                        entity=location,
                        evidence={
                            "pinned_location_ref": location,
                            "shots": [s.shot_id for s in group],
                            "luma_means": [round(v, 3) for v in lumas],
                            "max_excursion": LIGHTING_MAX_EXCURSION,
                        },
                        confidence=0.8,
                        suggested_repair=REPAIR_LIGHTING_FIX,
                    )
                )
        return tuple(findings)


# ---------------------------------------------------------------------------
# Verdict rule (Stage K §3 verdict rule)
# ---------------------------------------------------------------------------
def decide_verdict(
    findings: Sequence[ReviewFinding],
    *,
    covered_dimensions: Sequence[str] = (),
    required_dimensions: Optional[Sequence[str]] = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> Tuple[str, str]:
    """Stage K verdict rule: REJECT / REQUIRES_HUMAN / APPROVE.

    - any BLOCKING finding                              -> REJECT
    - no blocking but a low-confidence finding or a
      required dimension with no deterministic coverage -> REQUIRES_HUMAN
    - every required dimension passes deterministically -> APPROVE
    """
    findings = list(findings)
    if any(f.severity == SEVERITY_BLOCKING for f in findings):
        return VERDICT_REJECT, "blocking finding exists"
    # No blocking but findings remain (creative conflict, low confidence,
    # WARNING-class defect): human review, never auto-pass (Stage K §3 item 6).
    if findings:
        low = [f for f in findings if f.confidence < confidence_threshold]
        if low:
            return (
                VERDICT_REQUIRES_HUMAN,
                f"{len(low)} finding(s) below confidence "
                f"{confidence_threshold}",
            )
        return (
            VERDICT_REQUIRES_HUMAN,
            f"{len(findings)} non-blocking finding(s) need human review: "
            + ", ".join(f.code for f in findings),
        )
    # Required-dimension coverage: a required dimension with NO deterministic
    # evidence cannot pass (fail closed - a missing metric is not a pass).
    required = required_dimensions or REQUIRED_DIMENSIONS
    missing_dims = [d for d in required if d not in set(covered_dimensions)]
    if missing_dims:
        return (
            VERDICT_REQUIRES_HUMAN,
            f"required dimensions without deterministic coverage: {missing_dims}",
        )
    return VERDICT_APPROVE, "all required dimensions pass"


__all__ = [
    "TECHNICAL_REVIEW_SCHEMA_VERSION",
    "SEVERITY_BLOCKING",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "SEVERITIES",
    "VERDICT_REJECT",
    "VERDICT_REQUIRES_HUMAN",
    "VERDICT_APPROVE",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "REPAIR_ASSET_REVISION",
    "REPAIR_CAMERA_RECOMPILE",
    "REPAIR_FACIAL_ONLY",
    "REPAIR_AFFECTED_FRAMES",
    "REPAIR_AUDIO_MIX",
    "REPAIR_RIG_REPAIR",
    "REPAIR_FRAME_RANGE_ADJUST",
    "REPAIR_LIGHTING_FIX",
    "REPAIR_ASSET_APPROVAL",
    "REPAIR_VRAM_MITIGATION",
    "REPAIR_HUMAN_REVIEW",
    "DIM_IDENTITY",
    "DIM_LIP_SYNC",
    "DIM_OCCLUSION",
    "DIM_CONTINUITY",
    "DIM_MOTION_QUALITY",
    "DIM_LIGHTING",
    "DIM_CAMERA_COMPLIANCE",
    "REQUIRED_DIMENSIONS",
    "FINDING_MISSING_OBJECT",
    "FINDING_MISSING_TEXTURE",
    "FINDING_BROKEN_RIG",
    "FINDING_FRAME_RANGE",
    "FINDING_CAMERA_COLLISION",
    "FINDING_LIGHTING",
    "FINDING_AUDIO_TIMING",
    "FINDING_UNAPPROVED_ASSET",
    "FINDING_UNAPPROVED_ADDON",
    "FINDING_VRAM_BUDGET",
    "FINDING_FRAME_COUNT",
    "FINDING_FRAME_UNDECODABLE",
    "FINDING_FRAME_DIMENSION",
    "FINDING_FRAME_BLACK",
    "FINDING_FRAME_MISSING_RANGE",
    "FINDING_FLICKER",
    "FINDING_NOISE",
    "FINDING_EXPOSURE_DISCONTINUITY",
    "FINDING_VLM_TIMEOUT",
    "FINDING_LIP_SYNC",
    "FINDING_IDENTITY",
    "FINDING_OCCLUSION",
    "FINDING_CONTINUITY",
    "FINDING_MOTION_QUALITY",
    "FINDING_LIGHTING_DRIFT",
    "FINDING_CAMERA_COMPLIANCE",
    "FINDING_CROSS_SHOT_IDENTITY",
    "FINDING_CROSS_SHOT_LOCATION",
    "FINDING_CROSS_SHOT_LIGHTING",
    "ReviewFinding",
    "TechnicalReviewPolicy",
    "PreRenderReviewResult",
    "PreRenderReviewer",
    "FrameProbe",
    "FrameIntegrityReviewer",
    "TemporalWindow",
    "TemporalReviewer",
    "VlmReviewError",
    "ContentReviewResult",
    "ContentReviewer",
    "ShotReviewContext",
    "CrossShotReviewer",
    "decide_verdict",
]
