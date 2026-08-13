# UI7 — OUTLINE & SCREENPLAY UX — VERDICT

Phase: Desktop Redesign Roadmap UI7
Date: 2026-08-13
Gate: **WIND_STUDIO_UI7_SCREENPLAY_WORKSPACE_VERIFIED — PASS**

---

## Summary of Accomplishments

### 1. Outline Scene Presentation (`OutlineView.tsx`)
- Redesigned Scene-based cards:
  - Intent, location, estimated seconds badge.
  - Visual action, conflict turn, dialogue budget, beat references, and character tags.
  - Summary metrics: total scene duration vs target duration (with tolerance indicator), total scene count, location count, and cast required count.

### 2. Screenplay 3-Pane Reader Workspace (`ScreenplayView.tsx`)
- Implemented 3-pane Reader layout:
  1. **Left Rail (Scene Navigation)**: Quick jump list of scenes with scene order, location sluglines, and estimated seconds. Clicking a scene activates and highlights it.
  2. **Center Pane (Formatted Screenplay Document)**: Industry-standard screenplay formatting with Courier monospace font, uppercase sluglines, action description, centered uppercase character names, parentheticals, indented dialogue text, and right-aligned transitions (`CUT TO:`).
  3. **Right Inspector Panel**: Active scene details, target vs actual total duration, revision ID, content hash, linked outline scene IDs, and beat lineage.
- Enforced Read-Only status banner when episode state is `SCREENPLAY_LOCKED` or `READY_FOR_PRODUCTION`.

---

## Test & Build Matrix

| Surface | Result |
|---|---|
| `@windagent/story-ui` Vitest Suite (`storyUi.test.tsx`, `storyUiPhase6.test.tsx`, `storyUiPhase7.test.tsx`) | 3 test files / 17 tests PASS |
| `@windagent/studio-shell` Vitest Suite | 9 tests PASS |
| Desktop Typecheck (`tsc -b --noEmit`) | PASS |
| Desktop Unit Tests (`apps/desktop` Vitest) | 15 test files / 159 tests PASS |
| Desktop Production Build (`tsc -b && vite build`) | PASS |

---

## Gate Verdict

```text
WIND_STUDIO_UI7_SCREENPLAY_WORKSPACE_VERIFIED = PASS
```
