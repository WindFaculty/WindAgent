# ADR-FE-002: AgentDefinition vs AgentInstance

- **Status**: ACCEPTED
- **Date**: 2026-08-14
- **Phase**: Phase 1 (Canonical Domain Vocabulary)
- **Deciders**: Architecture Council, Agent Runtime Team

---

## Context and Problem Statement
Historically, the unqualified term `Agent` was overloaded:
- It referred to a configured prompt/template in `v2_agents` or `agents.json`.
- It also referred to an active running agent process executing tasks in `MultiAgentWorkspace`.

This ambiguity led to confusion when passing identifiers across RPC/REST calls, tracking state, and persisting historical execution sessions.

## Decision
We establish a strict dual-entity semantic distinction:

1. **`AgentDefinition`**:
   - **Definition**: The declarative configuration, capability matrix, and persona template.
   - **Properties**: `id` (`agdef_*`), `name`, `role`, `system_prompt`, `skill_ids`, `model_routing_policy`, `tool_permissions`, `version`.
   - **Mutability**: Versioned template.
2. **`AgentInstance`**:
   - **Definition**: An active or historical runtime execution instance created from an `AgentDefinition`.
   - **Properties**: `id` (`aginst_*`), `definition_id`, `conversation_id`, `state` (`IDLE`, `RUNNING`, `WAITING`, `TERMINATED`), `working_memory`, `allocated_resources`.
   - **Mutability**: Ephemeral or session-scoped state machine.

3. **V3 Contract Rule**: The unqualified term `Agent` is strictly prohibited in all V3 DTOs, OpenAPI schemas, and TypeScript interfaces.

## Schema & ID Mapping
| Concept | Legacy (V2) | Canonical (V3) | ID Prefix |
|---|---|---|---|
| Agent Template/Config | `Agent`, `agent_type` | `AgentDefinition` | `agdef_` |
| Runtime Worker | `Agent`, `agent_id` (mixed) | `AgentInstance` | `aginst_` |

## Consequences
- **Positive**: Clean separation between static template management and dynamic multi-agent orchestration.
- **Enforcement**: Linters and OpenAPI validators in Phase 3 will fail on raw `Agent` schema fields.
