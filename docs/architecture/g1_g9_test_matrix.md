# G1–G9 Acceptance Coverage Matrix

Status: **complete after Phase 9**. Every roadmap gate has an executable test.
Production-critical flows are proven by the Phase 8 integration suite, where
only the external Hermes and provider boundaries are scripted; the scheduler,
repositories, recovery manager, provider coordinator, Git worktree manager and
WebSocket router are the production implementations.

## G1 — Data model and migration

| Gate | Acceptance evidence | Executable test |
| --- | --- | --- |
| G1.1 | Alembic upgrade, downgrade and V2 preservation | `tests/unit/storage/migrations/test_phase1_migration_integrity.py::TestAlembicUpgrade::test_upgrade_head_builds_complete_fresh_schema`, `::test_downgrade_base_resets_test_db`, `::test_upgrade_from_v2_fixture_preserves_needed_data` |
| G1.2 | Conversation-key unique/FK/index constraints | `tests/unit/storage/migrations/test_phase1_migration_integrity.py::TestAlembicUpgrade::test_multi_agent_constraints_exist`, `::test_unique_windagent_session_id_enforced` |
| G1.3 | Editing a running plan appends version 2, keeps version 1 retrievable, and never retargets its live run | `tests/unit/orchestration/test_phase4_durable_plan_scheduler.py::test_revising_a_running_plan_appends_a_snapshot_and_preserves_live_runs`, `tests/unit/api/test_phase7_workspace_projection.py::test_plan_revision_endpoint_keeps_the_old_snapshot_retrievable` |

## G2 — Route lock and same-model failover

| Gate | Acceptance evidence | Executable test |
| --- | --- | --- |
| G2.1 | One durable route lock per running turn | `tests/unit/orchestration/test_phase3_routed_provider_turns.py::test_turn_429_failover_is_same_model_and_auditable` |
| G2.2 | HTTP 429 fails over to an exact-revision endpoint without changing the canonical model | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_same_model_failover_and_partial_stream_are_durable` |
| G2.3 | API key encryption and metadata-only public projection | `tests/unit/storage/migrations/test_phase1_migration_integrity.py::TestSecretEncryption::test_encrypt_prefix_and_roundtrip`, `::test_public_credential_dict_never_exposes_secret` |

## G3 — Hermes multi-session supervisor

| Gate | Acceptance evidence | Executable test |
| --- | --- | --- |
| G3.1 | Parent task creates independent sub-agent instance/session/run records and isolated events | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_parent_dag_event_isolation_fanout_fanin_concurrency_and_stop_race` |
| G3.2 | Stopping one sub-agent does not stop siblings | `tests/unit/orchestration/test_phase2_orchestrator_supervisor.py::test_stop_selected_agent_does_not_cancel_siblings_and_boot_reattaches` |
| G3.3 | Restart rebuilds live runtime registry | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_restart_mid_dag_surfaces_approval_and_unavailable_runtime` |

## G4 — Durable DAG scheduler, idempotency and CAS

| Gate | Acceptance evidence | Executable test |
| --- | --- | --- |
| G4.1 | Fan-out/fan-in advances only after its durable dependency gate | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_parent_dag_event_isolation_fanout_fanin_concurrency_and_stop_race` |
| G4.2 | Same concurrency group is serialized | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_parent_dag_event_isolation_fanout_fanin_concurrency_and_stop_race` |
| G4.3 | CAS makes a late completion lose to stop; idempotent side effects execute once | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_parent_dag_event_isolation_fanout_fanin_concurrency_and_stop_race`, `tests/unit/orchestration/test_phase4_durable_plan_scheduler.py::test_concurrency_lock_cancel_precedence_and_tool_idempotency` |

## G5 — Git worktree lifecycle

| Gate | Acceptance evidence | Executable test |
| --- | --- | --- |
| G5.1 | Two coding agents receive separate linked worktrees; primary checkout stays clean | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_coding_worktree_isolation_and_cancel_cleanup` |
| G5.2 | Cancel removes linked checkout and branch, retaining dirty output only in quarantine | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_coding_worktree_isolation_and_cancel_cleanup` |
| G5.3 | Startup reconciles durable and unrecorded worktrees | `tests/unit/orchestration/test_phase5_git_worktree_lifecycle.py::test_boot_reconciles_live_worktree_and_removes_unrecorded_crash_orphan` |

## G6 — Durable events and recovery

