# Artifacts - Danh sách file đánh dấu xóa

Ngày khảo sát: 2026-08-18
Phương pháp: dò từng file, đối chiếu mọi tham chiếu rtifacts/... từ code/test/CI/script còn tồn tại (loại bỏ tham chiếu từ doc lịch sử/kế hoạch đã hoàn thành và script đã xóa). File nào còn được đọc/ghi bởi code sống -> KEEP; còn lại -> DEAD (đánh dấu xóa).

Tổng: **787 file** — **KEEP 289** — **DEAD 498**.

## A. VẪN ĐANG DÙNG — GIỮ LẠI (289 file)

| Nhóm | Số file | Lý do còn dùng |
|---|---|---|
| `code_video/` | 239 | Feature đang phát triển: test `test_code_video_*`, `generate_phase_07_artifacts.py`, `studio_capture.py`, `recorder.py` đọc/ghi |
| `architecture_v2_production_hardening/phase_07/` | 19 | `finalize_phase7.py` + test CI đọc/ghi |
| `architecture_v2_runtime_cutover/phase_13/dependency_boundary_report.json` + `import_graph.json` | 2 | `check_architecture_imports.py` (guard CI) ghi mặc định |
| `core_canonical/phase_14/final/` | 10 | `verify_phase14_cutover.py` (verifier sống) ghi 10 file |
| `ci/` (`c6_junit.xml`, `version_consistency_report.json`, `phase7/version_consistency_report.json`) | 3 | `produce_c6_evidence.py` đọc junit; `check_version_consistency.py` ghi báo cáo |
| `logs/api.log` | 1 | `dev_api.ps1` ghi log |
| `orchestration_v2/` (`benchmark_report.json`, `repair/benchmark_report.json`, `repair/benchmark_raw_samples.json`) | 3 | `bench_orchestration_v2.py` ghi |
| `frontend_restructure/` (7 file) | 7 | `check_no_new_direct_fetch.py`, `validate/export_openapi.py`, test phase 3-5 đọc |
| `video_production/script_eval/phase_00_baseline/` | 5 | `produce_script_eval_phase0_baseline.py` (sống) ghi |

## B. KHÔNG CÒN ĐƯỢC SỬ DỤNG — ĐÁNH DẤU XÓA (498 file)

> Ghi chú: các file này là kết quả của các migration/audit/phase đã hoàn thành, không còn script/test/CI nào đọc hoặc ghi. Một số chỉ được nhắc trong doc kế hoạch lịch sử (`ban_ke_hoach_*.md`, `docs/plans/...`, `docs/video_production/...`) hoặc bởi script đã xóa.

### agent_workspace_orchestration_audit — 8 file

- agent_workspace_orchestration_audit/20260712T123942Z/commands.log
- agent_workspace_orchestration_audit/20260712T123942Z/evidence/stage-01/baseline.json
- agent_workspace_orchestration_audit/20260712T123942Z/evidence/stage-01/test-results.json
- agent_workspace_orchestration_audit/20260712T123942Z/feature_matrix.json
- agent_workspace_orchestration_audit/20260712T123942Z/git_provenance.json
- agent_workspace_orchestration_audit/20260712T123942Z/latest.txt
- agent_workspace_orchestration_audit/20260712T123942Z/risks.json
- agent_workspace_orchestration_audit/20260712T123942Z/test_results.json

### agent_workspace_orchestration_phase2 — 25 file

- agent_workspace_orchestration_phase2/20260712162009/git_status_before.txt
- agent_workspace_orchestration_phase2/20260712232155/commands.log
- agent_workspace_orchestration_phase2/20260712232155/git_branch_show_current.txt
- agent_workspace_orchestration_phase2/20260712232155/git_diff_cached_stat.txt
- agent_workspace_orchestration_phase2/20260712232155/git_diff_name_status.txt
- agent_workspace_orchestration_phase2/20260712232155/git_diff_stat_before.txt
- agent_workspace_orchestration_phase2/20260712232155/git_head.txt
- agent_workspace_orchestration_phase2/20260712232155/git_log.txt
- agent_workspace_orchestration_phase2/20260712232155/git_ls_files_others.txt
- agent_workspace_orchestration_phase2/20260712232155/git_porcelain_v2_before.txt
- agent_workspace_orchestration_phase2/20260712232155/git_remote.txt
- agent_workspace_orchestration_phase2/20260712232155/git_status_before.txt
- agent_workspace_orchestration_phase2/20260712232155/git_toplevel.txt
- agent_workspace_orchestration_phase2/20260712232155/git_worktree_list.txt
- agent_workspace_orchestration_phase2/20260712T144030Z/commands.log
- agent_workspace_orchestration_phase2/20260712T144030Z/environment.txt
- agent_workspace_orchestration_phase2/20260712T144030Z/git_diff_stat_before.txt
- agent_workspace_orchestration_phase2/20260712T144030Z/git_porcelain_v2_before.txt
- agent_workspace_orchestration_phase2/20260712T144030Z/git_status_before.txt
- agent_workspace_orchestration_phase2/20260712T144030Z/staged_worktree_before.patch
- agent_workspace_orchestration_phase2/20260712T144030Z/starting_head.txt
- agent_workspace_orchestration_phase2/20260712T144030Z/tracked_changes_manifest.txt
- agent_workspace_orchestration_phase2/20260712T144030Z/tracked_worktree_before.patch
- agent_workspace_orchestration_phase2/20260712T144030Z/untracked_files_manifest.txt
- agent_workspace_orchestration_phase2/20260712T144030Z/worktree_manifest.txt

