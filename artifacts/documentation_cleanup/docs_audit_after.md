# Documentation Audit — After

Repository: D:\code_ca_nhan\WindAgent
Branch: chore/cleanup-stale-md-docs
HEAD after: (see git log — same branch, no rebase/reset)
Date: 2026-08-13

## Summary

- files_before: 253 (docs/)
- files_after: 232
- deleted: 19 (blender roadmap + 9 roadmap_v2 stages + 5 release + 4 e2e_poc)
- moved to artifacts/documentation_cleanup/: 2 (bao_cao_tong_quan_2026-08-07.md, cleanup_classification_2026-08-08.md)
- rewritten: 4 (api_contract, event_protocol, model_provider_registry, safety_policy)
- patched (REWRITE nhỏ / link fix): 20 files (9 director/browser link fix, 6 cluster Flow-era cleanup, 2 3d_animation_plans authority, compiler_versioning, recovery_invariants, threat_model)
- created: 0 docs mới (giữ cấu trúc canonical hiện có)
- NOTE: mid-session, một agent song song (Antigravity) commit 40bb97c đã cuốn 11 file docs (blender doc, roadmap_v2 stages, 2 moves) — nội dung giống hệt quyết định audit này; commit docs chính thức là 5c2ad23.

## Kept (canonical)

- docs/plans/studio_roadmap_01/** — plan hiện hành + evidence + fixtures (có consumer: scripts/studio_roadmap/*, tests/contracts/*, tests/unit/api/*)
- docs/video_production/3d_animation_plans/** — plan VP3D hiện hành (stages A-Q)
- docs/video_production/{artifact_storage,assets,audio,browser_runtime,cost_quota,director,durable_workflow,generation_review,postproduction,preproduction,protocol,reliability,security,workspace}/** — contract docs khớp module owner sống
- docs/video_production_3d/** — contract VP3D Phase 5-7
- docs/api_contract.md, docs/event_protocol.md, docs/model_provider_registry.md, docs/safety_policy.md — rewritten
- road_map.md (root) — Studio Roadmap 1, plan hiện hành

## Deleted

- docs/blender_3d_animation_roadmap.md (roadmap 3D cũ, superseded)
- docs/roadmap_v2/stage_{a..i}_*.md (9) — roadmap v2 superseded
- docs/video_production/release/{release_0_1_notes,release_runbook,incident_response,support_matrix,migration_and_rollback}.md (5) — release 0.1 Flow-era
- docs/video_production/e2e_poc/{hardening_handoff,e2e_runbook,recovery_policy,traceability_policy}.md (4) — phase report + Flow-era policies
- road_map_v2.md, road_map_v2_implementation_plan.md (root, pre-existing deletions kept)

## Validation

- Broken internal links: 0 (trước: 9)
- Flow-residue gate: 13/13 PASS (chạy lại sau allowlist edit + deletions)
- Architecture imports checker: PASS (0 violations)
- References to deleted docs: 0 (git grep sau cleanup — chỉ còn reference có chủ đích trong test allowlist đã gỡ)
- Commands checked: uv run pytest (targeted), uv run python scripts/check_architecture_imports.py, scripts/verification/release_phase27.py (syntax ok, chỉ sửa string)

## Remaining uncertainties

- Không có file NEEDS_REVIEW. Contract cluster còn ~40 file chưa đọc từng chữ nhưng toàn bộ claim path/class trong đó đã được scan và xác minh tồn tại; module owner còn sống; nội dung mẫu khớp code.
- Phase 08 evidence thiếu phase_report.md (artifact, ngoài docs scope).
