# KẾ HOẠCH TRIỂN KHAI PROVIDER ROUTING V3 CHO WINDAGENT

## 0. Nhiệm vụ tổng quát

Tiếp tục phát triển repository:

```text
WindFaculty/WindAgent
```

Bắt đầu chính xác từ commit:

```text
59aaea22339d26ec9b10dcf398e4380f65f656ba
```

Xây dựng lại provider subsystem bằng cách:

1. Khai thác phần router/provider đang tồn tại trong `apps/backend`.
2. Di chuyển và chuẩn hóa logic vào package `providers/windagent_providers`.
3. Thiết kế lại schema provider/model/routing.
4. Hoàn thiện adapter thật cho:

   * OpenAI;
   * Anthropic;
   * Google;
   * NVIDIA;
   * OpenRouter;
   * Mistral;
   * Ollama;
   * local Ollama servers.
5. Bổ sung nhận diện endpoint và protocol khi người dùng nhấn **Test Connect**.
6. Chọn canonical model theo rule ở lượt đầu.
7. Khóa model cho toàn bộ session/task/workflow.
8. Khi endpoint gặp 429 hoặc lỗi khả dụng, chuyển sang endpoint khác cung cấp đúng cùng canonical model.
9. Không âm thầm đổi model.
10. Quản lý route cache, endpoint state cache, discovery cache và response cache an toàn.

---

# 1. Các quyết định kiến trúc đã khóa

Không thay đổi các quyết định sau nếu chưa có bằng chứng kỹ thuật rõ ràng và chưa ghi chúng vào báo cáo:

## 1.1 Model selection

Ở lần gọi đầu tiên của một scope:

```text
task/session/workflow label
    → routing rule
    → canonical model
    → persistent route lock
```

Các lượt sau phải đọc `route_lock`.

Không chạy lại model selection ở mỗi lượt.

## 1.2 Endpoint selection

Sau khi canonical model đã khóa:

```text
canonical model
    → exact-equivalent endpoint bindings
    → endpoint health/quota/circuit filtering
    → endpoint scoring
    → execute
```

Endpoint được phép thay đổi.

Canonical model không được thay đổi chỉ vì endpoint lỗi.

## 1.3 Failover

Failover tự động chỉ hợp lệ khi:

```text
binding.canonical_model_id giống nhau
binding.model_revision giống nhau
binding.equivalence_level == exact_revision
binding.enabled == true
endpoint không bị cooldown/open circuit
```

Khi toàn bộ endpoint của model đã khóa không dùng được, trả lỗi:

```text
SameModelEndpointExhausted
```

Không silent fallback sang model khác hoặc mock model.

## 1.4 Test Connect

Khi người dùng nhấn Test Connect:

* dùng provider do người dùng chọn làm hint;
* tự nhận diện protocol và vendor;
* cho phép manual override;
* trả confidence và evidence;
* không lưu credential trước khi người dùng xác nhận lưu;
* không thay đổi route lock hoặc runtime routing state.

## 1.5 Local provider

`local/` chỉ quản lý server Ollama local hoặc LAN.

Không triển khai:

* Transformers inference trực tiếp;
* llama.cpp trực tiếp trong process;
* GGUF loader trực tiếp;
* vLLM lifecycle trong phase này.

## 1.6 Storage boundary

`windagent_providers` không được import:

* SQLAlchemy ORM;
* FastAPI;
* `apps`;
* orchestration;
* intelligence;
* storage implementations.

Provider package chỉ khai báo contract/port và thực hiện protocol transport.

ORM, repository, Redis và transaction implementation phải nằm trong storage hoặc application composition layer.

---

# 2. Quy tắc thực hiện toàn cục

## 2.1 Git

