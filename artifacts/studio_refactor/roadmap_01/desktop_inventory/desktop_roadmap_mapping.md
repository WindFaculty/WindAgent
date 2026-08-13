# WindAgent Desktop -> Roadmap 1 Mapping

Source of truth for Roadmap 1: `docs/plans/studio_roadmap_01/` (contract studio.contract/v0.1, baseline 9a09375).

## Target package layout vs reality

| Roadmap package | Status | Equivalent today |
|---|---|---|
| frontend/packages/studio-contracts | EXISTS (roadmap-owned, frozen) | same path, generated types + fixtures + drift checker |
| frontend/packages/studio-client | EXISTS | same path, HttpStudioApiClient |
| frontend/packages/studio-state | EXISTS | same path, StudioStore |
| frontend/packages/story-ui | NOT_IMPLEMENTED | components/studio/ArtifactViews.tsx + RunProgress + ApprovalBar in apps/desktop (would migrate INTO story-ui) |
| frontend/packages/studio-shell | NOT_IMPLEMENTED | App.tsx header+sidebar+hash routing (would extract into studio-shell) |

## What already exists

- Real V3 studio API client + server-authority store (C2).
- Studio shell page with hash routing (C3): list/series/episode + deep-link rehydration.
- Story UI: RunProgress, idea cards, bibles/beats/outline views, ApprovalBar gated by awaiting_checkpoint (C4).
- Screenplay/review/diff/lock UI + hash-bound lock + post-lock read-only (C5).
- 142 desktop tests incl. studio shell + story suites; contract drift checkers in CI.

## What is equivalent (not 1:1)

- "Studio Home" == StudioPage route list view.
- "Series" == series view (needs description field surfaced; API accepts it).
- "Episode" == episode view (needs workspace tabs).
- "Story/Screenplay/Review" == artifact viewers + approval flow (read path complete).

## What is missing

- Episode Workspace tab structure (IDEA/STORY/OUTLINE/SCREENPLAY/REVIEW/REVISIONS/ACTIVITY).
- story-ui + studio-shell packages (extraction, not new code).
- Story Bible / World Bible / Character / Beat Sheet EDITORS (viewers exist; backend read side exists; write path = deriveRevision + run pipeline, not direct editing per contract).
- Screenplay editor in studio domain (production-ui StructuredEditor/TextEditor are production-domain dead exports — decide reuse vs separate).
- Review findings UX (navigation/filter), revision browsing beyond last-2 diff.
- Design system pass (tokens exist but scattered; production-ui uses inline hex).
- Navigation restructure (STUDIO-first groups) — currently hardcoded in App.tsx.

## What should be migrated

- components/studio/* -> frontend/packages/story-ui (RunProgress, ApprovalBar, ArtifactViews) with StudioStore/client as deps.
- App.tsx shell (header/sidebar/hash router) -> frontend/packages/studio-shell.
- StudioPage data logic stays in apps/desktop or moves to studio-shell; recommendation: page composition in apps/desktop, primitives in packages.

## What should remain shared

- @windagent/studio-* packages unchanged (frozen contract; CI gates depend on them).
- Tauri shell unchanged.
- @windagent/production-* packages unchanged (Roadmap 2 surface; keep fake client wiring until Production is in scope).

## Alignment verdict

Studio data/read path: ~done. Studio presentation (workspace, navigation, editors): the actual Roadmap-1 frontend work. Backend + contract + worker: out of scope of this inventory but verified present (routers/v3/studio/*, studio_runtime.py, 9 frozen story task types).
