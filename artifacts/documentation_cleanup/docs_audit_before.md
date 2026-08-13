# Documentation Audit — WindAgent

Repository: D:\code_ca_nhan\WindAgent
Branch: chore/cleanup-stale-md-docs
HEAD before: 400291d9707284879ea20a0d52420444f1969b33
Date: 2026-08-13

## Current Architecture Summary

Xem `artifacts/documentation_cleanup/docs_audit_before.md` (phần summary + quyết định cấp cao).
Tóm tắt: WindAgent = modular monolith V2 (apps/api, apps/worker, apps/cli, apps/desktop, apps/web + canonical packages core/orchestration/intelligence/providers/tools/storage/workflows/execution/verification/context/memory/observability/evals/plugins/skills); Studio Roadmap 1 (road_map.md) + VP3D (3d_animation_plans, phases 0-26 verified) là 2 plan hiện hành; API /api/v2/* + /api/v3/studio/*; EventEnvelope dotted taxonomy; provider V3 canonical registry; Flow browser runtime + apps/backend + /api/v1 đã retired (hard gate test_phase2_flow_removal_canonical.py).

## Decision Matrix

### docs/ root

| File | Decision | Confidence | Evidence | Reason | Replacement |
|---|---|---|---|---|---|
| api_contract.md | REWRITE | HIGH | routers/*.py + main.py | thiếu 9 nhóm route mới (browser, screenplay, video-production, v3 studio...) | bảng route sinh từ router registration |
| event_protocol.md | REWRITE | HIGH | core/windagent_core/events/* | mô tả ws://localhost:8765, /api/v1, tên event flat, Agent-S3 — đã retired | EventEnvelope + catalog dotted |
| model_provider_registry.md | REWRITE | HIGH | providers/windagent_providers/* | 8 provider cũ (agentrouter/bluesminds/zenmux/nararouter) không tồn tại; env key sai | adapters + canonical registry hiện tại |
| safety_policy.md | REWRITE | HIGH | core/windagent_core/security/, v2_permissions.py | mô tả services/tool_registry.py + 11 tool PyAutoGUI — đã retired | security primitives hiện tại |
| bao_cao_tong_quan.md | MOVE | HIGH | README.md là overview canonical; doc là snapshot report 2026-08-07 | report lịch sử, §3.3/§3.5 mô tả dir đã xóa | artifacts/documentation_cleanup/bao_cao_tong_quan_2026-08-07.md |
| cleanup_classification_2026-08-08.md | MOVE | HIGH | tài liệu audit tạm từ session trước | temporary audit | artifacts/documentation_cleanup/ |
| blender_3d_animation_roadmap.md | DELETE | HIGH | thay bởi 3d_animation_plans/; chứa token google_flow/TEXT_TO_VIDEO (allowlist cũ) | roadmap cũ, superseded | docs/video_production/3d_animation_plans/ |
| roadmap_v2/ (9 files) | DELETE | HIGH | road_map_v2.md đã xóa (session trước); road_map.md = Studio Roadmap 1 | superseded roadmap v2 | road_map.md |
| plans/studio_roadmap_01/** (plan 00-90 + contracts + evidence + fixtures) | KEEP | HIGH | scripts/studio_roadmap/*, tests/contracts/*, tests/unit/api/* reference evidence + fixtures | plan hiện hành, có consumer sống | — |
| video_production/3d_animation_plans/** (18 files) | KEEP (2 REWRITE nhỏ) | HIGH | plan VP3D hiện hành, phases 0-26 verified | còn sống; sửa authority line road_map.md | README + stage_a patched |
| video_production/release/* (5 files) | DELETE | HIGH | Flow-era, candidate SHA 1753831c, version 0.3.0 | release 0.1 historical (Flow retired) | artifacts/video_production/final/ |
| video_production/e2e_poc/* (4 files) | DELETE | HIGH | mô tả Flow backend session/generation (hardening_handoff, e2e_runbook, recovery_policy, traceability_policy) | Flow-era historical | artifacts/video_production/phase_24/ |

### docs/video_production/** contract cluster (99 files + schema)

Kiểm chứng bằng: (a) scan toàn bộ path/class claim trong doc vs code, (b) đọc mẫu 15+ file, (c) đối chiếu route/event/class chủ chốt.

| File | Decision | Confidence | Evidence | Reason |
|---|---|---|---|---|
| artifact_storage/* (5) | KEEP | HIGH | storage/windagent_storage/video_production/ (artifact model/key/dependency/invalidation/publish) | contract khớp module owner |
| assets/* (5) | KEEP | HIGH | core domain video_production + tools/windagent_tools/media_assets/ | khớp code |
| audio/* (5) | KEEP | HIGH | intelligence/video/audio/{alignment,mix,tts,voice}.py + core domain audio.py | khớp code |
| browser_runtime/* (4) | KEEP + patch | HIGH | tools/windagent_tools/browser/{action_policy,session,evidence_capture,healthcheck,runtime,agent_browser}.py — module map khớp 1:1 | sửa 4 reference Flow-era |
| cost_quota/* (5) | KEEP | HIGH | orchestration/production/{cost_catalog,estimator,quota_ledger,circuit_breaker,budget_policy}.py | khớp code |
| director/* (11) | KEEP (1 REWRITE nhỏ) | HIGH | intelligence/video/director/* + core domain prompt_compiler.py | compiler_versioning sửa module path; 8 link plan chết đã sửa |
| durable_workflow/* (5) | KEEP | HIGH | orchestration/production/{engine,scheduler,approvals,outbox,recovery}.py + workflows/video_production/definition.py | khớp code |
| generation_review/* (5) | KEEP | HIGH | intelligence/video/reviewers/{deterministic,selection,verdict,vlm}.py | khớp code |
| postproduction/* (4) | KEEP | HIGH | intelligence/video/postproduction/* | khớp code |
| preproduction/* (4) | KEEP | HIGH | video/ports.py + tests/architecture/test_phase05_characterization_harness.py | khớp code |
| protocol/* (5 + schema) | KEEP | HIGH | core/windagent_core/events/video_production.py, domain package.py, verifiers dùng schema (allowlisted) | event_catalog đối chiếu 14/14 event |
| reliability/* (4) | KEEP + patch | HIGH | orchestration/production/{engine,recovery,approvals,outbox,budget_policy}.py | 8 reference Flow-era đã sửa (FlowHumanState, FlowJobRegistry dead) |
| security/* (6) | KEEP + patch | HIGH | core/windagent_core/security/, phase 26 SE01-SE13 | 2 reference Flow đã sửa |
| workspace/* (5) | KEEP | HIGH | v2_production_workspace + v2_events (cursor replay) routers | api_contract/event_projection khớp routes |

### docs/video_production_3d/ (8 files)

| File | Decision | Confidence | Evidence | Reason |
|---|---|---|---|---|
| assets/* (4) | KEEP | HIGH | core/windagent_core/contracts/video_production/asset_resolver.py + domain/asset_resolution/ + providers/windagent_providers/assets/ | VP3D Phase 5-7 verified, khớp code |
| audio/* (4) | KEEP | HIGH | intelligence/video/audio/* + stage E plan | khớp code |

## References updated

- README.md: bỏ link chết ban_ke_hoach.md → road_map.md + docs links
- tests/architecture/test_phase2_flow_removal_canonical.py: bỏ docs/blender_3d_animation_roadmap.md khỏi allowlist
- scripts/verification/release_phase27.py: mitigation string → artifacts/video_production/final/known_limitations.md
- 9 file director/browser_runtime: link plans/ đã xóa → code path
- 6 file cluster: sửa reference Flow-era → hiện tại

## OUT_OF_SCOPE_CODE_FINDING (không sửa)

- docs/video_production/reliability/reconciliation_policy.md trước đây reference `FlowJobRegistry` — class không tồn tại (đã sửa trong doc, không đụng code)
- `apps/backend/` vẫn tồn tại trên disk (không còn là workspace member, git ls-files rỗng cho tracked source) — hồ sơ retired, ngoài scope docs
- Phase 08 evidence thiếu phase_report.md (chỉ phase_verdict.json + manifest) — thiếu sót artifact, không phải docs issue
