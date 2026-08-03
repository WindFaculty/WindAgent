#!/usr/bin/env python3
"""
Phase 21 verification — VP21_AUDIO_PIPELINE_VERIFIED (remediation plan 08, R2).

Evidence-mode verifier (R0 contract):
  python verify_phase21_audio_pipeline.py --evidence-dir <dir> --candidate-sha <sha>
  python verify_phase21_audio_pipeline.py --write-fixture <tempdir>

The gate verdict is DERIVED from validated production evidence, never from
hard-coded booleans. The old deterministic dialogue/TTS/alignment/mix checks
survive as a `CONTRACT_TESTED` workstream (plan §2) — they are written only
via --write-fixture into a temporary directory and never drive the production
verdict.

Production evidence required (plan §12/§13, gate VP21):
  audio_production_receipt.json  — real provider/voice + rights/consent +
                                   asset SHA-256 + alignment + loudness facts.
Without an approved provider/voice and real TTS run this gate is BLOCKED.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_DIR = ROOT / "artifacts" / "video_production" / "phase_21"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verification import evidence_lib  # noqa: E402
from scripts.verification.evidence_lib import (  # noqa: E402
    derive_verdict,
    load_json,
    parse_verifier_args,
    snapshot_dir,
    diff_snapshots,
    validate_evidence_manifest,
    validate_production_receipt,
    write_json,
)


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CONTRACT_TESTED workstream (plan §2 — fixtures stay in CI, never a verdict)
# ---------------------------------------------------------------------------

def contract_workstreams() -> dict[str, dict]:
    """Run the deterministic contract checks (fake TTS allowed here).

    Returns per-workstream receipts suitable for --write-fixture output. The
    results are reported as CONTRACT_TESTED, never as production PASSED.
    """
    from windagent_core.domain.video_production.audio import (
        AudioMixPlan,
        CharacterVoiceProfile,
        DialogueTrack,
        SoundEffectCue,
        TtsAudioAsset,
        WordTimestamp,
    )
    from windagent_core.domain.video_production.enums import (
        AudioAlignmentStatus,
        AudioCueKind,
        AudioInvalidationScope,
        LicenseState,
        VoiceRightsState,
    )
    from windagent_core.domain.video_production.ids import (
        AudioMixPlanId,
        CharacterId,
        CharacterVoiceProfileId,
        DialogueLineId,
        DialogueTrackId,
        SceneId,
        ShotId,
        SoundEffectCueId,
        TtsAudioAssetId,
        TtsRequestId,
        WordTimestampId,
    )
    from windagent_core.domain.video_production.screenplay import DialogueLine
    from windagent_intelligence.video.audio import (
        AlignmentService,
        DialoguePreparer,
        MixPlanner,
        TtsSynthesisRequest,
        TtsSynthesisResult,
        TtsSynthesizer,
        VoiceCastingService,
    )

    class _FakeTts:
        def __init__(self, *, timed_out=False, empty=False, invalid=False):
            self.timed_out = timed_out
            self.empty = empty
            self.invalid = invalid

        def synthesize(self, request: TtsSynthesisRequest) -> TtsSynthesisResult:
            if self.timed_out:
                return TtsSynthesisResult(request_id=str(request.request_id), timed_out=True)
            if self.empty:
                return TtsSynthesisResult(request_id=str(request.request_id))
            if self.invalid:
                return TtsSynthesisResult(
                    request_id=str(request.request_id),
                    content=b"x", sample_rate=0, channel_layout="", duration_seconds=0.0,
                )
            return TtsSynthesisResult(
                request_id=str(request.request_id),
                content=b"AUDIO" * 64, sample_rate=48000,
                channel_layout="stereo", duration_seconds=2.0,
                provider="flow", model="tts-v1", voice_id="v1",
            )

        async def asynthesize(self, request: TtsSynthesisRequest) -> TtsSynthesisResult:
            return self.synthesize(request)

    def _line(dlg_id, chr_id, text, delivery=""):
        return DialogueLine(
            dialogue_id=DialogueLineId(dlg_id), scene_id=SceneId("scn_1"),
            character_id=CharacterId(chr_id), order=1, text=text, delivery=delivery,
        )

    def _voice(profile_id, chr_id, *, voice_id="v1", approved=True,
               rights=VoiceRightsState.LICENSED):
        return CharacterVoiceProfile(
            profile_id=CharacterVoiceProfileId(profile_id),
            character_id=CharacterId(chr_id), voice_name=chr_id,
            provider="flow", model="tts-v1", voice_id=voice_id, voice_version="1",
            rights_state=rights, approved=approved, preview_only=not approved,
        )

    def _word(tid, word, start, end, conf=0.95):
        return WordTimestamp(
            timestamp_id=WordTimestampId(tid), word=word,
            start_seconds=start, end_seconds=end, confidence=conf,
        )

    def _track(dlg_id="dlg_1", audio_duration=2.0):
        asset = TtsAudioAsset(
            asset_id=TtsAudioAssetId(f"tsa_{dlg_id}"), content_hash="c" * 64,
            sample_rate=48000, channel_layout="stereo",
            duration_seconds=audio_duration, byte_size=100,
            source_request_hash="r" * 64,
        )
        return DialogueTrack(
            track_id=DialogueTrackId(f"dtr_{dlg_id}"),
            dialogue_id=DialogueLineId(dlg_id), character_id=CharacterId("chr_1"),
            text="hello", target_duration_seconds=2.0, audio=asset,
        )

    def _cue(*, licensed=True):
        return SoundEffectCue(
            cue_id=SoundEffectCueId("sfx_1"), kind=AudioCueKind.SFX,
            shot_id=ShotId("s1"), timeline_start_seconds=0.0,
            duration_seconds=1.0,
            license_state=LicenseState.LICENSED if licensed else LicenseState.UNKNOWN,
        )

    def _request(dlg_id="dlg_1", text="Xin chào"):
        req = TtsSynthesisRequest(
            request_id=TtsRequestId(f"ttr_{dlg_id}"), dialogue_id=dlg_id,
            text=text, voice_profile_hash="h" * 64,
        )
        return TtsSynthesisRequest(
            request_id=req.request_id, dialogue_id=req.dialogue_id,
            text=req.text, voice_profile_hash=req.voice_profile_hash,
            language=req.language, locale=req.locale,
            synthesis_params=req.synthesis_params,
            request_hash=req.compute_request_hash(),
        )

    def _checks() -> dict:
        checks = []
        prep = DialoguePreparer()
        receipt = prep.prepare([_line("dlg_1", "chr_1", "Xin chào, số 5. OK TV.")])
        checks.append(("number_expanded_in_prepared",
                       receipt.tracks and "5" not in receipt.tracks[0].prepared_text))
        checks.append(("original_text_preserved",
                       receipt.tracks and "5" in receipt.tracks[0].text))
        empty = prep.prepare([_line("dlg_e", "chr_1", "   ")])
        checks.append(("empty_line_is_issue",
                       empty.tracks == [] and any(i.code == "EMPTY_LINE" for i in empty.issues)))
        overlong = prep.prepare([_line("dlg_o", "chr_1", "a" * 500)])
        checks.append(("overlong_line_is_issue",
                       overlong.tracks == [] and any(i.code == "OVERLONG_LINE" for i in overlong.issues)))

        cast = VoiceCastingService()
        mapped = cast.cast(
            character_ids=["chr_A", "chr_B"], character_names={"chr_A": "A", "chr_B": "B"},
            catalog=[_voice("vpr_1", "chr_A", voice_id="va"), _voice("vpr_2", "chr_B", voice_id="vb")],
        )
        by_char = {str(p.character_id): p.voice_id for p in mapped.profiles}
        checks.append(("multi_character_mapping_never_swaps",
                       by_char.get("chr_A") == "va" and by_char.get("chr_B") == "vb"))

        synth = TtsSynthesizer()
        r1 = _request()
        r2 = _request()
        checks.append(("request_hash_deterministic",
                       r1.compute_request_hash() == r2.compute_request_hash()))
        valid = synth.synthesize(_FakeTts(), _request())
        checks.append(("valid_output_published", len(valid.assets) == 1))
        timeout = synth.synthesize(_FakeTts(timed_out=True), _request())
        checks.append(("timeout_never_published",
                       timeout.assets == [] and any(i.code == "TTS_TIMEOUT" for i in timeout.issues)))

        service = AlignmentService()
        low = service.align(
            [_track()], word_timestamps_by_track={"dlg_1": [_word("wt_1", "hello", 0.0, 0.5, conf=0.3)]},
        )
        checks.append(("low_confidence_routes_to_human",
                       low.tracks[0].alignment_status == AudioAlignmentStatus.LOW_CONFIDENCE))
        missing = service.align([_track()])
        checks.append(("audio_without_timestamps_is_finding",
                       any(i.code == "ALIGNMENT_MISSING" for i in missing.issues)))

        planner = MixPlanner()
        plan1, issues_ok = planner.plan(project_id="vp_1", revision_id="rev_1", dialogue_tracks=[])
        checks.append(("clean_mix_no_issues", issues_ok == []))
        _, bad_issues = planner.plan(
            project_id="vp_1", revision_id="rev_1", dialogue_tracks=[],
            sfx_cues=[_cue(licensed=False)],
        )
        checks.append(("unknown_license_blocks_mix",
                       any(i.code == "UNKNOWN_CUE_LICENSE" for i in bad_issues)))
        mix = AudioMixPlan(mix_id=AudioMixPlanId("amx_1"), project_id="vp_1", revision_id="rev_1")
        checks.append(("bgm_change_mix_only",
                       mix.invalidated_scope(AudioCueKind.BGM) == AudioInvalidationScope.MIX_ONLY))
        checks.append(("dialogue_change_track_and_mix",
                       mix.invalidated_scope("dialogue") == AudioInvalidationScope.TRACK_AND_MIX))

        return {
            "gate": "VP21_AUDIO_PIPELINE_VERIFIED",
            "tier": "CONTRACT_TESTED",
            "generated_at": utc_now_iso(),
            "checks": [{"check": c, "ok": bool(ok)} for c, ok in checks],
            "all_checks_pass": all(ok for _, ok in checks),
        }

    return {"contract_receipt": _checks()}


def write_fixtures(out_dir: Path) -> Path:
    """Write contract fixtures into `out_dir` (temp-only, never production)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, receipt in contract_workstreams().items():
        write_json(out_dir / f"{name}.json", receipt)
    verdict = {
        "gate": "VP21_AUDIO_PIPELINE_VERIFIED",
        "tier": "CONTRACT_TESTED",
        "status": "CONTRACT_TESTED",
        "note": "Fixture data only — not production evidence.",
        "generated_at": utc_now_iso(),
    }
    write_json(out_dir / "contract_verdict.json", verdict)
    return out_dir


