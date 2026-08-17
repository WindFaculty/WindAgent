Tiếp tục đúng roadmap trước, phần **Phase 11–16** nên được xem là giai đoạn **system convergence + legacy retirement**. Phase 6–10 đưa luồng sáng tác và production sang architecture mới; Phase 11–16 sẽ đưa phần hệ thống còn lại sang cùng chuẩn rồi mới cho phép xóa V2/dead code. Cách phân chia này khớp với roadmap gốc trong tài liệu. 

# Roadmap chi tiết — Phase 11 → Phase 16

## Dependency graph tổng thể

```text
PHASE 10
Production Cutover
      │
      ▼
┌──────────────────────────────┐
│ PHASE 11                     │
│ Agent System                 │
│ Agents / Workspace / Tasks   │
│ Workflows                    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ PHASE 12                     │
│ Model Infrastructure         │
│ Models / Providers / Routing │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ PHASE 13                     │
│ Platform / Admin             │
│ Browser / Files / Memory     │
│ Logs / Settings              │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ PHASE 14                     │
│ Web / Desktop Convergence    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ PHASE 15                     │
│ API V2 Retirement            │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ PHASE 16                     │
│ Dead Code Removal            │
│ Final Architecture Cert      │
└──────────────────────────────┘
```

**Phase 11 → 12 → 13 nên đi tuần tự về contract authority.**

Trong mỗi phase có thể chia frontend/backend/test thành worker song song sau khi contract freeze.

---

# PHASE 11 — Agent System Convergence

## Mục tiêu

Đưa toàn bộ hệ thống:

```text
Agent Workspace
Agents
Tasks
Conversations
Workflows
```

sang V3 architecture chung.

Phase này phải làm rõ một semantic rất quan trọng:

```text
AgentDefinition ≠ AgentInstance
```

Hiện UI đang trộn hai loại này.

`MultiAgentWorkspace` đã dùng durable conversation projections và có dữ liệu runtime tương đối thật, nhưng Browser panel vẫn polling mỗi 2 giây. `Agents.tsx` polling toàn bộ Agent list mỗi 5 giây, đồng thời nhiều thông số như uptime, latency, success rate và sparkline vẫn được hardcode.

---

## Phase 11.0 — Inventory & semantic freeze

Trước khi sửa:

```text
artifacts/frontend_restructure/phase_11/baseline/
├── agent_api_inventory.json
├── task_api_inventory.json
├── workflow_api_inventory.json
├── conversation_projection_inventory.json
├── agent_mock_inventory.json
├── agent_polling_inventory.json
├── agent_state_inventory.json
└── baseline_report.md
```

Phân loại toàn bộ concept hiện tại:

```text
Agent
Agent profile
Agent role
Agent runtime
Agent session
Agent instance
Conversation
Task
Task graph
Plan
Workflow
Workflow pack
Workflow run
```

---

# Phase 11.1 — Canonical Agent model

Chốt:

```text
AgentDefinition
    ↓ instantiated as
AgentInstance
```

### AgentDefinition

```text
id
name
slug
description
role
model_policy
tool_policy
permission_profile
memory_policy
default_configuration
version
```

### AgentInstance

```text
id
definition_id
conversation_id
status

canonical_model_id
provider_binding_id
route_lock_id

assigned_task_id
current_tool

started_at
stopped_at

runtime_metadata
version
```

Không dùng chung một endpoint `/agents` cho hai semantic.

---

# Phase 11.2 — API V3

Agent definitions:

```http
GET    /api/v3/agent-definitions
POST   /api/v3/agent-definitions

GET    /api/v3/agent-definitions/:id
PATCH  /api/v3/agent-definitions/:id
DELETE /api/v3/agent-definitions/:id
```

Agent runtime:

```http
GET /api/v3/agent-instances
GET /api/v3/agent-instances/:id
```

Commands:

```text
agentInstances.start
agentInstances.stop
agentInstances.restart
```

Không dùng:

```text
POST /agents/:id/start
```

nếu ID đó thực chất là definition.

---

# Phase 11.3 — Conversation authority

Canonical:

```text
Conversation
    ├── PlanVersion[]
    ├── AgentInstance[]
    ├── Task[]
    └── Event[]
```

API:

```http
GET /api/v3/conversations
GET /api/v3/conversations/:id

GET /api/v3/conversations/:id/agents
GET /api/v3/conversations/:id/tasks
GET /api/v3/conversations/:id/events
```

Nếu hiện V2 conversation/session implementation đã bền vững thì V3 chỉ wrap application service.

Không rewrite storage nếu không cần.

---

# Phase 11.4 — Task model

Canonical task:

```text
Task
├── id
├── conversation_id
├── objective
├── state
├── assigned_agent_instance_id
├── parent_task_id
├── dependencies[]
├── concurrency_group
├── attempts
├── result
└── version
```