Trước khi sửa mã:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git show --stat --oneline 59aaea22339d26ec9b10dcf398e4380f65f656ba
```

Yêu cầu:

```text
STARTING_SHA == 59aaea22339d26ec9b10dcf398e4380f65f656ba
```

Tạo branch mới:

```text
feat/provider-routing-v3
```

Không force-push.

Không rewrite commit nền.

Không merge vào `main` trong quá trình thực hiện.

Mỗi phase phải có ít nhất một commit logic riêng.

## 2.2 Thứ tự phase

Không được làm nhiều phase trong một commit lớn.

Không sang phase sau khi acceptance gate của phase hiện tại chưa pass.

Trạng thái phase chỉ có thể là:

```text
PASSED
FAILED
BLOCKED
PARTIAL_NOT_ELIGIBLE_FOR_PROMOTION
```

Không dùng từ “completed” nếu mới chỉ scaffold.

## 2.3 Không tạo implementation giả

Production adapter không được:

* trả response hard-coded;
* trả danh sách model tĩnh như dữ liệu runtime;
* đánh dấu health dựa trên `bool(api_key)`;
* trả `cancel=True` khi không thực sự hỗ trợ;
* mặc định quota còn đủ khi không biết;
* silent fallback sang mock;
* giả lập stream bằng cách chia response hoàn chỉnh thành các đoạn ký tự;
* tạo latency giả;
* tạo evaluation score giả.

Mock adapter chỉ được dùng trong test hoặc development fixture, phải có tên và namespace rõ ràng.

## 2.4 Kiểm thử

Dùng HTTP mock server hoặc `httpx.MockTransport` để test protocol.

Không gọi API trả phí trong unit test.

Live smoke test phải:

* bị skip mặc định;
* yêu cầu explicit environment flag;
* không ghi secret vào log;
* không phải acceptance gate bắt buộc cho CI thông thường.

## 2.5 Secret

Không đưa API key vào:

* exception;
* log;
* snapshot;
* fixture;
* report;
* Git diff;
* response body;
* artifact JSON.

API key phải được mã hóa at rest và được scrub khỏi URL/header/raw payload.

## 2.6 Migration

Schema migration phải có:

* upgrade;
* dữ liệu backfill;
* validation;
* rollback hoặc downgrade strategy;
* migration receipt;
* orphan audit;
* duplicate audit;
* secret audit.

Không xóa bảng cũ trước khi parity và cutover pass.

---

# 3. Cấu trúc mục tiêu

```text
providers/
├── pyproject.toml
├── README.md
└── windagent_providers/
    ├── __init__.py
    ├── base/
    │   ├── contracts.py
    │   ├── requests.py
    │   ├── responses.py
    │   ├── streaming.py
    │   ├── capabilities.py
    │   ├── protocols.py
    │   ├── errors.py
    │   ├── auth.py
    │   ├── rate_limits.py
    │   ├── usage.py
    │   ├── cache_directives.py
    │   └── transport.py
    ├── detection/
    │   ├── detector.py
    │   ├── probe_plan.py
    │   ├── fingerprints.py
    │   ├── evidence.py
    │   └── test_connection.py
    ├── registry/
    │   ├── provider_registry.py
    │   ├── endpoint_registry.py
    │   ├── adapter_factory.py
    │   ├── model_normalizer.py
    │   └── binding_resolver.py
    ├── routing/
    │   ├── endpoint_candidate.py
    │   ├── endpoint_selector.py
    │   ├── failover_policy.py
    │   ├── circuit_breaker.py
    │   ├── cooldown.py
    │   └── execution_coordinator.py
    ├── cache/
    │   ├── contracts.py
    │   ├── keys.py
    │   ├── discovery_cache.py
    │   ├── health_cache.py
    │   ├── route_cache.py
    │   ├── response_cache.py
    │   └── singleflight.py
    ├── openai/
    ├── anthropic/
    ├── google/
    ├── nvidia/
    ├── openrouter/
    ├── mistral/
    ├── ollama/
    └── local/
