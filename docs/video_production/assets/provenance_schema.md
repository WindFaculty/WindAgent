# Provenance Schema — Video Production (Phase 7)

Source: plan 02 `§21.3`. Ratified for `VP7_ASSET_PIPELINE_VERIFIED`.

## 1. Asset provenance record

Every acquired asset record carries (implemented as
`AssetProvenanceRecord` in `tools/windagent_tools/media_assets/provenance.py`):

| Field | Type | Required |
|---|---|---|
| asset_id | string (stable, content-derived) | yes |
| content_sha256 | 64-char SHA-256 | yes |
| source_type | `GENERATED` / `INTERNET` / `UPLOADED` / `PROVIDER` | yes |
| source_url | string | conditional |
| source_provider | string | no |
| retrieved_at | UTC datetime | yes |
| original_license | `UNKNOWN` / `LICENSED` / `PUBLIC_DOMAIN` / `CREATIVE_COMMONS` / `PROPRIETARY` / `REJECTED` | yes |
| license_evidence | list of URLs/records | yes for APPROVED |
| creator_attribution | string | no |
| transformation_history | list of steps | no |
| validation_receipt | dict (hash, MIME, size, dims, EXIF flag) | yes |
| lifecycle_state | DISCOVERED → DOWNLOADED → VALIDATED → LICENSE_UNKNOWN / APPROVED / REJECTED → BOUND_TO_PROJECT | yes |
| approval_state | dict (reviewed / approved / human) | yes |

## 2. License fail-closed rules

- `LICENSE_UNKNOWN` **never** becomes `APPROVED` on its own — it requires a
  human review with license evidence.
- An APPROVED transition requires `license_evidence`; without it the
  transition is rejected (`LicenseUnknownError`).
- Real-person likeness requires human approval + usage evidence
  (`LikenessRequiresApprovalError` otherwise).
- A REJECTED asset can only become APPROVED again via a **new review
  record** (`new_review_record=True`); silent re-approval is rejected
  (`RejectedAssetError`).

## 3. Lifecycle transitions (§21.5)

```text
DISCOVERED → DOWNLOADED → VALIDATED
VALIDATED  → LICENSE_UNKNOWN | APPROVED | REJECTED
LICENSE_UNKNOWN → APPROVED | REJECTED
APPROVED   → BOUND_TO_PROJECT
REJECTED   → APPROVED  (only with new review record)
```

Forbidden: `DOWNLOADED → BOUND_TO_PROJECT`, `REJECTED → APPROVED` without a
new review record, and any transition out of `BOUND_TO_PROJECT`.

## 4. Enforcement

`verify_phase7_assets.py` validates the schema and fail-closed rules against
real records built by the services; results are recorded in
`artifacts/video_production/phase_07/provenance_contract_receipt.json`.