State machine duy nhất:

```text
PENDING
READY
RUNNING
BLOCKED
SUCCEEDED
FAILED
CANCELLED
```

Không để:

```text
task.status
node_state
agent_run_status
run_status
```

tự phát triển thành những state machine gần giống nhau.

---

# Phase 11.5 — Agent Workspace rewrite

Target:

```text
features/agent-workspace/
├── AgentWorkspacePage.tsx
├── CoordinatorPanel.tsx
├── AgentInstanceList.tsx
├── TaskGraph.tsx
├── AgentInspector.tsx
├── AgentTerminal.tsx
├── BrowserRuntimePanel.tsx
└── hooks/
```

Data:

```text
conversation     → Query
agents           → Query
tasks            → Query
events           → Realtime cache
selected agent   → URL/local UI
```

Không còn:

```text
manual refresh
2-second Browser polling
global custom MultiAgentProvider authority
```

---

# Phase 11.6 — Realtime agent stream

Events:

```text
agent.instance.started
agent.instance.updated
agent.instance.stopped
agent.instance.failed

task.ready
task.started
task.progress
task.completed
task.failed

tool.started
tool.completed
tool.failed

conversation.updated
```

Terminal output:

```text
agent.output.chunk
```

hoặc log stream riêng.

---

# Phase 11.7 — Agents page

Target structure:

```text
features/agents/
├── AgentsPage.tsx
├── AgentDefinitionsPage.tsx
├── AgentDefinitionEditor.tsx
├── AgentInstancesPanel.tsx
├── AgentRuntimeMetrics.tsx
└── AgentActivity.tsx
```

Loại các runtime value đang giả như:

```text
uptime = 1h14m
rt = 1.25s
success = 95%
static sparkline
```

Nếu server không có metric đó:

```text
Not available
```

không fake.

---

# Phase 11.8 — Workflows

`Workflows.tsx` hiện là một mock catalog lớn được dựng hoàn toàn trong component.

Canonical model:

```text
WorkflowDefinition
WorkflowVersion

WorkflowRun
WorkflowStepRun
```

API:

```http
GET  /api/v3/workflows
POST /api/v3/workflows

GET /api/v3/workflows/:id
```

Run:

```http
POST /api/v3/workflow-runs
GET  /api/v3/workflow-runs/:id
```

Commands:

```text
workflowRuns.cancel
workflowRuns.retry
workflowRuns.pause
workflowRuns.resume
```

---

# Phase 11.9 — Workflow realtime

```text
workflow.run.started
workflow.step.started
workflow.step.completed
workflow.step.failed
workflow.run.completed
workflow.run.failed
```

UI progress phải derive từ step states.

Không lưu:

```text
progressVal = 68
```

như mock data.

---

# Phase 11.10 — Agent/Workflow integration test

Critical flow:

```text
Create/choose AgentDefinition
        ↓
Create Conversation
        ↓
Start AgentInstance
        ↓
Create/trigger WorkflowRun
        ↓
Task generated
        ↓
Task assigned to AgentInstance
        ↓
Agent execution observed
        ↓
Tool activity observed
        ↓
Task completes
        ↓
WorkflowRun completes
```

Failure scenario:

```text
agent dies
→ task state truthful
→ workflow step becomes FAILED/BLOCKED
→ restart/retry
→ recovery
```

---

# Phase 11 Gate

```text
AgentDefinition / Instance separated       PASS

Agents polling 5s                          = 0
Browser panel polling 2s                   = 0

hardcoded agent uptime                     = 0
hardcoded agent latency                    = 0
hardcoded agent success                    = 0

mock workflow datasets                     = 0

direct fetch                               = 0
generated V3 client                        PASS

Agent Workspace realtime                   PASS
Task graph realtime                        PASS
Workflow execution E2E                     PASS

Web                                        PASS
Desktop                                    PASS
```

Verdict:

```text
FRONTEND_V2_PHASE_11_AGENT_SYSTEM_VERIFIED
```

---

# PHASE 12 — Models, Providers & Routing

## Mục tiêu

Hợp nhất ba vùng hiện đang phân mảnh:

```text
Models
Endpoints / Providers
Router
```

thành một **Model Infrastructure domain**.

Snapshot hiện tại cho thấy `Models.tsx` và `Endpoints.tsx` gọi trực tiếp `/api/v2/providers`.

`Router.tsx` ngoài routing UI còn chứa lượng code UI/game/audio không liên quan trực tiếp đến routing production, là dấu hiệu cần decomposition mạnh.

---

# Phase 12.0 — Canonical vocabulary

Freeze:

```text
Provider
ProviderEndpoint

ModelDefinition

RoutingPolicy
RoutingRule

RouteDecision
RouteBinding
RouteLock
```

Cần phân biệt:

```text
ModelDefinition
```

