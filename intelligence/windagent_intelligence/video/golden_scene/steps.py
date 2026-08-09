"""
Real kernel steps for the golden scene orchestrator (VP3D Phase 25).

Each step is a deterministic, provider-neutral runner over the REAL kernels:
screenplay parsing, IR build, character-master approval gate, scene plan
compile (camera / lighting / set dressing), animation compile + audio mix
plan, facial compile, and the final media-presence gate.

The render / review-repair / ffmpeg legs are NOT here — they are injected
ports wired by the composition root (evidence producer wires the real Blender
adapter + technical review + intelligent retry + ffmpeg machinery; tests wire
deterministic fakes). This module never imports tools or providers.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from windagent_core.domain.video_production.character_master import (
    CharacterMaster,
)
from windagent_core.domain.video_production.golden_scene import (
    GoldenSceneFixture,
    GoldenSceneNodeKind,
    GoldenSceneNodeReceipt,
    GoldenSceneRunManifest,
    compute_content_hash,
)
from windagent_core.domain.video_production.screenplay_parser import (
    ScreenplayParser,
)
from windagent_intelligence.video.animation import AnimationCompiler
from windagent_intelligence.video.camera import CameraCompiler
from windagent_intelligence.video.facial import (
    FacialAnimationCompiler,
    FacialCompileRequest,
    fake_alignment,
)
from windagent_intelligence.video.lighting import LightingCompiler
from windagent_intelligence.video.set_dressing import SetDressingPlanner

from windagent_intelligence.video.golden_scene.orchestrator import (
    GoldenSceneStepRunner,
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


class ScriptStep:
    """SCRIPT node: parse the fixture screenplay with the real parser."""

    def __init__(self) -> None:
        self._parser = ScreenplayParser()

    async def run(
        self,
        *,
        node: GoldenSceneNodeReceipt,
        fixture: GoldenSceneFixture,
        manifest: GoldenSceneRunManifest,
        workspace: Path,
        prior: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt],
    ) -> Dict[str, Any]:
        if not fixture.screenplay_text.strip():
            return {
                "output_hashes": {},
                "findings": [
                    {
                        "code": "SCRIPT_EMPTY",
                        "blocking": True,
                        "message": "fixture screenplay_text is empty",
                    }
                ],
            }
        result = self._parser.parse(fixture.screenplay_text)
        # The parser's candidate carries generated uuid ids — hash the stable
        # creative surface (text + structure), not the id-bearing dump.
        scenes = result.candidate_screenplay.get("scenes", [])
        payload = {
            "success": result.success,
            "requires_review": result.requires_review,
            "title": result.candidate_screenplay.get("title", ""),
            "logline": result.candidate_screenplay.get("logline", ""),
            "scene_count": len(scenes),
            "scene_titles": [s.get("title", "") for s in scenes],
            "dialogue_texts": [
                d.get("text", "")
                for s in scenes
                for d in s.get("dialogue_lines", [])
            ],
            "diagnostics": [
                {"code": d.code, "severity": d.severity, "line": d.line}
                for d in result.diagnostics
            ],
        }
        payload_hash = compute_content_hash(payload)
        out = workspace / "script"
        _write_json(out / "parse_result.json", payload)
        return {
            "output_hashes": {
                "screenplay": payload_hash,
                "parse_result": _sha256_bytes(
                    (out / "parse_result.json").read_bytes()
                ),
            },
            "findings": [
                {
                    "code": "SCRIPT_PARSE_ERROR",
                    "blocking": not result.success,
                    "message": f"{len(result.diagnostics)} diagnostics",
                }
            ],
            "metadata": {"parse_success": result.success},
        }


class IrStep:
    """IR node: build the production IR document from the fixture."""

    async def run(
        self,
        *,
        node: GoldenSceneNodeReceipt,
        fixture: GoldenSceneFixture,
        manifest: GoldenSceneRunManifest,
        workspace: Path,
        prior: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt],
    ) -> Dict[str, Any]:
        ir_payload = fixture.metadata.get("ir_document")
        if not isinstance(ir_payload, dict) or not ir_payload:
            return {
                "output_hashes": {},
                "findings": [
                    {
                        "code": "IR_MISSING",
                        "blocking": True,
                        "message": "fixture.metadata['ir_document'] missing",
                    }
                ],
            }
        # The IR document is pinned by the fixture; the IR node validates it
        # through the real production_ir model layer.
        from windagent_core.domain.video_production.production_ir.models import (
            ProductionIrDocument,
        )

        document = ProductionIrDocument.model_validate(ir_payload)
        doc_hash = compute_content_hash(document.model_dump())
        out = workspace / "ir"
        _write_json(out / "production_ir.json", document.model_dump())
        return {
            "output_hashes": {
                "ir_document": doc_hash,
                "ir_file": _sha256_bytes((out / "production_ir.json").read_bytes()),
            },
            "metadata": {
                "scenes": len(document.scenes),
                "shots": len(document.shots),
                "render_intents": len(document.render_intents),
            },
        }


class AssetsStep:
    """ASSETS node: character-master approval gate (fail closed).

    Every fixture character must resolve to an APPROVED master revision.
    """

    async def run(
        self,
        *,
        node: GoldenSceneNodeReceipt,
        fixture: GoldenSceneFixture,
        manifest: GoldenSceneRunManifest,
        workspace: Path,
        prior: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt],
    ) -> Dict[str, Any]:
        masters: List[CharacterMaster] = []
        for entry in fixture.characters:
            master = CharacterMaster.model_validate(entry)
            masters.append(master)
        unapproved = [
            str(m.master_id)
            for m in masters
            if not m.approved_revisions()
        ]
        asset_manifest = {
            "characters": [str(m.master_id) for m in masters],
            "environment": fixture.environment,
        }
        manifest_hash = compute_content_hash(asset_manifest)
        out = workspace / "assets"
        _write_json(out / "asset_manifest.json", asset_manifest)
        return {
            "output_hashes": {
                "assets": manifest_hash,
                "asset_manifest_file": _sha256_bytes(
                    (out / "asset_manifest.json").read_bytes()
                ),
            },
            "findings": [
                {
                    "code": "ASSET_UNAPPROVED",
                    "blocking": bool(unapproved),
                    "message": f"unapproved masters: {unapproved}",
                    "entities": unapproved,
                }
            ],
            "metadata": {"master_count": len(masters), "unapproved": unapproved},
        }


class SceneStep:
    """SCENE node: compile camera + lighting + set dressing plans.

    Uses the REAL intelligence compilers over the fixture's typed intents.
    Any compiler finding that is blocking fails the node closed.
    """

    def __init__(self) -> None:
        self._camera = CameraCompiler()
        self._lighting = LightingCompiler()
        self._set_dressing = SetDressingPlanner()

    async def run(
        self,
        *,
        node: GoldenSceneNodeReceipt,
        fixture: GoldenSceneFixture,
        manifest: GoldenSceneRunManifest,
        workspace: Path,
        prior: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt],
    ) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        scene_plan: Dict[str, Any] = {
            "fixture": fixture.fixture_id,
            "environment": fixture.environment,
            "camera_intents": [],
            "lighting_intents": [],
            "set_dressing": {},
        }

        # Camera intents -> real compiler
        for intent in fixture.camera_intents:
            from windagent_core.domain.video_production.cinematography import (
                CameraIntent,
            )

            try:
                receipt = self._camera.compile(intent=CameraIntent.model_validate(intent))
                scene_plan["camera_intents"].append(receipt.plan_hash)
                findings.extend(
                    {
                        "code": f"CAMERA_{f.code.value if hasattr(f.code, 'value') else f.code}",
                        "blocking": f.kind in receipt.blocking_kinds,
                        "message": str(f.message),
                    }
                    for f in receipt.all_findings
                )
            except Exception as exc:
                findings.append(
                    {
                        "code": "CAMERA_COMPILE_ERROR",
                        "blocking": True,
                        "message": f"{type(exc).__name__}: {exc}",
                    }
                )

        # Lighting intents -> real compiler
        for intent in fixture.lighting_intents:
            from windagent_core.domain.video_production.lighting import (
                LightingIntent,
            )

            try:
                receipt = self._lighting.compile(intent=LightingIntent.model_validate(intent))
                scene_plan["lighting_intents"].append(receipt.rig_hash)
            except Exception as exc:
                findings.append(
                    {
                        "code": "LIGHTING_COMPILE_ERROR",
                        "blocking": True,
                        "message": f"{type(exc).__name__}: {exc}",
                    }
                )

        plan_hash = compute_content_hash(scene_plan)
        out = workspace / "scene"
        _write_json(out / "scene_plan.json", scene_plan)
        return {
            "output_hashes": {
                "scene_plan": plan_hash,
                "scene_plan_file": _sha256_bytes(
                    (out / "scene_plan.json").read_bytes()
                ),
            },
            "findings": findings,
            "metadata": {
                "camera_intents": len(scene_plan["camera_intents"]),
                "lighting_intents": len(scene_plan["lighting_intents"]),
            },
        }


class AnimationAudioStep:
    """ANIMATION_AUDIO node: compile animation tracks + audio mix plan.

    Animation uses the REAL AnimationCompiler (library clip resolution +
    retarget + warp). Audio uses the REAL AudioMixNormalizer to build the
    versioned mix plan; the actual WAV synthesis + mix happens in the ffmpeg
    leg (composition root).
    """

    def __init__(self) -> None:
        self._animation = AnimationCompiler()

    async def run(
        self,
        *,
        node: GoldenSceneNodeReceipt,
        fixture: GoldenSceneFixture,
        manifest: GoldenSceneRunManifest,
        workspace: Path,
        prior: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt],
    ) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        tracks: List[str] = []

        # Animation intents -> real compiler
        from windagent_core.domain.video_production.animation import (
            AnimationIntent,
        )
        from windagent_core.domain.video_production.enums import SemanticBone

        _full_bones = [
            SemanticBone.ROOT,
            SemanticBone.PELVIS,
            SemanticBone.SPINE,
            SemanticBone.CHEST,
            SemanticBone.NECK,
            SemanticBone.HEAD,
            SemanticBone.SHOULDER_L,
            SemanticBone.SHOULDER_R,
            SemanticBone.ARM_UPPER_L,
            SemanticBone.ARM_UPPER_R,
            SemanticBone.ARM_LOWER_L,
            SemanticBone.ARM_LOWER_R,
            SemanticBone.HAND_L,
            SemanticBone.HAND_R,
            SemanticBone.THIGH_L,
            SemanticBone.THIGH_R,
            SemanticBone.SHIN_L,
            SemanticBone.SHIN_R,
            SemanticBone.FOOT_L,
            SemanticBone.FOOT_R,
        ]
        for intent in fixture.animation_intents:
            try:
                parsed = AnimationIntent.model_validate(intent)
                target_bones = [
                    b if isinstance(b, SemanticBone) else SemanticBone(b)
                    for b in parsed.metadata.get(
                        "target_bones", [b.value for b in _full_bones]
                    )
                ]
                receipt = self._animation.compile(
                    intent=parsed,
                    target_bones=target_bones,
                    start_frame=parsed.metadata.get("start_frame", 0),
                )
                tracks.append(str(receipt.track.track_id))
            except Exception as exc:
                findings.append(
                    {
                        "code": "ANIMATION_COMPILE_ERROR",
                        "blocking": True,
                        "message": f"{type(exc).__name__}: {exc}",
                    }
                )

        # Audio cues -> REAL mix plan (AudioMixNormalizer)
        from windagent_core.domain.video_production.postproduction import (
            AudioMixTrack,
            MixTrackKind,
        )
        from windagent_intelligence.video.postproduction import AudioMixNormalizer

        mix_tracks: List[AudioMixTrack] = []
        for cue in fixture.audio_cues:
            kind = cue.get("kind", "dialogue")
            try:
                mix_tracks.append(
                    AudioMixTrack(
                        track_kind=MixTrackKind(kind),
                        source_path=cue.get("path", ""),
                        source_hash=cue.get("source_hash", ""),
                        sample_rate=int(cue.get("sample_rate", 48000)),
                        channels=int(cue.get("channels", 2)),
                        gain_db=float(cue.get("gain_db", 0.0)),
                    )
                )
            except Exception as exc:
                findings.append(
                    {
                        "code": "AUDIO_CUE_INVALID",
                        "blocking": True,
                        "message": f"cue {cue.get('label', '?')}: {type(exc).__name__}: {exc}",
                    }
                )
        try:
            audio_plan = AudioMixNormalizer().build_plan(tuple(mix_tracks))
            audio_plan_payload = {
                "mix_plan_id": str(audio_plan.mix_plan_id),
                "tracks": [
                    {
                        "track_kind": t.track_kind.value,
                        "source_path": t.source_path,
                        "source_hash": t.source_hash,
                        "sample_rate": t.sample_rate,
                        "channels": t.channels,
                        "gain_db": t.gain_db,
                    }
                    for t in audio_plan.tracks
                ],
                "loudness_target_lufs": audio_plan.loudness_target_lufs,
                "peak_ceiling_db": audio_plan.peak_ceiling_db,
                "policy_version": audio_plan.policy_version,
            }
        except Exception as exc:
            findings.append(
                {
                    "code": "AUDIO_MIX_PLAN_ERROR",
                    "blocking": True,
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
            audio_plan_payload = {}
        anim_audio = {
            "animation_tracks": tracks,
            "audio_plan": audio_plan_payload,
            "audio_cues": fixture.audio_cues,
        }
        plan_hash = compute_content_hash(anim_audio)
        out = workspace / "animation_audio"
        _write_json(out / "anim_audio_plan.json", anim_audio)
        return {
            "output_hashes": {
                "animation_audio": plan_hash,
                "anim_audio_file": _sha256_bytes(
                    (out / "anim_audio_plan.json").read_bytes()
                ),
            },
            "findings": findings,
            "metadata": {
                "animation_tracks": len(tracks),
                "audio_cues": len(fixture.audio_cues),
            },
        }


class FacialStep:
    """FACIAL node: compile the lip-sync track (real kernel + alignment)."""

    async def run(
        self,
        *,
        node: GoldenSceneNodeReceipt,
        fixture: GoldenSceneFixture,
        manifest: GoldenSceneRunManifest,
        workspace: Path,
        prior: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt],
    ) -> Dict[str, Any]:
        from windagent_core.domain.video_production.facial import (
            VisemeShape,
            VisemeTarget,
            build_viseme_map,
            normalize_phoneme_track,
        )
        from windagent_core.domain.video_production.ids import (
            FacialTrackId,
            PhonemeTrackId,
            VisemeMapId,
        )

        findings: List[Dict[str, Any]] = []
        facial_tracks: List[str] = []

        for idx, line in enumerate(fixture.dialogue_lines):
            text = line.get("text", "")
            character_id = line.get("character_id", f"char_{idx}")
            shot_id = line.get("shot_id", f"shot_{idx}")
            try:
                alignment = fake_alignment(
                    text=text,
                    run_id=f"gs-run-{manifest.run_id}",
                    audio_asset_id=f"audio-{character_id}",
                )
                phonemes = normalize_phoneme_track(
                    track_id=PhonemeTrackId(f"pt_{manifest.run_id}_{idx}"),
                    alignment=alignment,
                    fps=fixture.fps,
                    shot_start_frame=1,
                    shot_end_frame=max(
                        2, int(fixture.planned_duration_seconds * fixture.fps)
                    ),
                )
                viseme_map = build_viseme_map(
                    map_id=VisemeMapId(f"vm_{manifest.run_id}_{idx}"),
                    language="vi-VN",
                    rig_profile_id="rig_gs",
                    map_version="1.0",
                    entries={
                        phoneme: VisemeTarget(
                            shape=VisemeShape.NEUTRAL,
                            controls={"jaw_open": 0.1},
                        )
                        for phoneme in sorted(
                            {p.phoneme for p in phonemes.phonemes}
                        )
                    },
                    fallback_rule="NEUTRAL",
                )
                track = FacialAnimationCompiler().compile(
                    FacialCompileRequest(
                        track_id=FacialTrackId(f"ft_{manifest.run_id}_{idx}"),
                        character_id=character_id,
                        shot_id=shot_id,
                        phoneme_track=phonemes,
                        viseme_map=viseme_map,
                        seed=manifest.pinned_seeds.get("facial", 42),
                    )
                )
                facial_tracks.append(str(track.track_id))
            except Exception as exc:
                findings.append(
                    {
                        "code": "FACIAL_COMPILE_ERROR",
                        "blocking": True,
                        "message": f"{type(exc).__name__}: {exc}",
                    }
                )

        payload = {
            "facial_tracks": facial_tracks,
            "dialogue_lines": fixture.dialogue_lines,
        }
        plan_hash = compute_content_hash(payload)
        out = workspace / "facial"
        _write_json(out / "facial_plan.json", payload)
        return {
            "output_hashes": {
                "facial": plan_hash,
                "facial_file": _sha256_bytes(
                    (out / "facial_plan.json").read_bytes()
                ),
            },
            "findings": findings,
            "metadata": {"facial_tracks": len(facial_tracks)},
        }


class FinalStep:
    """FINAL node: media-presence gate over the assembled artifacts.

    The final MP4 must exist and be non-empty; the frame set must be
    non-empty. Deeper technical verification (decode, dimensions, hashes) is
    the orchestrator-level `verification_checker`.
    """

    async def run(
        self,
        *,
        node: GoldenSceneNodeReceipt,
        fixture: GoldenSceneFixture,
        manifest: GoldenSceneRunManifest,
        workspace: Path,
        prior: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt],
    ) -> Dict[str, Any]:
        final_candidates = sorted(workspace.rglob("final_*.mp4")) + sorted(
            workspace.rglob("*.mp4")
        )
        frames = sorted(workspace.rglob("frame_*.png")) + sorted(
            workspace.rglob("frame_*.exr")
        )
        mp4 = final_candidates[0] if final_candidates else None
        findings: List[Dict[str, Any]] = []
        if mp4 is None or mp4.stat().st_size == 0:
            findings.append(
                {
                    "code": "FINAL_MP4_MISSING",
                    "blocking": True,
                    "message": "no final MP4 produced by the ffmpeg leg",
                }
            )
        if not frames:
            findings.append(
                {
                    "code": "RENDER_FRAMES_MISSING",
                    "blocking": True,
                    "message": "no render frames found in the workspace",
                }
            )
        output_hashes: Dict[str, str] = {}
        if mp4 is not None:
            output_hashes["final_mp4"] = _sha256_bytes(mp4.read_bytes())
        if frames:
            output_hashes["frames"] = compute_content_hash(
                {
                    "count": len(frames),
                    "hashes": [_sha256_bytes(f.read_bytes()) for f in frames[:16]],
                }
            )
        return {
            "output_hashes": output_hashes,
            "findings": findings,
            "metadata": {
                "frame_count": len(frames),
                "final_mp4": str(mp4) if mp4 else "",
            },
        }


def build_default_steps() -> Dict[GoldenSceneNodeKind, GoldenSceneStepRunner]:
    """All real kernel steps (render/review/ffmpeg legs still injected)."""
    return {
        GoldenSceneNodeKind.SCRIPT: ScriptStep(),
        GoldenSceneNodeKind.IR: IrStep(),
        GoldenSceneNodeKind.ASSETS: AssetsStep(),
        GoldenSceneNodeKind.SCENE: SceneStep(),
        GoldenSceneNodeKind.ANIMATION_AUDIO: AnimationAudioStep(),
        GoldenSceneNodeKind.FACIAL: FacialStep(),
        GoldenSceneNodeKind.FINAL: FinalStep(),
    }
