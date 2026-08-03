#!/usr/bin/env python3
"""
Phase 22 verification — VP22_POST_PRODUCTION_VERIFIED (remediation plan 08, R1).

Evidence-mode verifier (R0 contract):
  python verify_phase22_postproduction.py --evidence-dir <dir> --candidate-sha <sha>
  python verify_phase22_postproduction.py --write-fixture <tempdir>

Gate VP22 passes ONLY when the final media manifest points to a real MP4
container (validated by bytes + real ffprobe), every technical check passes,
and the output was produced by the real toolchain (plan §10). Missing
FFmpeg/ffprobe, unreadable media, mock payloads or out-of-policy duration are
FAILED/BLOCKED.

Required evidence (plan §10):
  toolchain_receipt.json       real ffmpeg/ffprobe path + version + binary SHA-256
  render_manifest.json         EDL + clip hashes + encoding profile
  ffmpeg_command_receipts/     real subprocess receipts (argv, exit code, hashes)
  ffprobe_raw.json             real ffprobe structured JSON
  media_decode_receipt.json    first/mid/last frame decode + duration/codec facts
  reproducibility_report.json  byte-identical or documented semantic reproducibility
  final_media_manifest.json    final MP4 locator + SHA-256 + verification status
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_DIR = ROOT / "artifacts" / "video_production" / "phase_22"

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

# 30–45 s is the POC scope (plan 08 §18); policy window with a small tolerance.
MIN_DURATION_SECONDS = 30.0
MAX_DURATION_SECONDS = 45.0


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_fixtures(out_dir: Path) -> Path:
    """Write CONTRACT_TESTED fixtures (temp-only). Never production evidence."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fixture = {
        "gate": "VP22_POST_PRODUCTION_VERIFIED",
        "tier": "CONTRACT_TESTED",
        "generated_at": utc_now_iso(),
        "note": "Deterministic EDL/normalization contract checks — fixture only.",
        "checks": {
            "edl_hash_determinism_64": True,
            "edl_duration_transition_overlap": True,
            "padding_spec_non_16x9": True,
            "ffmpeg_argv_no_shell": True,
        },
    }
    write_json(out_dir / "render_contract_fixture.json", fixture)
    write_json(out_dir / "contract_verdict.json", {
        "gate": "VP22_POST_PRODUCTION_VERIFIED",
        "tier": "CONTRACT_TESTED",
        "status": "CONTRACT_TESTED",
        "note": "Fixture data only — not production evidence.",
        "generated_at": utc_now_iso(),
    })
    return out_dir


# ---------------------------------------------------------------------------
# Production evidence validation (gate VP22)
# ---------------------------------------------------------------------------

REQUIRED_FILES = (
    "toolchain_receipt.json",
    "render_manifest.json",
    "ffprobe_raw.json",
    "media_decode_receipt.json",
    "reproducibility_report.json",
    "final_media_manifest.json",
)


def _validate_command_receipts(evidence_dir: Path, reasons: list[str]) -> bool:
    cmd_dir = evidence_dir / "ffmpeg_command_receipts"
    if not cmd_dir.is_dir():
        reasons.append("missing ffmpeg_command_receipts/ directory")
        return False
    receipts = sorted(cmd_dir.glob("*.json"))
    if not receipts:
        reasons.append("ffmpeg_command_receipts/ contains no receipts")
        return False
    ok = True
    for path in receipts:
        rec = load_json(path) or {}
        # Command receipt schema — derived from FfmpegCommandReceipt + §3 receipt.
        if not isinstance(rec.get("argv"), list) or not rec["argv"]:
            reasons.append(f"{path.name}: argv list missing")
            ok = False
        elif Path(rec["argv"][0]).stem not in ("ffmpeg", "ffprobe"):
            reasons.append(f"{path.name}: argv[0] must be ffmpeg/ffprobe")
            ok = False
        if rec.get("return_code") != 0:
            reasons.append(f"{path.name}: return_code != 0")
            ok = False
        if not isinstance(rec.get("execution_time_seconds"), (int, float)) or rec.get("execution_time_seconds", 0) <= 0:
            reasons.append(f"{path.name}: execution_time_seconds must be > 0 (real execution)")
            ok = False
        for key in ("input_hashes", "output_hash"):
            val = rec.get(key)
            if key == "input_hashes":
                if not isinstance(val, list) or not all(evidence_lib.is_sha256(h) for h in val):
                    reasons.append(f"{path.name}: {key} must be 64-hex list")
                    ok = False
            elif not evidence_lib.is_sha256(val):
                reasons.append(f"{path.name}: {key} must be 64-hex")
                ok = False
        if evidence_lib.is_mock_payload(path):
            reasons.append(f"{path.name}: receipt is a mock payload")
            ok = False
    return ok


