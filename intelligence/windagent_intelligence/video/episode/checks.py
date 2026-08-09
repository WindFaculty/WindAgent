"""
Episode gates: identity/continuity + technical verification (VP3D Phase 26).

`episode_identity_checker` REUSES the Phase 25 golden-scene identity gate
(approved character masters + voice profiles + REAL continuity ledger over
the pinned package + shot graph) and adds the episode cross-scene check:
every character appearing in a scene must be part of the episode's approved
master set (structural identity across scenes).

`episode_verification_checker` checks per-scene render frames (PNG magic),
per-scene audio (RIFF/WAV magic), per-scene MP4 (ftyp + ffprobe when
available) and the episode media manifest (scene order == fixture order).

Both are fail-closed: missing evidence => not passed => verdict REJECT.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from windagent_core.domain.video_production.episode import (
    EpisodeFixture,
    EpisodeNodeReceipt,
)
from windagent_core.domain.video_production.golden_scene import (
    IdentityContinuityReceipt,
    TechnicalVerificationReceipt,
)
from windagent_intelligence.video.golden_scene.checks import (
    MP4_FTYP,
    PNG_MAGIC,
    WAV_MAGIC,
    default_identity_checker,
)


def _sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def episode_identity_checker(
    fixture: EpisodeFixture,
    receipts: Dict[str, EpisodeNodeReceipt],
) -> IdentityContinuityReceipt:
    """Character/voice identity + cross-scene continuity (backlog 2)."""
    # Reuse the golden-scene gate: approved masters + voice profiles + real
    # continuity ledger over the pinned package + shot graph.
    base = default_identity_checker(fixture, receipts)
    blocking: List[str] = list(base.blocking_issues)

    # Episode cross-scene check: every scene's characters are part of the
    # episode character set (no scene invents a character).
    known = {str(c.get("master_id") or c.get("id") or "") for c in fixture.characters}
    cross_scene_ok = True
    for scene in fixture.scenes:
        for character_id in scene.character_ids:
            if character_id not in known:
                cross_scene_ok = False
                blocking.append(
                    f"scene {scene.scene_id} references unknown character "
                    f"{character_id}"
                )
    # Every scene must have at least one shot (continuity across shots).
    for scene in fixture.scenes:
        if not scene.shot_ids:
            cross_scene_ok = False
            blocking.append(f"scene {scene.scene_id} has no shots")

    return IdentityContinuityReceipt(
        character_identity_ok=base.character_identity_ok and cross_scene_ok,
        voice_identity_ok=base.voice_identity_ok,
        continuity_ok=base.continuity_ok,
        blocking_issues=blocking,
    )


def episode_verification_checker(
    fixture: EpisodeFixture,
    receipts: Dict[str, EpisodeNodeReceipt],
    workspace: Path,
) -> TechnicalVerificationReceipt:
    """Per-scene frames/audio/MP4 + episode media order (backlog 2/5)."""
    checks: Dict[str, Any] = {}
    workspace = Path(workspace)

    scenes = fixture.ordered_scenes()
    scene_ids = [str(s.scene_id) for s in scenes]

    frames_ok = True
    audio_ok = True
    mp4_ok = True
    per_scene: Dict[str, Any] = {}
    for scene_id in scene_ids:
        scene_dir = workspace / scene_id
        pngs = sorted(scene_dir.rglob("frame_*.png"))
        real_pngs = [p for p in pngs if p.read_bytes()[:8] == PNG_MAGIC]
        wavs = sorted(scene_dir.rglob("*.wav")) + sorted(scene_dir.rglob("*.aac"))
        real_audio = [
            p for p in wavs if p.read_bytes()[:4] == WAV_MAGIC or p.suffix == ".aac"
        ]
        mp4s = sorted(scene_dir.rglob("scene_*.mp4")) + sorted(scene_dir.rglob("*.mp4"))
        mp4 = mp4s[0] if mp4s else None
        mp4_valid = False
        ffprobe: Dict[str, Any] = {}
        if mp4 is not None and mp4.stat().st_size > 0:
            head = mp4.read_bytes()[: 64 * 1024]
            mp4_valid = MP4_FTYP in head
            ffprobe_bin = shutil.which("ffprobe")
            if ffprobe_bin is not None and mp4_valid:
                try:
                    proc = subprocess.run(
                        [
                            ffprobe_bin, "-v", "error",
                            "-show_entries",
                            "format=duration:stream=codec_name,codec_type,width,height",
                            "-of", "json", str(mp4),
                        ],
                        capture_output=True, text=True, timeout=60,
                    )
                    parsed = json.loads(proc.stdout) if proc.stdout.strip() else {}
                    ffprobe = parsed
                    streams = parsed.get("streams", [])
                    mp4_valid = (
                        any(s.get("codec_type") == "video" for s in streams)
                        and any(s.get("codec_type") == "audio" for s in streams)
                    )
                except Exception as exc:
                    checks[f"scene_{scene_id}_ffprobe_error"] = str(exc)
        scene_frames_ok = bool(real_pngs)
        scene_audio_ok = bool(real_audio)
        frames_ok = frames_ok and scene_frames_ok
        audio_ok = audio_ok and scene_audio_ok
        mp4_ok = mp4_ok and mp4_valid
        per_scene[scene_id] = {
            "frames": len(real_pngs),
            "frames_ok": scene_frames_ok,
            "audio": len(real_audio),
            "audio_ok": scene_audio_ok,
            "mp4": mp4.name if mp4 else "",
            "mp4_ok": mp4_valid,
            "ffprobe": ffprobe,
        }

    # Episode media manifest: scene order must match the fixture order.
    manifest_path = workspace / "final" / "episode_media_manifest.json"
    ordering_ok = False
    manifest: Dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError:
            manifest = {}
    manifest_order = manifest.get("scene_order", [])
    ordering_ok = manifest_order == scene_ids and bool(manifest.get("episode_media"))
    if not ordering_ok:
        checks["episode_ordering"] = {
            "ok": False,
            "error": "episode media manifest missing or out of order",
            "manifest_order": manifest_order,
            "fixture_order": scene_ids,
        }
    else:
        checks["episode_ordering"] = {
            "ok": True,
            "scene_order": manifest_order,
        }

    checks["scenes"] = per_scene
    return TechnicalVerificationReceipt(
        frames_ok=frames_ok,
        audio_ok=audio_ok,
        final_mp4_ok=mp4_ok,
        checks=checks,
    )
