# Phase 7 Baseline Preflight Report

- **Commit SHA**: `ac2c19c59ca3c16c86e81d761c0a70b911bb294e`
- **Timestamp**: `2026-08-14T04:56:11Z`
- **Target**: Unified Projects + Studio convergence, eliminating StudioStore & manual hash parsing from Projects and Studio Home, establishing canonical V3 Project/Episode authority.

## Key Baseline Findings
1. `ProjectsPage.tsx` and `StudioPage.tsx` both instantiate `HttpStudioApiClient` + `StudioStore` directly.
2. `StudioPage.tsx` performs manual URL `#` hash parsing for routing.
3. V3 requires canonical endpoints for `/api/v3/projects`, `/api/v3/projects/{projectId}/episodes`, and `/api/v3/project-templates`.