### architecture_v2 — 28 file

- architecture_v2/baseline/api_inventory.json
- architecture_v2/baseline/baseline_receipt.json
- architecture_v2/baseline/database_inventory.json
- architecture_v2/baseline/dependency_graph.json
- architecture_v2/baseline/event_inventory.json
- architecture_v2/phase_00/provider_v3_baseline_test_receipt.json
- architecture_v2/phase_01/provider_v3_contracts_receipt.json
- architecture_v2/phase_01/scaffold_receipt.json
- architecture_v2/phase_02/core_domain_receipt.json
- architecture_v2/phase_02/provider_v3_schema_receipt.json
- architecture_v2/phase_03/event_model_receipt.json
- architecture_v2/phase_03/provider_v3_openai_transport_receipt.json
- architecture_v2/phase_04/provider_v3_native_adapters_receipt.json
- architecture_v2/phase_04/storage_receipt.json
- architecture_v2/phase_05/provider_router_receipt.json
- architecture_v2/phase_05/provider_v3_test_connect_receipt.json
- architecture_v2/phase_06/provider_v3_canonical_registry_receipt.json
- architecture_v2/phase_06/tool_platform_receipt.json
- architecture_v2/phase_07/plugins_skills_mcp_receipt.json
- architecture_v2/phase_07/provider_v3_rule_selection_route_lock_receipt.json
- architecture_v2/phase_08/orchestration_receipt.json
- architecture_v2/phase_09/context_memory_receipt.json
- architecture_v2/phase_10/workflow_packs_receipt.json
- architecture_v2/phase_11/verification_evals_observability_receipt.json
- architecture_v2/phase_12/api_worker_cli_receipt.json
- architecture_v2/phase_13/web_desktop_decouple_receipt.json
- architecture_v2/phase_14/legacy_cutover_receipt.json
- architecture_v2/phase_14/legacy_cutover_receipt_correction.json

### architecture_v2_completion — 51 file

- architecture_v2_completion/final/architecture_graph.json
- architecture_v2_completion/final/ci_receipt.json
- architecture_v2_completion/final/commit_receipt.json
- architecture_v2_completion/final/crash_recovery_receipt.json
- architecture_v2_completion/final/final_verdict.json
- architecture_v2_completion/final/legacy_removal_report.json
- architecture_v2_completion/final/migration_receipt.json
- architecture_v2_completion/final/multi_replica_fencing_receipt.json
- architecture_v2_completion/final/package_maturity_matrix.json
- architecture_v2_completion/final/performance_report.json
- architecture_v2_completion/final/rollback_receipt.json
- architecture_v2_completion/final/security_report.json
- architecture_v2_completion/final/test_matrix.json
- architecture_v2_completion/phase_15/backend_failure_classification.json
- architecture_v2_completion/phase_15/baseline_verdict.json
- architecture_v2_completion/phase_15/ci_receipt.json
- architecture_v2_completion/phase_15/package_maturity_matrix.json
- architecture_v2_completion/phase_15/repository_inventory.json
- architecture_v2_completion/phase_15/test_receipt.json
- architecture_v2_completion/phase_16/dependency_boundary_report.json
- architecture_v2_completion/phase_16/phase_16_verdict.json
- architecture_v2_completion/phase_17/canonical_schema_manifest.json
- architecture_v2_completion/phase_17/migration_rollback_receipt.json
- architecture_v2_completion/phase_17/observability_span_audit.json
- architecture_v2_completion/phase_17/phase_17_verdict.json
- architecture_v2_completion/phase_18/crash_recovery_receipt.json
- architecture_v2_completion/phase_18/durable_worker_fencing_matrix.json
- architecture_v2_completion/phase_18/multi_replica_isolation_test.json
- architecture_v2_completion/phase_18/phase_18_verdict.json
- architecture_v2_completion/phase_19/mcp_trust_report.json
- architecture_v2_completion/phase_19/phase_19_verdict.json
- architecture_v2_completion/phase_19/tool_catalog.json
- architecture_v2_completion/phase_19/tool_security_matrix.json
- architecture_v2_completion/phase_23/builtin_packs_receipt.json
- architecture_v2_completion/phase_23/dag_validation_receipt.json
- architecture_v2_completion/phase_23/migration_receipt.json
- architecture_v2_completion/phase_23/phase_23_verdict.json
- architecture_v2_completion/phase_24/phase_24_verdict.json
- architecture_v2_completion/phase_24/test_receipt.json
- architecture_v2_completion/phase_25/api_e2e_task_execution_receipt.json
- architecture_v2_completion/phase_25/canonical_api_routes.json
- architecture_v2_completion/phase_25/phase_25_verdict.json
- architecture_v2_completion/phase_25/websocket_replay_receipt.json
- architecture_v2_completion/phase_26/cli_convergence_matrix.json
- architecture_v2_completion/phase_26/desktop_sidecar_receipt.json
- architecture_v2_completion/phase_26/phase_26_verdict.json
- architecture_v2_completion/phase_26/web_client_verification.json
- architecture_v2_completion/phase_27/ast_import_scan_report.json
- architecture_v2_completion/phase_27/compatibility_shim_receipt.json
- architecture_v2_completion/phase_27/legacy_evacuation_manifest.json
- architecture_v2_completion/phase_27/phase_27_verdict.json

