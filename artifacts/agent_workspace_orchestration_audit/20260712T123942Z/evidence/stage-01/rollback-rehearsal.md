# Stage 1 — Rollback Rehearsal

## Chính sách rollback

- **Cấm downgrade schema DB live.** Application rollback chỉ được phép khi
  rehearsal trên bản copy chứng minh: backup nhất quán, dữ liệu immutable
  (plan/audit) được giữ, dual-read vẫn đọc được, restore verify khớp.
  Được enforce bằng `require_application_only_rollback(receipt)` —
  nếu thiếu bằng chứng, raise `ApplicationRollbackBlocked`.
- Với secret migration: **không rollback về plaintext**. Nếu runtime lỗi,
  rollback code nhưng giữ column/adapter encrypted (`enc:v1:kv<N>:`,
  `decrypt` đọc được ciphertext version cũ).
- Với constraint migration (GAP A): rollback bằng revision downgrade trên
  bản copy + verified backup; không xóa backup cho tới khi Stage 2 ổn định.

## Quy trình đã rehearsal

`rehearse_sqlite_release(source, backup_root)` (alembic path):

1. Backup nguyên tử `source-backup.sqlite3` (SQLite backup API, gồm WAL).
2. Tính digest sha256 của các bảng immutable
   (`task_plan_versions`, `task_nodes`, `task_edges`, `conversation_events`,
   `agent_turns`, `route_attempts_v3`, `partial_stream_artifacts`).
3. Copy → `upgrade-copy.sqlite3` → `alembic upgrade head`.
   Kiểm tra `immutable_data_preserved` + `dual_read_compatible`.
4. Copy → `downgrade-copy.sqlite3` → `upgrade head` → `downgrade base`
   (chỉ trên bản copy, chứng minh đường migration chạy được).
5. Restore backup vào `downgrade-copy` → `restore_verified` (digest khớp).
6. Nếu cả 3 check pass → `application_rollback_allowed=True`.

## Kết quả rehearsal (evidence)

| Item | Test | Result |
|---|---|---|
| Alembic upgrade/downgrade rehearsal + immutable data preserved | `test_phase9_safe_rollout.py::test_sqlite_rehearsal_preserves_immutable_plan_and_audit_data` | ✅ PASS |
| Pre-migration backup nhất quán (source không bị mutate) | `test_phase9_safe_rollout.py::test_pre_migration_backup_uses_consistent_sqlite_copy` | ✅ PASS |
| Legacy backup → migrate → restore → re-migrate (v2 canonical lane) | `test_phase9_rollback_rehearsal.py::test_full_rollback_rehearsal_sequence` | ✅ PASS |
| Backup bị tamper bị từ chối restore | `test_phase9_rollback_rehearsal.py::test_tampered_backup_checksum_rejection` | ✅ PASS |
| Backup thiếu bị từ chối restore | `test_phase9_rollback_rehearsal.py::test_missing_backup_rejection` | ✅ PASS |
| Alembic downgrade base reset test DB | `TestAlembicUpgrade::test_downgrade_base_resets_test_db` | ✅ PASS |

## Ghi chú vận hành

- `scripts/phase9_release_rehearsal.py` là CLI chạy rehearsal trên bản copy
  trước release; receipt có trường `application_rollback_allowed`.
- Không bao giờ chạy `alembic_downgrade_base` trên DB live — nó phá dữ liệu
  và chỉ dùng cho test/rehearsal copy.
