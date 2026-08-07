# Báo cáo cấu trúc dự án WindAgent

- **Ngày tạo:** 2026-08-07
- **Branch:** `fix/phase7-verification-integrity`
- **Remote:** `https://github.com/WindFaculty/WindAgent.git`

---

## 1. Tổng quan

WindAgent là một **desktop agent local-first** được xây dựng theo kiến trúc
**Modular Monolith Architecture V2**. Runtime được tách thành các ứng dụng
độc lập (API, Worker, CLI, Desktop, Web) chia sẻ chung các canonical packages
và persistent storage.

Ngoài hạ tầng agent cốt lõi, dự án đang triển khai chương trình
**Video Production Platform** (phases 0–27): pipeline tạo video từ ý tưởng →
kịch bản → shot plan → Google Flow browser provider → audio/hậu kỳ, với
nguyên tắc **không fake PASS**, mọi kết quả đều có evidence kiểm chứng.

## 2. Kiến trúc runtime

```text
apps/api        FastAPI REST, SSE, và WebSocket entrypoint
apps/worker     Durable background execution process
apps/cli        Doctor, architecture, và workflow commands
apps/desktop    Tauri + React desktop client
apps/web        React web client

core, orchestration, execution, intelligence, providers, tools, workflows,
verification, context, memory, storage, observability, evals, plugins, skills
                = Canonical Architecture V2 packages
```

Backend monolithic cũ đã được ngừng sử dụng. Production code, launcher, CI và
package installation chỉ dùng các canonical packages trên.

## 3. Cấu trúc thư mục

### 3.1 Packages workspace (`uv` workspace)

| Package | Vai trò |
| --- | --- |
| `core` | Domain models, contracts, events, errors, config, security |
| `orchestration` | Task manager, workflow engine, state machine, scheduler, dispatcher, retry, recovery |
| `execution` | Runtime execution của agent/task |
| `intelligence` | Task classifier, planner, context builder, model router, summarizer, reviewer, reporter, **video pipeline** (`video/`) |
| `providers` | OpenAI, Anthropic, Google, NVIDIA, OpenRouter, Mistral, Ollama, local… |
| `tools` | Registry, filesystem, shell, git, code search, AST, LSP, testing, browser, database, GitHub, MCP, **Google Flow**, video probe |
| `workflows` | Workflow definitions (social research, video production…) |
| `verification` | Quality gates, domain verification, shadow, report validator |
| `context` | Context building |
| `memory` | Memory persistence |
| `storage` | Persistent storage / DB |
| `observability` | Metrics, logs, events |
| `evals` | Evaluation harnesses |
| `plugins` | Plugin framework |
| `skills` | Skills |

### 3.2 Ứng dụng

| App | Công nghệ |
| --- | --- |
| `apps/api` | FastAPI (`/health/live`, `/health/ready`, `/docs`, `/api/v2/*`; `/api/v1/*` trả 410 Gone) |
| `apps/worker` | Durable background process |
| `apps/cli` | Doctor, architecture, workflow commands |
| `apps/web` | React web client |
| `apps/desktop` | Tauri + React desktop client |

### 3.3 Thư mục hỗ trợ

| Thư mục | Nội dung |
| --- | --- |
| `scripts/` | Architecture checker, verification scripts, phase verifiers, launcher PowerShell |
| `tests/` | Unit, integration, architecture (phase canonical), regression, fakes |
| `docs/` | Event protocol, API contract, ADRs, architecture, video_production plans/reports |
| `artifacts/` | Evidence của các phase (video_production phase_00–27, pipeline_evaluation, final) |
| `third_party/videoclaw/` | Upstream VideoClaw quarantined (MIT), PATCHES, manifest, LICENSE/NOTICE |
| `external/` | Vendored upstream (gitignored) |
| `data/` | Hình ảnh tham chiếu nhân vật (local, chưa track) |
| `configs/` | Cấu hình |
| `models/` | Model definitions |
| `src/` | `data_generator.py` |

