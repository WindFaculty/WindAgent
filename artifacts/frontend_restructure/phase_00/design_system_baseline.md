# Design System Baseline Report (Phase 0)

## Overview
- **Primary Stylesheet**: `apps/desktop/src/styles.css` (~126 KB)
- **Component Specific Stylesheets**: `Dashboard.css`, `ProjectsPage.css`, `story-ui/src/styles.css`
- **Total Design Tokens Discovered**: 61 (Unique: 61)
- **Total CSS Selectors Discovered**: 1141 (Unique: 1114)

## Token Categories
- **Studio Semantic Tokens (`--studio-*`)**: High-order studio tokens governing script editor, beat sheet, character nodes, and timeline cards.
- **Status Tokens (`--status-*`)**: Run, task, and health indicators (success, warning, error, idle, executing).
- **Layout & Spacing Tokens**: Margin, padding, grid columns, split pane handles.
- **UI Primitives (`.ui-button`, `.ui-badge`, etc.)**: Core primitive classes to be extracted in Phase 5 into `@windagent/ui`.

## Extraction & Convergence Strategy (Phase 5)
1. **Never redesign from scratch**: Extract established tokens from `styles.css` into `@windagent/tokens`.
2. **Preserve Compatibility Aliases**: Retain legacy classes (`.ui-button`, `.ui-badge`) pointing to token primitives so legacy views do not break.
3. **Eliminate Duplicates**: 0 tokens and 27 selectors have duplicate definitions across files; converge to single source of truth.