| Gate | Acceptance evidence | Executable test |
| --- | --- | --- |
| G6.1 | One conversation socket multiplexes agent events with agent identity preserved | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_socket_reconnect_replays_only_missed_events` |
| G6.2 | Reconnect uses the durable global cursor with capped exponential backoff | `apps/desktop/src/services/conversationSocketManager.test.ts::ConversationSocketManager uses one conversation socket and replays from the global cursor`, `::has deterministic capped exponential backoff with bounded jitter` |
| G6.3 | Interrupted stream is audit-only and never enters transcript events | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_same_model_failover_and_partial_stream_are_durable` |
| G6.4 | Restart reattaches completed runtime, advances DAG, surfaces approval and reports unavailable runtime | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_restart_mid_dag_surfaces_approval_and_unavailable_runtime` |

## G7 — Normalized multi-agent desktop state

| Gate | Acceptance evidence | Executable test |
| --- | --- | --- |
| G7.1 | Durable projections are normalized and terminal lines remain per agent | `apps/desktop/src/state/multiAgentStore.test.ts::normalizes durable workspace projections and keeps A/B terminal output isolated` |

## G8 — Three-column UI and task inspection

| Gate | Acceptance evidence | Executable test |
| --- | --- | --- |
| G8.1 | Required Vietnamese operator labels and compact current-task list are present | `tests/architecture/test_phase00_single_workspace_contract.py::test_workspace_preserves_three_column_operator_contract` |
| G8.2 | Browser panel is driven by selected-agent live browser state and exposes the no-runtime state | `tests/architecture/test_phase00_single_workspace_contract.py::test_workspace_has_no_mock_browser_or_task_graph` |
| G8.3 | Inspector includes model, provider, route lock, permission, tool and worktree fields | `tests/architecture/test_phase00_single_workspace_contract.py::test_workspace_preserves_three_column_operator_contract` |
| G8.4 | Legacy AgentWorkspace mount/import is absent | `tests/architecture/test_phase00_single_workspace_contract.py::test_workspace_mount_is_single_and_canonical` |

## G9 — E2E, chaos and security

| Gate | Acceptance evidence | Executable test |
| --- | --- | --- |
| G9.1 | Stop/completion race has explicit cancellation precedence | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_parent_dag_event_isolation_fanout_fanin_concurrency_and_stop_race` |
| G9.2 | Restart reports and does not silently claim a crashed/unavailable Hermes run | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_restart_mid_dag_surfaces_approval_and_unavailable_runtime` |
| G9.3 | Eight parallel SQLite writers use WAL without lock errors | `tests/unit/storage/migrations/test_phase1_migration_integrity.py::TestParallelWriters::test_eight_parallel_writers_no_lock` |
| G9.4 | Secrets are redacted before persistence and event emission | `tests/unit/storage/migrations/test_phase1_migration_integrity.py::TestRedactionAtPersist::test_event_persist_redacts_secrets_preserves_prose`, `::test_tool_arguments_redacted_on_submit` |
| G9.5 | API rejects workspace-root traversal and symlink escape | `tests/unit/storage/migrations/test_phase1_migration_integrity.py::TestWorkspaceRootValidation::test_api_rejects_traversal_with_400`, `::test_symlink_escape_rejected` |
| G9.6 | Repeated runtime failure reaches the persisted retry cap with no fourth dispatch | `tests/integration/test_phase8_e2e_chaos.py::test_e2e_retry_storm_stops_at_durable_attempt_cap` |
| G9.7 | Cross-boundary E2E/chaos scenario coverage | `tests/integration/test_phase8_e2e_chaos.py` (all six scenarios) |
| G9.8 | Release stages fail closed; rehearsal preserves immutable plan/audit data and rollback remains application-only | `tests/unit/orchestration/test_phase9_safe_rollout.py` |

## CI gate

`python-unit-*` runs the architecture, unit and regression suites. `python-integration-*`
runs `tests/integration`, including `test_phase8_e2e_chaos.py`. The desktop
job runs `npm.cmd test` and `npm.cmd run type-check` in `apps/desktop`.

The Phase 9 regression command is:

```powershell
python -m pytest tests/architecture/test_phase00_single_workspace_contract.py tests/unit/storage/migrations/test_phase1_migration_integrity.py tests/unit/orchestration/test_phase2_orchestrator_supervisor.py tests/unit/orchestration/test_phase3_routed_provider_turns.py tests/unit/orchestration/test_phase4_durable_plan_scheduler.py tests/unit/orchestration/test_phase5_git_worktree_lifecycle.py tests/unit/orchestration/test_phase6_conversation_recovery.py tests/unit/api/test_phase7_workspace_projection.py tests/integration/test_phase8_e2e_chaos.py tests/unit/orchestration/test_phase9_safe_rollout.py -q
```