```

Không bắt buộc tạo mọi file ngay từ Phase 1. Chỉ tạo file khi có contract hoặc implementation thực.

---

# PHASE 0 — BASELINE, INVENTORY VÀ MIGRATION MAP

## Mục tiêu

Xác định chính xác phần nào của router/provider cũ sẽ được:

* tái sử dụng;
* di chuyển;
* viết lại;
* loại bỏ sau cutover.

Không thay đổi production behavior trong phase này.

## Phạm vi cần đọc

Tối thiểu:

```text
providers/windagent_providers/
apps/backend/services/provider_gateway.py
apps/backend/services/router_execution_service.py
apps/backend/services/router_policy.py
apps/backend/services/quota_service.py
apps/backend/services/model_service.py
apps/backend/db/models.py
apps/backend/routers/
apps/api/
storage/
tests/
pyproject.toml
```

Tìm thêm các file liên quan bằng `rg`:

```bash
rg -n "ModelProvider|ModelCatalog|CanonicalModel|ProviderModelBinding"
rg -n "RouteLock|RouteAttempt|RoutingRule"
rg -n "provider_gateway|router_policy|quota_service"
rg -n "OpenAICompatible|AnthropicProvider|GeminiProvider|OllamaProvider"
rg -n "WINDAGENT_V2_PROVIDERS"
```

## Công việc

1. Lập inventory toàn bộ:

   * schema;
   * endpoint CRUD;
   * provider adapters;
   * quota;
   * health;
   * discovery;
   * routing rules;
   * execution logs;
   * API key handling;
   * public API.
2. Tạo migration map:

```text
old component
new component
reuse/migrate/replace/delete
reason
dependency
risk
test coverage
```

3. Ghi baseline test hiện tại.
4. Xác định test nào chỉ đang kiểm tra scaffold/mock.
5. Xác định toàn bộ API provider/router hiện có.
6. Tạo tài liệu:

```text
docs/providers/provider_v3_inventory.md
docs/providers/provider_v3_migration_map.md
docs/providers/provider_v3_architecture_decisions.md
```

7. Sửa receipt Phase 14 nếu receipt đang tuyên bố cutover hoàn tất nhưng execution path chưa thật sự được cutover. Không xóa lịch sử; tạo correction receipt mới.

## Không được làm

* Không đổi schema.
* Không đổi execution path.
* Không tạo adapter mới.
* Không xóa legacy code.
* Không bật provider V3 flag.

## Acceptance gate

```text
[ ] Starting SHA được xác minh
[ ] Worktree ban đầu sạch hoặc thay đổi có sẵn được ghi nhận
[ ] Inventory provider/router đầy đủ
[ ] Có old-to-new migration map
[ ] Có API parity inventory
[ ] Có baseline test receipt
[ ] Không thay đổi runtime behavior
[ ] Không có secret trong artifact
```

## Commit

```text
docs(providers): inventory legacy router and define provider v3 migration map
```

---

# PHASE 1 — PROVIDER CONTRACT FOUNDATION

## Mục tiêu

Hoàn thiện contract chung trước khi triển khai adapter.

## Công việc

Tạo hoặc chuẩn hóa:

```text
ProviderRequest
ProviderResponse
ProviderStreamEvent
ProviderUsage
ProviderHealth
QuotaState
RateLimitState
ConnectionTestResult
ProtocolDetectionResult
ProviderCapabilities
ModelDescriptor
DiscoveredModel
CacheDirective
ProviderFailure
```

## Request contract phải hỗ trợ

* messages;
* system instruction;
* temperature;
* top-p;
* seed;
* max output tokens;
* stop sequences;
* tools;
* tool choice;
* structured output;
* image/multimodal parts;
* provider extensions;
* request ID;
* idempotency key;
* timeout/deadline;
* cache directive;
* cancellation.

## Response contract phải hỗ trợ

* canonical model ID;
* provider model ID;
* endpoint ID;
* text;
* tool calls;
* structured output;
* finish reason;
* prompt tokens;
* completion tokens;
* cached tokens;
* reasoning tokens;
* provider request ID;
* first-token latency;
* total latency;
* cost metadata;
* scrubbed raw metadata.

## Error taxonomy bắt buộc

```text
AuthenticationFailure
PermissionFailure
RateLimitFailure
QuotaExhaustedFailure
ModelNotFoundFailure
InvalidRequestFailure
ContextOverflowFailure
ContentPolicyFailure
ProviderUnavailableFailure
NetworkFailure
TimeoutFailure
ProtocolMismatchFailure
MalformedResponseFailure
CancellationFailure
SameModelEndpointExhausted
```

## Port interfaces

Khai báo interface cho:

```text
EndpointRegistryPort
CanonicalModelRegistryPort
RouteLockPort
RouteAttemptPort
QuotaStatePort
EndpointStatePort
CachePort
UsageLedgerPort
```

Không viết SQL implementation trong package provider.

## Tests

* request validation;
* response normalization;
* error serialization;
* secret redaction;
* stream event ordering;
* finish reason normalization;
* capability matching;
* dependency/import boundary.

## Acceptance gate

```text
[ ] Contract 100% type-annotated
[ ] mypy/pyright hoặc project typecheck pass
[ ] Provider package không import ORM/FastAPI/apps
[ ] Error taxonomy không dựa vào string matching ở application layer
[ ] Public exports rõ ràng
[ ] Contract test pass
[ ] Architecture import check pass
```

## Commit

```text
feat(providers): establish provider v3 contracts and normalized error model
```

---

# PHASE 2 — SCHEMA V3 VÀ REPOSITORY LAYER

## Mục tiêu

Thiết kế lại schema mà không làm mất provider configuration hiện có.

## Schema mới

Tạo các bảng:

```text
provider_vendors
provider_credentials
provider_endpoints
canonical_models
endpoint_model_bindings
model_routing_rules_v3
route_locks
route_attempts
endpoint_runtime_state
endpoint_health_samples
endpoint_rate_limit_windows
provider_quota_snapshots_v3
provider_usage_ledger
model_discovery_snapshots
response_cache_entries
```

## Yêu cầu quan trọng

### `provider_credentials`

* tách credential khỏi endpoint;
* mã hóa at rest;
* có secret version;
* hỗ trợ env reference;
* hỗ trợ nhiều key cho một vendor;
* không trả ciphertext ra API.

### `provider_endpoints`

Phải chứa tối thiểu:

```text
vendor_id
credential_id
base_url
protocol_mode
configured_protocol
detected_protocol
protocol_confidence
region
priority
weight
enabled
test_status
last_tested_at
```

### `canonical_models`

Đại diện model logic mà session khóa.

### `endpoint_model_bindings`

Phải có:

```text
endpoint_id
canonical_model_id
provider_model_id
model_revision
equivalence_level
equivalence_fingerprint
capabilities
pricing overrides
enabled
priority
```

### `route_locks`

Phải có unique active lock cho:

```text
scope_type + scope_id
```

Việc tạo lock phải atomic.

## Migration

1. Tạo migration mới, không sửa migration cũ đã chạy.
2. Backfill provider cũ.
3. Backfill model catalog.
4. Backfill canonical model và bindings.
5. Backfill routing rules nếu ánh xạ được.
6. Ghi các record không ánh xạ được vào migration report.
7. Không tự động gộp model khi confidence thấp.
8. Giữ bảng cũ phục vụ rollback/parity.

## Repository

Triển khai repository SQL trong storage/application layer, không trong providers package.

## Tests

* empty database upgrade;
* populated legacy database upgrade;
* duplicate endpoint;
* duplicate binding;
* encrypted credential;
* one active lock constraint;
* concurrent lock creation;
* downgrade hoặc documented rollback;
* deterministic backfill;
* orphan audit.

## Acceptance gate

```text
[ ] Migration upgrade pass
[ ] Legacy populated DB migration pass
[ ] Credential plaintext count == 0
[ ] Orphan endpoint bindings == 0
[ ] Duplicate active route locks == 0
[ ] Backfill deterministic
[ ] Legacy tables chưa bị xóa
[ ] Repository contract tests pass
```

## Commit

```text
feat(storage): add provider v3 schema repositories and legacy backfill
```

---

# PHASE 3 — OPENAI-COMPATIBLE TRANSPORT CORE

## Mục tiêu

Tạo transport thật dùng chung cho:

* OpenAI;
* OpenRouter;
* NVIDIA NIM;
* Mistral OpenAI-compatible;
* custom OpenAI-compatible endpoint.

## Công việc

Triển khai:

* shared `httpx.AsyncClient` lifecycle;
* connection pooling;
* connect/read/write/total timeout;
* request codec;
* response codec;
* SSE parser;
* fragmented SSE handling;
* multiline data event;
* tool-call delta accumulation;
* structured output;
* usage metadata;
* rate-limit headers;
* request ID extraction;
* error normalization;
* secret scrubber;
* model discovery;
* health probe;
* cancellation semantics;
* retry-safe execution.

## Adapter riêng

Tạo thin adapter cho:

```text
openai/
openrouter/
nvidia/
mistral/
```

Mỗi adapter override đúng phần vendor-specific:

* header;
* auth;
* model endpoint;
* completion endpoint;
* provider metadata;
* error shape;
* rate-limit headers;
* extra request fields.

Không copy toàn bộ transport vào từng adapter.

## Tests

Dùng mock HTTP server để kiểm tra:

* non-stream success;
* stream success;
* fragmented chunks;
* tool calls;
* structured output;
* 401;
* 403;
* 404 model;
* 429 + Retry-After;
* 500/502/503/504;
* malformed JSON;
* malformed SSE;
* timeout;
* cancellation;
* secret redaction.

## Acceptance gate

```text
[ ] Bốn provider adapter dùng shared transport
[ ] Không có production response hard-coded
[ ] Streaming parser chịu được chunk fragmentation
[ ] Tool calls normalize chính xác
[ ] 429 normalize thành RateLimitFailure
[ ] Health probe thực hiện network call thật
[ ] Model discovery dùng endpoint thật
[ ] Không silent mock fallback
[ ] Contract suite pass cho từng adapter
```

## Commit

```text
feat(providers): implement openai-compatible transport and vendor adapters
```

---

# PHASE 4 — NATIVE ANTHROPIC, GOOGLE VÀ OLLAMA ADAPTERS

## Mục tiêu

Triển khai native protocol thay vì ép toàn bộ qua OpenAI-compatible.

## Anthropic

Triển khai:

* Messages API mapping;
* system instruction;
* content blocks;
* tool use;
* tool result;
* stream events;
* usage;
* prompt cache metadata;
* rate-limit headers;
* normalized errors;
* model discovery phù hợp API hiện tại.

## Google

Triển khai:

* Generate Content mapping;
* content/parts;
* system instruction;
* function declarations;
* function calls;
* multimodal parts;
* streaming;
* usage;
* safety metadata;
* model discovery;
* normalized errors.

## Ollama

Triển khai:

* `/api/tags`;
* `/api/chat`;
* native streaming;
* keep-alive;
* model availability;
* health;
* local latency;
* tokens/sec nếu tính được;
* timeout/cancellation;
* tool support theo capability thực tế.

## `local/`

Triển khai:

* localhost Ollama endpoint;
* LAN Ollama endpoint;
* reachability probe;
* endpoint resource metadata;
* nhiều Ollama server;
* không khởi chạy model bằng Python.

## Tests

* native request shape;
* native streaming event;
* tool-call conversion;
* model discovery;
* unavailable Ollama;
* malformed Ollama stream;
* Google safety response;
* Anthropic tool-use sequence;
* cancellation;
* timeouts.

## Acceptance gate

```text
[ ] Anthropic generate/stream thật
[ ] Google generate/stream thật
[ ] Ollama generate/stream thật
[ ] Ollama health fail khi server không tồn tại
[ ] Model list không hard-coded
[ ] Tool calls normalize về contract chung
[ ] Native usage metadata được giữ
[ ] Contract suite pass cho từng adapter
```

## Commit

```text
feat(providers): implement native anthropic google and ollama adapters
```

---

# PHASE 5 — TEST CONNECT VÀ PROTOCOL DETECTION

## Mục tiêu

Nhận diện endpoint khi người dùng nhấn Test Connect.

## Input

```text
base_url
credential tạm thời
selected provider hoặc Auto
manual protocol override tùy chọn
```

## Probe plan

Thực hiện theo giới hạn và ưu tiên:

1. URL normalization.
2. DNS/TCP/TLS reachability.
3. Ollama fingerprint.
4. Anthropic native fingerprint.
5. Google native fingerprint.
6. OpenAI-compatible models endpoint.
7. OpenRouter/NVIDIA/Mistral vendor fingerprint.
8. Minimal completion chỉ khi cần và được phép.

## Output

```json
{
  "connected": true,
  "detected_vendor": "openrouter",
  "detected_protocol": "openai_chat_completions",
  "confidence": 0.96,
  "auth_valid": true,
  "model_discovery_supported": true,
  "models_found": 100,
  "evidence": [],
  "warnings": []
}
```

## API/application use cases

Triển khai use case và API cho:

```text
test connection
preview detected configuration
save provider endpoint
refresh discovered models
manual protocol override
```

Không để FastAPI router chứa business logic detection.

## Security

* credential test chỉ tồn tại trong memory;
* không persist trước Save;
* không echo secret;
* giới hạn redirect;
* chống SSRF;
* chặn metadata endpoints;
* chặn file URL;
* cấu hình rõ chính sách localhost/LAN;
* timeout cứng;
* giới hạn response body.

## Acceptance gate

```text
[ ] Nhận diện được Ollama
[ ] Nhận diện được Anthropic native
[ ] Nhận diện được Google native
[ ] Nhận diện được OpenAI-compatible
[ ] Có vendor fingerprint cho OpenRouter/NVIDIA/Mistral
[ ] Manual override hoạt động
[ ] Protocol mismatch trả warning
[ ] SSRF test pass
[ ] Credential không được persist khi chỉ Test Connect
[ ] Timeout và body limit hoạt động
```

## Commit

```text
feat(providers): add safe endpoint detection and test-connect workflow
```

---

# PHASE 6 — CANONICAL MODEL REGISTRY VÀ EQUIVALENCE

## Mục tiêu

Định nghĩa chính xác điều kiện “cùng model” trước khi endpoint failover.

## Công việc

* model ID normalization;
* alias handling;
* vendor/family/revision extraction;
* canonical matching;
* equivalence fingerprint;
* discovery snapshot;
* merge/split binding workflow;
* manual review khi confidence thấp;
* capability reconciliation;
* pricing reconciliation;
* context window validation;
* tool protocol validation.

## Equivalence levels

```text
exact_revision
exact_family_floating_revision
compatible_alias
approximate
unknown
```

Automatic failover chỉ dùng:

```text
exact_revision
```

Không tự động gộp:

* model khác revision;
* model quantization khác;
* model distillation khác;
* model context configuration khác khi ảnh hưởng hành vi;
* alias không đủ bằng chứng.

## Tests

* same model via two endpoints;
* same family but different revision;
* aliases;
* discovery rerun;
* duplicate prevention;
* manual split;
* manual merge;
* fingerprint stability;
* unsupported capability mismatch.

## Acceptance gate

```text
[ ] Exact-equivalent bindings được nhận diện
[ ] Different revision không được đánh dấu exact
[ ] Discovery rerun không tạo duplicate
[ ] Có audit trail merge/split
[ ] Binding confidence thấp không auto-merge
[ ] Failover candidate query chỉ trả exact bindings
```

## Commit

```text
feat(providers): add canonical model registry and binding equivalence
```

---

# PHASE 7 — RULE SELECTION VÀ STICKY ROUTE LOCK

## Mục tiêu

Rule chọn model một lần, sau đó duy trì model trong toàn scope.

## Input cho rule matcher

* task label;
* agent type;
* workflow type;
* required capabilities;
* estimated context;
* tool requirement;
* vision requirement;
* user-selected preference;
* cost class;
* privacy/local requirement.

## Luồng

```text
request
    → lookup active route lock
        → found: reuse canonical model
        → not found:
            evaluate enabled rules
            choose canonical model
            atomically create route lock
