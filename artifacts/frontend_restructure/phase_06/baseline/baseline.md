# Phase 6 Baseline Preflight Report

- **Commit SHA**: `ac2c19c59ca3c16c86e81d761c0a70b911bb294e`
- **Timestamp**: `2026-08-14T04:37:46Z`
- **Target**: Complete elimination of synthetic data from Dashboard, extraction of clean Monitoring surface, V3 observability authority backend integration.

## Key Baseline Findings
1. `apps/desktop/src/pages/Dashboard.tsx` contains 8 synthetic data violations including `Math.random()`, hardcoded chart curves, static KPI counters, and manual refresh simulations.
2. `frontend/app/src/app/App.tsx` polls `platform.getSystemMetrics` and health directly on root shell instead of utilizing reactive query and WebSocket caches.
3. V3 API requires canonical endpoints for `/api/v3/dashboard/summary`, `/api/v3/system/metrics`, `/api/v3/system/health`, and `/api/v3/monitoring/*`.