với:

```text
Provider-specific deployment/endpoint
```

Ví dụ:

```text
Gemini model
        │
        ├── Google AI Studio endpoint
        └── Vertex endpoint
```

không phải hai model khác nhau nếu canonical model ID giống nhau.

---

# Phase 12.1 — Provider registry thật

Provider phải lấy từ composition/provider registry thật.

Không trả static fixture.

Canonical:

```text
Provider
├── id
├── display_name
├── type
├── status
├── capabilities
└── endpoints[]
```

Endpoint:

```text
id
provider_id
base_url
status
latency
rate_limit_state
credential_reference
```

**Không trả API key ra frontend.**

---

# Phase 12.2 — Models API

```http
GET /api/v3/models
GET /api/v3/models/:id
```

Filter:

```text
provider
capability
context_window
modality
local/cloud
availability
```

Provider:

```http
GET   /api/v3/providers
GET   /api/v3/providers/:id
GET   /api/v3/providers/:id/models
GET   /api/v3/providers/:id/endpoints
GET   /api/v3/providers/:id/health
```

---

# Phase 12.3 — Provider connection testing

Command:

```text
providers.testConnection
```

Receipt:

```text
test_id
provider_id
endpoint_id
started_at
```

Result:

```text
reachable
latency_ms
auth_valid
model_discovery
error_code
```

Không để frontend tự ping URL/API.

---

# Phase 12.4 — Routing API

Canonical:

```http
GET  /api/v3/routing/rules
POST /api/v3/routing/rules

GET   /api/v3/routing/rules/:id
PATCH /api/v3/routing/rules/:id
DELETE /api/v3/routing/rules/:id
```

Graph:

```http
GET /api/v3/routing/graph
```

Metrics:

```http
GET /api/v3/routing/metrics
```

Simulation:

```http
POST /api/v3/routing/simulations
```

Không còn:

```text
/api/models/routing/rules
/api/models/routing/stats
/api/models/routing/traffic
/api/models/routing/graph
```

ở frontend mới.

---

# Phase 12.5 — Routing decision explainability

Một route decision nên có:

```text
request_id
requested_role
canonical_model_id
selected_provider
selected_endpoint

rule_id
reason

fallback_chain
route_lock_id
```

Điều này rất quan trọng cho Agent Workspace Phase 11.

Agent inspector có thể mở:

```text
route_lock_id
```

và truy ra lý do model/provider được chọn.

---

# Phase 12.6 — Models UI

```text
features/models/
├── ModelsPage
├── ModelDetail
├── ModelCapabilities
└── ModelAvailability
```

Không cần `ModelsProps.setActiveTab`.

Router chuẩn xử lý:

```ts
navigate("/models/providers")
```

---

# Phase 12.7 — Providers UI

Hợp nhất `Endpoints.tsx`.

```text
features/providers/
├── ProvidersPage
├── ProviderDetail
├── EndpointList
├── EndpointHealth
├── TestConnectionDialog
└── CredentialStatus
```

Credentials UI chỉ được biết:

```text
configured: true
```

không đọc secret.

---

# Phase 12.8 — Router decomposition

Target:

```text
features/routing/
├── RoutingPage.tsx
├── RoutingRules.tsx
├── RoutingRuleEditor.tsx
├── RouteGraph.tsx
├── TrafficDistribution.tsx
├── RouteSimulator.tsx
├── RoutingMetrics.tsx
└── RouteDecisionInspector.tsx
```

Remove production coupling với:

```text
WebAudioSound
SoundSynth
game state
easter egg
```

Nếu muốn giữ game:

```text
devtools/
experiments/
```

không nằm trong routing feature.

---

# Phase 12.9 — Provider realtime

Không cần stream toàn bộ catalog.

Realtime phù hợp cho:

```text
provider.health.changed
endpoint.health.changed
routing.policy.changed
routing.decision
```

Routing traffic metrics có thể stream hoặc aggregate theo interval backend.

---

# Phase 12.10 — E2E

```text
Open Models
→ model list thật

Open Provider
→ endpoint status thật

Test Connection
→ real receipt/result

Create Routing Rule
→ persist

Run Simulation
→ receive RouteDecision

Trigger Agent
→ verify agent route_lock
→ selected model/provider matches decision
```

---

# Phase 12 Gate

```text
direct /api/v2/providers references       = 0

/api/models/routing references            = 0

handwritten ProviderInfo duplicate        = 0

provider fixture runtime data             = 0

Router game/audio production coupling     = 0

generated client                          PASS
provider health                           PASS
routing simulation                        PASS
Agent routing integration                 PASS

Web                                      PASS
Desktop                                  PASS
```

Verdict:

```text
FRONTEND_V2_PHASE_12_MODEL_INFRASTRUCTURE_VERIFIED
```

---