```

## Yêu cầu

* rule có version;
* route lock lưu routing snapshot;
* sửa rule không tác động lock cũ;
* process restart vẫn đọc được lock;
* concurrency-safe;
* explicit unlock;
* explicit model reselection;
* không fallback sang model khác khi endpoint lỗi.

## Events

Ghi tối thiểu:

```text
ModelSelected
RouteLocked
RouteReused
RouteReleased
ModelReselectionRequested
ModelReselected
```

## Tests

* 100 turns cùng session;
* concurrent first requests;
* restart simulation;
* rule update during active session;
* explicit unlock;
* explicit reselect;
* missing matching rule;
* disabled canonical model;
* insufficient capability.

## Acceptance gate

```text
[ ] Một scope chỉ có một active lock
[ ] 100 turns giữ cùng canonical model
[ ] Concurrent first calls không tạo hai model locks
[ ] Restart không làm mất affinity
[ ] Rule update không đổi lock hiện tại
[ ] Không silent model fallback
[ ] Reselection có event và reason
```

## Commit

```text
feat(routing): implement first-turn model selection and persistent route locks
```

---

# PHASE 8 — ENDPOINT FAILOVER, QUOTA VÀ CIRCUIT BREAKER

## Mục tiêu

Chuyển endpoint khi 429/lỗi khả dụng nhưng giữ nguyên canonical model.

## Candidate pipeline

```text
bindings của canonical model
    → exact revision only
    → enabled
    → capability-compatible
    → credential valid
    → health acceptable
    → quota available
    → not in cooldown
    → circuit not open
    → endpoint score
