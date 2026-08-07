# Báo Cáo Tổng Quan Dự Án WindAgent

> **Ngày tạo:** 2026-08-07  
> **Nhánh hiện tại:** `fix/phase7-verification-integrity`  
> **Commit mới nhất:** `aa01651` — feat(video-production): implement production workspace phases  
> **Remote:** https://github.com/WindFaculty/WindAgent.git

---

## 1. Tổng Quan Dự Án

**WindAgent** là một desktop agent AI local-first được xây dựng theo kiến trúc **Modular Monolith V2**. Runtime được tách thành các ứng dụng độc lập (API, Worker, CLI, Desktop, Web) chia sẻ chung các gói canonical và lớp lưu trữ bền vững.

| Thuộc tính | Giá trị |
|---|---|
| Phiên bản workspace | `0.3.0` |
| Python yêu cầu | `>=3.10` |
| Package manager | `uv` (Astral) |
| Node.js yêu cầu | `>=20` |
| API endpoint | `http://127.0.0.1:8765` |
| API phiên bản | `/api/v2/*` (v1 đã bị loại bỏ - trả về `410 Gone`) |

---

## 2. Cấu Trúc Thư Mục Cấp Cao

```
WindAgent/
├── apps/                          # Ứng dụng có thể cài đặt độc lập
│   ├── api/                       # FastAPI REST, SSE, WebSocket
│   ├── cli/                       # Doctor, architecture, workflow commands
│   ├── desktop/                   # Tauri + React desktop client
│   ├── web/                       # React web client
│   ├── worker/                    # Durable background execution process
│   └── artifacts/                 # App-level artifacts
├── core/                          # windagent-core package
├── intelligence/                  # windagent-intelligence package
├── orchestration/                 # windagent-orchestration package
├── execution/                     # windagent-execution package
├── providers/                     # windagent-providers package
├── tools/                         # windagent-tools package
├── workflows/                     # windagent-workflows package
├── verification/                  # windagent-verification package
├── context/                       # windagent-context package
├── memory/                        # windagent-memory package
├── storage/                       # windagent-storage package
├── observability/                 # windagent-observability package
├── evals/                         # windagent-evals package
├── plugins/                       # windagent-plugins package
├── skills/                        # windagent-skills package
├── docs/                          # Tài liệu kỹ thuật
├── tests/                         # Bộ kiểm thử
├── scripts/                       # Scripts tiện ích
├── artifacts/                     # Artifacts kiến trúc và bằng chứng CI
├── configs/                       # Cấu hình hệ thống
└── data/                          # Dữ liệu runtime (gitignored)
```

---

## 3. Chi Tiết Từng Thành Phần

### 3.1 Apps Layer (`apps/`)

#### `apps/api/` — FastAPI Backend
Package `windagent-api`, cung cấp toàn bộ REST API.

**Routers chính (`windagent_api/routers/`):**
| Router | Mô tả |
|---|---|
| `v2_conversations.py` | Quản lý hội thoại AI |
| `v2_sessions.py` | Quản lý phiên làm việc |
| `v2_tasks.py` | Task management |
| `v2_browser.py` | Browser automation |
| `v2_production_workspace.py` | Video production workspace |
| `v2_events.py` | SSE event streaming |
| `v2_artifacts.py` | Artifact management |
| `v2_memory.py` | Memory endpoints |
| `v2_observability.py` | Observability endpoints |
| `v2_permissions.py` | Permission control |
| `v2_plugins.py` | Plugin system |
| `v2_providers.py` | Model providers |
| `v2_runs.py` | Run management |
| `v2_skills.py` | Skills endpoints |
| `v2_tools.py` | Tools endpoints |
| `v2_workflows.py` | Workflow management |
| `v2_evals.py` | Evaluation endpoints |
| `conversation_streams.py` | WebSocket conversation streams |

**Files cốt lõi:**
- `main.py` — FastAPI app entry point, CORS, middleware
- `composition.py` — Dependency injection composition root
- `dependencies.py` — FastAPI dependencies
- `lifespan.py` — App startup/shutdown lifecycle
- `health.py` — Health check endpoints
- `browser_sessions.py` — Browser session management

#### `apps/worker/` — Background Worker
Xử lý tác vụ nền bền vững (durable execution).

#### `apps/cli/` — CLI Tools
Doctor commands, architecture check, workflow inspection.

#### `apps/desktop/` — Desktop Client
Tauri + React native desktop application.

#### `apps/web/` — Web Client
React web application frontend.

---

### 3.2 Core Package (`core/windagent_core/`)

Gói nền tảng chứa:
- **`domain/`** — Domain models và business logic cốt lõi
- **`contracts/`** — Interface contracts giữa các gói
- **`adapters/`** — Adapter implementations
- **`config/`** — Configuration management
- **`errors/`** — Error hierarchy
- **`events/`** — Event definitions
- **`security/`** — Security primitives
- **`version.py`** — Version management

---

### 3.3 Intelligence Package (`intelligence/windagent_intelligence/`)

Đây là gói phức tạp nhất, xử lý toàn bộ pipeline sản xuất video AI.

