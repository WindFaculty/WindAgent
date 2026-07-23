# Provider Routing V3 Architecture Decisions

**Document Version**: 1.0.0  
**Phase**: Phase 0 — Baseline, Inventory, and Migration Map  
**Starting Commit SHA**: `59aaea22339d26ec9b10dcf398e4380f65f656ba`  
**Branch**: `feat/provider-routing-v3`  

---

## 1. Context and Architectural Principles

This document records the locked technical decisions governing the **Provider Routing V3 Subsystem** in `WindAgent`. These decisions are mandatory for all subsequent implementation phases (Phase 1 through Phase 14).

---

## 2. Locked Architecture Decisions

### ADR-01: Model Selection & Route Locking
- **Rule**: Model selection runs **only on the first call** of a scope (`session`, `task`, or `workflow`):
  ```text
  task/session/workflow label
      → routing rule
      → canonical model
      → persistent route lock
  ```
- **Constraint**: Subsequent calls in the same scope MUST read the `route_lock`. Model selection MUST NOT be re-executed per turn.

### ADR-02: Endpoint Selection & Scoring
- **Rule**: After a canonical model is locked:
  ```text
  canonical model
      → exact-equivalent endpoint bindings
      → endpoint health/quota/circuit filtering
      → endpoint scoring
      → execute
  ```
- **Constraint**: Dynamic endpoint selection (failover across providers servicing the *exact same canonical model*) is permitted. Changing the canonical model during failover is strictly forbidden.

### ADR-03: Strict Same-Model Failover & No Silent Fallbacks
- **Rule**: Automatic failover is valid ONLY when:
  - `binding.canonical_model_id` matches exactly;
  - `binding.model_revision` matches exactly;
  - `binding.equivalence_level == "exact_revision"`;
  - `binding.enabled == true`;
  - Endpoint is not in cooldown or open circuit.
- **Error Handling**: When all endpoints for the locked canonical model are unavailable, the system MUST raise:
  ```text
  SameModelEndpointExhausted
  ```
- **Constraint**: Silent fallbacks to different canonical models, lower quality models, or mock adapters in production execution are strictly prohibited.

### ADR-04: Non-Persisted Test Connect Protocol
- **Rule**: When a user clicks **Test Connect**:
  - Use user-selected provider as hint;
  - Auto-detect protocol and vendor via probe matrix;
  - Support manual overrides;
  - Return confidence rating and detection evidence;
  - Do NOT save credentials to storage before explicit user confirmation;
  - Do NOT alter runtime route locks or routing state.

### ADR-05: Local Provider Scope Boundary
- **Rule**: The `local/` package manages Ollama servers on local machine or LAN networks ONLY.
- **Out of Scope**: Direct `transformers` inference, in-process `llama.cpp` bindings, direct `GGUF` file loaders, and `vLLM` process lifecycle management are explicitly excluded from this rebuild phase.

### ADR-06: Strict Storage & Dependency Boundary
- **Rule**: `providers/windagent_providers` is a standalone domain transport package.
- **Forbidden Imports**: `windagent_providers` MUST NOT import:
  - SQLAlchemy ORM (`sqlalchemy`, `storage.windagent_storage.orm`);
  - FastAPI (`fastapi`, `starlette`);
  - Application services (`apps.backend`);
  - Orchestration or Intelligence layers.
- **Port/Adapter Pattern**: Storage persistence, ORM mapping, Redis caching, and HTTP server routing reside strictly in `storage/` or `apps/` composition layers.