```

## Endpoint score

Cân nhắc:

* health;
* quota;
* configured priority;
* configured weight;
* latency;
* recent success rate;
* cost;
* region;
* recent 429;
* circuit state.

Điểm endpoint không được dùng để chọn model khác.

## Retry policy

### 429

* parse `Retry-After`;
* parse provider rate-limit headers;
* cập nhật cooldown;
* ghi route attempt;
* chuyển endpoint exact-equivalent.

### 5xx

* tăng failure count;
* circuit breaker;
* chuyển endpoint khi retry policy cho phép.

### 401/403

* credential invalid;
* không retry vô hạn;
* có thể thử binding dùng credential khác nếu cùng model.

### 404 model

* đánh dấu binding stale/unavailable;
* yêu cầu rediscovery.

### 400/422

* mặc định không failover;
* phân loại lỗi request.

### Context overflow

* trả về orchestration để compact/truncate theo policy;
* không chuyển endpoint mù.

### Partial streaming

Nếu đã phát token ra client:

* không nối stream endpoint B vào endpoint A một cách im lặng;
* ghi partial failure;
* kết thúc stream bằng error event;
* retry chỉ được tạo generation mới với attempt ID mới và contract rõ ràng.

## Distributed state

Cooldown, quota reservation và circuit state phải có backend hỗ trợ nhiều process.

Development có memory implementation.

Production dùng Redis hoặc storage atomic tương đương.

## Tests bắt buộc

### Kịch bản chính

```text
Endpoint A → HTTP 429
Endpoint B → success
Canonical model → unchanged
Route lock → unchanged
Attempt 1 → rate_limited
Attempt 2 → success
Endpoint A → cooldown
```

### Kịch bản bổ sung

* endpoint A timeout, B success;
* endpoint A 503, B success;
* all endpoints exhausted;
* 401 key A, credential B success;
* 400 no failover;
* partial stream failure;
* circuit open;
* half-open recovery;
* quota race;
* multi-process cooldown visibility.

## Acceptance gate

```text
[ ] 429 failover cùng model pass
[ ] Canonical model không đổi
[ ] Route lock không đổi
[ ] Attempt audit đầy đủ
[ ] Không duplicate billing ngoài retry contract
[ ] Circuit breaker pass
[ ] Distributed cooldown pass
[ ] 400 không bị retry mù
[ ] Partial streaming policy pass
[ ] All exhausted trả SameModelEndpointExhausted
```

## Commit

```text
feat(routing): add same-model endpoint failover quota and circuit breaker
```

---

# PHASE 9 — CACHE VÀ SINGLEFLIGHT

## Mục tiêu

Thêm cache mà không phá model affinity hoặc cô lập dữ liệu.

## Cache layers

### Route lock cache

```text
route-lock:{scope_type}:{scope_id}
```

Database là source of truth.

Cache miss phải đọc database trước khi tạo model selection mới.

### Endpoint state cache

```text
endpoint-health:{endpoint_id}
endpoint-cooldown:{endpoint_id}
endpoint-circuit:{endpoint_id}
endpoint-quota:{endpoint_id}
```

### Discovery cache

```text
models:{endpoint_id}:{credential_version}:{protocol_version}
```

### Response cache

Chỉ opt-in.

Key phải chứa:

```text
tenant/user namespace
canonical model
revision
normalized messages hash
system hash
tool schema hash
structured output hash
temperature
top_p
seed
max output tokens
provider behavior version
```

### Provider-native cache

Dùng `CacheDirective` để adapter tự ánh xạ.

## Không response-cache mặc định

* browser/computer use;
* tool có side effect;
* realtime research;
* file tạm;
* high-temperature without seed;
* approximate model binding;
* request chứa secret;
* request phụ thuộc mutable external state.

## Singleflight

Áp dụng cho:

* model discovery;
* health probes;
* identical cacheable requests;
* quota refresh.

Không dùng singleflight cho side-effecting tool flows.

## Tests

* cache isolation giữa user;
* credential rotation invalidation;
* model revision invalidation;
* tool schema invalidation;
* system prompt invalidation;
* cache backend unavailable;
* Redis concurrency;
* singleflight collapse;
* route cache stale recovery;
* no caching side-effect tool request.

## Acceptance gate

```text
[ ] Không cache chéo tenant/user
[ ] DB vẫn là source of truth cho route lock
[ ] Credential rotation invalidates discovery cache
[ ] Model revision change causes miss
[ ] Tool schema change causes miss
[ ] Side-effect requests không response-cache
[ ] Cache backend down không làm provider execution down
[ ] Singleflight concurrency test pass
```

## Commit

```text
feat(providers): add safe provider caches and distributed singleflight
```

---

# PHASE 10 — TÍCH HỢP PROVIDER V3 VÀO ROUTER/GATEWAY

## Mục tiêu

Thay execution path cũ bằng provider V3 theo strangler pattern có rollback.

## Execution path mục tiêu

```text
ProviderGateway
    → ModelRouteCoordinator
        → read/create route lock
        → canonical model
    → EndpointExecutionCoordinator
        → resolve exact bindings
        → filter health/quota/circuit
        → choose endpoint
        → adapter factory
        → execute
        → same-model failover
    → normalized response/stream