#### Modules cấp cao:
| Module | Chức năng |
|---|---|
| `context_builder/` | Xây dựng ngữ cảnh cho LLM |
| `model_router/` | Định tuyến đến model phù hợp |
| `pipeline.py` | Pipeline orchestration |
| `planner/` | Lên kế hoạch tác vụ |
| `reporter/` | Tạo báo cáo |
| `reviewer/` | Review và kiểm duyệt |
| `summarizer/` | Tóm tắt nội dung |
| `task_classifier/` | Phân loại tác vụ |

#### Video Production Pipeline (`video/`):

```
video/
├── director/                      # Đạo diễn AI (lên shot plan, script)
│   ├── service.py                 # DirectorService
│   ├── models.py                  # CinematicPlan, ShotSpec models
│   ├── validator.py               # Script/plan validator
│   ├── revision.py                # Script revision logic
│   ├── duration.py                # Duration budget management
│   └── prompts.py                 # LLM prompts
├── shot_planner/                  # Lên kế hoạch shot
├── screenplay/                    # Xử lý kịch bản
├── style_design/                  # Thiết kế phong cách
├── ideation/                      # Sinh ý tưởng sáng tạo
├── reference_selector/            # Chọn ảnh/video tham chiếu
├── entity_extraction/             # Trích xuất thực thể
├── prompt_compiler/               # Biên dịch prompts cho image/video gen
├── asset_prompts/                 # Prompt templates cho assets
├── audio/                         # Xử lý âm thanh
│   ├── pipeline.py                # Audio pipeline
│   ├── tts.py                     # Text-to-speech
│   ├── voice.py                   # Voice profile management
│   ├── dialogue.py                # Dialogue processing
│   ├── mix.py                     # Audio mixing
│   └── alignment.py               # Audio-visual alignment
├── postproduction/                # Hậu kỳ video
│   ├── ffmpeg_runner.py           # FFmpeg execution (sandbox)
│   ├── assembly_planner.py        # Video assembly planning
│   ├── verifier.py                # Output verification
│   ├── reproducibility.py         # Reproducible builds
│   └── input_normalizer.py        # Input normalization
├── reviewers/                     # Automated content review
├── assembly/                      # Video assembly
├── continuity/                    # Continuity ledger
├── continuation/                  # Story continuation
├── workspace/                     # Production workspace
│   └── workspace_service.py       # WorkspaceService (Phase 23)
└── e2e_poc/                       # End-to-end POC runner
    ├── poc_runner.py              # POC orchestration (Phase 24)
    ├── traceability_auditor.py    # Traceability checks
    ├── recovery_auditor.py        # Recovery auditing
    └── automation_calculator.py   # Automation metrics
```

---

### 3.4 Tests (`tests/`)

```
tests/
├── unit/
│   ├── intelligence/              # Unit tests cho intelligence package
│   │   ├── test_intelligence_system.py   (27KB)
│   │   ├── test_phase08_director.py      (12KB)
│   │   ├── test_phase09_shot_graph.py    (21KB)
│   │   ├── test_phase10_continuity.py    (17KB)
│   │   ├── test_phase11_compiler.py      (21KB)
│   │   ├── test_phase20_reviewers.py     (29KB)
│   │   ├── test_phase21_audio.py         (18KB)
│   │   ├── test_phase22_postproduction.py (6KB)
│   │   ├── test_phase23_workspace.py      (4KB)
│   │   └── test_phase24_e2e_poc.py        (3KB)
│   ├── api/, cli/, core/, desktop/
│   ├── execution/, memory/, observability/
│   ├── orchestration/, providers/, storage/
│   ├── tools/, web/, worker/, workflows/
│   └── verification/
├── integration/
├── regression/
├── architecture/
├── fakes/
└── fixtures/
```

---

### 3.5 Docs (`docs/`)

```
docs/
├── adr/                           # Architecture Decision Records
├── architecture/                  # Architecture diagrams & specs
│   ├── g1_g9_test_matrix.md
│   ├── multi_agent_schema_mapping.md
│   └── phase9_release_runbook.md
├── providers/                     # Provider documentation
├── video_production/              # Video production documentation (~22 subdirs)
│   ├── artifact_storage/          # Artifact storage contracts
│   ├── audio/                     # Audio processing policies
│   ├── browser_runtime/           # Browser automation contracts
│   ├── cost_quota/                # Budget & quota contracts
│   ├── director/                  # Director AI contracts
│   ├── durable_workflow/          # Workflow durability contracts
│   ├── e2e_poc/                   # E2E POC runbooks
│   ├── flow_human_control/        # Human-in-the-loop contracts
│   ├── flow_images/               # Image generation flow
│   ├── flow_navigation/           # Navigation flow state machine
│   ├── flow_video/                # Video generation flow
│   ├── generation_review/         # Review contracts
│   ├── plans/                     # Implementation plans
│   ├── postproduction/            # Post-production specs
│   ├── preproduction/             # Pre-production specs
│   ├── protocol/                  # Protocol definitions
│   ├── release/                   # Release notes & runbooks
│   ├── reliability/               # Reliability & recovery
│   ├── security/                  # Security policies
│   └── workspace/                 # Workspace contracts
├── api_contract.md                # API contract spec
├── event_protocol.md              # Event protocol
├── model_provider_registry.md     # Model provider catalog
├── mvp_scope.md                   # MVP scope definition
├── mvp_release_note.md            # MVP release notes
├── safety_policy.md               # Safety policies
└── router_runtime_review.md       # Router runtime review
```

