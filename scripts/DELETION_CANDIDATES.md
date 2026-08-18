# Scripts - Danh sách file đánh dấu xóa

Ngày khảo sát: 2026-08-18
Tiêu chí: file **không còn được tham chiếu** (không CI, không test, không import nội bộ nào còn sống, không tài liệu hướng dẫn chạy), hoặc là **one-off/debug/historical** đã hoàn thành vai trò. Tất cả file đều **compile hợp lệ** (không lỗi syntax) — chỉ loại bỏ vì không dùng nữa.

## A. Không còn chỗ nào tham chiếu (DEAD) — nên xóa

### A1. Audit phase cũ của quá trình migration (đã hoàn thành) — 18 file
- `scripts/audit_architecture_rules.py`
- `scripts/audit_phase0.py`
- `scripts/audit_phase1.py`
- `scripts/audit_phase2.py`
- `scripts/audit_phase3.py`
- `scripts/audit_phase4.py`
- `scripts/audit_phase5.py`
- `scripts/audit_phase6.py`
- `scripts/audit_phase7.py`
- `scripts/audit_phase8.py`
- `scripts/audit_phase9.py`
- `scripts/audit_phase10.py`
- `scripts/audit_phase11.py`
- `scripts/audit_phase12.py`
- `scripts/audit_phase13.py`
- `scripts/audit_phase14.py`
- `scripts/audit_phase15.py`
- `scripts/audit_phase16.py`

### A2. Guard-check Plan B (story/screenplay) bị thay bằng test pytest — 3 file
- `scripts/check_story_b1_artifact_contract.py`
- `scripts/check_story_b2_prompt_catalog.py`
- `scripts/check_story_b3_idea_gate.py`
  - Bị thay thế bởi `tests/contracts/test_story_b1_artifact_contract.py`, `test_story_b2_prompt_catalog.py`, `test_story_b3_idea_gate.py` (các test này import thẳng module `produce_b*` chứ không dùng các check script này).

### A3. Evidence producer phase VP3D đã xong, không còn ai gọi — 13 file
- `scripts/produce_phase20_evidence.py`
- `scripts/produce_phase21_evidence.py`
- `scripts/produce_phase22_evidence.py` (chỉ nối với `verification/produce_phase22_evidence.py` — cũng chết)
- `scripts/produce_phase23_evidence.py` (chỉ nối với `verification/produce_phase23_evidence.py` — cũng chết)
- `scripts/produce_phase24_evidence.py`
- `scripts/produce_phase25_evidence.py` (bản thật đang dùng là `verification/produce_phase25_evidence.py`)
- `scripts/produce_phase26_evidence.py` (bản thật đang dùng là `verification/produce_phase26_evidence.py`)
- `scripts/produce_phase9_12_evidence.py`
- `scripts/run_vp3d_phase4_evidence.py` (chỉ nối với `verification/produce_phase4_evidence.py` — cũng chết)
- `scripts/verify_phase23_workflows.py`
- `scripts/verify_phase24_verification_evals.py`
- `scripts/bench_phase3_performance.py`
- `scripts/phase9_release_rehearsal.py`

### A4. One-off / debug / tiện ích cũ — 6 file
- `scripts/_debug_hash_probe.py` (debug một lần)
- `scripts/download_stitch_screens.py` (tải screenshot một lần)
- `scripts/test_api_isolation.ps1` (kiểm tra cô lập package thủ công, đã thay bằng CI)
- `scripts/test_worker_isolation.ps1` (kiểm tra cô lập package thủ công, đã thay bằng CI)
- `scripts/frontend_api/generate_client.py` (chỉ được nhắc trong bản kế hoạch cũ, không build nào gọi)
- `scripts/schemas/check_contract_drift.py`

