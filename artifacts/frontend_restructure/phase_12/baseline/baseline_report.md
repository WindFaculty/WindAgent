# Phase 12 Baseline Report — Model Infrastructure Domain

## 1. Executive Summary
This baseline documents the fragmented state of the Models, Endpoints, and Router subsystems prior to Phase 12 convergence.

- **Models (`Models.tsx`)**: Called `/api/v2/providers` directly and performed client-side model mapping without canonical model metadata (context window, capabilities, modality, benchmark rankings).
- **Endpoints (`Endpoints.tsx`)**: Directly queried `/api/v2/providers` and `/api/v2/providers/health` via `fetch()`. Did not support backend connection testing or credential status check.
- **Router (`Router.tsx`)**: Spanned 2,565 lines (117 KB) and combined routing configuration with WebAudio synthesizer implementations and interactive mini-game mechanics. Called legacy `/api/models/routing/*` endpoints.

## 2. Target Architecture
All three domains are consolidated into the unified **Model Infrastructure domain**:
1. `features/models`: Canonical Model Definitions, capabilities, context limits, and endpoint bindings.
2. `features/providers`: Physical Provider & Endpoint Registry, health monitoring, connection testing, and secure credential status.
3. `features/routing`: Priority-based rule execution, routing topology graph, traffic metrics, simulation with explainable `RouteDecision`, and route lock inspection.