---

## 4. Kiến Trúc Pipeline Sản Xuất Video (End-to-End)

```
[User Request]
      │
      ▼
[WorkspaceService]       ← Phase 23: workspace management
      │
      ▼
[DirectorService]        ← Phase 8: cinematic planning, script revision
      │
      ├──► [ShotPlanner] ← Phase 9: shot graph construction
      │
      ├──► [Continuity]  ← Phase 10: cross-shot continuity ledger
      │
      └──► [PromptCompiler] ← Phase 11: compile to image/video prompts
                │
                ▼
         [ReferenceSelector + AssetPrompts]  ← select refs, generate prompts
                │
                ▼
         [Reviewers (VLM)]  ← Phase 20: automated quality gate
                │
                ▼
         [AudioPipeline]    ← Phase 21: TTS, voice profile, mix, alignment
                │
                ▼
         [PostProduction]   ← Phase 22: FFmpeg assembly, verification
                │
                ▼
         [E2E POC Runner]   ← Phase 24: end-to-end validation & traceability
```

---

## 5. Trạng Thái Phát Triển Theo Phases

| Phase | Mô tả | Trạng thái |
|---|---|---|
| Phase 1–3 | Core architecture, contracts | ✅ Hoàn thành |
| Phase 4 | VideoClaw quarantine | ✅ Hoàn thành |
| Phase 5 | VideoClaw behavior characterization | ✅ Hoàn thành |
| Phase 6 | Pre-production kernel canonical | ✅ Hoàn thành |
| Phase 7 | Secure media asset pipeline | ✅ Hoàn thành |
| Phase 8 | Director AI layer | ✅ Hoàn thành |
| Phase 9 | Shot graph construction | ✅ Hoàn thành |
| Phase 10 | Continuity ledger | ✅ Hoàn thành |
| Phase 11 | Prompt compiler | ✅ Hoàn thành |
| Phase 20 | Automated reviewers (VLM) | ✅ Hoàn thành |
| Phase 21 | Audio pipeline (TTS, voice, mix) | ✅ Hoàn thành |
| Phase 22 | Post-production (FFmpeg) | ✅ Hoàn thành |
| Phase 23 | Production workspace service | ✅ Hoàn thành |
| Phase 24 | E2E POC runner | ✅ Hoàn thành |
| Phase 25–27 | Hardening & production release | 🔄 In progress |

---

## 6. Workspace uv (Python Package Manager)

Dự án sử dụng **uv workspace** với 18 member packages:

| Package | Thư mục |
|---|---|
| `windagent-api` | `apps/api` |
| `windagent-cli` | `apps/cli` |
| `windagent-worker` | `apps/worker` |
| `windagent-core` | `core` |
| `windagent-orchestration` | `orchestration` |
| `windagent-intelligence` | `intelligence` |
| `windagent-providers` | `providers` |
| `windagent-tools` | `tools` |
| `windagent-workflows` | `workflows` |
| `windagent-verification` | `verification` |
| `windagent-context` | `context` |
| `windagent-memory` | `memory` |
| `windagent-execution` | `execution` |
| `windagent-storage` | `storage` |
| `windagent-observability` | `observability` |
| `windagent-evals` | `evals` |
| `windagent-plugins` | `plugins` |
| `windagent-skills` | `skills` |

---

## 7. Quy Tắc Gitignore (Không Push Lên GitHub)

Các loại file sau KHÔNG được push theo `.gitignore`:
- `*.db`, `*.sqlite` — Database files (windagent.db, test.db)
- `*.log` — Log files
- `.venv/`, `node_modules/` — Virtual environments
- `dist/`, `build/`, `out/` — Build artifacts
- `data/` — Runtime data directory
- `*-evidence/`, `final-evidence-bundle/` — CI evidence bundles
- `web-build/`, `desktop-build/` — Build outputs
- `db_backups/` — Database backups
- `.tmp/`, `.pytest_cache/` — Temporary files
- `artifacts/runs/*` — Live session JSONL audit logs

---

## 8. Hướng Dẫn Khởi Chạy

```powershell
# Khởi chạy API server
powershell -ExecutionPolicy Bypass -File scripts\dev_api.ps1

# Khởi chạy Desktop (Tauri)
powershell -ExecutionPolicy Bypass -File scripts\dev_desktop.ps1

# Khởi chạy Web frontend
cd apps/web && npm ci && npm run dev

# Chạy toàn bộ test suite
uv run pytest

# Kiểm tra kiến trúc imports
uv run python scripts/check_architecture_imports.py

# Health check
powershell -ExecutionPolicy Bypass -File scripts\healthcheck.ps1
```

---

*Báo cáo được tạo tự động ngày 2026-08-07 bởi Antigravity AI Assistant.*