### A5. Studio Roadmap Plan-A (A3..A7) & Plan-C (C1..C5) evidence đã nghiệm thu xong — 12 file
- `scripts/studio_roadmap/produce_a3_evidence.py`
- `scripts/studio_roadmap/produce_a4_evidence.py`
- `scripts/studio_roadmap/produce_a5_evidence.py`
- `scripts/studio_roadmap/produce_a6_evidence.py`
- `scripts/studio_roadmap/produce_a7_evidence.py`
- `scripts/studio_roadmap/produce_c1_evidence.py`
- `scripts/studio_roadmap/produce_c2_evidence.py`
- `scripts/studio_roadmap/produce_c3_evidence.py`
- `scripts/studio_roadmap/produce_c4_evidence.py`
- `scripts/studio_roadmap/produce_c5_evidence.py`
- `scripts/studio_roadmap/google_probe.py`
- `scripts/studio_roadmap/google_qualification.py`

> Lưu ý: `produce_c6_evidence.py` được GIỮ LẠI — `produce_c9_evidence.py` (có test dùng) import `KNOWN_FAILURES` từ nó.

### A6. Verification: evidence/verify/fixture phase không dùng — 24 file
- `scripts/verification/fixture_phase21_audio.py`
- `scripts/verification/fixture_phase22_postproduction.py`
- `scripts/verification/fixture_phase23_workspace.py`
- `scripts/verification/fixture_phase24_e2e.py`
- `scripts/verification/hash_artifacts.py`
- `scripts/verification/independent_validate_phase24.py`
- `scripts/verification/probe_blender_runtime.py`
- `scripts/verification/produce_b1_evidence.py`
- `scripts/verification/produce_phase10_evidence.py`
- `scripts/verification/produce_phase11_evidence.py`
- `scripts/verification/produce_phase13_evidence.py`
- `scripts/verification/produce_phase14_evidence.py`
- `scripts/verification/produce_phase15_evidence.py`
- `scripts/verification/produce_phase16_evidence.py`
- `scripts/verification/produce_phase17_evidence.py`
- `scripts/verification/produce_phase18_evidence.py`
- `scripts/verification/produce_phase22_evidence.py`
- `scripts/verification/produce_phase23_evidence.py`
- `scripts/verification/produce_phase4_evidence.py`
- `scripts/verification/produce_phase7_evidence.py`
- `scripts/verification/produce_phase9_evidence.py`
- `scripts/verification/produce_script_eval_phase1_contract.py`
- `scripts/verification/produce_script_eval_phase2_idea.py`
- `scripts/verification/remediate_r0.py`
- `scripts/verification/run_script_eval_phase2_benchmark.py`
- `scripts/verification/smoke_openrouter_key.py`
- `scripts/verification/verify_phase12_browser_runtime.py`
- `scripts/verification/verify_phase17_durable_workflow.py`
- `scripts/verification/verify_phase18_artifact_invalidation.py`
- `scripts/verification/verify_phase19_cost_quota.py`
- `scripts/verification/verify_phase19_cycles_renderer.py`
- `scripts/verification/verify_phase20_generation_review.py`
- `scripts/verification/verify_phase7_normalization.py`
- `scripts/verification/verify_phase8_character_master.py`
- `scripts/verification/verify_phase8_director.py`
- `scripts/verification/produce_a0_bootstrap_manifest.py` (chỉ còn trong evidence đã lưu)

### A7. Historical (đã archive, chỉ nằm trong `historical/`) — 4 file
- `scripts/verification/historical/runbook_phase24_e2e.py`
- `scripts/verification/historical/verify_phase10_continuity.py`
- `scripts/verification/historical/verify_phase11_compiler.py`
- `scripts/verification/historical/verify_phase9_shot_graph.py`

### A8. Thư mục bytecode rác — có thể xóa
- Mọi thư mục `scripts/**/__pycache__/` (82 file `.pyc`) — sinh tự động, không cần giữ.

---

## B. File VẪN ĐANG DÙNG — KHÔNG xóa

Nhóm này có tham chiếu sống (CI `.github/workflows/ci.yaml`, `ci_remote.yaml`, test, import nội bộ còn sống, hoặc tài liệu vận hành) — giữ lại:

