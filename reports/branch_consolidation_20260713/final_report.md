# Branch Consolidation Report

**Date:** 2026-07-13  
**Repository:** WindFaculty/WindAgent  
**Integration branch:** `integration/consolidate-all-20260713`  
**Integration SHA:** `1e33189c3b69e40260cd57de52f6b63c9be686be`  
**Origin/main SHA:** `98cf5c3902f640aa091a6e73d8a2237525c16d12`  

---

## Branch Inventory

| Branch | SHA | Ahead | Classification | Action |
|---|---|---|---|---|
| `feat/phase-1-baseline` | 2d4c6dc | 9 | unique_candidate | merged directly |
| `feat/hermes-agent-workspace-integration` | 3b2888a | 8 | unique_candidate | merged directly |
| `origin/feat/router-phase6-memory-a2a` | 9d0260f | 4 | unique_candidate | merged directly |
| `origin/feat/router-runtime-ui-integration` | 9da9a0b | 2 | covered_by_descendant | via router-phase6 |
| `origin/feat/router-omniroute-integration` | b9a6552 | 1 | covered_by_descendant | via router-phase6 |
| `origin/plan/cloud-router-priority` | 4a5fb31 | 0 | already_in_main | skip |

## Tree coverage

All 6 branches verified as ancestors of integration HEAD.

## Merge order

1. `feat/phase-1-baseline` — clean merge (no conflicts)
2. `origin/feat/router-phase6-memory-a2a` — 3 conflicts resolved
3. `origin/feat/hermes-agent-workspace-integration` — 6 conflicts resolved

## Conflict resolution summary

### Conflicts resolved

**database.py:** Combined HEAD migration block (api_key column + event_seq + seed_canonical_models) with incoming routing-rules column additions.

**models.py:** Kept HEAD superset (legacy AgentORM, orchestration tables) from feat/phase-1-baseline. Incoming contributed ModelCatalogORM, RouteLockORM, ParentTaskORM etc. which were already present.

**main.py:** Combined router imports from all branches. Kept /api/v1 prefix structure from HEAD. Added router-phase routers (model_routing, openai_compatible, router_observability), browser router, and their service init.

**schemas/event.py:** Combined EventName enum (worktree\* + replan + browser\* events).

**App.tsx:** Used incoming AgentWorkspace component for workspace tab. Added required state vars. Kept MultiAgentWorkspace import.

**types.ts:** Combined browser event types into EventName union.

**package.json:** Kept HEAD deps + added remark-gfm.

## Root cause fixes

| Root cause | Fix |
|---|---|
| WorkflowORM missing created_at/updated_at | Added columns |
| WorkflowStepORM missing 5 columns | Added name, tool_name, params_json, created_at, updated_at |
| WorkflowStepORM.step_type NOT NULL with no callers | Made nullable |
| ProviderQuotaSnapshotORM wrong schema | Replaced with origin/main version (quota_mode, remaining_*, reset_at) |
| ModelActivityORM wrong schema | Replaced with origin/main version (level, event_type, message) |
| Encryption key not set for api_key validate | Added default in conftest.py |
| Wrong test route paths (/models vs /api/v1/models) | Fixed test_models_api.py, test_router_integration.py |

## Test results

459 passed, 3 failed, 2 skipped (151s)

Remaining failures (pre-existing, not merge regressions):
- test_openai_compatible_stream_completion — mock streaming response format
- test_openai_compatible_non_stream_completion — model readiness not set
- test_openai_compatible_gateway_endpoints — usage.prompt_tokens > 0 assertion

## Known limitations

1. 3 openai_compatible tests fail due to pre-existing mock/routing setup
2. `key.txt` committed in repo — contains test encryption key, not production
3. Numerous artifact/debug files committed (artifacts/, audit_report/)
4. WorktreeORM, AgentInstanceORM migrations via database.py ALTER TABLE only — no alembic migration file for these

## Rollback

```
git checkout main
git branch -D integration/consolidate-all-20260713
git push origin --delete integration/consolidate-all-20260713
```