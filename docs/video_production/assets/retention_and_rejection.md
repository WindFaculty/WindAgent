# Retention and Rejection — Video Production (Phase 7)

Source: plan 02 `§21.2-§21.4`. Ratified for `VP7_ASSET_PIPELINE_VERIFIED`.

## 1. Retention

- Only **validated, provenance-aware, approved-or-bound** assets are
  retained in the canonical store.
- The store is content-addressed (SHA-256). Publish is atomic (temp file +
  `os.replace`): a crash/cancel never leaves a partial artifact visible, and
  a failed validation never publishes anything.
- Identical content is stored once (idempotent publish by hash).

## 2. Rejection paths

| Stage | Outcome |
|---|---|
| URL blocked (scheme/IP/DNS) | `UrlBlockedError`, nothing downloaded |
| Download failed (timeout/redirect/oversize) | `DownloadFailedError`, quarantine discarded |
| Validation failed (SVG/zero-byte/executable/archive/polyglot/MIME/pixels) | `MediaValidationError`, nothing published |
| License unknown without human review | `LicenseUnknownError`, stays LICENSE_UNKNOWN |
| Likeness without human approval | `LikenessRequiresApprovalError`, stays VALIDATED |
| Rejected asset re-selected | `RejectedAssetError`, blocked |

## 3. Post-rejection rules

- A REJECTED asset may only become APPROVED again through a **new review
  record** (`new_review_record=True`). Silent re-approval is impossible.
- Rejected assets cannot be re-selected through a duplicate URL or content
  hash: the lifecycle state guard is enforced before any state change.
- Rejection records are retained for audit; the byte payload is not
  published to the canonical store.

## 4. Enforcement

- Atomic-publish behavior is covered by `verify_phase7_assets.py` (store is
  inspected after each step; no partial artifacts).
- The lifecycle transitions are covered by the state-machine receipt.
