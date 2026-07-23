# Legacy Router & Provider Subsystem Inventory

**Document Version**: 1.0.0  
**Phase**: Phase 0 — Baseline, Inventory, and Migration Map  
**Starting Commit SHA**: `59aaea22339d26ec9b10dcf398e4380f65f656ba`  
**Branch**: `feat/provider-routing-v3`  

---

## 1. Executive Summary

This inventory documents all existing provider and router components in `WindAgent` as of commit `59aaea22339d26ec9b10dcf398e4380f65f656ba`. It forms the baseline for the **Provider Routing V3 Rebuild**, which unifies provider transport, model selection, persistent route locks, exact-equivalent failover, and endpoint health tracking into `providers/windagent_providers`.

---

## 2. Database Schema & ORM Model Inventory

### 2.1 Storage ORM (`storage/windagent_storage/orm/models.py`)
- **`ProviderConfigORM` (`v2_provider_configs`)**:
  - Columns: `id` (PK), `provider_name` (UNIQUE), `enabled` (BOOL), `config_json` (TEXT), `updated_at` (DATETIME).
  - Purpose: Storage boundary table for provider config state.

### 2.2 Legacy Backend DB Models (`apps/backend/db/models.py`)
- **`ModelProviderORM` (`model_providers`)**:
  - Columns: `id` (PK), `site_name`, `api_source`, `base_url`, `management_base_url`, `api_key_env`, `api_key` (encrypted via `utils.encryption.encrypt`), `management_api_key_env`, `provider_type` (`cloud`|`local`), `quota_mode`, `supports_openai_compatible`, `supports_model_discovery`, `models_endpoint`, `chat_endpoint`, `enabled`, `priority`, `notes`, `created_at`, `updated_at`.
- **`ModelCatalogORM` (`model_catalog`)**:
  - Columns: `id` (PK), `provider_id`, `model_id`, `display_name`, `type` (`API`|`Local`), `billing_mode`, `context_window`, `max_output_tokens`, `capabilities_json`, `tags_json`, `default_roles_json`, `description`, `deployment`, `quantization`, `enabled`, `discovered`, `source`, `created_at`, `updated_at`.
- **`CanonicalModelORM` (`canonical_models`)**:
  - Columns: `id` (PK), `vendor`, `family`, `canonical_name`, `revision`, `context_window`, `capabilities_json`, `tool_call_protocol`, `enabled`.
  - Relationship: Has many `ProviderModelBindingORM`.
- **`ProviderModelBindingORM` (`provider_model_bindings`)**:
  - Columns: `id` (PK), `canonical_model_id` (FK), `provider_id`, `provider_model_id`, `endpoint`, `priority`, `enabled`, `health`, `supports_streaming`, `supports_tools`, `last_429_at`, `cooldown_until`.
- **`RouteLockORM` (`route_locks`)**:
  - Columns: `id` (PK), `scope_type` (`session`|`task`|`workflow`), `scope_id`, `canonical_model_id` (FK), `policy_version`, `routing_snapshot_json`, `status`, `created_at`, `released_at`.
- **`RouteAttemptORM` (`route_attempts`)**:
  - Columns: `id` (PK, INT AUTO), `route_lock_id` (FK), `agent_session_id`, `turn_id`, `attempt_index`, `provider_binding_id`, `status`, `http_status`, `error_class`, `started_at`, `first_token_at`, `finished_at`, `prompt_tokens`, `completion_tokens`, `partial_artifact_id`.
- **`ModelRuntimeStatusORM` (`model_runtime_status`)**:
  - Columns: `model_id` (PK), `status`, `health`, `latency_p50_ms`, `latency_p90_ms`, `tokens_per_sec`, `success_rate`, `uptime_seconds`, `last_probe_at`, `last_error`.
- **`ProviderQuotaSnapshotORM` (`provider_quota_snapshots`)**:
  - Columns: `id` (PK, INT AUTO), `provider_id`, `quota_mode`, `rpm_limit`, `rpd_limit`, `tpm_limit`, `daily_token_limit`, `monthly_token_limit`, `remaining_requests_today`, `remaining_tokens_today`, `remaining_tokens_month`, `remaining_credit`, `credit_currency`, `reset_at`, `raw_json`, `source`, `created_at`.
