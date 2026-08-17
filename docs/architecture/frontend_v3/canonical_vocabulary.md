# Canonical Domain Vocabulary (Frontend V3 + Unified API V3)

This document establishes the authoritative domain vocabulary for WindAgent across all frontend components, API contracts, TypeScript types, and documentation.

---

## 1. Primary Aggregate Entities

| Term | Category | Authority | Description |
|---|---|---|---|
| **`Project`** | Primary Aggregate Root | ADR-FE-001 | The top-level workspace aggregate containing episodes, characters, world setting, assets, and configurations. Replaces `Series` as user-facing root. |
| **`Episode`** | Entity | ADR-FE-001 | A sequential or standalone narrative unit containing script scenes, beat sheets, and render segments. |
| **`Character`** | Entity | Core | Persona definition including visual archetype, voice profile, behavioral prompts, and lore. |
| **`World`** | Entity | Core | Setting, environment rules, timeline lore, visual mood boards, and location specs. |
| **`Asset`** | Entity | ADR-FE-003 | A versioned, curated, reusable production resource (3D model, approved audio stem, style preset). |
| **`Artifact`** | Immutable Entity | ADR-FE-003 | An immutable, structured output produced by an agent or pipeline run (screenplay JSON, scene breakdown). |
| **`File`** | Workspace Resource | ADR-FE-003 | A raw filesystem file without structured schema guarantees. |

---

## 2. Agent & Execution Entities

| Term | Category | Authority | Description |
|---|---|---|---|
| **`AgentDefinition`** | Template / Config | ADR-FE-002 | The declarative template defining an agent's persona, system prompt, skill bindings, and tool permissions. |
| **`AgentInstance`** | Runtime State | ADR-FE-002 | A running or historical execution instance of an `AgentDefinition` tied to a specific session or task. |
| **`Task`** | Execution Unit | ADR-FE-004 | A discrete unit of work requested by a user or orchestrator. |
| **`Run`** | Execution Attempt | ADR-FE-004 | A single physical execution attempt of a task or agent loop. |
| **`WorkflowDefinition`** | Template / DAG | ADR-FE-004 | Reusable Directed Acyclic Graph defining steps, transitions, and conditions. |
| **`WorkflowRun`** | Runtime Instance | ADR-FE-004 | An active or completed execution instance of a `WorkflowDefinition`. |

---

## 3. Concurrency & Memory Entities

| Term | Category | Authority | Description |
|---|---|---|---|
| **`Revision`** | Content Snapshot | ADR-FE-005 | An immutable historical snapshot of content for auditing, time-travel, and comparison. |
| **`version`** | Concurrency Counter | ADR-FE-005 | A positive integer incremented on every state mutation for Optimistic Concurrency Control. |
| **`Memory`** | Contextual Recall | ADR-FE-006 | Semantic, episodic, and associative knowledge retrieved by agents during execution. |
| **`Database`** | Infrastructure | ADR-FE-006 | Low-level persistent storage administration (SQLite/PostgreSQL). Not used for agent recall UI. |

---

## 4. Forbidden / Deprecated Vocabulary in V3

The following terms are **strictly prohibited** in new V3 interfaces, DTOs, and component names:

| Forbidden Term | Canonical Replacement | Reason |
|---|---|---|
| `Series` (as root aggregate) | `Project` | Unifies multi-media and episodic projects under one root. |
| `Agent` (unqualified) | `AgentDefinition` or `AgentInstance` | Disambiguates static config vs runtime execution. |
| `Database` (in sidebar/memory UI) | `Memory` | Matches end-user cognitive model of AI knowledge recall. |
| `run_id` (unscoped) | `task_id`, `run_id`, or `workflow_run_id` | Clarifies execution granularity. |
| `ETag` (as primary concurrency) | `version` / `expected_version` | Uniform OCC across REST, WebSockets, and Tauri IPC. |