# ---------------------------------------------------------------------------
# Production evidence validation (gate VP21)
# ---------------------------------------------------------------------------

REQUIRED_PRODUCTION_FILES = ("audio_production_receipt.json",)


def verify_production_evidence(
    evidence_dir: Path,
    candidate_sha: str | None,
) -> tuple[str, dict[str, bool], list[str]]:
    """Validate production evidence; returns (verdict, workstreams, reasons)."""
    workstreams: dict[str, bool] = {}
    reasons: list[str] = []

    if not evidence_dir.exists():
        return "BLOCKED", workstreams, ["evidence dir missing; no production evidence"]

    manifest = load_json(evidence_dir / "evidence_manifest.json")
    if manifest is None:
        reasons.append("missing evidence_manifest.json (content-addressed manifest required)")
        workstreams["evidence_manifest"] = False
    else:
        manifest_errors = validate_evidence_manifest(manifest, evidence_dir, candidate_sha=candidate_sha)
        workstreams["evidence_manifest"] = not manifest_errors
        reasons.extend(f"manifest: {e}" for e in manifest_errors)

    missing = [f for f in REQUIRED_PRODUCTION_FILES if not (evidence_dir / f).is_file()]
    for name in REQUIRED_PRODUCTION_FILES:
        path = evidence_dir / name
        if not path.is_file():
            reasons.append(f"missing production receipt: {name}")
            workstreams[name] = False
            continue
        receipt = load_json(path)
        errors = validate_production_receipt(receipt or {}, candidate_sha=candidate_sha)
        # Phase-specific semantic checks (plan §13).
        if receipt:
            if not isinstance(receipt.get("provider_request_hash"), str) or len(receipt.get("provider_request_hash", "")) != 64:
                errors.append("provider_request_hash must be a 64-hex real provider request hash")
            if not isinstance(receipt.get("consent_or_license_ref"), str) or not receipt["consent_or_license_ref"]:
                errors.append("consent_or_license_ref (redacted) is required")
            asset = receipt.get("asset")
            if not isinstance(asset, dict):
                errors.append("asset block missing")
            else:
                asset_file = evidence_dir / asset.get("locator", "")
                if not asset_file.is_file():
                    errors.append(f"asset file missing at locator {asset.get('locator')!r}")
                else:
                    media_errors = evidence_lib.validate_media_file(asset_file, expected_container="wav")
                    errors.extend(f"asset: {e}" for e in media_errors)
                    if not evidence_lib.is_sha256(asset.get("sha256")) or asset.get("sha256") != evidence_lib.sha256_file(asset_file):
                        errors.append("asset sha256 does not match the real file")
            if not isinstance(receipt.get("loudness_lufs"), (int, float)) or not isinstance(receipt.get("peak_db"), (int, float)):
                errors.append("loudness_lufs/peak_db must be real tool measurements")
        workstreams[name] = not errors
        reasons.extend(f"{name}: {e}" for e in errors)

    if missing:
        reasons.append(
            "no real TTS production evidence present — supply approved provider credentials "
            "and run the audio production pipeline (plan 08 R2)"
        )

    verdict = derive_verdict(workstreams=workstreams, blocking_reasons=reasons)
    return verdict, workstreams, reasons