- **`ModelRoutingRuleORM` (`model_routing_rules`)**:
  - Columns: `role` (PK), `name`, `description`, `primary_model_id` (FK), `fallback_model_id` (FK), `final_fallback_model_id` (FK), `status`, `priority`, `tags_json`, `policy_json`, `updated_at`.
- **`RouterExecutionLogORM` (`router_execution_logs`)**:
  - Columns: `id` (PK, INT AUTO), `role` (FK), `selected_model_id` (FK), `selection_tier`, `status`, `latency_ms`, `error_message`, `prompt_tokens`, `completion_tokens`, `estimated_cost`, `created_at`.

---

## 3. Service Layer Inventory (`apps/backend/services/`)

| Service File | Primary Responsibilities | Current Limitations |
| :--- | :--- | :--- |
| `provider_gateway.py` | Dispatching requests to legacy provider clients | Lacks unified protocol detection & discovery cache |
| `router_execution_service.py` | Model routing execution, policy tier evaluation, fallback handling | Evaluates fallback across different models (violates locked rule §1.3) |
| `router_policy.py` | Policy rule parsing and role-to-model mapping | Lacks V3 scope lock integration |
| `route_lock_service.py` | Creating and querying `RouteLockORM` | Basic CRUD; needs integration with `windagent_providers` |
| `model_service.py` | Model catalog CRUD, provider config CRUD, status updates | Tied to backend ORM directly |
| `quota_service.py` | Quota snapshot management | Hardcoded quota logic without vendor adapter integration |
| `model_client.py` | Direct HTTP calls to provider APIs | Ad-hoc payload transformations |
| `provider_clients/` | Provider transport drivers (`openai_compatible.py`, `anthropic.py`, `google_gemini.py`) | Scattered inside `apps/backend` instead of standalone package |

---

## 4. Provider Subsystem Package Inventory (`providers/windagent_providers/`)

Current implementation in `providers/windagent_providers`:
- `base.py`: Declares `BaseModelProvider`, `ProviderHealth`, `QuotaSnapshot`, `ModelChunk`.
- `capabilities.py`: Declares `ModelCapabilityProfile`.
- `adapters/openai_compatible.py`: Basic OpenAI protocol transport.
- `adapters/anthropic.py`: Basic Anthropic Messages protocol transport.
- `adapters/google_gemini.py`: Basic Google Gemini REST transport.
- `adapters/ollama.py`: Basic Ollama REST transport.
- `adapters/mock.py`: Test mock provider adapter.

---

## 5. Public API Inventory

### 5.1 Backend Routers (`apps/backend/routers/`)
- `GET /models`: List models in catalog.
- `POST /models/discover`: Model discovery endpoint.
- `GET /model-routing/rules`: Routing rules list.
- `POST /model-routing/rules`: Create/update routing rule.
- `GET /router-observability/logs`: Execution logs query.
- `POST /chat-completions`: OpenAI-compatible endpoint.

### 5.2 V2 API Routers (`apps/api/windagent_api/routers/`)
- `GET /v2/providers`: List V2 provider configs.
- `POST /v2/providers`: Save V2 provider config.

---

## 6. API Key Encryption & Security Inventory

- Encryption module: `apps/backend/utils/encryption.py`.
- Cipher: Fernet symmetric encryption with environment key `ENCRYPTION_KEY` or auto-generated key stored in key file.
- Encrypted values start with `enc:v1:`.
- `ModelProviderORM` validates and auto-encrypts `api_key` upon mutation via `@validates("api_key")`.

---

## 7. Baseline Test Suite Summary

- Total tests: 104 items (103 passed, 1 skipped).
- Provider test coverage:
  - `tests/unit/providers/test_provider_adapters.py`: Unit tests for `OpenAICompatibleProvider`, `AnthropicProvider`, `GoogleGeminiProvider`, `OllamaProvider`, and `MockProviderAdapter`.
  - `tests/unit/intelligence/test_model_router.py`: Unit tests for legacy model router.
- Coverage Status: Mock and scaffold tests exist, but full protocol detection, endpoint health cooldown, singleflight caching, and V3 strict failover require new test suites in Phase 1+.
