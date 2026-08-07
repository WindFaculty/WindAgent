"""VP3D Phase 4 — Deterministic scene pipeline (plan Stage B §4).

Sub-package of the Blender production engine. Everything here is the
TRUSTED, deterministic scene side of the pipeline:

- `compiler.py`    — ScenePlan model + ScenePlanCompiler (IR -> scene_plan.json)
                     + version-pinned trusted bpy script (never LLM-generated).
- `fixture.py`     — the typed deterministic smoke fixture (cube, ground,
                     camera, three lights, one material, keyframed animation).
- `frames.py`      — FrameManifest (atomic temp -> validated final), resume
                     computation, cancel-token polling.
- `idempotency.py` — job idempotency keys + artifact reuse / invalidation.
- `determinism.py` — two-run structural determinism report.
- `pipeline.py`    — BlenderSmokePipeline orchestrating the full
                     COMPILE -> SAVE -> INSPECT -> RENDER_CHUNK -> ASSEMBLE ->
                     VERIFY flow with cancel/resume/retry and reuse.

Layering: this package lives in the tools layer next to the engine adapter.
core/domain never imports it (architecture gate). The scene plan is
engine-neutral JSON produced from the engine-neutral Production IR.
"""
