# Terminology Mapping — ViMax to WindAgent

Every ViMax concept observed during clean-room research maps to a WindAgent canonical term. No ViMax names, class names, or method names appear in WindAgent runtime code, public API, or protocol schemas.

## Core Concepts

| ViMax Concept (observed) | WindAgent Canonical Term | Package Location |
|---|---|---|
| Camera tree | `ShotDependencyGraph` | `core/windagent_core/domain/video_production/shot.py` |
| Storyboard artist | `CinematicPlanner` | `intelligence/windagent_intelligence/video/director/` |
| Character portrait registry | `IdentityReferenceCatalog` | `core/windagent_core/domain/video_production/character.py` |
| Reference image selector | `ReferenceBindingPlanner` | `intelligence/windagent_intelligence/video/director/` |
| Script2Video pipeline | `ProductionPlanningWorkflow` | `workflows/windagent_workflows/video_production/` |
| Working directory cache | `ArtifactRevisionStore` | `storage/windagent_storage/artifacts/` |

## Planning Concepts

| ViMax Concept | WindAgent Canonical Term |
|---|---|
| Scene breakdown | `SceneDecomposition` |
| Shot planning | `ShotPlanning` |
| Frame planning | Not used — WindAgent plans at shot level, not frame level |
| Prompt template | `PromptSpec` (structured, not string template) |
| Parameter bundle | `GenerationParameters` |

## Continuity Concepts

| ViMax Concept | WindAgent Canonical Term |
|---|---|
| 180-degree rule check | `ScreenDirectionConstraint` |
| Eyeline match | `EyelineContinuity` |
| Match on action | `ActionMatchConstraint` |
| Camera position correction | `CameraPositionAdjustment` |

## Rendering Concepts

| ViMax Concept | WindAgent Canonical Term |
|---|---|
| Image generation | `ImageGenerationJob` |
| Video generation | `VideoGenerationJob` |
| Video extension | `VideoExtensionJob` |
| Result download | `GenerationResult` |
| File-exists check | **REJECTED** — replaced with `ContentAddressedArtifact` (Phase 18) |
| Skip cache | **REJECTED** — replaced with `ArtifactIntegrityCheck` |

## Workflow Concepts

| ViMax Concept | WindAgent Canonical Term |
|---|---|
| Pipeline stage | `WorkflowPhase` |
| Parallel dispatch | `ConcurrentPhase` |
| Sequential stage | `SequentialPhase` |
| Checkpoint | `PhaseCompletionEvent` |
| Resume | `WorkflowHydration` |

## Authority

| ViMax Concept | WindAgent Canonical Term |
|---|---|
| End-to-end orchestrator | **REJECTED** — WindAgent workflow engine retains sole authority |
| Script runner | `ProductionPlanningWorkflow` + `ProductionExecutionWorkflow` |

## Rules

1. No ViMax term appears in any WindAgent:
   - Python class name, function name, or variable name
   - JSON schema key
   - Event type string
   - CLI command or flag
   - API endpoint path
   - Config key
   - Documentation heading (except this file and ADR attribution)
2. Mapping is one-way: ViMax term → WindAgent term. Reverse mapping is not maintained.
3. New concepts discovered in future ViMax versions must go through the same clean-room observation and terminology mapping process before entering WindAgent.