# PHASE 13 — Platform & Administration

Phase này migrate:

```text
Browser
Files
Memory
Logs
Settings
```

Có thể chia:

```text
13A Browser
13B Files
13C Memory
13D Logs
13E Settings
13F integration
```

sau khi contract freeze.

Hiện Browser, Files và Memory đều chứa dataset tĩnh lớn ngay trong component.

Settings cũng đang lưu gần như toàn bộ cấu hình bằng React `useState` và chứa integration/permission/activity fixture.

---

# Phase 13A — Browser Runtime Console

## Semantic

Phân biệt:

```text
BrowserProfile
BrowserSession
BrowserTab
BrowserAction
BrowserArtifact
```

API:

```http
GET  /api/v3/browser/sessions
POST /api/v3/browser/sessions

GET /api/v3/browser/sessions/:id
```

Actions:

```text
browser.navigate
browser.click
browser.type
browser.scroll
browser.extract
browser.screenshot
browser.close
```

---

## Browser UI

```text
BrowserPage
├── BrowserSessionList
├── BrowserViewport
├── AddressBar
├── TabStrip
├── ControlMode
├── DOMInspector
├── ExtractionViewer
├── ActionTimeline
└── RuntimeLogs
```

Screenshot phải là server/browser runtime artifact thật.

---

## Browser realtime

```text
browser.session.started
browser.navigation
browser.action.started
browser.action.completed
browser.screenshot.updated
browser.session.closed
```

Không fake session health.

---

# Phase 13B — Files

Đây phải là **workspace file abstraction**, không trộn với Asset.

Canonical:

```text
FileResource
├── id
├── path
├── name
├── media_type
├── size
├── checksum
├── created_at
├── modified_at
└── permissions
```

API:

```http
GET  /api/v3/files
POST /api/v3/files

GET    /api/v3/files/:id
DELETE /api/v3/files/:id
```

Optional:

```text
download
preview
metadata
```

Phải enforce workspace root sandbox.

Không cho frontend gửi arbitrary Windows path rồi đọc trực tiếp.

---

# Phase 13C — Memory

Phân biệt rõ:

```text
Memory != Database
```

Canonical memory:

```text
MemoryRecord
├── id
├── scope
├── owner
├── type
├── content
├── metadata
├── embedding_state
├── created_at
├── last_accessed_at
└── version
```

Scope:

```text
conversation
project
agent
global
```

API:

```http
GET /api/v3/memory
GET /api/v3/memory/:id

POST /api/v3/memory/search
```

Nếu administrative database UI chưa thật sự cần thiết:

**bỏ tên Database khỏi navigation.**

Chỉ giữ:

```text
Memory
```

---

# Phase 13D — Logs

Xây mới:

```text
features/logs/
├── LogsPage
├── LogStream
├── LogFilters
├── AgentLogPanel
├── TaskLogPanel
├── ApiRequestLogPanel
└── ErrorLogPanel
```

Contract:

```text
LogRecord
├── timestamp
├── level
├── source
├── message
├── correlation_id
├── trace_id
├── conversation_id?
├── agent_instance_id?
├── task_id?
└── metadata
```

API:

```http
GET /api/v3/logs
```

Stream:

```text
/ws/v3/logs
```

Filters:

```text
level
source
correlation
conversation
agent
task
time
```

---

# Phase 13E — Settings

Settings phải tách thành:

```text
settings/
├── GeneralSettings
├── AppearanceSettings
├── AgentSettings
├── ModelSettings
├── RoutingSettings
├── BrowserSettings
├── SecuritySettings
├── IntegrationSettings
└── AdvancedSettings
```

API:

```http
GET /api/v3/settings
PATCH /api/v3/settings

GET /api/v3/settings/schema
```

---

## Settings schema

Backend trả:

```text
key
type
default
value

requires_restart
secret
read_only

min/max
enum
description
```

Nhờ đó frontend không cần hardcode toàn bộ setting semantics.

---

## Secret storage

Đặc biệt:

```text
API key
tokens
credentials
```

phải được lưu qua:

```text
backend secure store
or
Tauri secure/keychain adapter
```

Frontend chỉ nhận:

```json
{
  "configured": true
}
```

Không trả secret ngược ra browser.

---

# Phase 13F — Integration

Test chuỗi:

```text
Agent
→ launches BrowserSession
→ browser event visible
→ screenshot persisted as Artifact/File
→ Agent uses result
→ Memory created
→ logs contain same correlation_id
```

Đây là bài test rất giá trị vì nối gần như toàn platform layer.

---

# Phase 13 Gate

```text
Browser mock sessions                 = 0
Files mock dataset                    = 0
Memory mock dataset                   = 0
Settings runtime-only authority       = 0

Logs route                            PASS

Browser realtime                      PASS
File sandbox                          PASS
Memory retrieval                      PASS
secure setting storage                PASS

cross-domain correlation ID           PASS

Web                                   PASS
Desktop                               PASS
```

