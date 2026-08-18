# Phase 16 — Deletion Candidates Matrix & Classification

| Candidate File / Directory | Domain | Size | Classification | Rationale & Replacement |
| :--- | :--- | :--- | :--- | :--- |
| `apps/desktop/src/pages/Browser.tsx` | Platform | 45.1 KB | `DELETE` | Replaced by `@windagent/app/src/features/browser` (Phase 13) |
| `apps/desktop/src/pages/Files.tsx` | Platform | 42.6 KB | `DELETE` | Replaced by `@windagent/app/src/features/files` (Phase 13) |
| `apps/desktop/src/pages/Memory.tsx` | Platform | 43.9 KB | `DELETE` | Replaced by `@windagent/app/src/features/memory` (Phase 13) |
| `apps/desktop/src/pages/Settings.tsx` | Platform | 39.2 KB | `DELETE` | Replaced by `@windagent/app/src/features/settings` (Phase 13) |
| `apps/desktop/src/styles.css` | Styling | 126.2 KB | `DELETE` | Replaced by `@windagent/app/src/styles/index.css` (Phase 14) |
| `apps/desktop/src/pages/Dashboard.css` | Styling | 19.0 KB | `DELETE` | Replaced by Tailwind utility styling in `@windagent/app` |
| `apps/desktop/src/pages/ProjectsPage.css` | Styling | 19.9 KB | `DELETE` | Replaced by Tailwind utility styling in `@windagent/app` |
| `apps/desktop/src/pages/StudioPage.tsx` | Studio | 275 B | `DELETE` | Replaced by `@windagent/app` direct import in tests |
| `apps/desktop/src/pages/ProjectsPage.tsx` | Studio | 262 B | `DELETE` | Replaced by `@windagent/app` direct import in tests |
| `apps/desktop/src/pages/EpisodesPage.tsx` | Studio | 269 B | `DELETE` | Replaced by `@windagent/app` |
| `apps/desktop/src/pages/CharactersPage.tsx` | Studio | 573 B | `DELETE` | Replaced by `@windagent/app` |
| `apps/desktop/src/pages/StoryBoardPage.tsx` | Studio | 731 B | `DELETE` | Replaced by `@windagent/app` |
| `apps/desktop/src/pages/ReviewsPage.tsx` | Studio | 660 B | `DELETE` | Replaced by `@windagent/app` |
| `apps/desktop/src/pages/ProductionWorkspacePage.tsx` | Production | 1.4 KB | `DELETE` | Replaced by `@windagent/app` |
| `apps/desktop/src/pages/Agents.tsx` | Agent | 688 B | `DELETE` | Replaced by `@windagent/app` |
| `apps/desktop/src/pages/MultiAgentWorkspace.tsx` | Agent | 791 B | `DELETE` | Replaced by `@windagent/app` |
| `apps/desktop/src/pages/Workflows.tsx` | Agent | 584 B | `DELETE` | Replaced by `@windagent/app` |
| `apps/desktop/src/pages/Models.tsx` | Model | 605 B | `DELETE` | Replaced by `@windagent/app` |
| `apps/desktop/src/pages/Endpoints.tsx` | Model | 542 B | `DELETE` | Replaced by `@windagent/app` |
| `apps/desktop/src/pages/Router.tsx` | Routing | 588 B | `DELETE` | Replaced by `@windagent/app` |
| `apps/desktop/src/pages/Dashboard.tsx` | Dashboard | 642 B | `DELETE` | Replaced by `@windagent/app` |

---

### Total Dead Code Reclaimed:
- **Files**: 21
- **Bytes reclaimed**: ~345 KB
- **Provably unreachable consumers**: 0