### 3.4 Tài liệu gốc tiếng Việt

| File | Nội dung |
| --- | --- |
| `ban_ke_hoach.md` | Kế hoạch triển khai (gốc) |
| `ban_ke_hoach_v2.md` | Kế hoạch v2: multi-agent workspace, migration, security (G1.1–G9.7) |
| `road_map.md` | Roadmap Video Production Platform phases 0–27 |
| `kiến_trúc.md` | Kiến trúc mục tiêu |
| `task.md` / `prompt.md` | Task definition / prompt hiện tại |
| `run.ps1` | Script khởi chạy |

## 4. Kiến trúc Video Production Platform

Pipeline mục tiêu:

```text
VideoClaw-derived Pre-production
        ↓
VideoProductionPackage v1
        ↓
WindAgent Director & Production Layer
        ↓
Google Flow Browser Generation Provider
        ↓
Audio / Post-production / Verification
```

**Phân quyền:**

- `third_party/videoclaw` → ý tưởng, nghiên cứu, screenplay, nhân vật, asset đầu vào
  (quarantined, **không import runtime**)
- `wind_agent` → source of truth, đạo diễn, shot planning, continuity,
  scheduling, approval, cost, retry, recovery, verification
- `ProductionEngine (Blender 4.5 LTS …)` → render 3D scenes/shots qua engine adapter
- `ViMax` → chỉ tham khảo hành vi/kiến trúc (clean-room, không sao chép source)

**Vị trí implementation:**

- `intelligence/windagent_intelligence/video/` → kernel provider-neutral
  (ideation, screenplay, director, shot_planner, continuity, reviewers, audio, assembly)
- engine adapters (`BlenderEngineAdapter` …) → render qua `ProductionEnginePort`
- `tools/windagent_tools/video_probe.py` → ffmpeg/ffprobe media probe

## 5. Trạng thái git hiện tại

### 5.1 Branch

- Branch hiện tại: `fix/phase7-verification-integrity`
- Remote: `origin` → `https://github.com/WindFaculty/WindAgent.git`
- Up-to-date với `origin/fix/phase7-verification-integrity`

### 5.2 Lịch sử commit gần nhất

```text
aa01651 feat(video-production): implement production workspace phases
1753831 feat(phase7): implement secure media asset pipeline (VP7_ASSET_PIPELINE_VERIFIED)
5547a47 feat(phase6): canonical pre-production kernel (VP6_PREPRODUCTION_KERNEL_CANONICAL)
68030cd feat(phase5): characterize VideoClaw (VP5_VIDEOCLAW_BEHAVIOR_CHARACTERIZED)
051e695 feat(phase4): quarantine VideoClaw (VP4_VIDEOCLAW_QUARANTINED)
f7c4f25 test(verification): lock in --no-write verify-only contract
```

### 5.3 Thay đổi tại thời điểm báo cáo

**Đã track, đang sửa đổi:**

- `prompt.md` (thay nội dung task → nhiệm vụ kiểm thử pipeline video)
- `artifacts/architecture_v2_runtime_cutover/phase_13/import_graph.json`
- `docs/video_production/plans/03_phase_08_11_director_layer.md`

**Chưa track (công việc phase 8–27):**

- `artifacts/video_production/phase_08 … phase_27/` + `pipeline_evaluation/` + `remediation/` + `final/`
  (224 JSON, 21 MD, 13 MP4, 2 WAV…; media trong `phase_22` ~31MB — **không commit**)
- `ban_ke_hoach_v2.md`
- `docs/adr/0006-multi-agent-workspace-aggregates.md`
- `docs/architecture/g1_g9_test_matrix.md`, `multi_agent_schema_mapping.md`, `phase9_release_runbook.md`
- `docs/video_production/` (artifact_storage, audio, browser_runtime, cost_quota,
  director, durable_workflow, e2e_poc, flow_human_control, flow_images,
  flow_navigation, flow_video, generation_review, postproduction, release,
  reliability, security, workspace)