### architecture_v2_production_hardening — 20 file

- architecture_v2_production_hardening/phase_01/canonical_schema_manifest.json
- architecture_v2_production_hardening/phase_01/migration_receipt.json
- architecture_v2_production_hardening/phase_01/process_restart_report.json
- architecture_v2_production_hardening/phase_01/registry_parity_report.json
- architecture_v2_production_hardening/phase_01/rollback_receipt.json
- architecture_v2_production_hardening/phase_01/route_lock_concurrency_report.json
- architecture_v2_production_hardening/phase_01/same_model_failover_report.json
- architecture_v2_production_hardening/phase_01/test_results.json
- architecture_v2_production_hardening/phase_02/crash_point_matrix.json
- architecture_v2_production_hardening/phase_02/fault_injection_matrix.json
- architecture_v2_production_hardening/phase_02/outbox_idempotency_report.json
- architecture_v2_production_hardening/phase_02/recovery_report.json
- architecture_v2_production_hardening/phase_02/stale_result_report.json
- architecture_v2_production_hardening/phase_02/test_results.json
- architecture_v2_production_hardening/phase_07_repair/baseline/baseline_commit.json
- architecture_v2_production_hardening/phase_07_repair/baseline/baseline_verdict.json
- architecture_v2_production_hardening/phase_07_repair/baseline/ci_defect_inventory.json
- architecture_v2_production_hardening/phase_07_repair/baseline/cli_command_classification.json
- architecture_v2_production_hardening/phase_07_repair/baseline/invalid_artifact_inventory.json
- architecture_v2_production_hardening/phase_07_repair/baseline/validator_output_baseline.txt

### architecture_v2_real_cutover — 61 file