Verdict:

```text
FRONTEND_V2_PHASE_13_PLATFORM_ADMIN_VERIFIED
```

---

# PHASE 14 — Web/Desktop Convergence

Đây là phase architecture quan trọng.

Hiện:

```text
apps/web
    ↓
@desktop/App
    ↓
desktop styles
```

`apps/web/src/app/App.tsx` chỉ import nguyên Desktop app.

Phase 14 phải đảo dependency.

---

# Phase 14.1 — Target dependency

Sau migration:

```text
                 ┌──────── apps/web
                 │
frontend/app ────┤
                 │
                 └──────── apps/desktop
```

Không:

```text
Web → Desktop
```

---

# Phase 14.2 — Bootstrap-only applications

Target:

```text
apps/web/
└── src/
    ├── main.tsx
    └── platform.ts

apps/desktop/
└── src/
    ├── main.tsx
    └── platform.ts
```

Không chứa feature page.

---

# Phase 14.3 — Shared frontend authority

```text
frontend/app/
├── app/
│   ├── App.tsx
│   ├── router.tsx
│   ├── providers.tsx
│   └── routeManifest.ts
│
├── features/
└── shared/
```

---

# Phase 14.4 — PlatformAdapter

Canonical interface:

```ts
interface PlatformAdapter {
    platform: "web" | "desktop";

    getSystemCapabilities(): Promise<...>;

    openExternal(...): Promise<void>;

    selectFile?(...): Promise<...>;

    showNotification?(...): Promise<void>;

    getNativeSystemMetrics?(): Promise<...>;
}
```

Implement:

```text
WebPlatformAdapter
TauriPlatformAdapter
```

Feature không được check:

```ts
window.__TAURI__
```

trực tiếp.

---

# Phase 14.5 — Platform capability model

Feature dùng:

```text
supportsNativeFilePicker
supportsNativeNotifications
supportsSystemMetrics
supportsLocalRuntime
```

Ví dụ:

```text
if capability unsupported
→ disable / fallback explicitly
```

không:

```text
try Tauri
catch → fake value
```

---

# Phase 14.6 — Styling convergence

Remove:

```text
@desktop/styles.css
```

khỏi Web.

Authority:

```text
frontend/app/styles/
or
frontend/packages/ui/
```

Web và Desktop cùng import.

---

# Phase 14.7 — Router parity

Cùng route manifest:

```text
/dashboard
/studio/*
/assets/*
/agents/*
/models/*
/browser
/files
/memory
/logs
/settings
```

Test direct deep link trên cả:

```text
Browser HashRouter
Tauri
```

---

# Phase 14.8 — Platform parity E2E

Một dataset fixture/test backend duy nhất.

Chạy cùng flow:

```text
Web
vs
Desktop
```

Các flow:

```text
Project creation
Episode generation
Agent workspace
Provider page
Browser
Settings
Production
```

Expected semantic output phải giống nhau.

---

# Phase 14 Gate

Repo scan:

```text
@desktop/App from apps/web        = 0
@desktop/styles from apps/web     = 0

feature code under apps/web       = 0
feature code under apps/desktop   = 0

direct Tauri checks in features   = 0
```

Và:

```text
shared App                        PASS
shared Router                     PASS
Web E2E                           PASS
Tauri E2E/smoke                   PASS
route parity                      PASS
visual parity                     PASS
```

Verdict:

```text
FRONTEND_V2_PHASE_14_WEB_DESKTOP_CONVERGENCE_VERIFIED
```

---

# PHASE 15 — API V2 Retirement

**Phase 15 không được bắt đầu nếu Phase 14 chưa PASS.**

Đây không còn là migration.

Đây là:

> chứng minh V2 không còn consumer → disable → test → delete.

---

# Phase 15.0 — Zero-consumer audit

Repo-wide scan:

```text
/api/v2/
/api/models/
v2Unavailable
ProductionApiClient V2
HttpStudio V3 special-case
old Browser API
old provider endpoints
```

Xuất:

```text
artifacts/frontend_restructure/phase_15/baseline/
├── v2_routes.json
├── v2_consumers.json
├── legacy_route_consumers.json
├── compatibility_dependencies.json
└── retirement_matrix.md
```

Matrix:

| Endpoint            | Backend route | Consumer | V3 replacement      | Can remove |
| ------------------- | ------------- | -------- | ------------------- | ---------- |
| `/api/v2/providers` | ...           | 0        | `/api/v3/providers` | YES        |
| ...                 | ...           | ...      | ...                 | ...        |

---

# Phase 15.1 — Classification

Mỗi endpoint:

```text
REMOVE
KEEP_TEMPORARILY
EXTERNAL_COMPATIBILITY
UNKNOWN
```