```

## Công việc

1. Provider gateway không truy vấn ORM trực tiếp.
2. Router policy cũ không còn là production model selector.
3. OpenAI-compatible public API dùng coordinator mới.
4. Agent runtime adapters dùng coordinator mới.
5. Provider/model CRUD dùng schema V3.
6. Test Connect dùng detection service mới.
7. Giữ compatibility API khi cần.
8. Tạo feature flags độc lập:

```text
WINDAGENT_PROVIDER_V3_READ
WINDAGENT_PROVIDER_V3_WRITE
WINDAGENT_PROVIDER_V3_TEST_CONNECT
WINDAGENT_PROVIDER_V3_EXECUTE
WINDAGENT_PROVIDER_V3_ROUTE_LOCK
WINDAGENT_PROVIDER_V3_CACHE
```

Mặc định flag mới phải `false` cho đến khi gate pass.

Không chỉ kiểm tra master `WINDAGENT_ARCH_V2`.

## Rollout

```text
read V3
→ write V3
→ Test Connect V3
→ route lock V3
→ execution V3
→ cache V3
```

Mỗi bước có rollback riêng.

## Shadow/parity

* shadow read-only CRUD/list operations;
* không shadow request trả phí;
* destructive skip không được tính là parity pass;
* async comparator phải hỗ trợ awaitable;
* parity report phải phân biệt:

  * matched;
  * mismatched;
  * skipped;
  * not tested.

## Tests

* non-stream chat;
* streaming;
* tool use;
* structured output;
* coding agent;
* research agent;
* Ollama local;
* 429 failover;
* restart recovery;
* API compatibility;
* flags rollback;
* DB parity;
* no direct legacy ORM execution path.

## Acceptance gate

```text
[ ] Public gateway dùng provider V3 khi flag bật
[ ] Rollback về legacy hoạt động
[ ] Non-stream pass
[ ] Streaming pass
[ ] Tool call pass
[ ] Ollama pass
[ ] 429 same-model failover pass
[ ] Route lock restart recovery pass
[ ] Skipped shadow operation không tính parity pass
[ ] Provider V3 flags hoạt động độc lập
```

## Commit

```text
feat(migration): integrate provider v3 routing behind granular cutover flags
```

---

# PHASE 11 — HARDENING, CI, CUTOVER VÀ LEGACY DECOMMISSION

## Mục tiêu

Chứng minh subsystem đủ điều kiện production cutover.

## Fault injection

Tạo test cho:

* 429;
* timeout;
* DNS failure;
* TLS failure;
* malformed JSON;
* malformed SSE;
* truncated stream;
* 401/403;
* 404 model;
* 500/502/503/504;
* quota exhaustion;
* circuit open;
* cache backend down;
* database restart;
* process restart;
* concurrent route creation;
* credential rotation;
* partial stream failure.

## Observability

Metrics tối thiểu:

```text
provider requests
route attempts
endpoint selection
endpoint failover
model reselection
429 count
circuit state
quota usage
cache hit/miss
first-token latency
total latency
token usage
estimated cost
provider errors by class
```

Không đưa secret hoặc full prompt vào metric label.

## CI

Tạo CI thực sự chạy:

* formatting;
* lint;
* typing;
* architecture boundaries;
* provider contract tests;
* adapter tests;
* migration tests;
* security tests;
* integration tests;
* root test suite;
* legacy regression;
* build nếu bị ảnh hưởng.

Root test configuration không được bỏ qua legacy/provider integration một cách âm thầm.

## Cutover

Chỉ thực hiện khi toàn bộ gate pass:

1. Bật provider V3 read.
2. Bật provider V3 write.
3. Bật route lock.
4. Bật execution cho canary.
5. Theo dõi error/failover/cache.
6. Mở rộng rollout.
7. Giữ rollback trong ít nhất một migration release boundary.
8. Sau parity mới xóa hoặc archive legacy provider execution code.

Không xóa encryption compatibility trước khi credential migration được xác minh.

## Final acceptance matrix

```text
PROVIDER_V3_CONTRACTS_PASS
SCHEMA_MIGRATION_PASS
LEGACY_BACKFILL_PASS
REAL_ADAPTERS_PASS
TEST_CONNECT_PASS
PROTOCOL_DETECTION_PASS
CANONICAL_MODEL_EQUIVALENCE_PASS
MODEL_AFFINITY_PASS
CONCURRENT_ROUTE_LOCK_PASS
SAME_MODEL_429_FAILOVER_PASS
CIRCUIT_BREAKER_PASS
QUOTA_RESERVATION_PASS
CACHE_ISOLATION_PASS
STREAMING_PASS
TOOL_USE_PASS
OLLAMA_LOCAL_PASS
RESTART_RECOVERY_PASS
NO_SECRET_LEAK_PASS
LEGACY_API_PARITY_PASS
ROLLBACK_PASS
FULL_CI_PASS
```

Nếu bất kỳ gate nào chưa pass, verdict không được là accepted/cutover complete.

## Commit

```text
feat(providers): harden provider v3 and complete verified cutover
```

---

# 4. Test strategy tổng thể

## Unit tests

* codecs;
* error normalization;
* capability matching;
* endpoint scoring;
* retry policy;
* cache key;
* fingerprint;
* equivalence;
* circuit state.

## Contract tests

Một bộ contract suite dùng lại cho mọi adapter:

```text
list_models
health
generate
stream
tools
usage
rate limits
errors
cancellation
secret redaction
```

## Integration tests

* mock HTTP providers;
* real database;
* Redis-compatible test backend;
* API → coordinator → adapter → normalized response;
* restart recovery.

## Optional live tests

Chỉ chạy khi:

```text
WINDAGENT_RUN_LIVE_PROVIDER_TESTS=1
```

Từng provider yêu cầu secret riêng.

Không fail CI mặc định vì thiếu live credentials.

## Regression tests

Chạy cả:

* V2 root tests;
* provider V3 tests;
* legacy backend focused tests;
* router tests;
* API compatibility tests.

---

# 5. Báo cáo bắt buộc sau mỗi phase

Sau mỗi phase, Antigravity phải xuất báo cáo theo mẫu:

```text
PHASE:
VERDICT:

