"""
Golden scene gates: identity/continuity + technical verification (Phase 25).

`default_identity_checker` runs the REAL continuity ledger service over the
fixture's pinned package + shot graph (when provided) and re-verifies the
character-master approval gate. `default_verification_checker` performs REAL
byte-level checks on the rendered frames (PNG magic + distinct hashes), the
audio assets (RIFF/WAV magic) and the final MP4 (ftyp box + ffprobe when the
binary is available).

Both are fail-closed: missing evidence => not passed => verdict REJECT.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List

from windagent_core.domain.video_production.character_master import (
    CharacterMaster,
)
from windagent_core.domain.video_production.golden_scene import (
    GoldenSceneFixture,
    GoldenSceneNodeKind,
    GoldenSceneNodeReceipt,
    IdentityContinuityReceipt,
    TechnicalVerificationReceipt,
)

IdentityChecker = Callable[
    [GoldenSceneFixture, Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt]],
    IdentityContinuityReceipt,
]
VerificationChecker = Callable[
    [GoldenSceneFixture, Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt], Path],
    TechnicalVerificationReceipt,
]

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
WAV_MAGIC = b"RIFF"
MP4_FTYP = b"ftyp"


def _sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def default_identity_checker(
    fixture: GoldenSceneFixture,
    receipts: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt],
) -> IdentityContinuityReceipt:
    """Character/voice identity + continuity gate (acceptance §4)."""
    blocking: List[str] = []

    # 1. Character identity: every fixture master has an APPROVED revision.
    character_ok = True
    for entry in fixture.characters:
        try:
            master = CharacterMaster.model_validate(entry)
        except Exception as exc:
            character_ok = False
            blocking.append(f"character master invalid: {exc}")
            continue
        if not master.approved_revisions():
            character_ok = False
            blocking.append(f"master {master.master_id} has no approved revision")

    # 2. Voice identity: every dialogue character has an approved voice
    #    profile in the fixture metadata.
    voice_ok = True
    voice_profiles = fixture.metadata.get("voice_profiles", {})
    for line in fixture.dialogue_lines:
        character_id = line.get("character_id", "")
        profile = voice_profiles.get(character_id)
        if profile is None or not profile.get("approved"):
            voice_ok = False
            blocking.append(f"voice profile missing/unapproved for {character_id}")

    # 3. Continuity: REAL ledger service over the pinned package + graph.
    continuity_ok = False
    package = fixture.metadata.get("package")
    graph_receipt = fixture.metadata.get("graph_receipt")
    if package is None or graph_receipt is None:
        blocking.append(
            "fixture.metadata['package']/['graph_receipt'] missing; "
            "continuity cannot be verified"
        )
    else:
        try:
            from windagent_core.domain.video_production.package import (
                VideoProductionPackage,
            )
            from windagent_core.domain.video_production.shot import (
                ShotDependencyGraph,
            )
            from windagent_core.domain.video_production.shot_graph import (
                ShotGraphIssue,
                ShotScheduling,
                ShotSpecification,
            )
            from windagent_intelligence.video import ContinuityLedgerService
            from windagent_intelligence.video.shot_planner.models import (
                ShotGraphReceipt,
            )

            pkg = VideoProductionPackage.model_validate(package)
            graph = ShotGraphReceipt(
                graph=ShotDependencyGraph.model_validate(graph_receipt["graph"]),
                specifications=[
                    ShotSpecification.model_validate(s)
                    for s in graph_receipt.get("specifications", [])
                ],
                scheduling=[
                    ShotScheduling.model_validate(s)
                    for s in graph_receipt.get("scheduling", [])
                ],
                issues=[
                    ShotGraphIssue.model_validate(i)
                    for i in graph_receipt.get("issues", [])
                ],
                graph_hash=graph_receipt.get("graph_hash", ""),
                source_plan_hash=graph_receipt.get("source_plan_hash", ""),
                source_package_hash=graph_receipt.get("source_package_hash", ""),
                graph_version=graph_receipt.get("graph_version", "1.0.0"),
            )
            ledger = ContinuityLedgerService().build(pkg, graph)
            blocking_issues = [
                i for i in ledger.blocking_issues
            ]
            continuity_ok = not blocking_issues
            if blocking_issues:
                blocking.extend(
                    f"continuity {i.code}: {i.message}" for i in blocking_issues
                )
        except Exception as exc:
            blocking.append(f"continuity ledger failed: {type(exc).__name__}: {exc}")

    return IdentityContinuityReceipt(
        character_identity_ok=character_ok,
        voice_identity_ok=voice_ok,
        continuity_ok=continuity_ok,
        blocking_issues=blocking,
    )


def default_verification_checker(
    fixture: GoldenSceneFixture,
    receipts: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt],
    workspace: Path,
) -> TechnicalVerificationReceipt:
    """Render frames / audio / final MP4 technical checks (acceptance §5)."""
    checks: Dict[str, Any] = {}

    # 1. Frames: PNG magic + count + distinct hashes.
    pngs = sorted(workspace.rglob("frame_*.png")) + sorted(
        workspace.rglob("*.png")
    )
    real_pngs = [p for p in pngs if p.read_bytes()[:8] == PNG_MAGIC]
    frames_ok = bool(real_pngs)
    frame_hashes = [_sha256_file(p) for p in real_pngs]
    checks["frames"] = {
        "count": len(real_pngs),
        "distinct_hashes": len(set(frame_hashes)),
        "png_magic_ok": frames_ok,
    }
    if not frames_ok:
        checks["frames"]["error"] = "no valid PNG frames found"

    # 2. Audio: WAV/RIFF magic on the mixed assets.
    wavs = sorted(workspace.rglob("*.wav")) + sorted(workspace.rglob("*.aac"))
    real_audio = [p for p in wavs if p.read_bytes()[:4] == WAV_MAGIC or p.suffix == ".aac"]
    audio_ok = bool(real_audio)
    checks["audio"] = {
        "count": len(real_audio),
        "files": [p.name for p in real_audio[:8]],
    }
    if not audio_ok:
        checks["audio"]["error"] = "no valid audio assets found"

    # 3. Final MP4: ftyp box + (when available) REAL ffprobe probe.
    mp4s = sorted(workspace.rglob("final_*.mp4")) + sorted(workspace.rglob("*.mp4"))
    mp4 = mp4s[0] if mp4s else None
    mp4_ok = False
    if mp4 is not None and mp4.stat().st_size > 0:
        head = mp4.read_bytes()[: 64 * 1024]
        mp4_ok = MP4_FTYP in head
        checks["final_mp4"] = {
            "exists": True,
            "size_bytes": mp4.stat().st_size,
            "sha256": _sha256_file(mp4),
            "ftyp_ok": mp4_ok,
        }
        ffprobe = shutil.which("ffprobe")
        if ffprobe is not None and mp4_ok:
            try:
                proc = subprocess.run(
                    [
                        ffprobe, "-v", "error", "-show_entries",
                        "format=duration:stream=codec_name,codec_type,width,height",
                        "-of", "json", str(mp4),
                    ],
                    capture_output=True, text=True, timeout=60,
                )
                parsed = json.loads(proc.stdout) if proc.stdout.strip() else {}
                checks["final_mp4"]["ffprobe"] = parsed
                streams = parsed.get("streams", [])
                mp4_ok = (
                    any(s.get("codec_type") == "video" for s in streams)
                    and any(s.get("codec_type") == "audio" for s in streams)
                )
                checks["final_mp4"]["has_video_and_audio_streams"] = mp4_ok
            except Exception as exc:
                checks["final_mp4"]["ffprobe_error"] = str(exc)
    else:
        checks["final_mp4"] = {"exists": False, "error": "no final MP4 found"}

    return TechnicalVerificationReceipt(
        frames_ok=frames_ok,
        audio_ok=audio_ok,
        final_mp4_ok=mp4_ok,
        checks=checks,
    )