Không xóa `UNKNOWN`.

Phải điều tra trước.

---

# Phase 15.2 — Frontend zero-reference gate

Trước backend delete:

```text
/api/v2/ frontend references        = 0
/api/models/ frontend references    = 0
```

Không ngoại lệ production.

Test fixture có thể còn nếu cần migration test.

---

# Phase 15.3 — Disable-first strategy

Không delete toàn bộ V2 ngay.

Bước đầu:

```text
production config
→ disable V2 registration
```

Chạy full test matrix.

Mục tiêu phát hiện hidden consumer.

Nếu app vẫn chạy:

```text
V2 disabled
+
full E2E PASS
```

mới chuyển sang delete.

---

# Phase 15.4 — Route deletion order

Nên xóa theo domain đã migrate:

```text
1 Dashboard/System legacy
2 Studio compatibility
3 Production
4 Agents/Tasks/Workflows
5 Providers/Models/Routing
6 Browser
7 Files
8 Memory
9 Settings
10 miscellaneous
```

Không xóa tất cả trong một giant diff.

---

# Phase 15.5 — Remove V2 clients

Sau route removal:

```text
apps/desktop/src/api/client.ts
```

phải thu nhỏ đáng kể hoặc biến mất nếu tất cả client đã chuyển package generated.

Xóa:

```text
v2Unavailable(...)
legacy DTOs
legacy URL helpers
legacy retry code
manual request wrappers
```

---

# Phase 15.6 — OpenAPI contract cleanup

OpenAPI cuối:

```text
/api/v3/*
```

không expose deprecated V2.

Contract generation:

```text
FastAPI
 ↓
openapi.json
 ↓
generated TS
 ↓
frontend
```

---

# Phase 15.7 — Negative tests

Phải cố ý gọi:

```text
/api/v2/providers
/api/v2/tasks
/api/v2/browser/...
```

Expected:

```text
404
```

hoặc deliberate Gone nếu chọn policy đó.

Quan trọng là không còn silently forward.

---

# Phase 15.8 — Full E2E khi V2 đã biến mất

Chạy lại:

```text
Dashboard
Project
Episode
Screenplay
Storyboard
Production
Agent
Workflow
Provider
Routing
Browser
Files
Memory
Settings
```

Đây là certification thực sự.

---

# Phase 15 Gate

```text
frontend /api/v2 references        = 0
frontend /api/models references    = 0

runtime V2 consumer                = 0

V2 backend routers                 = 0
v2Unavailable                      = 0

OpenAPI V2 paths                   = 0

negative V2 request                PASS
full Web E2E                       PASS
full Desktop E2E                   PASS
backend regression                 PASS
```

Verdict:

```text
FRONTEND_V2_PHASE_15_API_V2_RETIRED
```

---

# PHASE 16 — Dead Code Removal & Final Certification

Đây mới là phase được phép dọn mạnh.

Không được nhầm:

```text
"unused-looking"
```

với:

```text
"provably unreachable"
```

---

# Phase 16.0 — Build dead-code inventory

Sử dụng nhiều evidence source:

```text
TypeScript compiler
ESLint
dependency graph
route manifest
package imports
Vite build graph
tests
code search
coverage
```

Output:

```text
artifacts/frontend_restructure/phase_16/baseline/
├── unreachable_files.json
├── unused_exports.json
├── unused_packages.json
├── orphan_components.json
├── orphan_styles.json
├── orphan_tests.json
├── duplicate_contracts.json
└── deletion_candidates.md
```

---

# Phase 16.1 — Classification

Mỗi candidate:

```text
DELETE
KEEP
TEST_ONLY
DEV_ONLY
MIGRATION_ONLY
UNKNOWN
```

Chỉ:

```text
DELETE
```

mới được xóa tự động.

`UNKNOWN` giữ lại.

---

# Phase 16.2 — Old pages

Delete nếu consumer = 0:

```text
old Dashboard
old StudioPage
old ProjectsPage
old EpisodesPage
old StoryBoardPage
old CharactersPage
old ReviewsPage
old ProductionWorkspacePage

old Agents
old Models
old Endpoints
old Router

old Browser
old Files
old Memory
old Settings
```

Tên cụ thể phụ thuộc implementation Phase 6–14.

Không xóa dựa trên roadmap alone.

---

# Phase 16.3 — Old client packages

Candidates:

```text
studio-client
studio-state
studio-contracts

production-client
production-contracts
```

Chỉ xóa nếu generated V3 equivalents đã thay hoàn toàn.

Một package không nên bị xóa chỉ vì tên "old".

Kiểm tra dependency graph trước.

---

# Phase 16.4 — Mock retirement

Repo scan:

```text
FakeProductionApiClient

DEFAULT_EPISODES
DEFAULT_CHARACTERS
DEFAULT_SCENES
DEFAULT_COMMENTS
DEFAULT_VERSIONS

sessionsData
filesData
memoryData
workflowsData

Math.random()
setTimeout(fake generation)
mock fallback
```

Production source:

```text
0 runtime mock
```

Test fixtures được phép.

---

# Phase 16.5 — CSS cleanup

Sau khi old components bị xóa:

```text
unused CSS selector scan
```

Dọn:

```text
old styles.css sections
page-specific legacy CSS
duplicate Tailwind styles
unused variables
duplicate tokens
```

Không rewrite visual design ở phase này.

Chỉ cleanup.

---

# Phase 16.6 — Dependency cleanup

Package manager:

```text
unused dependencies
duplicate dependencies
state libraries no longer used
old routing libs
old API packages
mock-only runtime libs
```

Nếu Redux hoặc Zustand không còn consumer:

```text
remove
```

Nhưng chỉ dựa trên actual import graph.

---

# Phase 16.7 — State architecture certification

Repo scan đảm bảo:

```text
Server state
→ TanStack Query

URL state
→ Router

Realtime
→ shared realtime client

UI state
→ local/Zustand where justified
```

Không còn page-level custom server stores.

---

# Phase 16.8 — Architecture checker

Thêm invariant vĩnh viễn vào CI.

Ví dụ:

```text
RULE F001
feature cannot import apps/desktop

RULE F002
feature cannot import apps/web

RULE F003
feature cannot call fetch()

RULE F004
feature cannot reference /api/v2

RULE F005
feature cannot reference /api/models

RULE F006
apps/web cannot import apps/desktop

RULE F007
runtime Fake client forbidden

RULE F008
route must be registered in routeManifest

RULE F009
navigation must reference valid route

RULE F010
API contract imports only from generated contracts
```

Sau Phase 16, những lỗi cũ không được quay lại.

---

# Phase 16.9 — Final end-to-end certification

Tôi đề xuất final certification không chỉ test từng page.

Chạy **một flow xuyên toàn hệ thống**:

```text
Create Project
      ↓
Create Episode
      ↓
Generate Idea
      ↓
Select Idea
      ↓
Story Bible
      ↓
Outline
      ↓
Screenplay
      ↓
Review
      ↓
Lock
      ↓
Characters / World
      ↓
Storyboard
      ↓
Generate Asset
      ↓
Review Asset
      ↓
Production Plan
      ↓
Production Job
      ↓
Artifact
      ↓
Agent inspection
      ↓
Provider route inspection
      ↓
Logs / correlation trace
```

Sau đó:

```text
restart backend
restart frontend
```

và xác minh dữ liệu vẫn tồn tại.

---

# Phase 16.10 — Web/Desktop final parity

Chạy cùng certification trên:

```text
Web
Tauri Desktop
```

Không nhất thiết render job phải chạy hai lần.

Nhưng UI/API semantics phải parity.

---

# Phase 16.11 — Final repo scan

Kết quả bắt buộc:

```text
direct fetch() in feature code          = 0

/api/v2 frontend refs                   = 0
/api/models frontend refs               = 0

v2Unavailable                           = 0

FakeProductionApiClient runtime         = 0

hardcoded runtime mock datasets         = 0

manual hash parser                      = 0

Web importing Desktop                   = 0

feature code inside app bootstrap       = 0

orphan routes                           = 0

orphan navigation                       = 0

duplicate handwritten API contracts     = 0
```

---

# Phase 16.12 — Final evidence bundle

```text
artifacts/frontend_restructure/final/
├── final_verdict.json
├── final_report.md
│
├── architecture_report.json
├── api_inventory.json
├── route_inventory.json
├── navigation_inventory.json
│
├── openapi_report.json
├── generated_client_report.json
│
├── mock_runtime_scan.json
├── legacy_api_scan.json
├── dead_code_scan.json
├── package_dependency_report.json
│
├── backend_tests.json
├── frontend_tests.json
├── contract_tests.json
├── e2e_tests.json
│
├── web_build.json
├── desktop_build.json
│
├── web_e2e.json
├── desktop_e2e.json
│
├── screenshots/
├── performance/
│
└── risk_register.md
```

---

# Phase 16 Gate

```text
Architecture checker             PASS

TypeScript                       PASS
Lint                             PASS

Backend tests                    PASS
Frontend tests                   PASS

API contract tests               PASS

Web build                        PASS
Desktop build                    PASS

Web E2E                          PASS
Desktop E2E                      PASS

Full project→production E2E      PASS

Legacy API scan                  CLEAN
Runtime mock scan                CLEAN
Dead code scan                   CLEAN
Dependency scan                  CLEAN
Route/navigation scan            CLEAN
```

Final verdict:

```text
FRONTEND_ARCHITECTURE_V2
UNIFIED_API_V3
PRODUCTION_CUTOVER_VERIFIED
READY_FOR_MAIN_PROMOTION
```