- architecture_v2_real_cutover/phase_00/architecture_check_baseline.txt
- architecture_v2_real_cutover/phase_00/baseline_info.txt
- architecture_v2_real_cutover/phase_00/changed_files.txt
- architecture_v2_real_cutover/phase_00/dependency_graph.json
- architecture_v2_real_cutover/phase_00/execution_receipt.json
- architecture_v2_real_cutover/phase_00/git_branch_show_current.txt
- architecture_v2_real_cutover/phase_00/git_diff_cached_stat.txt
- architecture_v2_real_cutover/phase_00/git_diff_name_status.txt
- architecture_v2_real_cutover/phase_00/git_diff_stat_before.txt
- architecture_v2_real_cutover/phase_00/git_head.txt
- architecture_v2_real_cutover/phase_00/git_log.txt
- architecture_v2_real_cutover/phase_00/git_ls_files_others.txt
- architecture_v2_real_cutover/phase_00/git_porcelain_v2_before.txt
- architecture_v2_real_cutover/phase_00/git_remote.txt
- architecture_v2_real_cutover/phase_00/git_stash_list.txt
- architecture_v2_real_cutover/phase_00/git_status_after.txt
- architecture_v2_real_cutover/phase_00/git_status_before.txt
- architecture_v2_real_cutover/phase_00/git_toplevel.txt
- architecture_v2_real_cutover/phase_00/git_worktree_list.txt
- architecture_v2_real_cutover/phase_00/phase0_attestation.json
- architecture_v2_real_cutover/phase_00/python_imports.json
- architecture_v2_real_cutover/phase_00/reference_commit_type.txt
- architecture_v2_real_cutover/phase_00/reference_is_ancestor.txt
- architecture_v2_real_cutover/phase_00/secret_scan_summary.json
- architecture_v2_real_cutover/phase_00/staged_worktree_before.patch
- architecture_v2_real_cutover/phase_00/test_results.json
- architecture_v2_real_cutover/phase_00/test_results_raw.txt
- architecture_v2_real_cutover/phase_00/tracked_worktree_before.patch
- architecture_v2_real_cutover/phase_01/changed_files.txt
- architecture_v2_real_cutover/phase_01/dependency_graph.json
- architecture_v2_real_cutover/phase_01/dependency_policy_report.json
- architecture_v2_real_cutover/phase_01/execution_receipt.json
- architecture_v2_real_cutover/phase_01/phase_01_check_results.json
- architecture_v2_real_cutover/phase_01/test_results.json
- architecture_v2_real_cutover/phase_02/changed_files.txt
- architecture_v2_real_cutover/phase_02/execution_receipt.json
- architecture_v2_real_cutover/phase_02/test_results.json
- architecture_v2_real_cutover/phase_03/changed_files.txt
- architecture_v2_real_cutover/phase_03/execution_receipt.json
- architecture_v2_real_cutover/phase_03/test_results.json
- architecture_v2_real_cutover/phase_04/changed_files.txt
- architecture_v2_real_cutover/phase_04/execution_receipt.json
- architecture_v2_real_cutover/phase_04/test_results.json
- architecture_v2_real_cutover/phase_05/changed_files.txt
- architecture_v2_real_cutover/phase_05/execution_receipt.json
- architecture_v2_real_cutover/phase_05/test_results.json
- architecture_v2_real_cutover/phase_06/changed_files.txt
- architecture_v2_real_cutover/phase_06/execution_receipt.json
- architecture_v2_real_cutover/phase_06/test_results.json
- architecture_v2_real_cutover/phase_07/changed_files.txt
- architecture_v2_real_cutover/phase_07/execution_receipt.json
- architecture_v2_real_cutover/phase_07/test_results.json
- architecture_v2_real_cutover/phase_08/changed_files.txt
- architecture_v2_real_cutover/phase_08/execution_receipt.json
- architecture_v2_real_cutover/phase_08/test_results.json
- architecture_v2_real_cutover/phase_09/changed_files.txt
- architecture_v2_real_cutover/phase_09/execution_receipt.json
- architecture_v2_real_cutover/phase_09/test_results.json
- architecture_v2_real_cutover/phase_10/changed_files.txt
- architecture_v2_real_cutover/phase_10/execution_receipt.json
- architecture_v2_real_cutover/phase_10/test_results.json

### architecture_v2_runtime_cutover — 80 file

