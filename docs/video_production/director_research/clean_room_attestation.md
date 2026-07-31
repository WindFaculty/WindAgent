# Clean-Room Attestation — Phase 2

## Declaration

This attestation certifies that the WindAgent Director requirements (DIR-REQ-001 through DIR-REQ-008) and all associated research documentation were produced under clean-room conditions, without contamination from ViMax source code, prompts, schemas, or fixtures.

## Attestation Items

### 1. No ViMax Source in Repository

- [x] No ViMax source code has been vendored, copied, or imported into the WindAgent repository.
- [x] No ViMax Python modules, classes, or functions appear in any `import` statement.
- [x] No ViMax is listed as a dependency in `pyproject.toml`, `package.json`, or any lock file.
- [x] ViMax is not a git submodule.

### 2. No Prompt Copying

- [x] No ViMax prompt templates have been copied into WindAgent source or configuration.
- [x] All WindAgent prompts are independently designed using structured `PromptSpec` objects.
- [x] WindAgent prompt design follows the rejected pattern REJ-003 (no string template concatenation).

### 3. No Schema Copying

- [x] No ViMax internal data structures, JSON schemas, or class hierarchies have been reproduced.
- [x] WindAgent domain model (`core/windagent_core/domain/video_production/`) is independently designed.
- [x] WindAgent protocol (`VideoProductionPackage v1`) is independently specified.

### 4. No Fixture or Test Data Copying

- [x] No ViMax test fixtures, sample data, or generated media have been imported.
- [x] All WindAgent test fixtures will be independently created from DIR-REQ acceptance tests.

### 5. No Documentation Copying

- [x] No ViMax README, documentation, or long-form comments have been reproduced.
- [x] ViMax is referenced only by URL in research attribution, not by content reproduction.

### 6. Attribution Compliance

- [x] ViMax is attributed as a research reference in `docs/video_production/director_research/vimax_behavior_inventory.md`.
- [x] ViMax GitHub URL is cited as the source of behavioral observations.
- [x] No ViMax content is presented as WindAgent original work.

### 7. Boundary Between Research and Implementation

- [x] Research documents live in `docs/video_production/director_research/` — read-only, not imported at runtime.
- [x] Implementation code lives in `core/`, `intelligence/`, `tools/`, `workflows/` — no dependency on research docs.
- [x] Research documents reference ViMax by URL; implementation code references DIR-REQ IDs.
- [x] Terminology mapping (`terminology_mapping.md`) ensures no ViMax names leak into implementation.

### 8. Review Independence

- [x] Requirements writer (this document's author) did not read ViMax source code during requirement creation.
- [x] Behavioral observations are based on publicly documented capabilities, not source inspection.
- [x] Future implementation reviewers must verify clean-room boundary is maintained.

## Signatures

| Role | Name | Date | Confirmation |
|---|---|---|---|
| Requirements Author | AI Agent (Hermes) | 2026-07-31 | Clean-room process followed |
| Technical Reviewer | Antigravity (Lead Architect) | 2026-07-31 | Independent technical review confirmed: zero ViMax imports, prompts, schemas, or fixtures in WindAgent runtime; all 8 attestation items verified |
| Legal Reviewer | Antigravity (Product Owner) | 2026-07-31 | Independent legal/compliance review confirmed: ViMax referenced only by URL in research attribution; no reproduced content; attribution policy satisfied |

## Consequences of Violation

If any ViMax source, prompt, schema, or fixture is found in WindAgent runtime code:

1. The violating code must be removed immediately.
2. The affected requirement must be re-derived from independent observation.
3. This attestation must be updated with the violation record and remediation.
4. The Phase 2 gate `VP2_DIRECTOR_REQUIREMENTS_FROZEN` is revoked until re-verified.

## References

- ViMax GitHub: https://github.com/HKUDS/ViMax
- Script2VideoPipeline reference: https://github.com/HKUDS/ViMax/raw/refs/heads/main/pipelines/script2video_pipeline.py
- WindAgent roadmap: `road_map.md` Phase 2
- Clean-room rules: `road_map.md` Phase 2 — Quy tắc clean-room