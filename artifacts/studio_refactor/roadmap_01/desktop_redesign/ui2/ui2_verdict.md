# UI2 — EXTRACT `studio-shell` — VERDICT

Phase: Desktop Redesign Roadmap UI2
Date: 2026-08-13
Gate: **WIND_STUDIO_UI2_STUDIO_SHELL_EXTRACTED — PASS**

---

## Summary of Accomplishments

### 1. Extracted Package `@windagent/studio-shell`
Created new package at `frontend/packages/studio-shell/` with modular layout components:
- **Layout Components** (`src/layout/`):
  - `AppShell.tsx`: Outer app layout frame (`.app-container`).
  - `TopBar.tsx`: Top bar layout containing header brand, status badges, metrics, window controls.
  - `Sidebar.tsx`: Left sidebar layout container (`.left-sidebar`) with nav items, version box, and user profile box.
  - `MainWorkspace.tsx`: Main content wrapper (`.workspace-wrapper` & `.main-content`).
  - `WorkspaceHeader.tsx`: Optional header for inner workspace screens.
- **Navigation Descriptors** (`src/navigation/`):
  - `navigation.types.ts`: Navigation descriptor types (`NavigationItemDescriptor`, `NavigationGroupDescriptor`).
  - `navigation.config.ts`: Canonical desktop navigation descriptors (`DESKTOP_NAVIGATION_GROUPS`).
  - `NavigationGroup.tsx`: Render component for sidebar navigation items.
- **Status Components** (`src/status/`):
  - `BackendStatus.tsx`: Connected/Offline status badges for Backend and Hermes.
  - `RuntimeMetrics.tsx`: CPU, RAM, GPU, VRAM resource indicators with SVG sparklines.
  - `RuntimeStatusStrip.tsx`: TopBar metrics container.
- **Barrel Export**: `src/index.ts`.
- **Package Tests**: `src/__tests__/studioShell.test.tsx`.

### 2. Refactored `App.tsx` into Composition Root
- Converted `apps/desktop/src/App.tsx` (594 lines god-file) into a clean composition root delegating layout rendering to `@windagent/studio-shell`.
- Preserved 100% of health polling, system resource metric updates, navigation routes, and Studio deep-link hydration.

---

## Test & Build Matrix

| Surface | Result |
|---|---|
| `@windagent/studio-shell` Package Vitest | 6 tests PASS |
| Desktop Typecheck (`tsc -b --noEmit`) | PASS |
| Desktop Unit Tests (`apps/desktop` Vitest) | 15 test files / 159 tests PASS |
| Desktop Build (`tsc -b && vite build`) | PASS |
| Legacy Pages & Studio Deep Links | PASS |

---

## Gate Verdict

```text
WIND_STUDIO_UI2_STUDIO_SHELL_EXTRACTED = PASS
```
