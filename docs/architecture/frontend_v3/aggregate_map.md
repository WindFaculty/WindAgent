# Frontend V3 Aggregate Map & Entity Boundaries

This document defines the Domain Aggregate Roots, child entities, value objects, and relationship boundaries across the WindAgent system.

---

## 1. Primary Aggregate Root: `Project`

```mermaid
classDiagram
    class Project {
        +string id (proj_*)
        +string name
        +string description
        +int version
        +string current_revision_id
        +datetime created_at
        +datetime updated_at
    }

    class Episode {
        +string id (ep_*)
        +string project_id
        +int episode_number
        +string title
        +string status
        +int version
    }

    class Character {
        +string id (char_*)
        +string project_id
        +string name
        +string visual_archetype
        +string voice_model_id
    }

    class WorldSetting {
        +string id (world_*)
        +string project_id
        +string premise
        +list timeline_rules
    }

    class AssetBinding {
        +string id
        +string project_id
        +string asset_id (ast_*)
        +string role
    }

    Project *-- "0..*" Episode : contains
    Project *-- "0..*" Character : defines
    Project *-- "1" WorldSetting : describes
    Project o-- "0..*" AssetBinding : references
```

---

## 2. Orchestration Aggregate Root: `WorkflowRun`

```mermaid
classDiagram
    class WorkflowDefinition {
        +string id (wfdef_*)
        +string name
        +list steps_dag
        +int version
    }

    class WorkflowRun {
        +string id (wfrun_*)
        +string workflow_def_id
        +string project_id
        +string status
        +datetime started_at
        +datetime completed_at
    }

    class TaskExecution {
        +string id (tsk_*)
        +string workflow_run_id
        +string step_key
        +string status
    }

    class RunAttempt {
        +string id (run_*)
        +string task_id
        +int attempt_number
        +string agent_instance_id
        +string status
        +list output_artifact_ids
    }

    WorkflowDefinition ..> WorkflowRun : instantiates
    WorkflowRun *-- "1..*" TaskExecution : manages
    TaskExecution *-- "1..*" RunAttempt : executes
```

---

## 3. Agent Aggregate Root: `AgentDefinition` & `AgentInstance`

```mermaid
classDiagram
    class AgentDefinition {
        +string id (agdef_*)
        +string name
        +string role
        +string system_prompt
        +list skill_ids
        +int version
    }

    class AgentInstance {
        +string id (aginst_*)
        +string agent_def_id
        +string session_id
        +string state
        +json working_memory
    }

    AgentDefinition *-- "0..*" AgentInstance : spawns
```

---

## 4. Invariant Rules Across Boundaries

1. **Transactional Boundary**: Mutations to an `Episode`, `Character`, or `WorldSetting` increment the parent `Project.version` or the sub-aggregate version according to the concurrency contract.
2. **Artifact Immutability**: Once an `Artifact` is written by a `RunAttempt`, its content and checksum cannot be altered. Edits produce a new `Revision` or new `Artifact`.
3. **Asset Decoupling**: An `Asset` exists independently in the asset catalog (`/api/v3/assets`) and is linked to Projects via `AssetBinding`.
