# Migration and Rollback — Release 0.1

> Kế hoạch 07 §22 (Migration certification). Candidate:
> `1753831c752343aa89419e807aa57058266ff75c` ·
> `migration_rehearsal_receipt.json` → `MIGRATION_REHEARSAL: PASSED`.

## 1. Migration certification summary

| Requirement (plan §22) | Status | Evidence |
|---|---|---|
| Upgrade từ release/baseline được support | PASSED | `dry_run_migration` + `migrate_database` |
| Schema checksum/registry đúng | PASSED | canonical tables verified (`canonical_tables_verified == len(CANONICAL_TABLES)`) |
| Backup trước migration | PASSED | rehearsal thao tác trên copy (`source.db` untouched) |
| Rollback rehearsal hoặc forward-fix policy | PASSED | `rehearse_rollback` → `ROLLBACK_SUCCESS` |
| Existing non-video data không bị hỏng | PASSED | seed `chat_sessions` preserved (`pre_existing_data_preserved`) |
| Video workflow/artifact/job/ledger records bảo toàn | PASSED | migration set frozen + rehearsal |
| Re-run migration idempotent hoặc fail an toàn | PASSED | double `migrate_database` on copy succeeds |

## 2. Rehearsal recipe

Lane `MIGRATION_REHEARSAL` (release_phase27.py) thực hiện:

1. Tạo fresh SQLite DB với pre-existing non-video data (`chat_sessions` seed).
2. `dry_run_migration(source)` — dry-run không sửa DB (`dry_run == True`).
3. `rehearse_rollback(source)` — rollback rehearsal → `ROLLBACK_SUCCESS`.
4. Copy → `migrate_database` lần 1 (upgrade) → `MIGRATION_SUCCESS`.
5. `migrate_database` lần 2 trên bản đã migrate (idempotent) → `MIGRATION_SUCCESS`.
6. Verify seed row còn nguyên → `pre_existing_data_preserved == True`.

Re-run thủ công:

```bash
python scripts/migrate_database_schema.py --dry-run --db-path /tmp/wa_mig.db
```

## 3. Migration set frozen

Migration set/checksum được đóng băng tại candidate:
- `scripts/migrate_database_schema.py` + `scripts/migrate_event_logs.py`
- Kiểm tra bởi lane `ATTESTATION` (`migration_set_present`) và
  `build_hash_manifest.json` (build inputs).
- Bất kỳ thay đổi migration sau freeze → candidate SHA mới, rerun các lane
  bị ảnh hưởng, final verdict cũ bị vô hiệu (plan §19).

## 4. Rollback policy (plan §26)

- **Rollback release không downgrade database nếu không an toàn.** Chỉ áp dụng
  downgrade khi có rehearsal chứng minh forward-compatible; ngược lại dùng
  forward-fix policy.
- Disable/rollback provider KHÔNG xóa project/artifact evidence.
- Active run được pause/reconcile trước khi disable.
- Backup phải tồn tại trước mọi migration thực thi trên dữ liệu production.

## 5. Known limitation

- Rehearsal chạy trên SQLite; PostgreSQL được phủ bởi CI matrix job (delegated).
  Live PostgreSQL migration chưa được rehearsal local — ghi nhận trong
  `support_matrix.md` Known gaps và không trình bày là certified.
