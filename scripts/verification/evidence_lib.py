#!/usr/bin/env python3
"""
Shared evidence-mode toolkit for Phase 21–24 verifiers (remediation plan 08, R0).

Implements the R0 verification boundary contract:

1. CLI contract (plan §6.1):
     verifier --evidence-dir <dir> --candidate-sha <sha>   # default: read-only
     verifier --write-fixture <dir>                        # test fixture only
   Unknown / unused flags are rejected (fail-closed).

2. Read-only enforcement (plan §6.1, gate R0):
   In read-only mode a verifier MUST NOT create/modify/delete any file inside
   the evidence directory. `snapshot_dir()` + `assert_unchanged()` let tests
   prove hash+mtime identity before/after a run.

3. Production receipt schema (plan §3):
   Every production receipt must carry schema_version, candidate_sha, run_id,
   started_at/completed_at (RFC3339), command_or_provider, input/output SHA-256
   hashes, an authorized evidence_locator and a status. Anything missing,
   mis-formatted, paradoxical or placeholder-hash-based is rejected.

4. Content-addressed evidence_manifest.json (plan §6.3):
   Records schema hash, candidate SHA, per-file SHA-256 + size + detected media
   container/MIME, retention and locator. The manifest itself is hashed.

5. Fail-closed media validation (plan §2):
   Media files must be validated by bytes and a real tool. Mock byte strings
   (`b"mock_*"`, `b"rendered_media_*"`, repeated `b"AUDIO"`) and file-name
   extensions that do not match the container magic are rejected.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0.0"

CANDIDATE_SHA_RE = re.compile(r"^[a-f0-9]{40}$|^[a-f0-9]{64}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
RFC3339 = "%Y-%m-%dT%H:%M:%S"

VALID_STATUSES = ("PASSED", "FAILED", "BLOCKED")

# Non-negotiable rule (plan §2): fixture writers must never write here.
PRODUCTION_ARTIFACTS_ROOT = "artifacts/video_production"

REQUIRED_RECEIPT_FIELDS = (
    "schema_version",
    "candidate_sha",
    "run_id",
    "started_at",
    "completed_at",
    "command_or_provider",
    "input_hashes",
    "output_hashes",
    "evidence_locator",
    "status",
)

# Locators that reveal host secrets / absolute profile paths are disallowed.
_DISALLOWED_LOCATOR_MARKERS = (
    "token=",
    "api_key=",
    "password=",
    "secret=",
    "C:\\Users",
    "\\profile\\",
    "AppData",
)

# Recognised media containers by magic bytes (offset-aware).
_MEDIA_MAGIC: tuple[tuple[str, bytes, int], ...] = (
    ("mp4", b"ftyp", 4),          # ISO BMFF / MP4
    ("wav", b"WAVE", 8),          # RIFF....WAVE
    ("webm", b"\x1a\x45\xdf\xa3", 0),  # EBML (WebM/Matroska)
    ("mov", b"ftyp", 4),          # also ISO BMFF
    ("jpg", b"\xff\xd8\xff", 0),
    ("png", b"\x89PNG\r\n\x1a\n", 0),
    ("json", b"{", 0),
    ("json", b"[", 0),
)

# Mock byte-string prefixes produced by the old fixture-era verifiers.
_MOCK_PREFIXES = (
    b"mock_",
    b"rendered_media_",
    b"AUDIO" * 4,
)


# ---------------------------------------------------------------------------
# Hashing / format helpers
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_candidate_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(CANDIDATE_SHA_RE.match(value))


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.match(value))


def is_placeholder_hash(value: Any) -> bool:
    """True for legacy placeholder hashes like `sha256_*`, `hash_*`, `git_sha_*`."""
    if not isinstance(value, str):
        return True
    lowered = value.lower()
    return (
        lowered.startswith("sha256_")
        or lowered.startswith("hash_")
        or lowered.startswith("git_sha_")
        or lowered.startswith("mock_")
        or "placeholder" in lowered
    )


def parse_rfc3339(value: Any) -> datetime.datetime | None:
    """Parse an RFC3339 / ISO8601 timestamp; returns None when invalid."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Media magic detection (bytes, never extension alone)
