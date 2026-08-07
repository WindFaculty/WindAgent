# Flow Retirement Manifest — Stage A (VP3D_P2_GOOGLE_FLOW_REMOVED)

Date of record: 2026-08-07
Authority: `docs/video_production/3d_animation_plans/stage_a_foundation_architecture.md`
Gate: `VP3D_P2_GOOGLE_FLOW_REMOVED`

This manifest is the single reviewable record of every Flow / generative-video
residue action taken during Stage A. Active runtime/build/test paths must NOT
contain Flow tokens outside the bounded allowlists listed below. Everything
else was either rewritten engine-neutral or archived here (or in
`scripts/verification/historical/`).

## 1. Deleted / retired (hard removal, previous Stage A work)

| Item | Action |
|---|---|
| `tools/windagent_tools/google_flow/` | deleted (Stage A Phase 2) |
| `intelligence/windagent_intelligence/video/prompt_compiler/` | deleted; types retired to `legacy_v1` |
| `intelligence/windagent_intelligence/video/shot_planner/generation_mode.py` (`GenerationModeDecider`) | deleted |
| `core/.../contracts/video_production/production_executor.py` | moved to orchestration layer (engine executor) |
| `tests/unit/intelligence/test_phase11_compiler.py` | retired (subject deleted) |
| canonical `GenerationMode`, `Shot.generation_mode`, `GenerationModeDecision`, `FlowGenerationSpecification`, `GenerationRequest.provider/generation_mode` | retired from canonical runtime; types preserved in `legacy_v1` |

## 2. Archived — scripts (moved to `scripts/verification/historical/`)

These are historical verification of the retired Flow-browser pipeline. They
imported deleted modules and cannot run; none is referenced by current
build/test/runtime.

| Script | Reason |
|---|---|
| `evaluate_pipeline.py` | imports `windagent_tools.google_flow.*` (deleted); historical pipeline evaluation |
| `verify_phase9_shot_graph.py` | imports `GenerationModeDecider` (deleted); verifies retired shot-graph modes |
| `verify_phase10_continuity.py` | imports `GenerationModeDecider` (deleted) |
| `verify_phase11_compiler.py` | imports `GenerationModeDecider` / `GenerationMode` (deleted); compiler retired |
| `runbook_phase24_e2e.py` | Flow-live-run runbook requiring `FLOW_SESSION`/`FLOW_ACCOUNT` credentials; Flow runtime deleted |

## 3. Archived — docs (moved to `docs/video_production/historical/`)

| Path (new) | Reason |
|---|---|
| `historical/flow_navigation/` (4 files) | Flow browser navigation contracts |
| `historical/flow_images/` (5 files) | Flow image generation contracts |
| `historical/flow_video/` (5 files) | Flow video generation contracts |
| `historical/flow_human_control/` (3 files) | Flow account/session/CAPTCHA contracts |
| `historical/director/generation_mode_decision.md` | retired director generation-mode matrix |
| `historical/director/prompt_block_contract.md` | retired prompt-compiler contract |
| `historical/plans/03_phase_08_11_director_layer.md` | Flow-era phase plan |
| `historical/plans/04_phase_12_16_flow_browser_provider.md` | Flow-browser-provider phase plan |

## 4. Rewritten engine-neutral (kept active)

| File | Change |
|---|---|
| `scripts/verification/chaos_phase25.py` | `provider="google_flow_browser"` -> `engine_render`; `Flow*` simulation scaffolding -> `Render*`/`HumanControl*`/`ControlSurface*`; `CH15_FLOW_PROJECT_DELETED` -> `CH15_ENGINE_PROJECT_DELETED`; URLs/dirs neutralized. Receipt `observed` keys and scenario matrix contract unchanged (32 tests pass). |
| `tests/unit/verification/test_phase25_reliability.py` | `CH15_ENGINE_PROJECT_DELETED` scenario id |
| `scripts/verification/verify_phase18_artifact_invalidation.py` | sample `generation_mode` values `"TEXT_TO_VIDEO"` -> `"ENGINE_RENDER"` (opaque storage data) |
| `intelligence/.../video/e2e_poc/poc_runner.py` | runbook steps `FLOW_IMAGE_GENERATION`/`FLOW_VIDEO_GENERATION` -> `ASSET_GENERATION`/`SHOT_RENDER_GENERATION` |
| `tools/windagent_tools/video_probe.py` | docstring: removed `google_flow` process-boundary reference |
| `core/.../production_ir/enums.py`, `models.py` | docstrings no longer name generative-video modes |
| `docs/video_production/protocol/provider_port_contract.md` | removed `tools/google_flow` adapter mention |

## 5. Bounded allowlists (only these may contain Flow/generative-video tokens)

Deliberately narrow, explicit path allowlists — no broad exclude patterns.

### 5a. Legacy compatibility package (read-only historical types)

```
core/windagent_core/domain/video_production/legacy_v1/**
```
Bounded, non-exported from canonical `__init__.py`, imported ONLY by the
migrator and legacy-fixture tests. Sunset plan: `legacy_v1/SUNSET.md`.

### 5b. Legacy fixture migrator

```
core/windagent_core/domain/video_production/production_ir/migrator.py
```
Reads legacy `GenerationModeDecision`/`FlowGenerationSpecification`/
`GenerationRequest` fixtures and produces engine-neutral IR; the IR output
never contains generation modes or provider fields.

### 5c. Legacy persisted-format schema (read by Phase 3 handoff verifiers)

```
docs/video_production/protocol/video_production_package_v1.schema.json
docs/video_production/protocol/video_production_package_v1.md
```
Machine-readable legacy `VideoProductionPackage v1` schema/spec. Referenced by
`scripts/verification/verify_phase03_handoff.py` and
`scripts/verification/verify_phase3_protocol.py` (active). Kept so the legacy
format stays documented and readable; the canonical runtime does not emit it.

### 5d. Authority / roadmap docs that document the retirement

```
docs/blender_3d_animation_roadmap.md
docs/video_production/3d_animation_plans/stage_a_foundation_architecture.md
```
Program roadmaps that name the concepts being removed; they are the authority
for the removal, not runtime dependencies.

### 5e. Historical archives (this dir + scripts archive)

```
docs/video_production/historical/**
scripts/verification/historical/**
```
Archived content is never imported by current build/test/runtime.

## 6. Credentials

No Flow credential/session key or env template remains in active scripts,
config, or `.env*` templates. The only `FLOW_*` references are inside the
archived `runbook_phase24_e2e.py` and `docs/video_production/historical/**`.

## 7. Verification

Residue scan (Task 4 scanner) reports 0 active violations outside the allowlists
above. Full regression unchanged outside the retired items listed in §1–§3.