- architecture_v2_runtime_cutover/CURRENT_VERDICT.json
- architecture_v2_runtime_cutover/final/api_lifecycle_report.json
- architecture_v2_runtime_cutover/final/clean_clone_report.json
- architecture_v2_runtime_cutover/final/dependency_report.json
- architecture_v2_runtime_cutover/final/e2e_report.json
- architecture_v2_runtime_cutover/final/file_hash_manifest.json
- architecture_v2_runtime_cutover/final/health_report.json
- architecture_v2_runtime_cutover/final/lease_recovery_report.json
- architecture_v2_runtime_cutover/final/migration_report.json
- architecture_v2_runtime_cutover/final/outbox_report.json
- architecture_v2_runtime_cutover/final/package_isolation_report.json
- architecture_v2_runtime_cutover/final/publication_receipt.json
- architecture_v2_runtime_cutover/final/remediation_rerun_20260726/clean_worktree_verification.json
- architecture_v2_runtime_cutover/final/remediation_rerun_20260726/local_verification.json
- architecture_v2_runtime_cutover/final/rollback_report.json
- architecture_v2_runtime_cutover/final/worker_runtime_report.json
- architecture_v2_runtime_cutover/phase_00/changed_files.txt
- architecture_v2_runtime_cutover/phase_00/execution_receipt.json
- architecture_v2_runtime_cutover/phase_00/test_results.json
- architecture_v2_runtime_cutover/phase_01/changed_files.txt
- architecture_v2_runtime_cutover/phase_01/execution_receipt.json
- architecture_v2_runtime_cutover/phase_01/test_results.json
- architecture_v2_runtime_cutover/phase_02/changed_files.txt
- architecture_v2_runtime_cutover/phase_02/execution_receipt.json
- architecture_v2_runtime_cutover/phase_02/test_results.json
- architecture_v2_runtime_cutover/phase_03/changed_files.txt
- architecture_v2_runtime_cutover/phase_03/execution_receipt.json
- architecture_v2_runtime_cutover/phase_03/performance_report.json
- architecture_v2_runtime_cutover/phase_03/phase_verdict.json
- architecture_v2_runtime_cutover/phase_03/test_results.json
- architecture_v2_runtime_cutover/phase_04/architecture_enforcement/architecture_policy_v3.yaml
- architecture_v2_runtime_cutover/phase_04/architecture_enforcement/import_graph.json
- architecture_v2_runtime_cutover/phase_04/architecture_enforcement/test_results.json
- architecture_v2_runtime_cutover/phase_04/architecture_enforcement/test_run_report.json
- architecture_v2_runtime_cutover/phase_04/changed_files.txt
- architecture_v2_runtime_cutover/phase_04/execution_receipt.json
- architecture_v2_runtime_cutover/phase_04/test_results.json
- architecture_v2_runtime_cutover/phase_05/changed_files.txt
- architecture_v2_runtime_cutover/phase_05/execution_receipt.json
- architecture_v2_runtime_cutover/phase_05/test_results.json
- architecture_v2_runtime_cutover/phase_06/clean_install_report.json
- architecture_v2_runtime_cutover/phase_06/compatibility_shim_report.json
- architecture_v2_runtime_cutover/phase_06/deleted_files_manifest.json
- architecture_v2_runtime_cutover/phase_06/execution_receipt.json
- architecture_v2_runtime_cutover/phase_06/legacy_consumer_inventory.json
- architecture_v2_runtime_cutover/phase_06/legacy_file_classification.json
- architecture_v2_runtime_cutover/phase_06/migrated_contract_tests.json
- architecture_v2_runtime_cutover/phase_06/test_results.json
- architecture_v2_runtime_cutover/phase_06/zero_legacy_import_report.json
- architecture_v2_runtime_cutover/phase_07/execution_receipt.json
- architecture_v2_runtime_cutover/phase_07/test_results.json
- architecture_v2_runtime_cutover/phase_08/execution_receipt.json
- architecture_v2_runtime_cutover/phase_08/test_results.json
- architecture_v2_runtime_cutover/phase_09/execution_receipt.json
- architecture_v2_runtime_cutover/phase_09/rollback_report.json
- architecture_v2_runtime_cutover/phase_09/test_results.json
- architecture_v2_runtime_cutover/phase_10/execution_receipt.json
- architecture_v2_runtime_cutover/phase_10/health_report.json
- architecture_v2_runtime_cutover/phase_10/test_results.json
- architecture_v2_runtime_cutover/phase_11/execution_receipt.json
- architecture_v2_runtime_cutover/phase_11/health_report.json
- architecture_v2_runtime_cutover/phase_11/test_results.json
- architecture_v2_runtime_cutover/phase_12/changed_files.txt
- architecture_v2_runtime_cutover/phase_12/execution_receipt.json
- architecture_v2_runtime_cutover/phase_12/test_results.json
- architecture_v2_runtime_cutover/phase_13/changed_files.txt
- architecture_v2_runtime_cutover/phase_13/execution_receipt.json
- architecture_v2_runtime_cutover/phase_13/test_results.json
- architecture_v2_runtime_cutover/phase_14/changed_files.txt
- architecture_v2_runtime_cutover/phase_14/execution_receipt.json
- architecture_v2_runtime_cutover/phase_14/test_evidence.log
- architecture_v2_runtime_cutover/phase_14/test_results.json
- architecture_v2_runtime_cutover/phase_15/changed_files.txt
- architecture_v2_runtime_cutover/phase_15/test_evidence.log
- architecture_v2_runtime_cutover/phase_15/test_results.json
- architecture_v2_runtime_cutover/phase_16/changed_files.txt
- architecture_v2_runtime_cutover/phase_16/execution_receipt.json
- architecture_v2_runtime_cutover/phase_16/test_results.json
- architecture_v2_runtime_cutover/remediation/cleanup_manifest.json
- architecture_v2_runtime_cutover/remediation/worktree_manifest.json

### ci — 3 file

- ci/a7_junit.xml
- ci/database_preflight.json
- ci/runtime_smoke_report.json

### core_canonical — 29 file

