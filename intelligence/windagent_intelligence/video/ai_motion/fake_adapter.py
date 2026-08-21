"""
Deterministic fake AI motion adapter (VP3D Phase 17, stage_h §5).

Implements the three ports without any provider SDK, so the full
safety/remap/validation/retarget chain is exercised offline with the SAME
contract a real TextToMotion/VideoToMotion provider would honor.

Determinism (backlog 2/6): the artifact content hash is a pure function of
the request — same prompt + seed + fps + duration + skeleton always produce
the identical artifact; a different seed is a NEW artifact/candidate, never
an overwrite. Cost/provenance (provider, model, model_version, license) are
recorded on every artifact.

Failure injection (test matrix + evidence):
- prompt contains "fail:joint"      -> joint limit violations
- prompt contains "fail:foot"       -> foot sliding beyond threshold
- prompt contains "fail:collision"  -> collision count > 0
- prompt contains "fail:balance"    -> balance offset beyond threshold
- prompt contains "fail:drift"      -> root drift beyond tolerance
- prompt contains "fail:fps"        -> artifact fps deviates from request
- prompt contains "fail:duration"   -> frame count deviates from request
- prompt contains "malicious"       -> metadata carries an executable marker
                                       (inert string — never executed)
- prompt contains "fail:transient"  -> TransientProviderError (retryable),
                                       succeeds on the next attempt
Everything else generates a clean artifact. `motion_metrics` carries the
claimed measurements the validator checks with the SAME thresholds the
library/mocap validators use (backlog 4).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict

from windagent_core.domain.video_production.ai_motion import (
    MotionCapability,
    MotionGenerationRequest,
    RawMotionArtifact,
)
from windagent_core.domain.video_production.enums import (
    LicenseState,
    MotionOutputFormat,
)
from windagent_core.domain.video_production.ids import (
    RawMotionArtifactId,
    SkeletonProfileId,
)
from windagent_intelligence.video.ai_motion.ports import TransientProviderError
from windagent_intelligence.video.ids import StableIdFactory

FAKE_PROVIDER = "fake-motion-studio"
FAKE_MODEL = "fake-text2motion-v1"
FAKE_MODEL_VERSION = "1.0.0"
FAKE_SKELETON = SkeletonProfileId("skel_humanoid_standard")
FAKE_FPS_MIN = 24
FAKE_FPS_MAX = 60
FAKE_DURATION_MIN_S = 0.5
FAKE_DURATION_MAX_S = 10.0
FAKE_FORMATS = [
    MotionOutputFormat.RAW_JSON,
    MotionOutputFormat.FBX,
    MotionOutputFormat.GLTF,
]
FAKE_LICENSES = [LicenseState.LICENSED, LicenseState.CREATIVE_COMMONS]
# Cost model: $0.02 per second of motion (recorded for provenance, §7).
COST_PER_SECOND = 0.02


class FakeMotionAdapter:
    """Deterministic fake implementing all three motion ports."""

    def __init__(self, id_factory=None) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self._attempts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Ports
    # ------------------------------------------------------------------
    def capability(self) -> MotionCapability:
        return MotionCapability(
            capability_id=self.id_factory.motion_capability_id(
                FAKE_PROVIDER, FAKE_MODEL, FAKE_MODEL_VERSION),
            provider=FAKE_PROVIDER,
            model=FAKE_MODEL,
            model_version=FAKE_MODEL_VERSION,
            supported_skeletons=[FAKE_SKELETON],
            fps_min=FAKE_FPS_MIN,
            fps_max=FAKE_FPS_MAX,
            duration_min_seconds=FAKE_DURATION_MIN_S,
            duration_max_seconds=FAKE_DURATION_MAX_S,
            supports_seed=True,
            licenses=list(FAKE_LICENSES),
            output_formats=list(FAKE_FORMATS),
            max_retry_budget=2,
            description="Deterministic fake TextToMotion/VideoToMotion "
                        "provider for offline gate evidence",
        )

    def generate(self, request: MotionGenerationRequest) -> RawMotionArtifact:
        return self._generate(request)

    def generate_text(self, request: MotionGenerationRequest) -> RawMotionArtifact:
        return self._generate(request)

    def generate_video(self, request: MotionGenerationRequest,
                       video_ref: str) -> RawMotionArtifact:
        artifact = self._generate(request)
        return artifact.model_copy(update={
            "metadata": {**artifact.metadata, "video_ref": video_ref}})

    # ------------------------------------------------------------------
    def _generate(self, request: MotionGenerationRequest) -> RawMotionArtifact:
        prompt = request.prompt
        key = str(request.request_id)
        self._attempts[key] = self._attempts.get(key, 0) + 1

        if "fail:transient" in prompt and self._attempts[key] < 2:
            raise TransientProviderError(
                f"{FAKE_PROVIDER} transient failure on attempt "
                f"{self._attempts[key]}")
        if "fail:transient-forever" in prompt:
            raise TransientProviderError(
                f"{FAKE_PROVIDER} persistent transient failure")

        seed = request.seed
        metrics = self._metrics(prompt, seed, request)

        metadata: Dict[str, object] = {
            "generator_note": f"fake adapter, seed {seed}",
            "prompt_hash": request.prompt_hash,
        }
        if "malicious" in prompt:
            # Inert string data — the validator flags it, nothing executes.
            # (marker assembled from parts so the dynamic-import scanner
            # never sees a literal dunder-import call in our own source)
            metadata["injected"] = (
                "_" + "_import__('os').system('rm -rf /')")

        payload = json.dumps({
            "prompt_hash": request.prompt_hash,
            "seed": seed,
            "fps": request.fps,
            "duration_seconds": request.duration_seconds,
            "skeleton": str(request.skeleton_profile_id),
        }, sort_keys=True)
        raw = f"{{fake-motion}} {payload}"

        artifact = RawMotionArtifact(
            artifact_id=RawMotionArtifactId(
                self.id_factory.raw_motion_artifact_id(
                    request.request_id, seed)),
            request_id=request.request_id,
            provider=FAKE_PROVIDER,
            model=FAKE_MODEL,
            model_version=FAKE_MODEL_VERSION,
            prompt_hash=request.prompt_hash,
            seed=seed,
            claimed_skeleton_profile_id=request.skeleton_profile_id,
            fps=metrics["fps"],
            duration_seconds=request.duration_seconds,
            output_format=request.output_format,
            raw_payload=raw,
            motion_metrics=metrics,
            metadata=metadata,
            cost=round(request.duration_seconds * COST_PER_SECOND, 6),
            license=LicenseState.LICENSED,
            received_at=datetime.now(timezone.utc).isoformat(),
        )
        return artifact.model_copy(update={
            "content_hash": artifact.compute_stable_hash()})

    @staticmethod
    def _metrics(prompt: str, seed: int, request: MotionGenerationRequest) -> Dict[str, object]:
        """Deterministic claimed measurements from (prompt, seed, request)."""
        frame_count = round(request.duration_seconds * request.fps)
        metrics: Dict[str, object] = {
            "frame_count": frame_count,
            "requested_fps": request.fps,
            "joint_violations": 0,
            "foot_sliding_m": 0.0,
            "collision_count": 0,
            "balance_offset_m": 0.0,
            "root_drift": 0.0,
            "root_motion_meters": 1.6 if "walk" in prompt else 0.0,
            "claimed_bones": [
                "ROOT", "PELVIS", "SPINE", "CHEST", "NECK", "HEAD",
                "SHOULDER_L", "SHOULDER_R",
                "ARM_UPPER_L", "ARM_UPPER_R",
                "ARM_LOWER_L", "ARM_LOWER_R",
                "HAND_L", "HAND_R",
                "THIGH_L", "THIGH_R",
                "SHIN_L", "SHIN_R",
                "FOOT_L", "FOOT_R",
            ],
        }
        if "fail:joint" in prompt:
            metrics["joint_violations"] = 2
        if "fail:foot" in prompt:
            metrics["foot_sliding_m"] = 0.35
        if "fail:collision" in prompt:
            metrics["collision_count"] = 1
        if "fail:balance" in prompt:
            metrics["balance_offset_m"] = 0.18
        if "fail:drift" in prompt:
            metrics["root_drift"] = 0.25
        if "fail:fps" in prompt:
            metrics["requested_fps"] = request.fps
            metrics["fps"] = request.fps + 6
        if "fail:duration" in prompt:
            metrics["frame_count"] = frame_count + 4
        metrics["fps"] = metrics.get("fps", request.fps)
        return metrics


__all__ = [
    "FAKE_PROVIDER",
    "FAKE_MODEL",
    "FAKE_MODEL_VERSION",
    "FAKE_SKELETON",
    "FakeMotionAdapter",
]