REPOSITORY:
STARTING_BRANCH:
STARTING_SHA:
FINAL_BRANCH:
FINAL_SHA:
REMOTE_SHA_MATCH:
WORKTREE_CLEAN:

OBJECTIVE:
COMPLETED:
NOT_COMPLETED:
BLOCKERS:

FILES_ADDED:
FILES_MODIFIED:
FILES_DELETED:

SCHEMA_CHANGES:
MIGRATION_RESULT:

TEST_COMMANDS:
TEST_RESULTS:
TYPECHECK:
LINT:
ARCHITECTURE_CHECK:
SECURITY_CHECK:

ACCEPTANCE_GATES:
- gate: PASS/FAIL/BLOCKED
- gate: PASS/FAIL/BLOCKED

KNOWN_LIMITATIONS:
RISKS:
ROLLBACK_PATH:

COMMITS:
PR:
NEXT_PHASE_ELIGIBLE: YES/NO
```

Không được chỉ báo cáo tổng số test.

Phải ghi chính xác lệnh đã chạy, số pass/fail/skip và test nào chưa chạy.

---

# 6. Artifact bắt buộc

Lưu artifact theo phase:

```text
artifacts/provider_v3/phase_00/
artifacts/provider_v3/phase_01/
...
artifacts/provider_v3/phase_11/
```

Mỗi phase tối thiểu có:

```text
phase_receipt.json
test_receipt.json
changed_files.json
acceptance_matrix.json
known_limitations.md
commands.log
```

Phase schema phải thêm:

```text
migration_receipt.json
backfill_audit.json
secret_audit.json
```

Phase routing phải thêm:

```text
route_lock_audit.json
failover_scenario_matrix.json
```

Phase cache phải thêm:

```text
cache_isolation_audit.json
```

Final phase phải thêm:

```text
final_audited_report.md
final_verdict.json
cutover_receipt.json
rollback_receipt.json
```

---

# 7. Stop conditions

Dừng phase hiện tại và báo `BLOCKED` khi:

* starting SHA sai;
* repository có thay đổi không rõ nguồn;
* migration có nguy cơ mất dữ liệu;
* phát hiện plaintext secret;
* cần gọi API trả phí nhưng không có test double;
* architecture boundary buộc provider package import ORM;
* không thể chứng minh hai binding là cùng revision;
* route lock có race condition chưa xử lý;
* failover có thể đổi model im lặng;
* cache có nguy cơ chéo user;
* full test suite bị loại trừ bằng cách thay config thay vì sửa lỗi.

Không tự hạ acceptance gate để đạt PASS.

Không sửa test chỉ để phù hợp implementation sai.

Không tạo receipt “passed” khi test chưa chạy.

---

# 8. Definition of Done

Provider Routing V3 chỉ hoàn tất khi WindAgent có thể thực hiện luồng sau bằng implementation thật:

```text
1. Người dùng thêm endpoint.
2. Nhấn Test Connect.
3. Hệ thống nhận diện protocol/vendor và lấy model thật.
4. Model được chuẩn hóa thành canonical model.
5. Task đầu tiên khớp rule.
6. Canonical model được khóa vào session.
7. Endpoint A được chọn và thực hiện request.
8. Endpoint A trả 429.
9. Endpoint A được cooldown.
10. Endpoint B cung cấp đúng cùng revision được chọn.
11. Request thành công.
12. Route lock vẫn giữ nguyên canonical model.
13. Lượt tiếp theo tiếp tục dùng model đã khóa.
14. Mọi attempt, quota, health, cache và usage đều có audit.
15. Restart backend không làm mất route affinity.
16. Không có secret leak.
17. Có rollback về legacy execution path.
```

Final verdict hợp lệ:

```text
ACCEPTED_PROVIDER_V3_CUTOVER_VERIFIED
```

Nếu chưa đạt toàn bộ:

```text
PARTIAL_PROVIDER_V3_NOT_ELIGIBLE_FOR_CUTOVER
```