- core_canonical/phase_00/baseline_receipt.json
- core_canonical/phase_00/config_inventory.json
- core_canonical/phase_00/dependency_graph.json
- core_canonical/phase_00/duplicate_model_inventory.json
- core_canonical/phase_00/error_inventory.json
- core_canonical/phase_00/event_inventory.json
- core_canonical/phase_00/lifecycle_inventory.json
- core_canonical/phase_00/security_inventory.json
- core_canonical/phase_14_completion/backend_adoption/backend_full_test.txt
- core_canonical/phase_14_completion/baseline/backend_collect.txt
- core_canonical/phase_14_completion/baseline/backend_collection.txt
- core_canonical/phase_14_completion/baseline/backend_cwd_collection.txt
- core_canonical/phase_14_completion/baseline/backend_full_current.txt
- core_canonical/phase_14_completion/baseline/backend_test.txt
- core_canonical/phase_14_completion/baseline/environment_manifest.txt
- core_canonical/phase_14_completion/baseline/existing_phase_14_artifacts.json
- core_canonical/phase_14_completion/baseline/git_log.txt
- core_canonical/phase_14_completion/baseline/git_status.txt
- core_canonical/phase_14_completion/baseline/head_sha.txt
- core_canonical/phase_14_completion/baseline/NOTE.txt
- core_canonical/phase_14_completion/baseline/repository_state.json
- core_canonical/phase_14_completion/baseline/root_collect.txt
- core_canonical/phase_14_completion/baseline/root_collection.txt
- core_canonical/phase_14_completion/baseline/root_test.txt
- core_canonical/phase_14_completion/baseline/starting_verdict.json
- core_canonical/phase_14_completion/baseline/stash_list.txt
- core_canonical/phase_14_completion/final_verdict.json
- core_canonical/phase_14_completion/test_reconciliation/failing_test_inventory.json
- core_canonical/phase_14_completion/test_reconciliation/test_scope_diff.json

### documentation_cleanup — 5 file

- documentation_cleanup/bao_cao_tong_quan_2026-08-07.md
- documentation_cleanup/cleanup_classification_2026-08-08.md
- documentation_cleanup/docs_audit_after.md
- documentation_cleanup/docs_audit_before.md
- documentation_cleanup/docs_cleanup_manifest.json

### frontend_restructure — 129 file

