# Phase 4 Report — VideoClaw Quarantine

- **Gate:** `VP4_VIDEOCLAW_QUARANTINED`
- **Status:** PASSED
- **Source:** `https://github.com/HITsz-TMG/VideoClaw` @ `5a16ae23a4f1cb6886c44c0205f7b7e52a34c276`
- **Generated at:** 2026-07-31T18:14:17.192532+00:00

## Intake summary

- Vendored snapshot: `third_party/videoclaw/upstream/` (443 files, 47079435 bytes)
- Archive SHA-256: `6353b4cc1785b1c5d466b4e90427eb964844593f5721d74fa008c90b6baa6b18`
- Content SHA-256: 86a8af167d4fdbbfc077df457a96085453ba5d98439c6194400546c5df8577be
- Python files: 73; image files: 37

## Quarantine boundary

- Boundary status: CLEAN
- Import violations: 0
- Dynamic/subprocess violations: 0

## Secret scan

- Files scanned: 443
- Findings: 0

## Evidence

- `source_archive_receipt.json` — pinned commit + archive SHA-256 (download-time evidence)
- `source_inventory.json` — file count / size / composition
- `content_hash_receipt.json` — recomputed per-file digest vs UPSTREAM_MANIFEST.json (authoritative gate)
- `quarantine_boundary_report.json` — workspace membership / import / sys.path / subprocess / packaging
- `secret_scan_receipt.json` — credential-shape scan
- `phase_verdict.json`
