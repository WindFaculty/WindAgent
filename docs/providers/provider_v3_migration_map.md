# Provider Routing V3 Old-to-New Migration Map

**Document Version**: 1.0.0  
**Phase**: Phase 0 — Baseline, Inventory, and Migration Map  
**Starting Commit SHA**: `59aaea22339d26ec9b10dcf398e4380f65f656ba`  
**Branch**: `feat/provider-routing-v3`  

---

## 1. Migration Overview Matrix

| Old Component | Target New Component | Action | Reason / Rationale | Dependency | Risk Level | Test Coverage Plan |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `apps/backend/services/provider_clients/` | `providers/windagent_providers/` (`openai/`, `anthropic/`, `google/`, `ollama/`) | **MIGRATE** | Move provider transport protocol drivers out of backend service layer into standalone domain package to satisfy clean storage boundary (§1.6). | Phase 1 Contracts | Low | Mock HTTP transport unit tests in `tests/unit/providers/` |
| `apps/backend/services/provider_gateway.py` | `providers/windagent_providers/routing/execution_coordinator.py` | **REPLACE** | Legacy gateway handled ad-hoc routing and fallback across distinct canonical models. V3 execution coordinator enforces persistent route lock (§1.1) and exact-equivalent endpoint failover (§1.3). | Phase 5 Execution Coordinator | Medium | Unit tests for route lock enforcement and fallback |
| `apps/backend/services/router_execution_service.py` | `providers/windagent_providers/routing/` (`endpoint_selector.py`, `failover_policy.py`) | **REPLACE** | Replace legacy fallback engine with exact-equivalent binding filter (§1.3) and circuit breaker / cooldown policies. | Phase 5 Routing | Medium | Circuit breaker & cooldown test suite |
| `apps/backend/services/router_policy.py` | `providers/windagent_providers/registry/binding_resolver.py` | **MIGRATE** | Extract canonical model resolution logic; align rule mapping with canonical model locks. | Phase 3 Registry | Low | Policy resolution unit tests |
| `apps/backend/services/route_lock_service.py` | `storage/windagent_storage/repositories/` + V3 Route Lock Port | **REUSE & MIGRATE** | Keep DB persistence in storage layer, wrap with clean port interface in `windagent_providers`. | Phase 5 Routing | Low | Storage repository integration tests |
| `apps/backend/services/model_service.py` | Storage Repository + Provider Registry Bridge | **REUSE & MIGRATE** | Catalog CRUD remains in application/storage layer; runtime model normalization and discovery moves to V3 registry. | Phase 3 Registry | Low | Catalog CRUD test suite |
| `apps/backend/services/quota_service.py` | `providers/windagent_providers/base/rate_limits.py` | **REPLACE** | Replace static quota checks with vendor quota snapshot contracts and live header parsing. | Phase 1 Contracts | Medium | Quota parser tests |
| `apps/backend/db/models.py` (`CanonicalModelORM`, `ProviderModelBindingORM`, `RouteLockORM`, `RouteAttemptORM`) | Same ORM tables in backend/storage | **REUSE** | Database tables (§5.1-§5.2) match V3 requirements; no schema changes in Phase 0. Schema extensions in Phase 2 if needed. | Phase 2 Schema | Low | Migration parity verification |
| `apps/backend/routers/models.py` | `apps/backend/routers/models.py` | **REUSE & MIGRATE** | Delegate endpoint execution to V3 Provider Registry and Execution Coordinator. | Phase 8 API Cutover | Low | Router API unit tests |
| `providers/windagent_providers/` (legacy V2 scaffold) | `providers/windagent_providers/` | **REPLACE / EXTEND** | Expand modular package structure (`base/`, `detection/`, `registry/`, `routing/`, `cache/`, vendor packages). | Phase 1 Foundation | Low | V3 Foundation test suite |

---

## 2. Component Disposition Details

### 2.1 REUSE
- **ORM Models**: `CanonicalModelORM`, `ProviderModelBindingORM`, `RouteLockORM`, `RouteAttemptORM`, `ModelProviderORM`, `ModelCatalogORM`. These existing tables already represent canonical models, provider bindings, and route locks cleanly.
- **API Key Encryption**: `utils/encryption.py` `encrypt` / `decrypt` functions and `@validates("api_key")` logic on ORM models.

### 2.2 MIGRATE
- **Provider Protocol Adapters**: Port OpenAI, Anthropic, Gemini, and Ollama transport drivers from `apps/backend/services/provider_clients/` into `providers/windagent_providers/<vendor>/`, standardizing request/response payload conversions to `ProviderRequest` and `ProviderResponse`.
- **Route Lock Persistence**: Keep storage calls in `storage/windagent_storage/` while connecting them to the V3 `RouteLock` contract.

### 2.3 REPLACE
- **Fallback / Failover Engine**: Remove cross-model fallback logic in `router_execution_service.py`. Implement V3 failover engine requiring `binding.canonical_model_id` equality, `equivalence_level == exact_revision`, and `SameModelEndpointExhausted` error when all endpoints of the locked canonical model fail.
- **Test Connect Probe**: Implement non-persisted protocol detection and health check probing in `providers/windagent_providers/detection/` without writing secrets to DB before user confirmation.

### 2.4 DELETE (Post-Cutover)
- Legacy `apps/backend/services/provider_clients/` directory after all vendor adapters are migrated and verified in `providers/windagent_providers/`.
