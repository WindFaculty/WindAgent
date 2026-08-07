# Stage 1 — Acceptance Matrix (evidence)

> Bundle: `evidence/stage-01/` — generated 2026-08-07, branch
> `fix/phase7-verification-integrity` @ `9080fcb4bb6d9a6531a095c624a0f6d8796f4081`.
> Test run: `test-results.json` (102 passed / 0 failed / 1 skipped, exit 0).

| Gap | Acceptance | Test / receipt | Result |
|---|---|---|---|
| G1.1 | Empty DB `alembic upgrade head` tạo đủ schema; downgrade revision thành công; existing DB upgrade không mất dữ liệu | `TestAlembicUpgrade` (test_phase1_migration_integrity.py) + `test_phase9_migrations.py` + `test_phase9_rollback_rehearsal.py` | ✅ PASS |
| G1.2 | Query theo `windagent_session_id` chỉ 0/1 row; FK/index tồn tại và orphan insert bị chặn | `test_multi_agent_constraints_exist`, `test_unique_windagent_session_id_enforced`, `TestForeignKeyEnforcement` (sync + async) | ✅ PASS |
| G1.3 | Edit plan đang chạy sinh row/version mới; version cũ đọc lại đúng | `test_phase7_workspace_projection.py` (409 concurrency) + `test_phase4_durable_plan_scheduler.py` | ✅ PASS |
| G2.3 | DB không còn plaintext; GET provider không trả key/ciphertext; update key vẫn dùng được | `TestSecretEncryption`, `TestKeyRotation` (GAP C), `v3_schema_migration` data lane | ✅ PASS |
| G9.5 | Mọi biến thể path thoát root nhận 4xx, không tạo session/run | `TestWorkspaceRootValidation` + `test_phase3_negative.py` + `test_api_rejects_traversal_with_400` | ✅ PASS |
| GAP A | `PRAGMA foreign_keys=ON` trên sync + async; orphan insert bị reject | `TestForeignKeyEnforcement` + toàn bộ suite FK-enabled | ✅ PASS |
| GAP A phát hiện | Production worker `claim_next` tạo lease không có `workflow_step_runs` → bug thật đã fix | `test_phase14_two_process_e2e.py`, `test_phase2_transactional_finalization.py` | ✅ PASS |
| GAP B | Preflight đếm duplicate/orphan, block migration, báo bằng ID | `DuplicateRule`/`OrphanRule` + `test_phase7_schema_mapping.py` | ✅ PASS |
| GAP C | `key_version`, `reencrypt_to_current`, per-version env key | `TestKeyRotation` (6 tests) | ✅ PASS |
| GAP D | Lệnh kiểm tra Alembic `current`/single-head | `TestAlembicHeadIntegrity` (6 tests: heads, verify_single_head, current before/after upgrade/downgrade) | ✅ PASS |

## Ghi chú

- Test đơn lẻ pre-existing không liên quan Stage 1: `test_ci_run_manifest_aggregates_all_required_lanes`
  (HEAD repo ≠ CANDIDATE_SHA hardcode trong test) — đã xác minh bằng stash A/B, không phải regression từ Stage 1.
- Test bị skip (1): phụ thuộc platform (symlink) — xem `test_symlink_escape_rejected`.
