# Privacy Retention and Deletion (Phase 26 §14.8)

Gate: `VP26_SECURITY_VERIFIED` — scenario **SE13** provides the evidence;
`privacy_deletion_receipt.json` is the machine-readable receipt.

## 1. Purpose and data classes

| Data class | Purpose | Retention owner |
|---|---|---|
| Source / reference assets | reference binding for generation | artifact retention policy |
| Generated media (frames/clips/final cut) | deliverable production | artifact retention policy |
| Rejected candidates | audit of generation decisions | short TTL → GC under retention |
| Screenshots | browser verification / debugging | bounded, redacted, workspace-scoped |
| Browser profile / session state | authenticated browser runs | `BrowserStateRetentionPolicy` (age/count/size) |
| Logs / events / evidence | auditability | evidence manifest retention (365 d default) |

Purpose is explicit per workflow; data is only collected for the purpose it
was created (reference → generation → delivery; screenshots → verification).

## 2. Retention

- **Browser state**: `BrowserStateManager` cleans by max age, max count and
  max total size (SE13 proves age- and count-based removal).
- **Artifacts**: records are **never hard-deleted by invalidation**; a
  revision/reference change marks `STALE` (or `SUPERSEDED` when a
  replacement exists) and appends an audit entry for later garbage
  collection under the retention policy (SE13 proves records survive with
  history, and `valid_records()` no longer lists them).
- **Evidence**: `evidence_manifest.json` records per-file retention days.
- **Backups**: backup retention is separate from primary retention; backups
  are deleted on their own schedule (`backup_manager.cleanup_old_backups`).
- **Legal hold** (if applicable): frozen records are excluded from cleanup by
  an explicit hold flag before the retention sweep.

## 3. Deletion flow

```text
1. authorization + confirmation        (PermissionEngine REQUIRE_APPROVAL / SE10)
2. mark / schedule deletion
3. remove project references
4. delete unreferenced data per retention
5. clear session / profile if requested
6. write a deletion receipt that contains NO deleted content
```

SE13 asserts the receipt holds only artifact ids + content hashes — the
deleted payload bytes never appear in the receipt JSON.

## 4. Content-addressed shared objects

- Storage is content-addressed (SHA-256). Identical payloads share one blob;
  deletion is **reference-count / record-based**: removing a project's
  references leaves the blob until the last reference is gone, then the
  retention GC can drop it. Invalidation never deletes — it only transitions
  record status, so a blob shared by another project stays intact.
- `project archive` ≠ `project delete`: archive keeps records (read-only);
  delete removes references and marks data for GC.

## 5. Known limits (recorded, not release-blocking)

- **SEC-004 (low)**: cross-project event delivery is deployment-scoped — the
  envelope carries `project_id` and the consumer must scope the channel
  (SE11 demonstrates the check).
- Backups deleted on their own retention schedule; a deleted primary object
  may survive in a pre-deletion backup until that backup ages out.