- Guard: `check_architecture_imports.py`, `check_duplicate_canonical_models.py`, `check_event_taxonomy.py`, `check_no_legacy_orchestration.py`, `check_no_new_direct_fetch.py`, `check_no_story_in_legacy_engines.py`, `check_openapi_snapshot.py`, `check_secret_exposure.py`, `check_story_b0_legacy_boundary.py`, `check_version_consistency.py`, `check_video_workspace_architecture.py`, `validate_artifact_schema.py`, `scaffold_architecture_v2.py`
- Migration: `migrate_database_schema.py` (dùng bởi health checker + release_phase27), `migrate_event_logs.py` (dùng bởi `verification/release_phase27.py`)
- Verify sống: `verify_phase14_cutover.py` (test dùng), `check_phase12_duplicates.py` (verify_phase14_cutover dùng)
- Evidence sống: `produce_stage_i_evidence.py` (test dùng), `verification/produce_phase25_evidence.py`, `verification/produce_phase26_evidence.py`, `verification/produce_phase9_preview.py` + `verification/blender_rig_preview.py` (test dùng)
- Core verification lib: `verification/evidence_lib.py`, `verification/secret_redactor.py`, `verification/test_environment_builder.py`, `verification/security_phase26.py`, `verification/release_phase27.py`, `verification/capture_environment.py`, `verification/database_preflight.py`, `verification/runtime_version_smoke.py`, `verification/generate_phase7_evidence.py`, `verification/validate_evidence_bundle.py`, `verification/validate_ci_evidence.py`, `verification/run_command_receipt.py`, `verification/run_negative_injections.py`, `verification/build_phase7_source_index.py`, `verification/finalize_phase7.py`, `verification/finalize_evidence.py`, `verification/hydrate_phase7_evidence.py`
- Verify phase 3-7: `verification/verify_phase03_handoff.py`, `verify_phase3_protocol.py`, `verify_phase4_intake.py`, `verify_phase5_characterization.py`, `verify_phase6_kernel.py`, `verify_phase7_assets.py`, `verification/phase5_upstream_probe.py`
- Verify 21-27: `verification/verify_phase21_audio_pipeline.py`, `verify_phase22_postproduction.py`, `verify_phase23_production_workspace.py`, `verify_phase24_e2e_poc.py`, `verify_phase25_reliability.py`, `verify_phase26_security.py`, `verify_phase27_release.py` + fixture tương ứng (`fixture_phase25/26/27`)
- Story pipeline: `verification/produce_b2..b9_evidence.py` (test b2..b9 gate import)
- Studio Roadmap còn sống: `studio_roadmap/run_ci_checkers.py` (CI chạy), `studio_roadmap/c7_slice_harness.py`, `c7_desktop_evidence.py`, `c8_recovery_harness.py`, `certification_launcher.py`, `produce_c7_evidence.py`, `produce_c8_evidence.py`, `produce_c9_evidence.py` (test `test_studio_c8_c9_certification.py` dùng)
- Frontend API: `frontend_api/export_openapi.py`, `frontend_api/validate_openapi.py` (audit_phase3 + generate_client dùng; nếu xóa A1/A4 thì 2 file này chỉ còn dùng lẫn nhau — cân nhắc giữ vì validate_openapi còn trong docs kế hoạch)
- Schemas: `schemas/generate_ts_contracts.py` (test `test_api_contract_compatibility.py` dùng)
- Dev: `dev_api.ps1`, `dev_desktop.ps1`, `dev_frontend.ps1`, `healthcheck.ps1` (run.ps1/README/tests dùng)
- Benchmark: `bench_orchestration_v2.py` (test `test_cutover_defects.py` dùng)
- `verification/__init__.py`, `verification/historical/__init__.py` (package markers)

---

## C. Kết quả thực thi
- Đã xóa **93 file** (A1, A2, A3, A4, A5 trừ `produce_c6_evidence.py`, A6, A7) + toàn bộ thư mục `__pycache__/`.
- Khôi phục `scripts/studio_roadmap/produce_c6_evidence.py` (vì `produce_c9_evidence.py` đang dùng bởi test import từ nó).
- Sau xóa: `python -m compileall -q scripts` → pass (0 lỗi), không còn import nào trỏ vào file đã xóa.
- Còn lại **89 file** trong `scripts/` (đều đang được tham chiếu bởi CI/test/import nội bộ sống).