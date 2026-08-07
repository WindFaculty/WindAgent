# Legacy Compatibility Layer — Sunset Manifest (VP3D Stage A)

This directory (`core/windagent_core/domain/video_production/legacy_v1/`) is
the **bounded compatibility layer** for generative-video types retired during
Stage A. It exists ONLY so persisted legacy artifacts remain readable and so
the bounded legacy reader `ProductionIrMigrator` can map them onto the
engine-neutral Production IR.

## Boundary rules (enforced by `tests/architecture/test_phase2_flow_removal_canonical.py`)

1. **Not exported canonically** — nothing in this package is re-exported from
   `windagent_core.domain.video_production.__init__` or `windagent_core.__init__`.
2. **Not called by the new runtime** — the runtime builds
   `ProductionIrDocument` / `ShotExecutionIntent` and dispatches through
   `ProductionEnginePort`; it never constructs a `GenerationModeDecision`,
   `FlowGenerationSpecification`, or `GenerationMode`.
3. **Allowlisted paths only** — the residue scanner excludes exactly this
   directory, the migrator, and the legacy fixture tests that exercise the
   migration path. No broad excludes.

## Retired types

| Type | Former canonical home | Replacement |
|---|---|---|
| `GenerationMode` | `enums.py` | (none — the engine adapter decides execution) |
| `GenerationModeReasonCode` | `enums.py` | (none) |
| `GenerationModeDecision` | `shot_graph.py` | (none; rationale is advisory only) |
| `FlowGenerationSpecification` | `prompt_compiler.py` | `ShotExecutionIntent.creative_prompt` + `AssetReference` hashes |
| `FlowGenerationSpecificationId` | `ids.py` | (none) |
| `LegacyGenerationRequest` | `generation_job.py` | `EngineJobReceipt` + IR |

## Sunset criteria

Delete this package (and the migrator's legacy-input branches) when ALL of
the following hold:

- no persisted legacy artifact (VideoProductionPackage v1 / GenerationRequest)
  is read by any active workflow, storage reader, or verification script;
- the compatibility window documented in Stage A Phase 1 §8 has ended;
- the retirement manifest in
  `artifacts/video_production_3d/phase_02/retirement_manifest.json` lists the
  deletion.
