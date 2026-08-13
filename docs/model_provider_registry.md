# Model Provider Registry

Tài liệu mô tả hệ thống provider/model hiện tại của WindAgent (Provider
Subsystem V3). Nguồn chuẩn: `providers/windagent_providers/`.

## 1. Kiến trúc

- **Adapters**: mỗi provider một adapter riêng trong `providers/windagent_providers/<vendor>/adapter.py`,
  tuân theo `base/provider.py` + `base/contracts.py` (`DiscoveredModel`, capabilities).
- **Canonical Model Registry**: `registry/canonical_registry.py` —
  `CanonicalModelRegistryService` quản lý model canonical + endpoint binding.
  Production dùng SQL repository (`EndpointBindingRepositoryPort`); dev/test
  fallback in-memory (không dùng cho production).
- **Routing**: `routing/` định tuyến theo canonical model, equivalence level,
  fallback chain; `studio/capability_probe.py` probe năng lực provider.
- **Discovery**: snapshot discovery từ endpoint được đăng ký.

## 2. Danh sách provider adapters

| Adapter | Package | Ghi chú |
|---|---|---|
| Google Gemini | `providers/windagent_providers/google/` | Auth bằng header `x-goog-api-key` (không bao giờ qua query string). Env: `GOOGLE_API_KEY` / `GEMINI_API_KEY` |
| Ollama | `providers/windagent_providers/ollama/` | Local models; env `OLLAMA_BASE_URL`; hỗ trợ route không cần credential và stream structured output |
| OpenRouter | `providers/windagent_providers/openrouter/` | Gateway đa model |
| OpenAI | `providers/windagent_providers/openai/` | OpenAI-compatible |
| OpenAI-compatible | `providers/windagent_providers/openai_compatible/` | Generic OpenAI-compatible endpoint |
| Anthropic | `providers/windagent_providers/anthropic/` | Claude family |
| Mistral | `providers/windagent_providers/mistral/` | Mistral/Codestral |
| NVIDIA NIM | `providers/windagent_providers/nvidia/` | NIM hosted inference |
| Local | `providers/windagent_providers/local/` | Model chạy local |
| Assets | `providers/windagent_providers/assets/` | Asset gateway (`mesh_api.py`, `redaction.py`) |

API key được inject qua constructor adapter (composition root đọc từ env),
không hardcode trong code. Không expose key ra response/log (xem
`base/secret_redaction.py`, `core/windagent_core/security/redaction.py`).

## 3. Env vars chính

| Env | Mục đích |
|---|---|
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | Google Gemini auth (`x-goog-api-key`) |
| `OLLAMA_BASE_URL` | Base URL Ollama local |
| `WINDAGENT_DATABASE_URL` | Storage durable (canonical registry, events) |
| `WINDAGENT_STUDIO_CANONICAL_MODEL` | Canonical model cho Studio runtime |
| `WINDAGENT_STUDIO_MODEL_ROUTE` | Route cho Studio model calls |
| `WINDAGENT_STUDIO_RUNTIME` | Studio runtime mode (real/fake) |
| `WINDAGENT_BLENDER_ENGINE` / `WINDAGENT_BLENDER_EXECUTABLE` | Blender production engine |
| `WINDAGENT_ENV` | Environment mode |

## 4. API surface

- `GET /api/v2/providers` — danh sách provider (`ModelProviderInfo`)
- `GET /api/v2/providers/health` — health từng provider

## 5. Lưu ý

- Model pin/version: mô tả model cụ thể (tên, context window) tại
  `core/windagent_core/domain/types.py` + canonical registry; không hardcode
  snapshot model list vào tài liệu này vì nó thay đổi theo discovery.
- Provider đã gỡ (agentrouter, bluesminds, zenmux, nararouter, model registry
  cũ) không còn tồn tại trong code.