def main() -> int:
    args = parse_verifier_args(
        sys.argv[1:],
        default_evidence_dir=DEFAULT_EVIDENCE_DIR,
        description="Phase 21 evidence-mode verifier (VP21_AUDIO_PIPELINE_VERIFIED)",
    )

    if not args.read_only:
        # Fixture mode: temp dir only (enforced by the parser).
        out = write_fixtures(args.write_fixture)
        print(f"CONTRACT_TESTED fixtures written to {out}")
        print("These fixtures are contract tests only — never production evidence.")
        return 0

    # Read-only production mode: snapshot, validate, prove immutability.
    before = snapshot_dir(args.evidence_dir)
    verdict, workstreams, reasons = verify_production_evidence(
        args.evidence_dir, args.candidate_sha
    )
    after = snapshot_dir(args.evidence_dir)
    mutations = diff_snapshots(before, after)
    if mutations:
        # A read-only verifier must NEVER mutate evidence (gate R0).
        verdict = "FAILED"
        reasons = [f"READ-ONLY VIOLATION: {m}" for m in mutations] + reasons
        print("READ-ONLY VIOLATION: verifier mutated evidence files!")

    print(f"Phase 21 verdict: {verdict}")
    for ws, ok in workstreams.items():
        print(f"  {ws}: {'PASS' if ok else 'FAIL'}")
    for reason in reasons:
        print(f"  REASON: {reason}")
    return 0 if verdict == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