- frontend_restructure/final/api_inventory.json
- frontend_restructure/final/architecture_report.json
- frontend_restructure/final/backend_tests.json
- frontend_restructure/final/contract_tests.json
- frontend_restructure/final/dead_code_scan.json
- frontend_restructure/final/desktop_build.json
- frontend_restructure/final/desktop_e2e.json
- frontend_restructure/final/e2e_tests.json
- frontend_restructure/final/final_report.md
- frontend_restructure/final/final_verdict.json
- frontend_restructure/final/frontend_tests.json
- frontend_restructure/final/generated_client_report.json
- frontend_restructure/final/legacy_api_scan.json
- frontend_restructure/final/mock_runtime_scan.json
- frontend_restructure/final/navigation_inventory.json
- frontend_restructure/final/openapi_report.json
- frontend_restructure/final/package_dependency_report.json
- frontend_restructure/final/risk_register.md
- frontend_restructure/final/route_inventory.json
- frontend_restructure/final/web_build.json
- frontend_restructure/final/web_e2e.json
- frontend_restructure/phase_00/api_consumer_matrix.json
- frontend_restructure/phase_00/api_endpoint_inventory.json
- frontend_restructure/phase_00/baseline/baseline_manifest.json
- frontend_restructure/phase_00/baseline/environment_manifest.json
- frontend_restructure/phase_00/baseline/git_manifest.json
- frontend_restructure/phase_00/baseline_failures.json
- frontend_restructure/phase_00/baseline_report.md
- frontend_restructure/phase_00/baseline_verdict.json
- frontend_restructure/phase_00/build_matrix.json
- frontend_restructure/phase_00/css_duplicate_report.json
- frontend_restructure/phase_00/css_selector_inventory.json
- frontend_restructure/phase_00/css_token_inventory.json
- frontend_restructure/phase_00/design_system_baseline.md
- frontend_restructure/phase_00/final_verdict.json
- frontend_restructure/phase_00/frontend_file_inventory.json
- frontend_restructure/phase_00/mock_data_inventory.json
- frontend_restructure/phase_00/navigation_inventory.json
- frontend_restructure/phase_00/package_inventory.json
- frontend_restructure/phase_00/risk_register.md
- frontend_restructure/phase_00/route_inventory.json
- frontend_restructure/phase_00/route_navigation_mismatch.json
- frontend_restructure/phase_00/state_management_inventory.json
- frontend_restructure/phase_00/test_matrix.json
- frontend_restructure/phase_01/final_verdict.json
- frontend_restructure/phase_01/legacy_to_canonical_map.json
- frontend_restructure/phase_01/unresolved_terms.json
- frontend_restructure/phase_01/vocabulary_manifest.json
- frontend_restructure/phase_02/final_verdict.json
- frontend_restructure/phase_02/openapi_quality_gate.json
- frontend_restructure/phase_02/v3_common_contracts_manifest.json
- frontend_restructure/phase_03/generation_manifest.json
- frontend_restructure/phase_03/openapi_manifest.json
- frontend_restructure/phase_03/operation_id_report.json
- frontend_restructure/phase_04/platform_adapter_manifest.json
- frontend_restructure/phase_04/route_authority_manifest.json
- frontend_restructure/phase_04/shell_architecture_report.json
- frontend_restructure/phase_05/accessibility_audit_report.json
- frontend_restructure/phase_05/component_catalog_manifest.json
- frontend_restructure/phase_05/design_token_manifest.json
- frontend_restructure/phase_06/baseline/api_contract_baseline.json
- frontend_restructure/phase_06/baseline/baseline.md
- frontend_restructure/phase_06/baseline/commit.json
- frontend_restructure/phase_06/baseline/dashboard_runtime_inventory.json
- frontend_restructure/phase_06/baseline/synthetic_data_inventory.json
- frontend_restructure/phase_06/baseline/test_baseline.json
- frontend_restructure/phase_06/final/final_verdict.json
- frontend_restructure/phase_06/final/runtime_cutover_manifest.json
- frontend_restructure/phase_06/final/synthetic_data_elimination_report.json
- frontend_restructure/phase_07/baseline/api_contract_baseline.json
- frontend_restructure/phase_07/baseline/baseline.md
- frontend_restructure/phase_07/baseline/commit.json
- frontend_restructure/phase_07/baseline/hash_routing_inventory.json
- frontend_restructure/phase_07/baseline/studio_store_usage_inventory.json
- frontend_restructure/phase_07/baseline/test_baseline.json
- frontend_restructure/phase_07/final/final_verdict.json
- frontend_restructure/phase_07/final/projects_studio_convergence_manifest.json
- frontend_restructure/phase_07/final/studio_store_elimination_report.json
- frontend_restructure/phase_08/baseline/baseline.md
- frontend_restructure/phase_08/baseline/commit.json
- frontend_restructure/phase_08/baseline/mock_episodes_inventory.json
- frontend_restructure/phase_08/baseline/test_baseline.json
- frontend_restructure/phase_08/final/episode_workspace_manifest.json
- frontend_restructure/phase_08/final/final_verdict.json
- frontend_restructure/phase_08/final/mock_episodes_elimination_report.json
- frontend_restructure/phase_09/contract_freeze/entity_map.json
- frontend_restructure/phase_09/final/final_verdict.json
- frontend_restructure/phase_09/final/phase_report.md
- frontend_restructure/phase_10/final/final_verdict.json
- frontend_restructure/phase_10/final/phase_report.md
- frontend_restructure/phase_11/baseline/agent_api_inventory.json
- frontend_restructure/phase_11/baseline/agent_mock_inventory.json
- frontend_restructure/phase_11/baseline/agent_polling_inventory.json
- frontend_restructure/phase_11/baseline/agent_state_inventory.json
- frontend_restructure/phase_11/baseline/baseline_report.md
- frontend_restructure/phase_11/baseline/conversation_projection_inventory.json
- frontend_restructure/phase_11/baseline/task_api_inventory.json
- frontend_restructure/phase_11/baseline/workflow_api_inventory.json
- frontend_restructure/phase_11/final/final_verdict.json
- frontend_restructure/phase_11/final/phase_report.md
- frontend_restructure/phase_12/baseline/baseline_report.md
- frontend_restructure/phase_12/baseline/model_api_inventory.json
- frontend_restructure/phase_12/baseline/provider_api_inventory.json
- frontend_restructure/phase_12/baseline/provider_mock_inventory.json
- frontend_restructure/phase_12/baseline/router_game_audio_coupling_inventory.json
- frontend_restructure/phase_12/baseline/routing_api_inventory.json
- frontend_restructure/phase_12/final/final_verdict.json
- frontend_restructure/phase_12/final/phase_report.md
- frontend_restructure/phase_13/final/final_verdict.json
- frontend_restructure/phase_13/final/phase_report.md
- frontend_restructure/phase_14/final/final_verdict.json
- frontend_restructure/phase_14/final/phase_report.md
- frontend_restructure/phase_15/baseline/compatibility_dependencies.json
- frontend_restructure/phase_15/baseline/legacy_route_consumers.json
- frontend_restructure/phase_15/baseline/retirement_matrix.md
- frontend_restructure/phase_15/baseline/v2_consumers.json
- frontend_restructure/phase_15/baseline/v2_routes.json
- frontend_restructure/phase_15/final/final_verdict.json
- frontend_restructure/phase_15/final/phase_report.md
- frontend_restructure/phase_16/baseline/deletion_candidates.md
- frontend_restructure/phase_16/baseline/duplicate_contracts.json
- frontend_restructure/phase_16/baseline/orphan_components.json
- frontend_restructure/phase_16/baseline/orphan_styles.json
- frontend_restructure/phase_16/baseline/orphan_tests.json
- frontend_restructure/phase_16/baseline/unreachable_files.json
- frontend_restructure/phase_16/baseline/unused_exports.json
- frontend_restructure/phase_16/baseline/unused_packages.json
- frontend_restructure/phase_16/final/final_verdict.json
- frontend_restructure/phase_16/final/phase_report.md

### full_system_audit — 2 file

- full_system_audit/20260619_142321/feature_matrix.json
- full_system_audit/20260619_142321/findings.json