---

# Các Phase có thể chạy song song

Sau khi Phase 10 hoàn thành, tôi sẽ tổ chức execution như sau:

```text
Phase 11.0 Contract freeze
        │
        ├──── 11A Agents
        ├──── 11B Agent Workspace
        ├──── 11C Tasks
        └──── 11D Workflows
                 │
                 ▼
             11 Integration
                 │
                 ▼
Phase 12.0 Contract freeze
        │
        ├──── 12A Models
        ├──── 12B Providers
        ├──── 12C Routing
        └──── 12D Provider Health
                 │
                 ▼
             12 Integration
                 │
                 ▼
Phase 13.0 Contract freeze
        │
        ├──── 13A Browser
        ├──── 13B Files
        ├──── 13C Memory
        ├──── 13D Logs
        └──── 13E Settings
                 │
                 ▼
             13 Integration
                 │
                 ▼
             Phase 14
                 │
                 ▼
             Phase 15
                 │
                 ▼
             Phase 16
```

**Phase 14–16 không nên chạy song song.**

Đặc biệt:

```text
Phase 14
Web/Desktop converge
      ↓
Phase 15
prove V2 unused + delete
      ↓
Phase 16
prove legacy code unused + delete
```

Nếu đảo thứ tự, khả năng xóa nhầm compatibility code vẫn còn consumer sẽ tăng mạnh.

---

# Gate tổng từ Phase 11–16

| Invariant                  | P11 | P12 | P13 | P14 | P15 | P16 |
| -------------------------- | --: | --: | --: | --: | --: | --: |
| Generated V3 client        |   ✓ |   ✓ |   ✓ |   ✓ |   ✓ |   ✓ |
| No direct fetch            |   ✓ |   ✓ |   ✓ |   ✓ |   ✓ |   ✓ |
| Realtime where appropriate |   ✓ |   ✓ |   ✓ |   ✓ |   ✓ |   ✓ |
| Runtime mock-free in scope |   ✓ |   ✓ |   ✓ |   ✓ |   ✓ |   ✓ |
| Web                        |   ✓ |   ✓ |   ✓ |   ✓ |   ✓ |   ✓ |
| Desktop                    |   ✓ |   ✓ |   ✓ |   ✓ |   ✓ |   ✓ |
| V2 disabled                |     |     |     |     |   ✓ |   ✓ |
| V2 deleted                 |     |     |     |     |   ✓ |   ✓ |
| Dead code removed          |     |     |     |     |     |   ✓ |

---

# Final architecture sau Phase 16

```text
                         ┌──────────────────┐
                         │ FastAPI / API V3 │
                         └────────┬─────────┘
                                  │
                             OpenAPI
                                  │
                                  ▼
                    ┌────────────────────────┐
                    │ generated api-client   │
                    └────────────┬───────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
             HTTP Query                     Realtime
                 │                               │
                 └───────────────┬───────────────┘
                                 ▼
                       frontend/app
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
       Studio            Production         System
           │                 │                 │
 Project/Episode     Storyboard/Render    Agents/Models
 Character/World     Assets/Review        Browser/Logs
           │                 │                 │
           └─────────────────┼─────────────────┘
                             │
                      PlatformAdapter
                       ┌─────┴─────┐
                       ▼           ▼
                      Web        Tauri
```

Sau Phase 16 sẽ không còn mô hình hiện tại kiểu:

```text
Web
 ↓
Desktop App
 ↓
giữa V2/V3 clients
 ↓
mock/fake/runtime APIs
```

mà chuyển thành **một application frontend duy nhất, một contract authority duy nhất, một API V3 duy nhất và hai platform bootstrap mỏng**.

Với roadmap tổng thể Phase 0–16, tôi sẽ đặt bốn major certification gates:

```text
PHASE 0–5
FOUNDATION_VERIFIED
        ↓
PHASE 6–10
STUDIO_PRODUCTION_VERTICAL_SLICE_VERIFIED
        ↓
PHASE 11–13
SYSTEM_DOMAIN_MIGRATION_VERIFIED
        ↓
PHASE 14
WEB_DESKTOP_CONVERGENCE_VERIFIED
        ↓
PHASE 15
API_V2_RETIRED
        ↓
PHASE 16
FRONTEND_ARCHITECTURE_V2_FINAL_VERIFIED
```

Đây là điểm kết thúc hợp lý cho đợt tái cấu trúc: **Phase 15 chỉ xóa API legacy sau khi không còn consumer; Phase 16 chỉ xóa frontend legacy sau khi architecture mới đã được chứng minh độc lập.** Cách này tránh chính lỗi thường gặp nhất trong một migration lớn: dọn code quá sớm rồi phải dựng lại compatibility layer sau đó.