def verify_production_evidence(
    evidence_dir: Path,
    candidate_sha: str | None,
) -> tuple[str, dict[str, bool], list[str]]:
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

    for name in REQUIRED_FILES:
        path = evidence_dir / name
        if not path.is_file():
            reasons.append(f"missing production receipt: {name}")
            workstreams[name] = False
            continue
        receipt = load_json(path)
        if name == "ffprobe_raw.json":
            # ffprobe_raw.json is the raw structured tool output (plan §9.4),
            # not a §3 production receipt — validate its structure instead.
            # Video + audio stream presence is the minimum proof the final
            # file is decodable real media (never a mock byte string).
            errors = []
            if not isinstance(receipt, dict):
                errors.append("ffprobe_raw.json must be a JSON object")
            else:
                streams = receipt.get("streams")
                fmt = receipt.get("format")
                if not isinstance(streams, list) or not streams:
                    errors.append("streams array missing (unreadable media)")
                else:
                    codec_types = {s.get("codec_type") for s in streams}
                    if "video" not in codec_types:
                        errors.append("no video stream")
                    if "audio" not in codec_types:
                        errors.append("no audio stream")
                if not isinstance(fmt, dict) or evidence_lib.is_placeholder_hash(
                    fmt.get("format_name", "")
                ):
                    errors.append("format block missing or placeholder")
            workstreams[name] = not errors
            reasons.extend(f"{name}: {e}" for e in errors)
            continue
        errors = validate_production_receipt(receipt or {}, candidate_sha=candidate_sha)
        workstreams[name] = not errors
        reasons.extend(f"{name}: {e}" for e in errors)

    # --- toolchain_receipt: real ffmpeg/ffprobe facts ----------------------
    toolchain = load_json(evidence_dir / "toolchain_receipt.json")
    if toolchain:
        for key in ("ffmpeg_path", "ffprobe_path"):
            val = toolchain.get(key)
            if not isinstance(val, str) or not val:
                reasons.append(f"toolchain_receipt: {key} required (real executable path)")
                workstreams.setdefault("toolchain_receipt", False)
        if not evidence_lib.is_sha256(toolchain.get("ffmpeg_binary_sha256", "")):
            reasons.append("toolchain_receipt: ffmpeg_binary_sha256 must be 64-hex")
            workstreams.setdefault("toolchain_receipt", False)
        if toolchain.get("workstream") and "toolchain_receipt" not in workstreams:
            workstreams["toolchain_receipt"] = True

    # --- command receipts: real subprocess execution ------------------------
    cmd_ok = _validate_command_receipts(evidence_dir, reasons)
    workstreams["ffmpeg_command_receipts"] = cmd_ok

    # --- final_media_manifest + real media file -----------------------------
    final = load_json(evidence_dir / "final_media_manifest.json")
    if final:
        locator = final.get("media_locator") or final.get("locator")
        media_path = evidence_dir / locator if locator else None
        errors: list[str] = []
        if not media_path or not media_path.is_file():
            errors.append("final media file missing at manifest locator")
        else:
            errors.extend(evidence_lib.validate_media_file(media_path, expected_container="mp4"))
            expected = final.get("final_media_sha256")
            if not evidence_lib.is_sha256(expected):
                errors.append("final_media_sha256 must be 64-hex")
            elif expected != evidence_lib.sha256_file(media_path):
                errors.append("final_media_sha256 does not match the real file")
            duration = final.get("duration_seconds")
            if not isinstance(duration, (int, float)):
                errors.append("duration_seconds missing")
            elif not (MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS):
                errors.append(
                    f"duration {duration}s outside POC policy "
                    f"[{MIN_DURATION_SECONDS}, {MAX_DURATION_SECONDS}]s"
                )
            status = final.get("verification_status")
            if status != "PASSED":
                errors.append(f"verification_status must be PASSED, got {status!r}")
        workstreams["final_media_manifest"] = not errors
        reasons.extend(f"final_media_manifest: {e}" for e in errors)
    else:
        reasons.append("final_media_manifest.json missing")
        workstreams["final_media_manifest"] = False

    # --- media_decode_receipt: frames decoded from the real file ------------
    decode = load_json(evidence_dir / "media_decode_receipt.json")
    if decode:
        frame_count = decode.get("sample_frames_decoded")
        if not isinstance(frame_count, int) or frame_count < 3:
            reasons.append("media_decode_receipt: sample_frames_decoded < 3 (first/mid/last)")
            workstreams.setdefault("media_decode_receipt", False)
        if decode.get("decoded_ok") is not True:
            reasons.append("media_decode_receipt: decoded_ok is not true")
            workstreams.setdefault("media_decode_receipt", False)
        if "media_decode_receipt" not in workstreams:
            workstreams["media_decode_receipt"] = True
    else:
        reasons.append("media_decode_receipt.json missing")
        workstreams["media_decode_receipt"] = False

    # --- reproducibility_report ---------------------------------------------
    repro = load_json(evidence_dir / "reproducibility_report.json")
    if repro:
        if repro.get("is_reproducible") is not True:
            reasons.append("reproducibility_report: render is not reproducible per policy")
            workstreams.setdefault("reproducibility_report", False)
        if repro.get("byte_identical") is False and repro.get("reproducibility_mode") != "semantic":
            reasons.append(
                "reproducibility_report: non-byte-identical render must document "
                "semantic reproducibility and allowed differing fields (plan §9.5)"
            )
            workstreams.setdefault("reproducibility_report", False)
        if not evidence_lib.is_sha256(repro.get("output_sha256", "")):
            reasons.append("reproducibility_report: output_sha256 must be 64-hex")
            workstreams.setdefault("reproducibility_report", False)
        if "reproducibility_report" not in workstreams:
            workstreams["reproducibility_report"] = True
    else:
        reasons.append("reproducibility_report.json missing")
        workstreams["reproducibility_report"] = False

    verdict = derive_verdict(workstreams=workstreams, blocking_reasons=reasons)
    return verdict, workstreams, reasons


def main() -> int:
    args = parse_verifier_args(
        sys.argv[1:],
        default_evidence_dir=DEFAULT_EVIDENCE_DIR,
        description="Phase 22 evidence-mode verifier (VP22_POST_PRODUCTION_VERIFIED)",
    )

    if not args.read_only:
        out = write_fixtures(args.write_fixture)
        print(f"CONTRACT_TESTED fixtures written to {out}")
        return 0

    before = snapshot_dir(args.evidence_dir)
    verdict, workstreams, reasons = verify_production_evidence(
        args.evidence_dir, args.candidate_sha
    )
    after = snapshot_dir(args.evidence_dir)
    mutations = diff_snapshots(before, after)
    if mutations:
        verdict = "FAILED"
        reasons = [f"READ-ONLY VIOLATION: {m}" for m in mutations] + reasons
        print("READ-ONLY VIOLATION: verifier mutated evidence files!")

    print(f"Phase 22 verdict: {verdict}")
    for ws, ok in workstreams.items():
        print(f"  {ws}: {'PASS' if ok else 'FAIL'}")
    for reason in reasons:
        print(f"  REASON: {reason}")
    return 0 if verdict == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
