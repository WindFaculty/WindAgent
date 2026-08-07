# Provenance Policy — Stage C Phase 6 (Asset Trust & Provenance)

Policy for how WindAgent acquires, trusts, and records provenance of 3D assets.
Satisfies `3d_animation_plans/stage_c_asset_production.md` Phase 6 backlog
items 1–7 and its negative-test matrix. The shared execution lives in
`tools/windagent_tools/media_assets/`; lifecycle policy lives in
`core/windagent_core/domain/video_production/asset_lifecycle.py`.

## 1. Provenance fields (item 1, item 2)

Every acquired asset records, when applicable:

| Field | Meaning |
|-------|---------|
| `source_type` | LOCAL_LIBRARY / INTERNET / API (PROVIDER) / MCP / GENERATED |
| `source_provider` | provider or library id |
| `source_author` | author / artist attribution |
| `license_state` + `license_evidence` | classification + evidence chain |
| `retrieved_at` | download / generation time (UTC) |
| `content_sha256` | original content hash (post-sanitization) |
| `tool` / `model` / `seed` | generation tooling for GENERATED assets |
| `prompt_hash` | canonical prompt hash for GENERATED assets |
| `generation_receipt` | deterministic generation parameters |
| `checksum_verified` | independent checksum verification flag |
| `derived_from_hash` / `normalization_receipt` | conversion lineage |

## 2. Provenance is mandatory

An asset with missing mandatory provenance is treated as `UNKNOWN` and is
quarantined (item 2, item 3). Mandatory: source type, license state, and a
verified content hash. Missing author/attribution is recorded as empty but
does not by itself quarantine the asset when a permissive license is proven.

## 3. Quarantine (item 3)

An asset moves to `QUARANTINED` when:

- its license is `UNKNOWN` (no verifiable license evidence);
- there is no demonstrable commercial-use right for a commercial project;
- its checksum cannot be independently verified;
- it carries a trademark or requires attribution without a human review.

The only way out of quarantine is a fresh human review promoting it to
`APPROVED` (requires `new_review_record=True` at the state-machine level).
Provider metadata is **never** sufficient to undep quarantine on its own —
the state machine forbids `QUARANTINED → APPROVED` without a review record,
and the trust enforcer never returns `APPROVE` for an `UNKNOWN`/proprietary
license without `human_reviewed=True`.

> Negative test: "Unknown license không thể chuyển sang `APPROVED` chỉ bằng
> metadata provider" — covered by `test_unknown_license_never_approved_by_metadata_alone`.

## 4. Downloader safety (item 4)

- HTTP(S) only; scheme validated before any connection.
- Redirects bounded and each hop re-validated with SSRF checks before fetch.
- Max bytes and timeout enforced; payload buffered in memory under the bound.
- MIME sniffed from magic bytes; extension is never evidence.
- Executable and disallowed payloads rejected.
- Archive/mesh/texture scanned statically; embedded scripts, drivers and
  add-ons are never auto-run (item 5). See `AssetContentScanner`.

## 5. Conversion lineage (item 6)

Every derived asset (LOD, normalized mesh, optimized texture) points to its
source `content_sha256` via `derived_from_hash` and carries its
`normalization_receipt`. Lineage is content-addressed: the derived hash is
computed over the transformed bytes, so a changed asset always yields a new
version/hash. See `AssetProvenanceService.record_derivation`.

## 6. Likeness, trademark, attribution (item 7)

- Real-person likeness requires human approval + usage evidence
  (existing rule in `advance_license`).
- Trademark or required-attribution assets require human approval and a
  verified checksum (`promote_from_quarantine`, `AssetTrustEnforcer`).

## 7. Redaction (negative test)

Logs and receipts never carry live tokens or still-valid signed download
URLs. Signed URL query parameters (`X-Amz-Signature`, `X-Amz-Credential`,
`token`, `sig`) are redacted at the boundary before any receipt is emitted;
provenance stores the bare source URL, and URL serialization is passed
through the redactor.

## Gate

`VP3D_P6_ASSET_TRUST_PROVENANCE_VERIFIED` — lifecycle quarantine,
trust enforcement, content scanning, generated provenance, conversion
lineage, redaction, and the negative-test matrix.