### logs — 1 file

- logs/backend.log

### orchestration_v2 — 27 file

- orchestration_v2/benchmark_baseline.json
- orchestration_v2/cutover_receipt.json
- orchestration_v2/cutover_verdict_correction.json
- orchestration_v2/decommission_receipt.json
- orchestration_v2/deleted_legacy_files.json
- orchestration_v2/legacy_inventory.json
- orchestration_v2/repair/api_parity_report.json
- orchestration_v2/repair/benchmark_environment.json
- orchestration_v2/repair/ci_receipt.json
- orchestration_v2/repair/clean_clone_e2e_report.json
- orchestration_v2/repair/concurrency_report.json
- orchestration_v2/repair/crash_recovery_report.json
- orchestration_v2/repair/defect_inventory.json
- orchestration_v2/repair/destructive_replay_report.json
- orchestration_v2/repair/final_verdict.json
- orchestration_v2/repair/migration_report.json
- orchestration_v2/repair/multiprocess_lease_report.json
- orchestration_v2/repair/phase1_regression_tests_receipt.json
- orchestration_v2/repair/phase2_schema_receipt.json
- orchestration_v2/repair/phase3_execution_port_receipt.json
- orchestration_v2/repair/phase4_dispatcher_receipt.json
- orchestration_v2/repair/phase5_execute_endpoint_receipt.json
- orchestration_v2/repair/phase6_control_surface_receipt.json
- orchestration_v2/repair/phase7_recovery_receipt.json
- orchestration_v2/repair/phase8_benchmark_receipt.json
- orchestration_v2/repair/phase9_ci_receipt.json
- orchestration_v2/repair/websocket_parity_report.json

### production_ui — 18 file

- production_ui/final_acceptance/d6e8a7f9c2b1e4f3a5d8b7c6a9e0f1d2c3b4a5e6/asset_golden_receipt.json
- production_ui/final_acceptance/d6e8a7f9c2b1e4f3a5d8b7c6a9e0f1d2c3b4a5e6/checksums.json
- production_ui/final_acceptance/d6e8a7f9c2b1e4f3a5d8b7c6a9e0f1d2c3b4a5e6/environment.json
- production_ui/final_acceptance/d6e8a7f9c2b1e4f3a5d8b7c6a9e0f1d2c3b4a5e6/integrated_golden_receipt.json
- production_ui/final_acceptance/d6e8a7f9c2b1e4f3a5d8b7c6a9e0f1d2c3b4a5e6/run_manifest.json
- production_ui/final_acceptance/d6e8a7f9c2b1e4f3a5d8b7c6a9e0f1d2c3b4a5e6/script_golden_receipt.json
- production_ui/final_acceptance/d6e8a7f9c2b1e4f3a5d8b7c6a9e0f1d2c3b4a5e6/stage_gate_summary.json
- production_ui/final_acceptance/d6e8a7f9c2b1e4f3a5d8b7c6a9e0f1d2c3b4a5e6/versions.json
- production_ui/final_acceptance/d6e8a7f9c2b1e4f3a5d8b7c6a9e0f1d2c3b4a5e6/video_foundation_receipt.json
- production_ui/phase_00/api_contract_snapshot.json
- production_ui/phase_00/backend_test_receipt.json
- production_ui/phase_00/baseline_manifest.json
- production_ui/phase_00/desktop_test_receipt.json
- production_ui/phase_00/event_contract_snapshot.json
- production_ui/phase_00/phase_verdict.json
- production_ui/phase_00/regression_smoke_receipt.json
- production_ui/phase_00/toolchain_inventory.json
- production_ui/phase_00/web_test_receipt.json

### provider_v3 — 8 file

- provider_v3/phase_08/acceptance_matrix.json
- provider_v3/phase_08/changed_files.json
- provider_v3/phase_08/commands.log
- provider_v3/phase_08/phase_receipt.json
- provider_v3/phase_08/test_receipt.json
- provider_v3/phase_10/phase_receipt.json
- provider_v3/phase_11/final_verdict.json
- provider_v3/phase_11/phase_receipt.json

### runs — 1 file

- runs/sample_workflow.json

### video_production_3d — 1 file

- video_production_3d/VERIFICATION_REPORT.md

### wind_studio_refactor — 1 file

- wind_studio_refactor/audit/final_report.md

---

## C. Thư mục rỗng / chỉ còn placeholder (không chứa file)

- `eval/` — rỗng
- `reports/`, `graphics/`, `timeline/`, `final/`, `plans/`, `takes/` (trong code_video) — chỉ còn `.gitkeep`
- `runs/<uuid>/screenshots/` — rỗng (có thể dọn thư mục UUID)

> Lưu ý: file `.gitkeep` được giữ để ổn định cấu trúc thư mục code_video.

