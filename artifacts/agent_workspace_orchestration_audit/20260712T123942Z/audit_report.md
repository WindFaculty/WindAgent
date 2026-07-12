# WindAgent Agent Workspace Orchestration — Current State Audit

## 1. Final Verdict

**partial_foundation_implemented**

Core requirement gaps block `accepted_feature_complete`:
- multi-agent sessions: PARTIAL (schema + supervisor exist, unwired live)
- DAG scheduler: PARTIAL (engine real, no live caller)
- canonical model lock: PARTIAL (logic, unwired)
- same-model failover: PARTIAL (logic, unwired)
- durable WebSocket replay: PARTIAL (seq+replay yes; per-session not conversation; fixed backoff)
- restart recovery: PARTIAL (runs+events only; no scheduler/lock/worktree/approval)
- worktree isolation: PARTIAL (service real, unwired)
- frontend sub-agent workspace: PARTIAL (3-col shell real; browser mock; inspector thin)

HEAD == 9205dfa. Whole orchestration = uncommitted working tree (19M+21?). Runtime unverified (services down). 33/33 unit pass.

## 2. Executive Summary

**Feature thực tế làm được gì**
- 3-column UI thật: Orchestrator Chat / Sub-agent Board+Task Graph / Inspector (MultiAgentWorkspace.tsx).
- Task Graph = real DAG từ DB (task_nodes/task_edges), không phải tool-call list.
- Task editor: add/delete node, edge, edge cycle-detect, optimistic lock (plan.version 409), replan event.
- Terminal thật: stream `terminal_output` per selected agent qua WS. Không dựng từ chat.
- Permission profile Standard default, áp dụng per tool-call (session_bridge._profile_decision).
- Event bus persist-then-broadcast, replay_after, client dedup by seq.
- Sub-agent card hiện agent_type + permission_profile + status.

**Feature chưa làm được gì**
- Orchestrator không tạo parent task/DAG từ chat. spawn_subagent/run_plan/ensure_orchestrator/ParentTaskORM() chỉ trong test.
- Live path vẫn single-agent: chat → start_run(role string) → SSE. Không qua supervisor/DAG/route_lock.
- 3-tier model pin + same-model failover không chạy live (role string, không lock).
- Partial stream không persist trên crash (save_partial_artifact 0 caller).
- Idempotency key không ghi/không check → retry có thể chạy tool 2 lần.
- WS per-session, không multiplex conversation. Backoff cố định 1500ms.
- Recovery chỉ rebuild runs+events; không scheduler/lock/worktree/approval.

**Phần chỉ là foundation**
- dag_scheduler, route_lock_service, worktree_service, supervisor, recovery_service, permission_profile: library hoàn chỉnh + test xanh, nhưng chưa nối router. Standalone, không integration.

**Phần mock/stub**
- Browser preview = hardcoded "Awesome App" (MultiAgentWorkspace:899-1003). Vi phạm req 18+20.
- App.tsx random metrics fallback khi non-Tauri (135-157). Cosmetic.
- Dead AgentWorkspace.tsx: terminal dựng từ chat split, dropdown agent_type → new session. Unmounted, xóa.

**Rủi ro nghiêm trọng nhất**
- S1 HIGH: api_key lưu plaintext (models.py:269, column 163). Leak qua DB.
- S3 MED: workspace_root không validate traversal (sessions payload → bridge).
- C1 MED: stop vs completion TOCTOU, không row version → status flip-flop.
- C8/C9 MED: orphan Hermes run (reattached không cancel) + orphan worktree/branch sau cancel (không remove).
- R2 (XL): orchestration unwired = gap lớn nhất.

## 3. Provenance

HEAD 9205dfa == ref. diff ref..HEAD empty. Branch feat/phase-1-baseline. Single worktree. 19 tracked modified + 21 untracked = toàn bộ orchestration chưa commit. Detail git_provenance.json.

## 4. Feature Matrix (20 req)

Full per-req status + evidence: feature_matrix.json. Summary:
- IMPLEMENTED: 6 (research no worktree), 13 (default Standard).
- PARTIAL: 1,3,4,5,7,8,9,12,14,16,17,18,19.
- ABSENT: 2,15.
- BROKEN: 10 (partial audit live), 20 (mock browser + dead chat-terminal).
- UNVERIFIED_RUNTIME: mọi scenario Hermes thật (services down).

## 5. Architecture Map

Live path Phase-1 single-agent. Subsystems tồn tại nhưng 0 live caller: spawn_subagent/run_plan/acquire_lock/save_partial_artifact. Detail architecture_map.md.

## 6. Database Schema

SQLite create_all, no migration. Dangerous: scalar_one_or_none giả định 1 AgentSession/session (không unique); conversation_id loose string không FK; event_seq nullable không unique; task FK không cascade. Detail database_schema_audit.md.

## 7. API + Event Traceability

REST task CRUD + pause/resume/cancel/retry thực (conversations.py). WS event → reducer normalized per-agent (multiAgentStore). Gap: không có API orchestrator spawn DAG; pause/retry chỉ flag node, không chạy scheduler. Detail api_event_traceability.md.

## 8. Security + Concurrency

S1 plaintext key (HIGH). S2 raw command trong arguments_redacted (MED). S3 traversal (MED). C1 stop/complete TOCTOU (MED). C3 two-task-same-agent worktree clash (MED). C5 SQLite no WAL (MED). C8 orphan Hermes (MED). C9 orphan worktree (MED). Detail risks.json + PHASE7 report.

## 9. Tests

33 passed / 0 failed / 1 warning / 6.4s. pytest test_phase2..9. Runtime unverified. test_results.json.

## 10. Roadmap

9 groups, 30+ gaps, mỗi gap có current/expected/evidence/impact/dep/difficulty/order/acceptance. Top order:
1. commit + Alembic migration + security early (api_key encrypt, traversal guard)
2. route_lock acquire per turn + same-model failover live
3. supervisor spawn_subagent live (chat → DAG)
4. dag_scheduler.run_plan + concurrency_group + idempotency
5. worktree live + cleanup on cancel + reconcile boot
6. WS conversation multiplex + exponential backoff + partial persist + full recovery
7. normalized frontend state (extend agent_instance_id tag)
8. UI: i18n labels, live browser per-agent, full inspector, delete dead AgentWorkspace
9. chaos/security hardening (CAS version, orphan cancel, WAL, secret redact, retry cap) + E2E fake-Hermes

Detail roadmap.md.

## 11. Screenshots

BLOCKED. backend:8765 DOWN, frontend:1420 DOWN. No running UI to capture. Runtime scenarios = UNVERIFIED_RUNTIME (fake/unit evidence only).

## 12. Artifact path

`D:/code_ca_nhan/WindAgent/artifacts/agent_workspace_orchestration_audit/20260712T123942Z/`
(latest.txt points here)