# ---------------------------------------------------------------------------

def detect_container(path: Path) -> str | None:
    """Detect media container from file magic bytes (or None if unrecognised)."""
    try:
        head = path.read_bytes()[:16]
    except OSError:
        return None
    if not head:
        return None
    for name, magic, offset in _MEDIA_MAGIC:
        if head[offset : offset + len(magic)] == magic:
            return name
    return None


def is_mock_payload(path: Path) -> bool:
    """True when the file content is a legacy mock byte-string, not real media."""
    try:
        head = path.read_bytes()[: 4 * 4]
    except OSError:
        return True
    return any(head.startswith(prefix) for prefix in _MOCK_PREFIXES)


def validate_media_file(
    path: Path,
    *,
    expected_container: str | None = None,
    min_size_bytes: int = 64,
) -> list[str]:
    """Fail-closed media validation: missing/empty/mock/magic-mismatch => errors."""
    errors: list[str] = []
    if not path.exists():
        return [f"media file missing: {path.name}"]
    size = path.stat().st_size
    if size < min_size_bytes:
        errors.append(f"media file suspiciously small ({size}B < {min_size_bytes}B): {path.name}")
    if is_mock_payload(path):
        errors.append(f"media file is a mock byte-string, not real media: {path.name}")
    container = detect_container(path)
    if container is None:
        errors.append(f"media file has no recognised container magic: {path.name}")
    if expected_container and container != expected_container:
        errors.append(
            f"media extension says {expected_container} but magic bytes say {container}: {path.name}"
        )
    return errors


# ---------------------------------------------------------------------------
# Production receipt validation (plan §3)
# ---------------------------------------------------------------------------

def validate_production_receipt(
    receipt: dict[str, Any],
    *,
    candidate_sha: str | None = None,
    allow_statuses: tuple[str, ...] = VALID_STATUSES,
) -> list[str]:
    """Validate a production receipt against the §3 schema. Returns errors."""
    errors: list[str] = []
    if not isinstance(receipt, dict):
        return ["receipt must be a JSON object"]

    missing = [f for f in REQUIRED_RECEIPT_FIELDS if f not in receipt]
    if missing:
        errors.append(f"receipt missing fields: {missing}")
        # Field-level checks below would be meaningless; stop early.
        return errors

    if receipt.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {SCHEMA_VERSION}, got {receipt.get('schema_version')!r}"
        )

    sha = receipt.get("candidate_sha")
    if not is_candidate_sha(sha):
        errors.append(f"candidate_sha must be 40/64-hex, got {sha!r}")
    if candidate_sha and sha != candidate_sha:
        errors.append(f"candidate_sha mismatch: receipt {sha!r} != expected {candidate_sha!r}")

    run_id = receipt.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        errors.append("run_id must be a non-empty stable id")

    started = parse_rfc3339(receipt.get("started_at"))
    completed = parse_rfc3339(receipt.get("completed_at"))
    if started is None:
        errors.append(f"started_at must be RFC3339, got {receipt.get('started_at')!r}")
    if completed is None:
        errors.append(f"completed_at must be RFC3339, got {receipt.get('completed_at')!r}")
    if started and completed and completed < started:
        errors.append("completed_at is before started_at (paradoxical timestamps)")

    for key in ("input_hashes", "output_hashes"):
        values = receipt.get(key, [])
        if not isinstance(values, list) or not values:
            errors.append(f"{key} must be a non-empty list of SHA-256 hashes")
            continue
        for h in values:
            if is_placeholder_hash(h):
                errors.append(f"{key} contains placeholder hash: {h}")
            elif not is_sha256(h):
                errors.append(f"{key} hash must be 64-hex, got {h!r}")

    locator = receipt.get("evidence_locator")
    if not isinstance(locator, str) or not locator.strip():
        errors.append("evidence_locator must be a non-empty authorized/redacted locator")
    else:
        lowered = locator.lower()
        for marker in _DISALLOWED_LOCATOR_MARKERS:
            if marker.lower() in lowered:
                errors.append(f"evidence_locator leaks disallowed content ({marker})")

    status = receipt.get("status")
    if status not in allow_statuses:
        errors.append(f"status must be one of {allow_statuses}, got {status!r}")

    return errors


