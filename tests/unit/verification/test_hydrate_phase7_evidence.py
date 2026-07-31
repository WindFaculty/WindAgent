"""Tests for the fail-closed Phase 7 CI-evidence hydrator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.verification.hydrate_phase7_evidence import HydrationError, _tree_digest, hydrate


BASELINE_SHA = "a" * 40
EVIDENCE_SHA = "b" * 40


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_manifest(path: Path, source_root: Path, archives_root: Path) -> dict[str, object]:
    evidence = source_root / "alpha-evidence"
    (evidence / "receipts").mkdir(parents=True)
    (evidence / "receipts" / "build.json").write_text('{"result":"PASS"}\n', encoding="utf-8")
    (evidence / "environment.json").write_text('{"git_sha":"' + EVIDENCE_SHA + '"}\n', encoding="utf-8")
    archive = archives_root / "1001.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"not-a-real-zip; the hydrator verifies immutable bytes only")
    tree = _tree_digest(evidence)
    manifest: dict[str, object] = {
        "schema_version": "1.0.0",
        "baseline_sha": BASELINE_SHA,
        "evidence_source_sha": EVIDENCE_SHA,
        "run_id": "42",
        "run_attempt": "1",
        "artifacts": [
            {
                "artifact_id": "1001",
                "archive_filename": "1001.zip",
                "archive_sha256": _sha256(archive.read_bytes()),
                "archive_size_bytes": archive.stat().st_size,
                "content_type": "application/zip",
                "file_count": tree.file_count,
                "immutable_locator": "https://api.github.com/repos/example/repo/actions/artifacts/1001/zip",
                "producer_job": "unit-test",
                "relative_path": "alpha-evidence",
                "required": True,
                "source_commit": EVIDENCE_SHA,
                "tree_sha256": tree.sha256,
                "tree_size_bytes": tree.total_bytes,
            }
        ],
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def _hydrate(tmp_path: Path, *, receipt: bool = True) -> tuple[dict[str, object], Path, Path, Path]:
    source_root = tmp_path / "source"
    archives_root = tmp_path / "archives"
    destination = tmp_path / "destination"
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, source_root, archives_root)
    receipt_path = tmp_path / "hydration-receipt.json" if receipt else None
    result = hydrate(
        manifest_path=manifest_path,
        source_root=source_root,
        archives_root=archives_root,
        destination=destination,
        expected_baseline_sha=BASELINE_SHA,
        expected_evidence_source_sha=EVIDENCE_SHA,
        receipt_path=receipt_path,
        dry_run=False,
    )
    return result, destination, source_root, manifest_path


def test_hydrate_verifies_and_copies_exact_evidence(tmp_path: Path) -> None:
    result, destination, source_root, _ = _hydrate(tmp_path)

    assert result["result"] == "PASS"
    assert result["archive_integrity_verified"] is True
    assert result["tree_integrity_verified"] is True
    assert (destination / "alpha-evidence" / "receipts" / "build.json").read_bytes() == (
        source_root / "alpha-evidence" / "receipts" / "build.json"
    ).read_bytes()
    receipt = json.loads((tmp_path / "hydration-receipt.json").read_text(encoding="utf-8"))
    assert receipt["result"] == "PASS"
    assert receipt["artifacts"][0]["archive_verified"] is True


def test_hydrate_rejects_tampered_tree_before_copy(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    archives_root = tmp_path / "archives"
    destination = tmp_path / "destination"
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, source_root, archives_root)
    (source_root / "alpha-evidence" / "environment.json").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(HydrationError, match="tree (size|SHA-256) mismatch"):
        hydrate(
            manifest_path=manifest_path,
            source_root=source_root,
            archives_root=archives_root,
            destination=destination,
            expected_baseline_sha=BASELINE_SHA,
            expected_evidence_source_sha=EVIDENCE_SHA,
            receipt_path=None,
            dry_run=False,
        )
    assert not destination.exists()


def test_hydrate_rejects_path_traversal_before_copy(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    archives_root = tmp_path / "archives"
    destination = tmp_path / "destination"
    manifest_path = tmp_path / "manifest.json"
    manifest = _write_manifest(manifest_path, source_root, archives_root)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    artifacts[0]["relative_path"] = "../escape-evidence"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(HydrationError, match="escapes its declared root"):
        hydrate(
            manifest_path=manifest_path,
            source_root=source_root,
            archives_root=archives_root,
            destination=destination,
            expected_baseline_sha=BASELINE_SHA,
            expected_evidence_source_sha=EVIDENCE_SHA,
            receipt_path=None,
            dry_run=False,
        )
    assert not destination.exists()


def test_hydrate_rejects_archive_hash_mismatch_before_copy(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    archives_root = tmp_path / "archives"
    destination = tmp_path / "destination"
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, source_root, archives_root)
    (archives_root / "1001.zip").write_bytes(b"tampered archive")

    with pytest.raises(HydrationError, match="archive size mismatch|archive SHA-256 mismatch"):
        hydrate(
            manifest_path=manifest_path,
            source_root=source_root,
            archives_root=archives_root,
            destination=destination,
            expected_baseline_sha=BASELINE_SHA,
            expected_evidence_source_sha=EVIDENCE_SHA,
            receipt_path=None,
            dry_run=False,
        )
    assert not destination.exists()


def test_hydrate_rejects_provenance_mismatch_and_existing_destination(tmp_path: Path) -> None:
    result, destination, source_root, manifest_path = _hydrate(tmp_path)
    assert result["result"] == "PASS"

    with pytest.raises(HydrationError, match="baseline_sha does not match"):
        hydrate(
            manifest_path=manifest_path,
            source_root=source_root,
            archives_root=tmp_path / "archives",
            destination=tmp_path / "another-destination",
            expected_baseline_sha="c" * 40,
            expected_evidence_source_sha=EVIDENCE_SHA,
            receipt_path=None,
            dry_run=False,
        )
    with pytest.raises(HydrationError, match="refusing to overwrite"):
        hydrate(
            manifest_path=manifest_path,
            source_root=source_root,
            archives_root=tmp_path / "archives",
            destination=destination,
            expected_baseline_sha=BASELINE_SHA,
            expected_evidence_source_sha=EVIDENCE_SHA,
            receipt_path=None,
            dry_run=False,
        )
