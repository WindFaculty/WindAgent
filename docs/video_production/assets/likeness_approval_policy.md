# Likeness Approval Policy — Video Production (Phase 7)

Source: plan 02 `§21.4`. Ratified for `VP7_ASSET_PIPELINE_VERIFIED`.

## 1. Identity safety

- A character reference builder **never merges identity on display name**.
  The reference master binds to a stable `character_id` + `revision_id`
  (`IdentityReferenceBuilder`), so two characters with the same display name
  stay distinct.
- Location references bind the same way to a stable `location_id`
  (`LocationReferenceBuilder`).

## 2. Real-person likeness

- Any asset that depicts a real person or a person's likeness
  (`real_person_likeness=True`) **requires human approval AND usage
  evidence** before it can be approved.
- Without human approval the transition raises
  `LikenessRequiresApprovalError` (fail closed).
- The approval evidence must be recorded in `approval_state` and the license
  evidence list.

## 3. Traceability of generated variants

- Generated variants trace back to their source reference and prompt:
  `prompt_version` + `prompt_hash` are recorded on the reference, and a
  variant carries its `source_asset_id` in metadata.
- Rejected assets cannot be re-selected via duplicate URL or content hash —
  the lifecycle state `REJECTED` blocks silent re-approval (requires a new
  review record).

## 4. Enforcement

`verify_phase7_assets.py` includes negative tests proving:
- duplicate display names produce distinct references;
- likeness without human approval is rejected;
- rejected assets cannot silently re-approve.
