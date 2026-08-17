# ADR-FE-001: Project vs Series Canonicalization

- **Status**: ACCEPTED
- **Date**: 2026-08-14
- **Phase**: Phase 1 (Canonical Domain Vocabulary)
- **Deciders**: Architecture Council, Frontend V3 Team, Studio Team

---

## Context and Problem Statement
In the existing codebase (`v2_*` APIs and `apps/desktop/src/pages/`), the concepts of "Project" and "Series" have been used interchangeably or with overlapping responsibilities:
- `StudioSeries`, `series_id`, `/api/v3/studio/series` refer to video series workflows.
- `ProjectsPage.tsx` and `/api/v2/production_workspace` refer to general multi-media projects.
- This creates cognitive overload for developers and ambiguous user experiences in navigation and state management.

## Decision
1. **`Project` is the sole canonical aggregate root** exposed to users and the frontend architecture.
2. A `Project` encapsulates:
   - **Episodes**: Script and timeline beats for episodic or narrative content.
   - **Characters**: Persona definitions, cast voice models, visual references.
   - **World / Setting**: Lore, locations, environment guidelines.
   - **Assets**: 2D/3D assets, audio stems, render outputs.
   - **Production Configuration**: Target aspect ratio, render engines, agent team presets.
3. **`Series` is retained as a compatibility concept** during the migration window (Phase 1–5).
   - Backend routes under `/api/v3/studio/series` remain functional as compatibility aliases.
   - New unified endpoints will expose `/api/v3/projects`.
4. **Deprecation Path**: Complete removal of `Series` as a top-level standalone aggregate occurs in Phase 14–16.

## Schema & ID Mapping
| Concept | Legacy (V2/Early V3) | Canonical (V3) | ID Prefix |
|---|---|---|---|
| Top-level container | `Series`, `StudioSeries` | `Project` | `proj_` (alias: `series_`) |
| Sub-container | `Episode` | `Episode` | `ep_` |

## Consequences
- **Positive**: Single clear root for all frontend state, breadcrumbs, and workspace scopes.
- **Negative**: Temporary dual-support mapping in API layer during migration window.