- `scripts/verification/evaluate_pipeline.py`
- `data/` (ảnh tham chiếu nhân vật — **không commit**)

## 6. Trạng thái Video Production Platform

### 6.1 Kết quả certification (offline)

`artifacts/video_production/final/final_verdict.md`:

- **Gate:** `VIDEO_PRODUCTION_PLATFORM_VERIFIED`
- **Release gate:** `READY_FOR_CONTROLLED_RELEASE`
- **Verdict:** `PASSED` (offline certification)
- **Điều kiện trước real-credit run:** có Flow session được ủy quyền + human
  takeover plan + ngân sách credits được duyệt (REL-001/003/004, non-blocking
  cho certification offline).

### 6.2 Kết quả pipeline evaluation (2026-08-06)

`artifacts/video_production/pipeline_evaluation/pipeline_evaluation_report.md`:

- **Verdict:** `PIPELINE_PARTIAL_WITH_BLOCKERS` — không có fake PASS
- Script path (brief → concept → screenplay → package) đạt tới `package_assembly`
  nhưng live model path **BLOCKED** (503 MODEL_UNAVAILABLE trên gateway
  `api.tokenrouter.com`), các stage live chạy qua deterministic port và được gắn
  nhãn trung thực `PASS_MOCK_ONLY`
- Chất lượng kịch bản: **79/100 — REQUIRES_REVISION**
- Orchestration F1–F8: happy path `PASS_LIVE`, còn lại `PASS_LOCAL`/`FAILED`
  (F5 missing character ref bị reject đúng theo validator)
- Google Flow: selectors/state machine/browser binary `PASS_LOCAL`;
  live interaction `BROWSER_INTERACTION` (dừng trước submit)
- Media probe: `PASS_LOCAL` (12 images, 4 streams, 8 valid video streams)
- **Blocker chính:** `RC_LIVE_MODEL_UNAVAILABLE` (CRITICAL) — cần route live
  adapter qua OpenAI-compatible transport với model khả dụng

### 6.3 Các phase đã chứng nhận

| Phase | Gate |
| --- | --- |
| 4 | `VP4_VIDEOCLAW_QUARANTINED` |
| 5 | `VP5_VIDEOCLAW_BEHAVIOR_CHARACTERIZED` |
| 6 | `VP6_PREPRODUCTION_KERNEL_CANONICAL` |
| 7 | `VP7_ASSET_PIPELINE_VERIFIED` |
| 27 (final) | `VIDEO_PRODUCTION_PLATFORM_VERIFIED` / `READY_FOR_CONTROLLED_RELEASE` |

## 7. Cách chạy & kiểm tra

```powershell
# Khởi động API (port 8765)
powershell -ExecutionPolicy Bypass -File scripts\dev_api.ps1

# Healthcheck + architecture checker + pytest
powershell -ExecutionPolicy Bypass -File scripts\healthcheck.ps1
$env:UV_CACHE_DIR = "$PWD\.tmp-uv-cache"
uv run python scripts/check_architecture_imports.py
uv run pytest

# Web / Desktop
cd apps/web  && npm ci && npm run dev
cd apps/desktop && npm ci && npm test -- --run && npx tsc --noEmit && npm run build

# Pipeline evaluation
uv run python scripts/verification/evaluate_pipeline.py
```

Yêu cầu: Python 3.10+, `uv`, Node 20+, npm; optional Rust/Tauri cho desktop,
PostgreSQL cho multi-replica profile.

## 8. Kết luận

- Dự án là monolith modular hoàn chỉnh theo Architecture V2, đã cutover khỏi
  backend monolithic cũ.
- Video Production Platform đã hoàn thành phases 0–7 (đã commit) và phases 8–27
  (artifacts chưa commit, chủ yếu JSON/MD evidence + media trong phase_22).
- Release 0.1 đạt certification offline; còn 2 blocker cho real-credit E2E:
  (1) model gateway không routable, (2) cần Flow session được ủy quyền + duyệt credits.