# ---------------------------------------------------------------------------
# Evidence manifest (content-addressed, plan §6.3)
# ---------------------------------------------------------------------------

def _manifest_payload(manifest: dict[str, Any]) -> str:
    without_self = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    return json.dumps(without_self, sort_keys=True, ensure_ascii=False)


def build_evidence_manifest(
    evidence_dir: Path,
    candidate_sha: str,
    *,
    schema_version: str = SCHEMA_VERSION,
    retention_days: int = 365,
) -> dict[str, Any]:
    """Build a content-addressed evidence manifest for an evidence directory."""
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(evidence_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "evidence_manifest.json":
            continue
        rel = path.relative_to(evidence_dir).as_posix()
        size = path.stat().st_size
        container = detect_container(path)
        entry: dict[str, Any] = {
            "sha256": sha256_file(path),
            "size_bytes": size,
            "media_container": container,
            "mime": _container_mime(container),
            "retention_days": retention_days,
            "locator": rel,
        }
        files[rel] = entry

    manifest = {
        "schema_version": schema_version,
        "candidate_sha": candidate_sha,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "schema_hash": sha256_bytes(
            json.dumps(REQUIRED_RECEIPT_FIELDS, sort_keys=True).encode("utf-8")
        ),
        "files": files,
    }
    manifest["manifest_sha256"] = sha256_bytes(_manifest_payload(manifest).encode("utf-8"))
    return manifest


def _container_mime(container: str | None) -> str:
    if container is None:
        return "application/octet-stream"
    return {
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "webm": "video/webm",
        "wav": "audio/wav",
        "jpg": "image/jpeg",
        "png": "image/png",
        "json": "application/json",
    }.get(container, "application/octet-stream")


def validate_evidence_manifest(
    manifest: dict[str, Any],
    evidence_dir: Path,
    *,
    candidate_sha: str | None = None,
) -> list[str]:
    """Validate an evidence manifest against the on-disk directory. Returns errors."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["evidence_manifest.json must be a JSON object"]

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"manifest schema_version must be {SCHEMA_VERSION}")

    sha = manifest.get("candidate_sha")
    if not is_candidate_sha(sha):
        errors.append(f"manifest candidate_sha must be 40/64-hex, got {sha!r}")
    if candidate_sha and sha != candidate_sha:
        errors.append(f"manifest candidate_sha mismatch: {sha!r} != {candidate_sha!r}")

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        return [*errors, "manifest files map must be a non-empty object"]

    for rel, entry in sorted(files.items()):
        path = evidence_dir / rel
        if not path.is_file():
            errors.append(f"manifest references missing file: {rel}")
            continue
        expected = entry.get("sha256")
        actual = sha256_file(path)
        if not is_sha256(expected) or expected != actual:
            errors.append(f"manifest hash mismatch for {rel}: expected {expected}, got {actual}")
        if entry.get("size_bytes") != path.stat().st_size:
            errors.append(f"manifest size mismatch for {rel}")

    # Verify the manifest's self-hash.
    expected_hash = manifest.get("manifest_sha256")
    if not is_sha256(expected_hash):
        errors.append("manifest_sha256 must be 64-hex")
    elif expected_hash != sha256_bytes(_manifest_payload(manifest).encode("utf-8")):
        errors.append("manifest_sha256 does not match manifest content")

    return errors


# ---------------------------------------------------------------------------
# Read-only enforcement helpers
# ---------------------------------------------------------------------------

def snapshot_dir(root: Path) -> dict[str, tuple[str, int]]:
    """Snapshot every file under `root`: relpath -> (sha256, mtime_ns)."""
    snap: dict[str, tuple[str, int]] = {}
    if not root.exists():
        return snap
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            st = path.stat()
            snap[rel] = (sha256_file(path), st.st_mtime_ns)
    return snap


def diff_snapshots(
    before: dict[str, tuple[str, int]],
    after: dict[str, tuple[str, int]],
) -> list[str]:
    """Return human-readable descriptions of any mutation between snapshots."""
    changes: list[str] = []
    for rel in sorted(set(before) | set(after)):
        if rel not in before:
            changes.append(f"file created: {rel}")
        elif rel not in after:
            changes.append(f"file deleted: {rel}")
        elif before[rel] != after[rel]:
            changes.append(f"file modified: {rel}")
    return changes


# ---------------------------------------------------------------------------
# CLI contract (plan §6.1) — strict, rejects unknown flags
# ---------------------------------------------------------------------------

class VerifierArgs:
    """Parsed, validated CLI arguments for an evidence-mode verifier."""

    def __init__(
        self,
        *,
        evidence_dir: Path | None,
        candidate_sha: str | None,
        write_fixture: Path | None,
        verbosity: int,
    ) -> None:
        self.evidence_dir = evidence_dir
        self.candidate_sha = candidate_sha
        self.write_fixture = write_fixture
        self.verbosity = verbosity

    @property
    def read_only(self) -> bool:
        return self.write_fixture is None

    @property
    def production_mode(self) -> bool:
        """True when validating real evidence (not generating fixtures)."""
        return self.read_only


def parse_verifier_args(
    argv: list[str],
    *,
    default_evidence_dir: Path,
    description: str,
) -> VerifierArgs:
    """Strict argument parser for the R0 verifier CLI.

    Accepted flags:
      --evidence-dir <dir>    evidence directory to validate (default: supplied)
      --candidate-sha <sha>   candidate SHA the receipts must match
      --write-fixture <dir>   write test fixtures into <dir> (never production)
      -v / -vv                verbosity
    Any other flag is rejected (fail-closed, plan §6.1).
    """
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--evidence-dir",
        default=str(default_evidence_dir),
        help="evidence directory to validate (default: %(default)s)",
    )
    parser.add_argument(
        "--candidate-sha",
        default=None,
        help="candidate SHA (40/64-hex) that all receipts must match",
    )
    parser.add_argument(
        "--write-fixture",
        default=None,
        metavar="DIR",
        help="write test fixtures into DIR (temp dir only; refuses production artifacts)",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)

    args = parser.parse_args(argv)

    if args.write_fixture:
        out = Path(args.write_fixture).resolve()
        prod_root = Path(PRODUCTION_ARTIFACTS_ROOT).resolve()
        try:
            out.relative_to(prod_root)
            parser.error(
                f"--write-fixture refuses production artifacts path: {out} "
                f"(fixtures may only live under a temporary test directory)"
            )
        except ValueError:
            pass
        return VerifierArgs(
            evidence_dir=None,
            candidate_sha=None,
            write_fixture=out,
            verbosity=args.verbose,
        )

    evidence_dir = Path(args.evidence_dir).resolve()
    sha = args.candidate_sha
    if sha and not is_candidate_sha(sha):
        parser.error(f"--candidate-sha must be 40/64 lowercase hex, got {sha!r}")
    return VerifierArgs(
        evidence_dir=evidence_dir,
        candidate_sha=sha,
        write_fixture=None,
        verbosity=args.verbose,
    )


# ---------------------------------------------------------------------------
# Verdict derivation helpers
# ---------------------------------------------------------------------------

def derive_verdict(
    *,
    workstreams: dict[str, bool],
    blocking_reasons: list[str],
) -> str:
    """Derive a gate verdict from validated workstreams (never hard-coded).

    BLOCKED takes precedence (missing evidence is fail-closed); then FAILED.
    """
    if blocking_reasons:
        return "BLOCKED"
    if not all(workstreams.values()):
        return "FAILED"
    return "PASSED"


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
