# Phase 11 Baseline Report — Agent System Convergence

## Executive Summary
Phase 11 unifies the agent execution system, task graph management, durable conversation projections, and workflow orchestration into the Canonical V3 Architecture.

## Key Audit Findings
1. **Semantic Ambiguity**: Legacy endpoints and UI mixed `AgentDefinition` with `AgentInstance`. Definitions are static templates while Instances are stateful runtime workers.
2. **Aggressive Polling**: `Agents.tsx` performed 5-second full-list polling, and `MultiAgentWorkspace.tsx` polled the browser session endpoint every 2 seconds.
3. **Hardcoded Mock Metrics**: `Agents.tsx` displayed hardcoded uptime (`1h 14m`), latency (`1.25s`), success rate (`95%`), and static sparkline SVGs.
4. **Mock Workflow Catalog**: `Workflows.tsx` maintained an in-memory mock dataset (`kronos`, `release`, `lab`) with fake progress percentages and canned step activity.
5. **Divergent Task States**: Various components handled task status with conflicting string values instead of the unified 7-state canonical state machine.

## Cutover Strategy
- Implement clean V3 endpoints:
  - `/api/v3/agent-definitions` (CRUD, activity, real metrics)
  - `/api/v3/agent-instances` (List, start, stop, restart)
  - `/api/v3/conversations` (Projections, agents, tasks, events)
  - `/api/v3/tasks` (CRUD, optimistic locking, cancel, retry)
  - `/api/v3/workflows` & `/api/v3/workflow-runs` (Catalog, execution, derived progress)
  - WebSocket `/ws/v3/agent-system` for realtime updates
- Build canonical feature modules under `frontend/app/src/features/`
- Cut over desktop pages to delegate directly to canonical modules.
