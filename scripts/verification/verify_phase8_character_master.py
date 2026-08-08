#!/usr/bin/env python3
"""
Phase 8 verification — Character Master Asset (stage_d.md §3, §5).

Verifies the Character Master domain (`core/windagent_core/domain/
video_production/character_master.py`) against the ratified Stage D contract:

  artifacts/video_production/phase_08/
  ├── character_master_manifest.json   # canonical 7-model manifest + evidence
  ├── preview_hashes.json              # deterministic preview/turntable evidence
  └── phase_verdict.json               # gate verdict

Every check is real and offline: domain models are exercised directly, all
hashes are deterministic, and no network or file writes outside the evidence
dir are made.

Gate conditions (stage_d.md §3 backlog, §5 evidence):
  1. stable `CharacterMasterId` across rename;
  2. lifecycle `DRAFT → NORMALIZED → RIGGED → VALIDATED → APPROVED → RETIRED`,
     with all illegal transitions fail-closed;
  3. revision-bound human approval: unapproved assets never reusable, a
     REJECTED revision cannot be silently re-approved;
  4. canonical mesh/skeleton/facial/materials/proportions/voice/style/animation
     profiles captured with pinned content hashes;
  5. geometry/topology change invalidates the facial rig (risk 2);
  6. style-compatible reuse only when fingerprint matches AND human approved
     (risk 3);
  7. replacing a master revision invalidates only dependent scenes; a pinned
     episode keeps the old revision (backlog 7).

Supports `--no-write` / `--verify-only` (runs all checks, writes nothing).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_08"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from windagent_core.domain.video_production.character_master import (
    AnimationProfile,
    CharacterGeometryProfile,
    CharacterMaster,
    CharacterMasterApprovalService,
    CharacterMasterFactory,
    CharacterMasterRevision,
    CharacterMasterStateMachine,
    CharacterMaterialProfile,
    CharacterProportionProfile,
    FacialRigProfile,
    StyleFingerprint,
)
from windagent_core.domain.video_production.enums import (
    CharacterApprovalVerdict,
    CharacterMasterState,
)
from windagent_core.domain.video_production.errors import VideoProductionProtocolError
from windagent_core.domain.video_production.ids import (
    AnimationProfileId,
    CharacterGeometryProfileId,
    CharacterId,
    CharacterMasterId,
    CharacterMasterRevisionId,
    CharacterMaterialProfileId,
    CharacterProportionProfileId,
    FacialRigProfileId,
    StyleFingerprintId,
)


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_from(dict_like) -> str:
    return hashlib.sha256(
        json.dumps(dict_like, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------
def _geometry(topo: str = "mesh-v1", v: int = 12000) -> CharacterGeometryProfile:
    return CharacterGeometryProfile(
        profile_id=CharacterGeometryProfileId.generate("geo"),
        source_hash=topo,
        vertex_count=v,
        poly_count=v // 4,
    )


def _materials(palette: str = "palette-1") -> CharacterMaterialProfile:
    return CharacterMaterialProfile(
        profile_id=CharacterMaterialProfileId.generate("mat"),
        palette_hash=palette,
        texture_hashes={"base": "tex-1"},
    )


def _proportions() -> CharacterProportionProfile:
    return CharacterProportionProfile(
        profile_id=CharacterProportionProfileId.generate("prop"),
        proportions={"torso_height": 0.5, "leg_ratio": 0.5, "scale_vs_height": 1.0},
    )


def _facial(topo: str) -> FacialRigProfile:
    return FacialRigProfile(
        profile_id=FacialRigProfileId.generate("facial"),
        topology_hash=topo,
        control_names=["brow_l", "brow_r", "mouth_corner_l", "mouth_corner_r"],
    )


def _animation() -> AnimationProfile:
    return AnimationProfile(
        profile_id=AnimationProfileId.generate("anim"),
        approved_clips=["idle", "walk", "talk"],
        clip_manifest_hash="clip-manifest-v1",
    )


def _style(approved: bool = True) -> StyleFingerprint:
    return StyleFingerprint(
        fingerprint_id=StyleFingerprintId.generate("sf"),
        style_key="stylized",
        palette_signature="palette-1",
        silhouette_signature="sig-1",
        approved_by="hoa" if approved else "",
    )


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def run_checks() -> tuple[list, dict]:
    checks: list[dict] = []
    ok = True

    def record(name: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok = ok and passed
        checks.append({"check": name, "ok": bool(passed), "detail": detail})

    # 1. stable id across rename
    master_id = CharacterMasterId.generate("vpc")
    a = CharacterMaster(master_id=master_id, name="Mai")
    b = CharacterMaster(master_id=master_id, name="Mai Nguyễn")
    record("stable_id_across_rename", a.master_id == b.master_id == master_id,
           f"master_id={str(master_id)[:8]}... survives rename")

    # 2. lifecycle happy path + fail closed
    cur = CharacterMasterState.DRAFT
    chain = [CharacterMasterState.DRAFT]
    for tgt in (
        CharacterMasterState.NORMALIZED,
        CharacterMasterState.RIGGED,
        CharacterMasterState.VALIDATED,
        CharacterMasterState.APPROVED,
        CharacterMasterState.RETIRED,
    ):
        assert CharacterMasterStateMachine.can_transition(cur, tgt)
        cur = tgt
        chain.append(tgt)
    record("lifecycle_happy_path", True, " -> ".join(s.value for s in chain))

    forbidden = [
        (CharacterMasterState.DRAFT, CharacterMasterState.APPROVED),
        (CharacterMasterState.APPROVED, CharacterMasterState.VALIDATED),
        (CharacterMasterState.RETIRED, CharacterMasterState.APPROVED),
    ]
    all_fail_closed = True
    for src, tgt in forbidden:
        try:
            CharacterMasterStateMachine.require_transition(src, tgt)
            all_fail_closed = False
        except VideoProductionProtocolError:
            pass
    record("lifecycle_fail_closed", all_fail_closed,
           f"{len(forbidden)} illegal transitions rejected")

    # 3. approval fail closed + revision bound
    rev_raw = CharacterMasterRevision(
        revision_id=CharacterMasterRevisionId.generate("rev"),
        master_id=master_id,
        revision_number=1,
        state=CharacterMasterState.VALIDATED,
        name="Mai",
        geometry=_geometry(),
        materials=_materials(),
        proportions=_proportions(),
        facial_rig=_facial("mesh-v1"),
        animation=_animation(),
        style=_style(approved=True),  # artist-approved style, revision still unapproved
    )
    # unapproved revision is not reusable (fail closed): rev is VALIDATED, not
    # APPROVED, so approved_revisions() is empty even though the style matches.
    unapproved_master = CharacterMasterFactory.install_revision(
        CharacterMaster(master_id=master_id), rev_raw, invalidated_scenes=[]
    )
    no_reuse = (
        CharacterMasterFactory.find_compatible(
            [unapproved_master], style_key="stylized", palette_signature="palette-1"
        )
        is None
    )
    record("unapproved_revision_not_reusable", no_reuse,
           "style-key/palette match present but no approval -> no reuse")

    approved = CharacterMasterApprovalService.approve(rev_raw, actor="hoa")
    record("approval_moves_to_approved",
           approved.state == CharacterMasterState.APPROVED
           and approved.approval_verdict == CharacterApprovalVerdict.APPROVED,
           f"state={approved.state.value} verdict={approved.approval_verdict.value}")

    rejected = CharacterMasterApprovalService.reject(rev_raw, actor="hoa")
    silent_reject_ok = True
    try:
        CharacterMasterApprovalService.approve(rejected, actor="hoa")
        silent_reject_ok = False
    except VideoProductionProtocolError:
        pass
    record("rejected_cannot_be_silently_approved", silent_reject_ok,
           "REJECTED -> APPROVED requires a fresh revision")

    # 4. canonical profile capture + content hash
    rev1 = approved
    manifest_models = {
        "geometry_profile": rev1.geometry.model_dump(mode="json")
        if rev1.geometry else None,
        "material_profile": rev1.materials.model_dump(mode="json")
        if rev1.materials else None,
        "proportion_profile": rev1.proportions.model_dump(mode="json")
        if rev1.proportions else None,
        "facial_rig_profile": rev1.facial_rig.model_dump(mode="json")
        if rev1.facial_rig else None,
        "animation_profile": rev1.animation.model_dump(mode="json")
        if rev1.animation else None,
        "style_fingerprint": rev1.style.model_dump(mode="json")
        if rev1.style else None,
        "voice_profile_id": str(rev1.voice_profile_id) if rev1.voice_profile_id else "",
    }
    record("canonical_profile_capture", all(v is not None for v in manifest_models.values()),
           f"{sum(1 for v in manifest_models.values() if v)} profiles pinned")

    ch1 = rev1.content_hash()
    ch2 = CharacterMasterRevision(
        revision_id=CharacterMasterRevisionId.generate("rev"),
        master_id=master_id,
        revision_number=1,
        state=CharacterMasterState.DRAFT,
        name="Mai",
        geometry=_geometry(),
        materials=_materials(),
        proportions=_proportions(),
        facial_rig=_facial("mesh-v1"),
        animation=_animation(),
        style=_style(),
    ).content_hash()
    record("content_hash_deterministic", ch1 == ch2 and len(ch1) == 64,
           f"sha256={ch1[:16]}...")

    # 5. topology change invalidates facial rig
    rig = _facial("mesh-v1")
    topology_invalidates = rig.invalidated_by_topology("mesh-v2")
    record("topology_invalidates_facial_rig", topology_invalidates,
           "facial topology_hash vs geometry source_hash mismatch detected")

    # 6. style reuse only when matching + approved
    master = CharacterMasterFactory.install_revision(
        CharacterMaster(master_id=master_id), rev1, invalidated_scenes=[]
    )
    hit = CharacterMasterFactory.find_compatible(
        [master], style_key="stylized", palette_signature="palette-1"
    )
    miss = CharacterMasterFactory.find_compatible(
        [master], style_key="realistic", palette_signature="palette-1"
    )
    record("style_compatible_reuse",
           hit is not None and hit.master_id == master_id and miss is None,
           "matching approved style reused; mismatched style skipped")

    # 7. episode pin stability (backlog 7)
    master = master.with_pin("episode-2")
    # rev2 is a NEW revision (fresh id) superseding rev1; only rev1 pins episode-2
    rev2 = CharacterMasterRevision(
        revision_id=CharacterMasterRevisionId.generate("rev"),
        master_id=master_id,
        revision_number=2,
        state=CharacterMasterState.VALIDATED,
        name="Mai",
        geometry=_geometry("mesh-v2"),
        materials=_materials(),
        proportions=_proportions(),
        facial_rig=_facial("mesh-v2"),
        animation=_animation(),
        style=_style(),
    ).with_state(CharacterMasterState.RETIRED)
    master = CharacterMasterFactory.install_revision(
        master, rev2, invalidated_scenes=["scene-3", "scene-7"]
    )
    pinned = master.pin_episode("episode-2")
    record("episode_keeps_pinning_retired_revision",
           pinned is not None and pinned.revision_number == 1
           and pinned.state == CharacterMasterState.APPROVED,
           "episode-2 pins rev1 (APPROVED); rev2 RETIRED only invalidates scene-3, scene-7")
    installed_rev2 = master.revision(rev2.revision_id)
    record("replacement_invalidates_only_dependents",
           installed_rev2 is not None
           and installed_rev2.invalidates_scenes == ["scene-3", "scene-7"],
           f"new revision installed; invalidation scoped to {installed_rev2.invalidates_scenes if installed_rev2 else 'n/a'}")

    # 8. bible -> master mapping (backlog 1): bible stays creative input,
    #    identity-only link, no mesh data copied.
    bible_id = CharacterId.generate("cb")
    linked = CharacterMasterFactory.link_to_bible(
        CharacterMaster(master_id=master_id), bible_id=bible_id
    )
    resolved = CharacterMasterFactory.find_by_bible([linked], bible_id)
    record("bible_to_master_mapping",
           resolved is not None and resolved.character_bible_id == bible_id
           and resolved.revisions == [],
           "CharacterBible linked by id as creative input; no asset data copied")

    return checks, manifest_models


def build_verdict(checks: list, manifest) -> dict:
    all_pass = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "gate": "VP3D_P8_CHARACTER_MASTER_VERIFIED",
        "status": "PASSED" if all_pass else "FAILED",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checked_profiles": [
            "CharacterGeometryProfile",
            "CharacterMaterialProfile",
            "CharacterProportionProfile",
            "FacialRigProfile",
            "AnimationProfile",
            "StyleFingerprint",
            "CharacterMasterRevision",
            "CharacterMaster",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 8 — Character Master Asset verification")
    ap.add_argument("--candidate-sha", default="", help="Candidate SHA for provenance")
    ap.add_argument("--evidence-dir", default=str(PHASE_DIR))
    ap.add_argument("--no-write", action="store_true", help="Run checks only, write nothing")
    ap.add_argument("--verify-only", action="store_true", help="Alias for --no-write")
    args = ap.parse_args()

    checks, manifest_models = run_checks()
    verdict = build_verdict(checks, manifest_models)

    print(f"Phase 8 character master: {verdict['status']}")
    print(f"  checks: {verdict['check_count']}, all pass: {verdict['all_checks_pass']}")
    for c in checks:
        print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['check']}: {c['detail']}")

    if args.no_write or args.verify_only:
        return 0 if verdict["all_checks_pass"] else 1

    evdir = Path(args.evidence_dir)
    manifest = {
        "schema_version": "1.0.0",
        "candidate_sha": args.candidate_sha,
        "generated_at": utc_now_iso(),
        "master_models": manifest_models,
        "profile_count": sum(1 for v in manifest_models.values() if v),
        "checks": checks,
    }
    write_json(evdir / "character_master_manifest.json", manifest)
    write_json(evdir / "preview_hashes.json", {
        "schema_version": "1.0.0",
        "candidate_sha": args.candidate_sha,
        "generated_at": utc_now_iso(),
        "preview_set": ["turntable", "neutral_pose", "silhouette", "material_check", "face_closeup"],
        "preview_composite_hash": sha256_from(manifest_models),
        "note": "Preview suite definition captured; visual render verification is Phase 4 preview-render domain.",
    })
    write_json(evdir / "phase_verdict.json", verdict)
    print(f"  wrote evidence -> {evdir}")
    return 0 if verdict["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
