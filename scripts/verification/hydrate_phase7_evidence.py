"""Fail-closed materialization of immutable Phase 7 CI evidence.

The hydrator deliberately has no network client.  Callers fetch the exact GitHub
Actions artifacts named by a source-controlled manifest, then this program
verifies the archive and extracted-tree digests before it copies anything into
an isolated checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


SCHEMA_VERSION = "1.0.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class HydrationError(ValueError):
    """Raised when evidence cannot be proven safe to materialize."""


@dataclass(frozen=True)
class TreeDigest:
    file_count: int
    total_bytes: int
    sha256: str


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    archive_filename: str
    archive_sha256: str
    archive_size_bytes: int
    content_type: str
    file_count: int
    immutable_locator: str
    producer_job: str
    relative_path: str
    required: bool
    source_commit: str
    tree_sha256: str
    tree_size_bytes: int


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise HydrationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _validate_git_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not GIT_SHA_RE.fullmatch(value):
        raise HydrationError(f"{field} must be a 40-character lowercase Git SHA")
    return value


def _validate_nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HydrationError(f"{field} must be a non-negative integer")
    return value


def _safe_relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise HydrationError(f"{field} must be a non-empty relative path")
    if "\\" in value:
        raise HydrationError(f"{field} must use POSIX separators")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or any(part in {"", ".", ".."} for part in posix.parts)
    ):
        raise HydrationError(f"{field} escapes its declared root: {value!r}")
    return posix.as_posix()


def _safe_join(root: Path, relative_path: str) -> Path:
    resolved_root = root.resolve()
    candidate = (resolved_root / relative_path).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise HydrationError(f"path escapes root: {relative_path!r}") from exc
    return candidate


def _tree_digest(root: Path) -> TreeDigest:
    if not root.is_dir():
        raise HydrationError(f"evidence root does not exist: {root}")

    records: list[str] = []
    file_count = 0
    total_bytes = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise HydrationError(f"evidence tree contains forbidden symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        records.append(f"{relative}\0{_sha256_file(path)}\0{size}")
        file_count += 1
        total_bytes += size

    canonical = "\n".join(records).encode("utf-8")
    return TreeDigest(
        file_count=file_count,
        total_bytes=total_bytes,
        sha256=hashlib.sha256(canonical).hexdigest(),
    )


def _read_manifest(path: Path) -> tuple[dict[str, Any], str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HydrationError(f"cannot read manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HydrationError(f"manifest is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise HydrationError("manifest root must be an object")
    return data, _sha256_file(path)


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise HydrationError(f"{field} must be a non-empty string")
    return value


def _parse_manifest(data: dict[str, Any]) -> tuple[str, str, str, str, list[Artifact]]:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise HydrationError(f"schema_version must equal {SCHEMA_VERSION}")
    baseline_sha = _validate_git_sha(data.get("baseline_sha"), "baseline_sha")
    evidence_source_sha = _validate_git_sha(
        data.get("evidence_source_sha"), "evidence_source_sha"
    )
    run_id = _require_string(data.get("run_id"), "run_id")
    run_attempt = _require_string(data.get("run_attempt"), "run_attempt")
    if not run_id.isdigit() or not run_attempt.isdigit():
        raise HydrationError("run_id and run_attempt must be decimal identifiers")

    raw_artifacts = data.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise HydrationError("artifacts must be a non-empty list")

    artifacts: list[Artifact] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, raw in enumerate(raw_artifacts):
        prefix = f"artifacts[{index}]"
        if not isinstance(raw, dict):
            raise HydrationError(f"{prefix} must be an object")
        artifact_id = _require_string(raw.get("artifact_id"), f"{prefix}.artifact_id")
        if not artifact_id.isdigit() or artifact_id in seen_ids:
            raise HydrationError(f"{prefix}.artifact_id must be unique decimal text")
        relative_path = _safe_relative_path(raw.get("relative_path"), f"{prefix}.relative_path")
        if relative_path in seen_paths:
            raise HydrationError(f"{prefix}.relative_path is duplicated")
        archive_filename = _safe_relative_path(
            raw.get("archive_filename"), f"{prefix}.archive_filename"
        )
        if "/" in archive_filename:
            raise HydrationError(f"{prefix}.archive_filename must not contain a directory")
        if not archive_filename.endswith(".zip"):
            raise HydrationError(f"{prefix}.archive_filename must end in .zip")
        if raw.get("content_type") != "application/zip":
            raise HydrationError(f"{prefix}.content_type must be application/zip")
        if raw.get("source_commit") != evidence_source_sha:
            raise HydrationError(f"{prefix}.source_commit differs from evidence_source_sha")
        if raw.get("required") is not True:
            raise HydrationError(f"{prefix}.required must be true for certification evidence")
        locator = _require_string(raw.get("immutable_locator"), f"{prefix}.immutable_locator")
        required_locator = f"/actions/artifacts/{artifact_id}/zip"
        if not locator.startswith("https://api.github.com/repos/") or not locator.endswith(
            required_locator
        ):
            raise HydrationError(f"{prefix}.immutable_locator is not an exact artifact ZIP locator")
        artifacts.append(
            Artifact(
                artifact_id=artifact_id,
                archive_filename=archive_filename,
                archive_sha256=_validate_sha(raw.get("archive_sha256"), f"{prefix}.archive_sha256"),
                archive_size_bytes=_validate_nonnegative_int(
                    raw.get("archive_size_bytes"), f"{prefix}.archive_size_bytes"
                ),
                content_type="application/zip",
                file_count=_validate_nonnegative_int(raw.get("file_count"), f"{prefix}.file_count"),
                immutable_locator=locator,
                producer_job=_require_string(raw.get("producer_job"), f"{prefix}.producer_job"),
                relative_path=relative_path,
                required=True,
                source_commit=evidence_source_sha,
                tree_sha256=_validate_sha(raw.get("tree_sha256"), f"{prefix}.tree_sha256"),
                tree_size_bytes=_validate_nonnegative_int(
                    raw.get("tree_size_bytes"), f"{prefix}.tree_size_bytes"
                ),
            )
        )
        seen_ids.add(artifact_id)
        seen_paths.add(relative_path)
    return baseline_sha, evidence_source_sha, run_id, run_attempt, artifacts


def _verify_archive(artifact: Artifact, archives_root: Path) -> None:
    archive = _safe_join(archives_root, artifact.archive_filename)
    if not archive.is_file() or archive.is_symlink():
        raise HydrationError(f"archive is missing or unsafe: {archive}")
    if archive.stat().st_size != artifact.archive_size_bytes:
        raise HydrationError(f"archive size mismatch for {artifact.artifact_id}")
    if _sha256_file(archive) != artifact.archive_sha256:
        raise HydrationError(f"archive SHA-256 mismatch for {artifact.artifact_id}")


def _verify_tree(artifact: Artifact, root: Path) -> TreeDigest:
    digest = _tree_digest(_safe_join(root, artifact.relative_path))
    if digest.file_count != artifact.file_count:
        raise HydrationError(f"file count mismatch for {artifact.artifact_id}")
    if digest.total_bytes != artifact.tree_size_bytes:
        raise HydrationError(f"tree size mismatch for {artifact.artifact_id}")
    if digest.sha256 != artifact.tree_sha256:
        raise HydrationError(f"tree SHA-256 mismatch for {artifact.artifact_id}")
    return digest


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    if path.exists():
        raise HydrationError(f"receipt path already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def hydrate(
    *,
    manifest_path: Path,
    source_root: Path,
    archives_root: Path,
    destination: Path,
    expected_baseline_sha: str,
    expected_evidence_source_sha: str,
    receipt_path: Path | None,
    dry_run: bool,
) -> dict[str, Any]:
    """Verify and materialize evidence, or raise ``HydrationError`` before copying."""
    data, manifest_sha256 = _read_manifest(manifest_path)
    baseline_sha, evidence_source_sha, run_id, run_attempt, artifacts = _parse_manifest(data)
    if baseline_sha != _validate_git_sha(expected_baseline_sha, "expected_baseline_sha"):
        raise HydrationError("manifest baseline_sha does not match expected_baseline_sha")
    if evidence_source_sha != _validate_git_sha(
        expected_evidence_source_sha, "expected_evidence_source_sha"
    ):
        raise HydrationError(
            "manifest evidence_source_sha does not match expected_evidence_source_sha"
        )
    if dry_run and receipt_path is not None:
        raise HydrationError("--dry-run cannot write a hydration receipt")

    source_root = source_root.resolve()
    archives_root = archives_root.resolve()
    destination = destination.resolve()
    if not source_root.is_dir() or not archives_root.is_dir():
        raise HydrationError("source_root and archives_root must be existing directories")
    if source_root == destination or archives_root == destination:
        raise HydrationError("destination must differ from source_root and archives_root")

    verified: list[tuple[Artifact, TreeDigest]] = []
    for artifact in artifacts:
        _verify_archive(artifact, archives_root)
        verified.append((artifact, _verify_tree(artifact, source_root)))

    targets = [(artifact, _safe_join(destination, artifact.relative_path)) for artifact, _ in verified]
    existing = [str(target) for _, target in targets if target.exists()]
    if existing:
        raise HydrationError("refusing to overwrite evidence destination: " + ", ".join(existing))

    evidence_receipts = [
        {
            "artifact_id": artifact.artifact_id,
            "archive_sha256": artifact.archive_sha256,
            "archive_verified": True,
            "relative_path": artifact.relative_path,
            "tree_sha256": digest.sha256,
            "tree_verified": True,
        }
        for artifact, digest in verified
    ]
    result = {
        "schema_version": SCHEMA_VERSION,
        "result": "DRY_RUN" if dry_run else "PASS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_sha": baseline_sha,
        "evidence_source_sha": evidence_source_sha,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "manifest_sha256": manifest_sha256,
        "archive_integrity_verified": True,
        "tree_integrity_verified": True,
        "artifacts": evidence_receipts,
    }
    if dry_run:
        return result

    destination.mkdir(parents=True, exist_ok=True)
    stage_root = Path(tempfile.mkdtemp(prefix=".phase7-hydration-", dir=destination))
    try:
        for artifact, _ in verified:
            source = _safe_join(source_root, artifact.relative_path)
            staged = _safe_join(stage_root, artifact.relative_path)
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, staged, copy_function=shutil.copy2)
            _verify_tree(artifact, stage_root)
        for artifact, target in targets:
            if target.exists():
                raise HydrationError(f"destination appeared during hydration: {target}")
            os.replace(_safe_join(stage_root, artifact.relative_path), target)
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root)

    if receipt_path is not None:
        _write_receipt(receipt_path.resolve(), result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--archives-root", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--expected-baseline-sha", required=True)
    parser.add_argument("--expected-evidence-source-sha", required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-hashes", action="store_true", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = hydrate(
            manifest_path=args.manifest,
            source_root=args.source_root,
            archives_root=args.archives_root,
            destination=args.destination,
            expected_baseline_sha=args.expected_baseline_sha,
            expected_evidence_source_sha=args.expected_evidence_source_sha,
            receipt_path=args.receipt,
            dry_run=args.dry_run,
        )
    except HydrationError as exc:
        if args.json:
            print(json.dumps({"result": "FAIL", "error": str(exc)}, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["result"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
