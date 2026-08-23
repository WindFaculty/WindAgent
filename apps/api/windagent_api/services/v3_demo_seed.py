"""Demo seed profile for the namespaced durable V3 resource authority.

Phase 4: sample mutable seed data is moved OUT of production routers into
this explicit demo profile. It is only installed when the API runs in a
non-production environment (development/test), so production startup never
silently installs demo records.

Contract tests that require samples run in development mode by default and
therefore receive this seed through the lifespan seeding hook.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from windagent_api.services.v3_resource_service import V3ResourceService

# Namespaces used by V3 routers (single source of truth for the demo seed).
NS_PROJECTS = "projects"
NS_EPISODES = "episodes"
NS_EPISODE_ARTIFACTS = "episode_artifacts"
NS_EPISODE_RUNS = "episode_runs"
NS_TASKS = "tasks"
NS_WORKFLOWS = "workflows"
NS_WORKFLOW_RUNS = "workflow_runs"
NS_PROVIDERS = "providers"
NS_MODELS = "models"
NS_ROUTING_RULES = "routing_rules"
NS_ROUTE_LOCKS = "route_locks"
NS_ASSETS = "assets"
NS_ASSET_REVISIONS = "asset_revisions"
NS_REVIEWS = "reviews"
NS_REVIEW_COMMENTS = "review_comments"
NS_REVIEW_DECISIONS = "review_decisions"
NS_WORLD_BIBLES = "world_bibles"
NS_LOCATIONS = "locations"
NS_FACTIONS = "factions"
NS_LORE = "lore"
NS_STORYBOARDS = "storyboards"
NS_SCENES = "scenes"
NS_GENERATION_JOBS = "generation_jobs"
NS_CHARACTERS = "characters"
NS_PRODUCTION_PLANS = "production_plans"
NS_SHOTS = "shots"
NS_PRODUCTION_JOBS = "production_jobs"
NS_DELIVERY_ARTIFACTS = "delivery_artifacts"
NS_AGENT_DEFINITIONS = "agent_definitions"
NS_AGENT_ACTIVITY = "agent_activity"
NS_AGENT_INSTANCES = "agent_instances"
NS_CONVERSATIONS = "conversations"
NS_CONVERSATION_EVENTS = "conversation_events"


# Candidate key fields used to derive a stable resource_id per item.
# Ordering contract:
#   job_id beats artifact_id      -> a production job is keyed by its own
#                                    identity, not by the asset it produced.
#   artifact_id beats revision_id -> episode artifacts sharing one revision
#                                    each keep their own envelope row.
_ID_KEY_FIELDS = (
    "id",
    "run_id",
    "lock_id",
    "job_id",
    "generation_id",
    "event_id",
    "project_id",
    "artifact_id",
    "revision_id",
)


def _resource_id(item: Dict[str, Any]) -> str:
    for field in _ID_KEY_FIELDS:
        if field in item and item[field]:
            return str(item[field])
    raise KeyError(f"No id field found in seed item: {item}")


async def _seed(service: V3ResourceService, namespace: str, items: List[Dict[str, Any]]) -> None:
    """Idempotently seed a namespace. Existing resources are left untouched."""
    for item in items:
        resource_id = _resource_id(item)
        existing = await service.get(namespace, resource_id)
        if existing is None:
            await service.create(namespace, resource_id, item)


async def _seed_storyboards(service: V3ResourceService) -> None:
    """Seed storyboards keyed by episode_id (the router's lookup key)."""
    for item in _STORYBOARDS:
        resource_id = item["episode_id"]
        existing = await service.get(NS_STORYBOARDS, resource_id)
        if existing is None:
            await service.create(NS_STORYBOARDS, resource_id, item)


async def _seed_production_plans(service: V3ResourceService) -> None:
    """Seed production plans keyed by episode_id (the router's lookup key)."""
    for item in _PRODUCTION_PLANS:
        resource_id = item["episode_id"]
        existing = await service.get(NS_PRODUCTION_PLANS, resource_id)
        if existing is None:
            await service.create(NS_PRODUCTION_PLANS, resource_id, item)


async def _seed_delivery_artifacts(service: V3ResourceService) -> None:
    """Seed delivery artifacts keyed by episode_id (the router's lookup key)."""
    for item in _DELIVERY_ARTIFACTS:
        resource_id = item["episode_id"]
        existing = await service.get(NS_DELIVERY_ARTIFACTS, resource_id)
        if existing is None:
            await service.create(NS_DELIVERY_ARTIFACTS, resource_id, item)


def seed_canonical_models(canonical_model_persister: Optional[Callable[[], None]]) -> None:
    """Register the demo canonical models through the injected persister.

    The ORM mapping lives behind the composition adapter
    (``composition.database.make_demo_canonical_model_persister``); this module
    stays application logic with no ORM/database imports.  Idempotent: existing
    rows are left untouched.
    """
    if canonical_model_persister is not None:
        canonical_model_persister()


async def seed_demo_data(
    service: V3ResourceService,
    canonical_model_persister: Optional[Callable[[], None]] = None,
    orchestrator_service=None,
) -> None:
    """Install the demo seed profile (non-production only).

    Phase 4 (P4-R4B): multi-agent execution facts (conversations, agent
    instances/sessions, conversation events) seed into the dedicated multi-agent
    authority through the composed orchestrator seam — never the generic
    ``v3_resources`` namespaces. When no orchestrator is supplied (unit-level
    seeding), those namespaces are left untouched.
    """
    seed_canonical_models(canonical_model_persister)
    await _seed(service, NS_PROJECTS, _PROJECTS)
    await _seed(service, NS_EPISODES, _EPISODES)
    await _seed(service, NS_EPISODE_ARTIFACTS, _EPISODE_ARTIFACTS)
    await _seed(service, NS_EPISODE_RUNS, _EPISODE_RUNS)
    await _seed(service, NS_TASKS, _TASKS)
    await _seed(service, NS_WORKFLOWS, _WORKFLOWS)
    await _seed(service, NS_WORKFLOW_RUNS, _WORKFLOW_RUNS)
    await _seed(service, NS_PROVIDERS, _PROVIDERS)
    await _seed(service, NS_MODELS, _MODELS)
    await _seed(service, NS_ROUTING_RULES, _ROUTING_RULES)
    await _seed(service, NS_ROUTE_LOCKS, _ROUTE_LOCKS)
    await _seed(service, NS_ASSETS, _ASSETS)
    await _seed(service, NS_ASSET_REVISIONS, _ASSET_REVISIONS)
    await _seed(service, NS_REVIEWS, _REVIEWS)
    await _seed(service, NS_REVIEW_COMMENTS, _REVIEW_COMMENTS)
    await _seed(service, NS_REVIEW_DECISIONS, _REVIEW_DECISIONS)
    await _seed(service, NS_WORLD_BIBLES, _WORLD_BIBLES)
    await _seed(service, NS_LOCATIONS, _LOCATIONS)
    await _seed(service, NS_FACTIONS, _FACTIONS)
    await _seed(service, NS_LORE, _LORE)
    await _seed_storyboards(service)
    await _seed(service, NS_SCENES, _SCENES)
    await _seed(service, NS_CHARACTERS, _CHARACTERS)
    await _seed_production_plans(service)
    await _seed(service, NS_SHOTS, _SHOTS)
    await _seed(service, NS_PRODUCTION_JOBS, _PRODUCTION_JOBS)
    await _seed_delivery_artifacts(service)
    await _seed(service, NS_AGENT_DEFINITIONS, _AGENT_DEFINITIONS)
    await _seed(service, NS_AGENT_ACTIVITY, _AGENT_ACTIVITY)
    if orchestrator_service is not None:
        await _seed_multi_agent_demo(orchestrator_service)


async def _seed_multi_agent_demo(orchestrator_service) -> None:
    """Idempotently seed Phase-11 sample conversations/instances/events into the
    dedicated multi-agent authority (P4-R4B)."""
    existing = await orchestrator_service.get_conversation("conv-default-01")
    if existing is None:
        await orchestrator_service.create_conversation(
            conversation_id="conv-default-01",
            title="Core System Architecture Convergence",
            objective="Unify agent workspace, definitions, tasks, and workflows into V3 architecture",
            plan_version_id="pv-01",
        )
    for inst in _AGENT_INSTANCES:
        existing_inst = await orchestrator_service.get_agent_instance(inst["id"])
        if existing_inst is None:
            await orchestrator_service.launch_agent(
                agent_instance_id=inst["id"],
                conversation_id=inst["conversation_id"],
                definition_id=inst["definition_id"],
                canonical_model_id=inst.get("canonical_model_id"),
                runtime_metadata=inst.get("runtime_metadata", {}),
                status="running" if inst.get("status") == "RUNNING" else "idle",
            )
    for evt in _CONVERSATION_EVENTS:
        await orchestrator_service.append_demo_event(
            event_id=evt["event_id"],
            conversation_id=evt["conversation_id"],
            event_type=evt["event_type"],
            payload=evt.get("payload", {}),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────────────────
_PROJECTS: List[Dict[str, Any]] = [
    {
        "id": "proj-cyberpunk-01",
        "name": "Cyberpunk Odyssey 2099",
        "description": "Vũ trụ siêu đô thị ngầm tương lai nơi các hacker và cyborg tìm kiếm ký ức đã mất.",
        "episodes_count": 3,
        "metadata": {"genre": "Cyberpunk / Sci-Fi", "accent": "#38bdf8"},
    },
    {
        "id": "proj-fantasy-02",
        "name": "Biên Niên Sử Vùng Đất Rồng",
        "description": "Cuộc phiêu lưu huyền ảo qua các vương quốc cổ đại nhằm khôi phục viên ngọc nguyên tố.",
        "episodes_count": 2,
        "metadata": {"genre": "High Fantasy / Adventure", "accent": "#34d399"},
    },
    {
        "id": "proj-noir-03",
        "name": "Thám Tử Đêm Sương Mù",
        "description": "Những vụ án bí ẩn tại thành phố cảng những năm 1940 với các âm mưu ngầm.",
        "episodes_count": 1,
        "metadata": {"genre": "Drama / Mystery Noir", "accent": "#fbbf24"},
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Episodes (canonical detail records)
# ─────────────────────────────────────────────────────────────────────────────
_EPISODES: List[Dict[str, Any]] = [
    {
        "id": "ep-cb-001",
        "project_id": "proj-cyberpunk-01",
        "project_name": "Cyberpunk Odyssey 2099",
        "title": "Tập 01: Mã Nguồn Thức Tỉnh",
        "episode_number": 1,
        "description": "Tin tặc trẻ Alex vô tình giải mã một chuỗi tín hiệu bí ẩn từ AI trung tâm của siêu đô thị Neo-Saigon.",
        "state": "SCREENPLAY",
        "current_checkpoint": "SCREENPLAY",
        "current_revision_id": "rev-cb-001-v3",
        "metadata": {"genre": "Cyberpunk / Sci-Fi"},
    },
    {
        "id": "ep-cb-002",
        "project_id": "proj-cyberpunk-01",
        "project_name": "Cyberpunk Odyssey 2099",
        "title": "Tập 02: Mê Cung Neon",
        "episode_number": 2,
        "description": "Bị truy kích bởi các thợ săn tiền thưởng cyborg, Alex phải lẩn trốn vào tầng ngầm 404.",
        "state": "OUTLINE",
        "current_checkpoint": "OUTLINE",
        "current_revision_id": "rev-cb-002-v1",
        "metadata": {"genre": "Cyberpunk / Sci-Fi"},
    },
    {
        "id": "ep-ft-001",
        "project_id": "proj-fantasy-02",
        "project_name": "Biên Niên Sử Vùng Đất Rồng",
        "title": "Tập 01: Tiếng Gọi Rừng Thiêng",
        "episode_number": 1,
        "description": "Người giám hộ trẻ phát hiện dấu vết sinh vật thần thoại thức giấc sau một ngàn năm ngủ say.",
        "state": "LOCKED",
        "current_checkpoint": "LOCKED",
        "current_revision_id": "rev-ft-001-lock",
        "metadata": {"genre": "High Fantasy / Adventure"},
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Episode artifacts & runs
# ─────────────────────────────────────────────────────────────────────────────
_EPISODE_ARTIFACTS: List[Dict[str, Any]] = [
    {
        "artifact_id": "art-idea-01",
        "episode_id": "ep-cb-001",
        "kind": "IdeaCandidateSet",
        "revision_id": "rev-cb-001-v1",
        "content": {
            "selected_idea_id": "idea-1",
            "ideas": [
                {"id": "idea-1", "title": "Mã Nguồn Thức Tỉnh", "premise": "Tin tặc phát hiện AI trung tâm đang cố gắng cảnh báo loài người về một đợt xóa sổ quy mô lớn.", "tone": "Hồi hộp, công nghệ cao, bí ẩn"},
                {"id": "idea-2", "title": "Ký Ức Đánh Cắp", "premise": "Một người máy cảnh sát bắt đầu nhớ lại kiếp sống con người trước khi bị biến đổi.", "tone": "Trầm mặc, triết lý, hành động"},
            ],
        },
    },
    {
        "artifact_id": "art-bible-01",
        "episode_id": "ep-cb-001",
        "kind": "StoryBible",
        "revision_id": "rev-cb-001-v2",
        "content": {
            "characters": [
                {"name": "Alex", "role": "Protagonist", "archetype": "Rebel Hacker"},
                {"name": "Vesper-9", "role": "Companion", "archetype": "Rogue Android"},
            ],
            "world_rules": "Siêu đô thị chia làm 3 tầng: Tầng Thượng lưu trên mây, Tầng Trung cư và Tầng Ngầm 404.",
            "theme": "Ranh giới giữa ý thức nhân tạo và linh hồn con người.",
        },
    },
    {
        "artifact_id": "art-outline-01",
        "episode_id": "ep-cb-001",
        "kind": "EpisodeOutline",
        "revision_id": "rev-cb-001-v2",
        "content": {
            "acts": [
                {"act_number": 1, "title": "Phát Hiện Tín Hiệu", "summary": "Alex quét thấy luồng dữ liệu lạ trong lúc tìm kiếm linh kiện ngầm."},
                {"act_number": 2, "title": "Cuộc Đột Kích", "summary": "Quân đoàn An ninh Tập đoàn ập vào căn hộ bí mật của Alex."},
                {"act_number": 3, "title": "Cú Nhảy Xuống Tầng 404", "summary": "Alex và Vesper-9 thoát khỏi tòa nhà và rơi vào mê cung ngầm."},
            ],
        },
    },
    {
        "artifact_id": "art-screenplay-01",
        "episode_id": "ep-cb-001",
        "kind": "ScreenplayDraft",
        "revision_id": "rev-cb-001-v3",
        "content": {
            "scenes": [
                {"scene_number": 1, "heading": "INT. PHÒNG LÀM VIỆC CỦA ALEX - ĐÊM", "action": "Ánh sáng xanh neon chớp nháy qua cửa sổ ẩm ướt.", "dialogue": [{"speaker": "ALEX", "text": "Chuỗi mã này... nó không được viết bởi con người."}]},
                {"scene_number": 2, "heading": "EXT. HẺM TẦNG 404 - ĐÊM", "action": "Tiếng còi báo động xé toạc màn đêm."},
            ],
        },
    },
]

_EPISODE_RUNS: List[Dict[str, Any]] = [
    {
        "run_id": "run-01",
        "episode_id": "ep-cb-001",
        "checkpoint": "IDEA",
        "status": "COMPLETED",
        "progress_percent": 100,
        "started_at": "2026-08-15T09:00:00Z",
        "completed_at": "2026-08-15T09:01:00Z",
    },
    {
        "run_id": "run-02",
        "episode_id": "ep-cb-001",
        "checkpoint": "STORY_BIBLE",
        "status": "COMPLETED",
        "progress_percent": 100,
        "started_at": "2026-08-15T09:05:00Z",
        "completed_at": "2026-08-15T09:06:30Z",
    },
    {
        "run_id": "run-03",
        "episode_id": "ep-cb-001",
        "checkpoint": "SCREENPLAY",
        "status": "COMPLETED",
        "progress_percent": 100,
        "started_at": "2026-08-15T09:10:00Z",
        "completed_at": "2026-08-15T09:12:00Z",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Tasks
# ─────────────────────────────────────────────────────────────────────────────
_TASKS: List[Dict[str, Any]] = [
    {
        "id": "task-01",
        "conversation_id": "conv-default-01",
        "objective": "Deconstruct target requirement and verify system prerequisites",
        "state": "SUCCEEDED",
        "assigned_agent_instance_id": "inst-orch-01",
        "parent_task_id": None,
        "dependencies": [],
        "concurrency_group": "init",
        "attempts": 1,
        "result": {"status": "verified", "nodes_generated": 3},
        "error": None,
    },
    {
        "id": "task-02",
        "conversation_id": "conv-default-01",
        "objective": "Synthesize backend endpoints and schema validation",
        "state": "RUNNING",
        "assigned_agent_instance_id": "inst-coder-01",
        "parent_task_id": "task-01",
        "dependencies": ["task-01"],
        "concurrency_group": "execution",
        "attempts": 1,
        "result": None,
        "error": None,
    },
    {
        "id": "task-03",
        "conversation_id": "conv-default-01",
        "objective": "Run regression test suite and verify contract invariants",
        "state": "READY",
        "assigned_agent_instance_id": None,
        "parent_task_id": "task-01",
        "dependencies": ["task-02"],
        "concurrency_group": "verification",
        "attempts": 0,
        "result": None,
        "error": None,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Workflows & runs
# ─────────────────────────────────────────────────────────────────────────────
_WORKFLOWS: List[Dict[str, Any]] = [
    {
        "id": "wf-kronos-01",
        "name": "Kronos Verification Pipeline",
        "description": "End-to-end pipeline for validating multi-model contracts and running deterministic checks.",
        "type": "ML Pipeline",
        "trigger": "Scheduled",
        "owner": "Researcher",
        "tags": ["ML", "Automation", "Scheduled", "High Priority"],
        "steps": [
            {"id": "step-01", "name": "Prepare Dataset", "description": "Download and validate benchmark fixtures", "tool_name": "fixture_loader", "timeout_seconds": 120},
            {"id": "step-02", "name": "Load Model Checkpoint", "description": "Acquire route lock and load model adapter", "tool_name": "model_loader", "timeout_seconds": 180},
            {"id": "step-03", "name": "Execute Deterministic Tests", "description": "Run contract assertion suite", "tool_name": "test_runner", "timeout_seconds": 300},
            {"id": "step-04", "name": "Generate Synthesis Report", "description": "Synthesize results into structured artifact", "tool_name": "report_generator", "timeout_seconds": 120},
        ],
        "acceptance_criteria": ["All contract assertions pass with zero failures", "Synthesis report checksum verified"],
    },
    {
        "id": "wf-release-qa-01",
        "name": "Release QA + Verification",
        "description": "Trigger production verification checks, compile bundle components, execute integration test suites.",
        "type": "DevOps",
        "trigger": "Manual",
        "owner": "Coder",
        "tags": ["DevOps", "Manual", "Deployments"],
        "steps": [
            {"id": "step-01", "name": "Lint & Typecheck", "description": "Run linter and TypeScript compiler checks", "tool_name": "tsc_linter", "timeout_seconds": 120},
            {"id": "step-02", "name": "Execute Contract Tests", "description": "Run all domain contract tests", "tool_name": "pytest_contracts", "timeout_seconds": 300},
            {"id": "step-03", "name": "Build Bundle Artifacts", "description": "Generate frontend and backend bundles", "tool_name": "bundler", "timeout_seconds": 240},
            {"id": "step-04", "name": "Rollback Plan Verification", "description": "Confirm rollback hooks and signatures", "tool_name": "rollback_verifier", "timeout_seconds": 60},
        ],
        "acceptance_criteria": ["TypeScript clean build", "Contract test suite 100% pass"],
    },
]

_WORKFLOW_RUNS: List[Dict[str, Any]] = [
    {
        "id": "run-kronos-01",
        "workflow_id": "wf-kronos-01",
        "workflow_name": "Kronos Verification Pipeline",
        "status": "RUNNING",
        "triggered_by": "Researcher",
        "steps": [
            {"id": "srun-01", "run_id": "run-kronos-01", "step_id": "step-01", "step_name": "Prepare Dataset", "status": "COMPLETED", "error": None, "attempts": 1},
            {"id": "srun-02", "run_id": "run-kronos-01", "step_id": "step-02", "step_name": "Load Model Checkpoint", "status": "COMPLETED", "error": None, "attempts": 1},
            {"id": "srun-03", "run_id": "run-kronos-01", "step_id": "step-03", "step_name": "Execute Deterministic Tests", "status": "RUNNING", "error": None, "attempts": 1},
            {"id": "srun-04", "run_id": "run-kronos-01", "step_id": "step-04", "step_name": "Generate Synthesis Report", "status": "PENDING", "error": None, "attempts": 0},
        ],
        "error": None,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Providers
# ─────────────────────────────────────────────────────────────────────────────
_PROVIDERS: List[Dict[str, Any]] = [
    {
        "id": "google",
        "display_name": "Google AI",
        "type": "google",
        "status": "healthy",
        "capabilities": ["chat", "code", "vision", "audio", "tools", "reasoning"],
        "website_url": "https://ai.google.dev",
        "endpoints": [
            {"id": "ep-google-ai-studio", "provider_id": "google", "name": "Google AI Studio Gateway", "base_url": "https://generativelanguage.googleapis.com/v1beta", "status": "healthy", "latency_ms": 28.4, "rate_limit_rpm": 1000, "rate_limit_tpm": 4000000, "credential_reference": "env:GEMINI_API_KEY", "is_configured": True, "models_count": 2, "last_checked_at": "2026-08-15T08:00:00Z"},
            {"id": "ep-google-vertex", "provider_id": "google", "name": "Google Cloud Vertex AI", "base_url": "https://us-central1-aiplatform.googleapis.com/v1", "status": "healthy", "latency_ms": 34.2, "rate_limit_rpm": 3000, "rate_limit_tpm": 10000000, "credential_reference": "gcp:service_account", "is_configured": True, "models_count": 2, "last_checked_at": "2026-08-15T08:00:00Z"},
        ],
        "models_count": 2,
        "has_credentials": True,
    },
    {
        "id": "anthropic",
        "display_name": "Anthropic",
        "type": "anthropic",
        "status": "healthy",
        "capabilities": ["chat", "code", "vision", "tools", "reasoning"],
        "website_url": "https://anthropic.com",
        "endpoints": [
            {"id": "ep-anthropic-direct", "provider_id": "anthropic", "name": "Anthropic Messages API", "base_url": "https://api.anthropic.com/v1", "status": "healthy", "latency_ms": 42.1, "rate_limit_rpm": 500, "rate_limit_tpm": 200000, "credential_reference": "env:ANTHROPIC_API_KEY", "is_configured": True, "models_count": 2, "last_checked_at": "2026-08-15T08:00:00Z"},
        ],
        "models_count": 2,
        "has_credentials": True,
    },
    {
        "id": "openai",
        "display_name": "OpenAI",
        "type": "openai",
        "status": "healthy",
        "capabilities": ["chat", "code", "vision", "audio", "tools", "reasoning"],
        "website_url": "https://openai.com",
        "endpoints": [
            {"id": "ep-openai-direct", "provider_id": "openai", "name": "OpenAI Chat API", "base_url": "https://api.openai.com/v1", "status": "healthy", "latency_ms": 38.9, "rate_limit_rpm": 1000, "rate_limit_tpm": 500000, "credential_reference": "env:OPENAI_API_KEY", "is_configured": True, "models_count": 2, "last_checked_at": "2026-08-15T08:00:00Z"},
        ],
        "models_count": 2,
        "has_credentials": True,
    },
    {
        "id": "deepseek",
        "display_name": "DeepSeek",
        "type": "deepseek",
        "status": "healthy",
        "capabilities": ["chat", "code", "reasoning"],
        "website_url": "https://deepseek.com",
        "endpoints": [
            {"id": "ep-deepseek-direct", "provider_id": "deepseek", "name": "DeepSeek Open API", "base_url": "https://api.deepseek.com/v1", "status": "healthy", "latency_ms": 65.3, "rate_limit_rpm": 300, "rate_limit_tpm": 100000, "credential_reference": "env:DEEPSEEK_API_KEY", "is_configured": True, "models_count": 1, "last_checked_at": "2026-08-15T08:00:00Z"},
        ],
        "models_count": 1,
        "has_credentials": True,
    },
    {
        "id": "openrouter",
        "display_name": "OpenRouter Multi-Provider",
        "type": "openrouter",
        "status": "healthy",
        "capabilities": ["chat", "code", "vision", "tools", "reasoning"],
        "website_url": "https://openrouter.ai",
        "endpoints": [
            {"id": "ep-openrouter-main", "provider_id": "openrouter", "name": "OpenRouter Universal Gateway", "base_url": "https://openrouter.ai/api/v1", "status": "healthy", "latency_ms": 52.0, "rate_limit_rpm": 2000, "rate_limit_tpm": 1000000, "credential_reference": "env:OPENROUTER_API_KEY", "is_configured": True, "models_count": 2, "last_checked_at": "2026-08-15T08:00:00Z"},
        ],
        "models_count": 2,
        "has_credentials": True,
    },
    {
        "id": "ollama",
        "display_name": "Ollama Local Runtime",
        "type": "ollama",
        "status": "healthy",
        "capabilities": ["code", "chat", "tools"],
        "website_url": "http://localhost:11434",
        "endpoints": [
            {"id": "ep-ollama-local", "provider_id": "ollama", "name": "Localhost Ollama Server", "base_url": "http://127.0.0.1:11434", "status": "healthy", "latency_ms": 4.2, "rate_limit_rpm": 10000, "rate_limit_tpm": 10000000, "credential_reference": "local:none", "is_configured": True, "models_count": 1, "last_checked_at": "2026-08-15T08:00:00Z"},
        ],
        "models_count": 1,
        "has_credentials": True,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────
_MODELS: List[Dict[str, Any]] = [
    {
        "id": "google/gemini-1.5-pro",
        "name": "Gemini 1.5 Pro",
        "vendor": "Google",
        "family": "Gemini",
        "description": "Flagship multimodal model with 2M token context window for complex reasoning and analysis.",
        "context_window": 2000000,
        "max_output_tokens": 8192,
        "capabilities": ["chat", "code", "vision", "audio", "tools", "reasoning"],
        "modalities": ["multimodal->text"],
        "is_local": False,
        "is_active": True,
        "pricing": {"input_per_million": 3.5, "output_per_million": 10.5},
        "bindings": [
            {"id": "bind-gemini-pro-studio", "endpoint_id": "ep-google-ai-studio", "provider_id": "google", "provider_model_id": "gemini-1.5-pro-latest", "equivalence_level": "exact", "confidence": 1.0, "is_active": True},
            {"id": "bind-gemini-pro-vertex", "endpoint_id": "ep-google-vertex", "provider_id": "google", "provider_model_id": "gemini-1.5-pro-002", "equivalence_level": "exact", "confidence": 1.0, "is_active": True},
        ],
        "benchmarks": {"MMLU": 85.9, "HumanEval": 84.1, "MATH": 67.7},
    },
    {
        "id": "google/gemini-1.5-flash",
        "name": "Gemini 1.5 Flash",
        "vendor": "Google",
        "family": "Gemini",
        "description": "High-frequency lightweight multimodal model optimized for speed and cost-efficiency.",
        "context_window": 1000000,
        "max_output_tokens": 8192,
        "capabilities": ["chat", "code", "vision", "tools"],
        "modalities": ["multimodal->text"],
        "is_local": False,
        "is_active": True,
        "pricing": {"input_per_million": 0.075, "output_per_million": 0.3},
        "bindings": [
            {"id": "bind-gemini-flash-studio", "endpoint_id": "ep-google-ai-studio", "provider_id": "google", "provider_model_id": "gemini-1.5-flash-latest", "equivalence_level": "exact", "confidence": 1.0, "is_active": True},
        ],
        "benchmarks": {"MMLU": 78.9, "HumanEval": 74.3, "MATH": 54.9},
    },
    {
        "id": "anthropic/claude-3-5-sonnet",
        "name": "Claude 3.5 Sonnet",
        "vendor": "Anthropic",
        "family": "Claude",
        "description": "Leading frontier intelligence for coding, nuance, and agent orchestration.",
        "context_window": 200000,
        "max_output_tokens": 8192,
        "capabilities": ["chat", "code", "vision", "tools", "reasoning"],
        "modalities": ["multimodal->text"],
        "is_local": False,
        "is_active": True,
        "pricing": {"input_per_million": 3.0, "output_per_million": 15.0},
        "bindings": [
            {"id": "bind-claude-sonnet-direct", "endpoint_id": "ep-anthropic-direct", "provider_id": "anthropic", "provider_model_id": "claude-3-5-sonnet-20241022", "equivalence_level": "exact", "confidence": 1.0, "is_active": True},
            {"id": "bind-claude-sonnet-openrouter", "endpoint_id": "ep-openrouter-main", "provider_id": "openrouter", "provider_model_id": "anthropic/claude-3.5-sonnet", "equivalence_level": "exact", "confidence": 1.0, "is_active": True},
        ],
        "benchmarks": {"MMLU": 88.7, "HumanEval": 93.7, "MATH": 78.3},
    },
    {
        "id": "anthropic/claude-3-haiku",
        "name": "Claude 3 Haiku",
        "vendor": "Anthropic",
        "family": "Claude",
        "description": "Fastest, most compact model for near-instant responses.",
        "context_window": 200000,
        "max_output_tokens": 4096,
        "capabilities": ["chat", "code", "tools"],
        "modalities": ["text->text"],
        "is_local": False,
        "is_active": True,
        "pricing": {"input_per_million": 0.25, "output_per_million": 1.25},
        "bindings": [
            {"id": "bind-claude-haiku-direct", "endpoint_id": "ep-anthropic-direct", "provider_id": "anthropic", "provider_model_id": "claude-3-haiku-20240307", "equivalence_level": "exact", "confidence": 1.0, "is_active": True},
        ],
        "benchmarks": {"MMLU": 75.2, "HumanEval": 75.9, "MATH": 40.2},
    },
    {
        "id": "openai/gpt-4o",
        "name": "GPT-4o",
        "vendor": "OpenAI",
        "family": "GPT-4",
        "description": "Omni multimodal model integrating text, vision, and audio capabilities.",
        "context_window": 128000,
        "max_output_tokens": 4096,
        "capabilities": ["chat", "code", "vision", "audio", "tools"],
        "modalities": ["multimodal->multimodal"],
        "is_local": False,
        "is_active": True,
        "pricing": {"input_per_million": 2.5, "output_per_million": 10.0},
        "bindings": [
            {"id": "bind-gpt4o-direct", "endpoint_id": "ep-openai-direct", "provider_id": "openai", "provider_model_id": "gpt-4o", "equivalence_level": "exact", "confidence": 1.0, "is_active": True},
        ],
        "benchmarks": {"MMLU": 88.7, "HumanEval": 90.2, "MATH": 76.6},
    },
    {
        "id": "openai/gpt-4o-mini",
        "name": "GPT-4o mini",
        "vendor": "OpenAI",
        "family": "GPT-4",
        "description": "Cost-efficient small model for text and vision tasks.",
        "context_window": 128000,
        "max_output_tokens": 4096,
        "capabilities": ["chat", "code", "vision", "tools"],
        "modalities": ["multimodal->text"],
        "is_local": False,
        "is_active": True,
        "pricing": {"input_per_million": 0.15, "output_per_million": 0.6},
        "bindings": [
            {"id": "bind-gpt4o-mini-direct", "endpoint_id": "ep-openai-direct", "provider_id": "openai", "provider_model_id": "gpt-4o-mini", "equivalence_level": "exact", "confidence": 1.0, "is_active": True},
        ],
        "benchmarks": {"MMLU": 82.0, "HumanEval": 87.2, "MATH": 70.2},
    },
    {
        "id": "deepseek/deepseek-r1",
        "name": "DeepSeek R1",
        "vendor": "DeepSeek",
        "family": "DeepSeek",
        "description": "Advanced open-weights reasoning model with chain-of-thought verification.",
        "context_window": 128000,
        "max_output_tokens": 8192,
        "capabilities": ["chat", "code", "reasoning"],
        "modalities": ["text->text"],
        "is_local": False,
        "is_active": True,
        "pricing": {"input_per_million": 0.55, "output_per_million": 2.19},
        "bindings": [
            {"id": "bind-deepseek-r1-direct", "endpoint_id": "ep-deepseek-direct", "provider_id": "deepseek", "provider_model_id": "deepseek-reasoner", "equivalence_level": "exact", "confidence": 1.0, "is_active": True},
            {"id": "bind-deepseek-r1-openrouter", "endpoint_id": "ep-openrouter-main", "provider_id": "openrouter", "provider_model_id": "deepseek/deepseek-r1", "equivalence_level": "exact", "confidence": 1.0, "is_active": True},
        ],
        "benchmarks": {"MMLU": 90.8, "HumanEval": 92.3, "MATH": 97.3},
    },
    {
        "id": "ollama/qwen2.5-coder",
        "name": "Qwen 2.5 Coder (Local)",
        "vendor": "Alibaba",
        "family": "Qwen",
        "description": "Local code intelligence running offline via Ollama runtime.",
        "context_window": 32768,
        "max_output_tokens": 4096,
        "capabilities": ["code", "chat", "tools"],
        "modalities": ["text->text"],
        "is_local": True,
        "is_active": True,
        "pricing": {"input_per_million": 0.0, "output_per_million": 0.0},
        "bindings": [
            {"id": "bind-ollama-qwen-coder", "endpoint_id": "ep-ollama-local", "provider_id": "ollama", "provider_model_id": "qwen2.5-coder:latest", "equivalence_level": "exact", "confidence": 1.0, "is_active": True},
        ],
        "benchmarks": {"MMLU": 74.5, "HumanEval": 86.4, "MATH": 62.1},
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Routing rules & locks
# ─────────────────────────────────────────────────────────────────────────────
_ROUTING_RULES: List[Dict[str, Any]] = [
    {
        "id": "rule-planner-core",
        "name": "Planner & Orchestrator Master",
        "version": 1,
        "enabled": True,
        "priority": 10,
        "canonical_model_id": "anthropic/claude-3-5-sonnet",
        "fallback_model_id": "google/gemini-1.5-pro",
        "final_fallback_model_id": "openai/gpt-4o",
        "description": "High-reasoning routing for Coordinator, Planner, and Episode Orchestrators.",
        "agent_types": ["Coordinator", "Planner", "Director"],
        "required_capabilities": ["reasoning", "tools"],
        "min_context_tokens": 10000,
        "primary_usage": 82.0,
        "fallback_usage": 18.0,
        "success_rate": 99.8,
        "avg_latency_ms": 42.0,
    },
    {
        "id": "rule-code-agent",
        "name": "Code & Script Generation",
        "version": 1,
        "enabled": True,
        "priority": 10,
        "canonical_model_id": "anthropic/claude-3-5-sonnet",
        "fallback_model_id": "deepseek/deepseek-r1",
        "final_fallback_model_id": "ollama/qwen2.5-coder",
        "description": "Specialized coding, AST analysis, and tool-use scripts.",
        "agent_types": ["Coder", "ScriptWriter", "Worker"],
        "required_capabilities": ["code", "tools"],
        "primary_usage": 76.5,
        "fallback_usage": 23.5,
        "success_rate": 99.1,
        "avg_latency_ms": 38.4,
    },
    {
        "id": "rule-multimodal-vision",
        "name": "Visual & Storyboard Analysis",
        "version": 1,
        "enabled": True,
        "priority": 20,
        "canonical_model_id": "google/gemini-1.5-pro",
        "fallback_model_id": "openai/gpt-4o",
        "final_fallback_model_id": "google/gemini-1.5-flash",
        "description": "Massive context multimodal processing for video shots and asset review.",
        "agent_types": ["VisualInspector", "Critic", "AssetEvaluator"],
        "required_capabilities": ["vision"],
        "requires_vision": True,
        "primary_usage": 90.0,
        "fallback_usage": 10.0,
        "success_rate": 99.5,
        "avg_latency_ms": 29.0,
    },
    {
        "id": "rule-fast-classification",
        "name": "Lightweight Intent & Tool Filtering",
        "version": 1,
        "enabled": True,
        "priority": 50,
        "canonical_model_id": "google/gemini-1.5-flash",
        "fallback_model_id": "anthropic/claude-3-haiku",
        "final_fallback_model_id": "openai/gpt-4o-mini",
        "description": "Low-latency routing for simple turn classifications and status extractions.",
        "cost_classes": ["economy"],
        "primary_usage": 95.0,
        "fallback_usage": 5.0,
        "success_rate": 99.9,
        "avg_latency_ms": 14.2,
    },
    {
        "id": "rule-local-offline",
        "name": "Offline & Privacy-Locked Tasks",
        "version": 1,
        "enabled": True,
        "priority": 0,
        "canonical_model_id": "ollama/qwen2.5-coder",
        "description": "Offline local inference fallback when cloud network is disabled.",
        "requires_local": True,
        "primary_usage": 100.0,
        "fallback_usage": 0.0,
        "success_rate": 100.0,
        "avg_latency_ms": 5.0,
    },
    {
        "id": "rule-default-fallback",
        "name": "Default Fallback Routing",
        "version": 1,
        "enabled": True,
        "priority": 100,
        "canonical_model_id": "anthropic/claude-3-5-sonnet",
        "fallback_model_id": "google/gemini-1.5-pro",
        "final_fallback_model_id": "openai/gpt-4o",
        "description": "Catch-all fallback for roles not matched by a more specific rule.",
        "primary_usage": 85.0,
        "fallback_usage": 15.0,
        "success_rate": 99.4,
        "avg_latency_ms": 38.0,
    },
]

_ROUTE_LOCKS: List[Dict[str, Any]] = [
    {
        "lock_id": "lock-conv-main-01",
        "scope": "conversation",
        "scope_id": "conv-cyberpunk-001",
        "canonical_model_id": "anthropic/claude-3-5-sonnet",
        "status": "active",
        "routing_snapshot": {
            "rule_id": "rule-planner-core",
            "rule_version": 1,
            "canonical_model_id": "anthropic/claude-3-5-sonnet",
            "reason": "Matched agent_type Coordinator with required capabilities [reasoning, tools]",
        },
    }
]

# ─────────────────────────────────────────────────────────────────────────────
# Assets & revisions
# ─────────────────────────────────────────────────────────────────────────────
_ASSETS: List[Dict[str, Any]] = [
    {
        "id": "asset-concept-cb-001-01",
        "name": "Concept Art - Phát Hiện Tín Hiệu",
        "type": "IMAGE",
        "episode_id": "ep-cb-001",
        "project_id": "proj-cyberpunk-01",
        "scene_id": "scene-cb-001-01",
        "character_id": None,
        "current_revision_id": "rev-asset-001-v1",
        "status": "DRAFT",
        "provenance": {
            "source": "GENERATED",
            "generator": "Imagen",
            "model": "imagen-3.5-generate",
            "prompt": "Cyberpunk interior, holographic keyboard, neon blue light through rain-streaked window, high contrast, cinematic, neo-noir",
            "reference_ids": ["char-kaelen-01", "loc-tầng-404-01"],
            "job_id": None,
            "content_hash": "scene-cb-001-01-concept-v1",
            "parent_revision_id": None,
        },
    },
]

_ASSET_REVISIONS: List[Dict[str, Any]] = [
    {
        "revision_id": "rev-asset-001-v1",
        "asset_id": "asset-concept-cb-001-01",
        "version": 1,
        "status": "DRAFT",
        "media_url": None,
        "provenance": {
            "source": "GENERATED",
            "generator": "Imagen",
            "model": "imagen-3.5-generate",
            "prompt": "Cyberpunk interior, holographic keyboard, neon blue light",
            "reference_ids": [],
            "job_id": None,
            "content_hash": "scene-cb-001-01-concept-v1",
            "parent_revision_id": None,
        },
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Reviews
# ─────────────────────────────────────────────────────────────────────────────
_REVIEWS: List[Dict[str, Any]] = [
    {
        "id": "review-sb-001",
        "subject_type": "storyboard",
        "subject_id": "sb-cb-001",
        "episode_id": "ep-cb-001",
        "project_id": "proj-cyberpunk-01",
        "status": "PENDING",
    },
    {
        "id": "review-screen-001",
        "subject_type": "screenplay",
        "subject_id": "rev-cb-001-v3",
        "episode_id": "ep-cb-001",
        "project_id": "proj-cyberpunk-01",
        "status": "APPROVED",
    },
]

_REVIEW_COMMENTS: List[Dict[str, Any]] = [
    {
        "id": "cmt-001",
        "review_id": "review-sb-001",
        "author": "Director Agent",
        "role": "Director Agent",
        "text": "Cảnh mở đầu cần ánh sáng neon mạnh hơn để nhấn mạnh bầu không khí cyberpunk neo-noir. Góc máy hiện tại quá thẳng đứng.",
    },
    {
        "id": "cmt-002",
        "review_id": "review-sb-001",
        "author": "Producer Agent",
        "role": "Producer Agent",
        "text": "Thời lượng Scene 3 (190s) quá dài cho một đoạn đối thoại. Cân nhắc chia làm 2 phân cảnh.",
    },
]

_REVIEW_DECISIONS: List[Dict[str, Any]] = [
    {
        "id": "dec-screen-001",
        "review_id": "review-screen-001",
        "decision": "APPROVED",
        "revision_id": "rev-cb-001-v3",
        "expected_version": 3,
        "reason": "Bản thảo đáp ứng yêu cầu kịch tính và độ dài của tập phim.",
        "decided_by": "Director Agent",
    }
]

# ─────────────────────────────────────────────────────────────────────────────
# World bible
# ─────────────────────────────────────────────────────────────────────────────
_WORLD_BIBLES: List[Dict[str, Any]] = [
    {
        "project_id": "proj-cyberpunk-01",
        "world_name": "Neo-Saigon 2099",
        "setting_summary": "Siêu đô thị chia làm 3 tầng: Tầng Thượng lưu trên đỉnh mây, Tầng Trung cư nhộn nhịp và Tầng Ngầm 404 của các tin tặc và phế nhân.",
        "core_theme": "Ranh giới giữa ý thức nhân tạo và linh hồn con người trong thời đại dữ liệu thống trị tất cả.",
        "rules": [
            "AI được coi là công cụ pháp lý, không phải thực thể.",
            "Tầng Ngầm 404 là vùng tự trị, ngoài tầm kiểm soát của Apex Cortex.",
            "Mọi giao dịch đều được lưu trong blockchain phi tập trung.",
        ],
        "timeline_era": "Hậu-Sụp Đổ Tài Chính Toàn Cầu năm 2071",
    },
]

_LOCATIONS: List[Dict[str, Any]] = [
    {"id": "loc-tầng-404-01", "project_id": "proj-cyberpunk-01", "name": "Tầng Ngầm 404", "type": "Exterior", "description": "Khu vực ngầm hỗn loạn bên dưới thành phố, nơi ẩn náu của tin tặc và những người ngoài vòng pháp luật.", "atmosphere": "Tối tăm, ẩm ướt, đèn neon, tiếng máy móc vang vọng"},
    {"id": "loc-apex-tower-01", "project_id": "proj-cyberpunk-01", "name": "Apex Cortex Tower", "type": "Interior", "description": "Trụ sở tập đoàn Apex Cortex cao 200 tầng, vươn lên khỏi tầng mây.", "atmosphere": "Lạnh lùng, vô trùng, ánh sáng trắng sterile, an ninh dày đặc"},
]

_FACTIONS: List[Dict[str, Any]] = [
    {"id": "fac-apex-01", "project_id": "proj-cyberpunk-01", "name": "Apex Cortex Corp", "ideology": "Kiểm soát thông tin = kiểm soát nhân loại", "influence_level": 95, "description": "Tập đoàn công nghệ độc quyền thống trị nền kinh tế dữ liệu toàn cầu."},
    {"id": "fac-ghost-net-01", "project_id": "proj-cyberpunk-01", "name": "Ghost Net Collective", "ideology": "Thông tin tự do, không có quyền lực tập trung", "influence_level": 35, "description": "Liên minh tin tặc hoạt động trong Tầng Ngầm 404, chiến đấu cho quyền riêng tư kỹ thuật số."},
]

_LORE: List[Dict[str, Any]] = [
    {"id": "lore-collapse-01", "project_id": "proj-cyberpunk-01", "title": "Sụp Đổ Tài Chính 2071", "category": "History", "content": "Cuộc khủng hoảng kinh tế toàn cầu xảy ra khi các AI giao dịch tần số cao sụp đổ đồng loạt, xóa sổ 60% tài sản số toàn thế giới trong 3 giờ."},
]

# ─────────────────────────────────────────────────────────────────────────────
# Storyboard & scenes
# ─────────────────────────────────────────────────────────────────────────────
_STORYBOARDS: List[Dict[str, Any]] = [
    {
        "id": "sb-cb-001",
        "episode_id": "ep-cb-001",
        "source_screenplay_revision_id": "rev-cb-001-v3",
        "status": "DRAFT",
    }
]

_SCENES: List[Dict[str, Any]] = [
    {
        "id": "scene-cb-001-01",
        "storyboard_id": "sb-cb-001",
        "episode_id": "ep-cb-001",
        "scene_number": 1,
        "title": "Phát Hiện Tín Hiệu (COLD OPEN)",
        "status": "CONCEPT_READY",
        "script_text": "INT. PHÒNG LÀM VIỆC CỦA ALEX - ĐÊM. Ánh sáng xanh neon chớp nháy qua cửa sổ ẩm ướt. Tiếng mưa axit rơi lộp bộp. Alex gõ liên hồi trên bàn phím holographic.",
        "duration_seconds": 150,
        "location": "INT. Phòng làm việc Alex - Đêm",
        "character_ids": ["char-kaelen-01"],
        "concept_image_url": None,
        "source_screenplay_revision_id": "rev-cb-001-v3",
    },
    {
        "id": "scene-cb-001-02",
        "storyboard_id": "sb-cb-001",
        "episode_id": "ep-cb-001",
        "scene_number": 2,
        "title": "Cuộc Đột Kích",
        "status": "DRAFT",
        "script_text": "EXT. HẺM TẦNG 404 - ĐÊM. Tiếng còi báo động xé toạc màn đêm. Đèn pha từ các phi thuyền tuần tra quét qua những bức tường phủ đầy rêu điện tử.",
        "duration_seconds": 105,
        "location": "EXT. Hẻm Tầng 404 - Đêm",
        "character_ids": ["char-kaelen-01", "char-nova-01"],
        "concept_image_url": None,
        "source_screenplay_revision_id": "rev-cb-001-v3",
    },
    {
        "id": "scene-cb-001-03",
        "storyboard_id": "sb-cb-001",
        "episode_id": "ep-cb-001",
        "scene_number": 3,
        "title": "Đối Mặt Sylas",
        "status": "DRAFT",
        "script_text": "INT. VĂN PHÒNG APEX CORTEX - ĐÊM. Sylas đứng trước cửa sổ toàn kính nhìn xuống thành phố. Alex tiến vào từ phía sau.",
        "duration_seconds": 190,
        "location": "INT. Văn phòng Apex Cortex - Đêm",
        "character_ids": ["char-kaelen-01", "char-sylas-01"],
        "concept_image_url": None,
        "source_screenplay_revision_id": "rev-cb-001-v3",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Characters
# ─────────────────────────────────────────────────────────────────────────────
_CHARACTERS: List[Dict[str, Any]] = [
    {
        "id": "char-kaelen-01",
        "project_id": "proj-cyberpunk-01",
        "identity": {"name": "Kaelen Vance", "role": "Protagonist", "biography": "Cựu đặc nhiệm bị bỏ lại tại các phân khu Outer Rim. Dựa vào sự chính xác chiến thuật và nghi ngờ chính quyền để sinh tồn. Dù vẻ ngoài lạnh lùng, sở hữu la bàn đạo đức kiên định."},
        "psychology": {"dominant_trait": "Stoic", "flaw": "Distrustful", "alignment_score": 75},
        "visual_profile": {"avatar_url": None, "banner_url": None, "physical_description": "Tóc bạc, mắt xám, vóc dáng rắn chắc", "style_notes": "Áo khoác dài tối màu, găng tay chiến thuật"},
        "voice_profile": {"voice_model_id": "ELEVEN_GRIT_02", "voice_style": "Trầm ấm, đanh thép, quyết đoán", "sample_lines": ["Không ai được bỏ lại.", "Chiến thuật trước, cảm xúc sau."]},
        "relationships": [
            {"target_character_id": "char-nova-01", "target_name": "Nova Tink", "relationship_type": "Ally"},
            {"target_character_id": "char-sylas-01", "target_name": "Sylas Thorne", "relationship_type": "Rival"},
        ],
    },
    {
        "id": "char-nova-01",
        "project_id": "proj-cyberpunk-01",
        "identity": {"name": "Nova Tink", "role": "Supporting", "biography": "Kỹ sư cơ khí thiên tài với tính cách lập dị. Có khả năng biến phế liệu công nghệ thành vũ khí thông minh trong thời gian kỷ lục."},
        "psychology": {"dominant_trait": "Chaotic Good", "flaw": "Impulsive", "alignment_score": 60},
        "visual_profile": {"avatar_url": None, "banner_url": None, "physical_description": "Tóc đỏ ngắn, mắt xanh lá, ngón tay nhanh thoăn thoắt", "style_notes": "Áo liền thân kỹ thuật số, găng tay công cụ"},
        "voice_profile": {"voice_model_id": "ELEVEN_ENERGETIC_01", "voice_style": "Nhanh, hào hứng, tự nhiên", "sample_lines": ["Xong rồi! Thật ra nhanh hơn tôi nghĩ.", "Đừng chạm vào cái đó — trừ khi bạn muốn bị điện giật."]},
        "relationships": [
            {"target_character_id": "char-kaelen-01", "target_name": "Kaelen Vance", "relationship_type": "Ally"},
        ],
    },
    {
        "id": "char-sylas-01",
        "project_id": "proj-cyberpunk-01",
        "identity": {"name": "Sylas Thorne", "role": "Antagonist", "biography": "Giám đốc điều hành tập đoàn Apex Cortex. Thao túng thị trường thông tin để củng cố quyền lực. Tin rằng sự hỗn loạn là công cụ, không phải mối đe dọa."},
        "psychology": {"dominant_trait": "Manipulative", "flaw": "Arrogant", "alignment_score": 15},
        "visual_profile": {"avatar_url": None, "banner_url": None, "physical_description": "Tóc đen bóng, khuôn mặt sắc lạnh, ăn mặc hoàn hảo theo phong cách corporate", "style_notes": "Vest cao cấp, cà vạt bạch kim, nhẫn Apex Cortex"},
        "voice_profile": {"voice_model_id": "ELEVEN_COLD_01", "voice_style": "Lạnh lùng, thong thả, thao túng", "sample_lines": ["Tất cả đều có giá. Kể cả lý tưởng của anh.", "Hỗn loạn? Không. Đây là thiết kế."]},
        "relationships": [
            {"target_character_id": "char-kaelen-01", "target_name": "Kaelen Vance", "relationship_type": "Rival"},
        ],
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Production
# ─────────────────────────────────────────────────────────────────────────────
_PRODUCTION_PLANS: List[Dict[str, Any]] = [
    {
        "id": "plan-ep-cb-001",
        "episode_id": "ep-cb-001",
        "project_id": "proj-cyberpunk-01",
        "screenplay_revision_id": "rev-cb-001-v3",
        "storyboard_revision_id": "sb-cb-001",
        "character_references": ["char-kaelen-01", "char-nova-01", "char-sylas-01"],
        "asset_references": ["asset-concept-cb-001-01"],
        "status": "ACTIVE",
        "progress_percent": 35,
    }
]

_SHOTS: List[Dict[str, Any]] = [
    {
        "id": "shot-cb-001-01",
        "episode_id": "ep-cb-001",
        "production_plan_id": "plan-ep-cb-001",
        "scene_id": "scene-cb-001-01",
        "shot_number": 1,
        "camera_movement": "Slow Dolly In",
        "focal_length": "50mm Anamorphic",
        "status": "RENDERED",
        "duration_seconds": 70,
        "audio_asset_id": "asset-audio-01",
        "animation_asset_id": "asset-anim-01",
        "render_asset_id": "asset-render-01",
    },
    {
        "id": "shot-cb-001-02",
        "episode_id": "ep-cb-001",
        "production_plan_id": "plan-ep-cb-001",
        "scene_id": "scene-cb-001-01",
        "shot_number": 2,
        "camera_movement": "Over-the-shoulder Pan",
        "focal_length": "35mm",
        "status": "RENDER_PENDING",
        "duration_seconds": 80,
        "audio_asset_id": "asset-audio-02",
        "animation_asset_id": "asset-anim-02",
        "render_asset_id": None,
    },
    {
        "id": "shot-cb-001-03",
        "episode_id": "ep-cb-001",
        "production_plan_id": "plan-ep-cb-001",
        "scene_id": "scene-cb-001-02",
        "shot_number": 3,
        "camera_movement": "Tracking Shot",
        "focal_length": "24mm Wide",
        "status": "ANIMATION_PENDING",
        "duration_seconds": 105,
        "audio_asset_id": "asset-audio-03",
        "animation_asset_id": None,
        "render_asset_id": None,
    },
]

_PRODUCTION_JOBS: List[Dict[str, Any]] = [
    {
        "job_id": "job-audio-001",
        "episode_id": "ep-cb-001",
        "shot_id": "shot-cb-001-01",
        "job_type": "AUDIO",
        "state": "SUCCEEDED",
        "progress_percent": 100,
        "error_code": None,
        "retryable": False,
        "failure_stage": None,
        "attempt": 1,
        "max_attempts": 3,
        "artifact_id": "asset-audio-01",
        "correlation_id": "corr-audio-001",
        "submitted_at": "2026-08-15T10:00:00Z",
        "completed_at": "2026-08-15T10:01:15Z",
    },
    {
        "job_id": "job-anim-001",
        "episode_id": "ep-cb-001",
        "shot_id": "shot-cb-001-01",
        "job_type": "ANIMATION",
        "state": "SUCCEEDED",
        "progress_percent": 100,
        "error_code": None,
        "retryable": False,
        "failure_stage": None,
        "attempt": 1,
        "max_attempts": 3,
        "artifact_id": "asset-anim-01",
        "correlation_id": "corr-anim-001",
        "submitted_at": "2026-08-15T10:05:00Z",
        "completed_at": "2026-08-15T10:08:40Z",
    },
    {
        "job_id": "job-render-001",
        "episode_id": "ep-cb-001",
        "shot_id": "shot-cb-001-01",
        "job_type": "RENDER",
        "state": "SUCCEEDED",
        "progress_percent": 100,
        "error_code": None,
        "retryable": False,
        "failure_stage": None,
        "attempt": 1,
        "max_attempts": 3,
        "artifact_id": "asset-render-01",
        "correlation_id": "corr-render-001",
        "submitted_at": "2026-08-15T10:10:00Z",
        "completed_at": "2026-08-15T10:25:00Z",
    },
]

_DELIVERY_ARTIFACTS: List[Dict[str, Any]] = [
    {
        "id": "delivery-ep-cb-001",
        "episode_id": "ep-cb-001",
        "video_asset_id": "asset-video-ep-cb-001",
        "resolution": "1080p (1920x1080)",
        "codec": "H.264 / AAC",
        "duration_seconds": 18,
        "file_size_bytes": 48500000,
        "download_url": None,
        "manifest_url": None,
    }
]

# ─────────────────────────────────────────────────────────────────────────────
# Agent definitions, activity, instances, conversations
# ─────────────────────────────────────────────────────────────────────────────
_AGENT_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "id": "def-orchestrator-01",
        "name": "Coordinator Orchestrator",
        "slug": "orchestrator",
        "description": "Decomposes high-level user goals, synthesizes execution plans, and routes tasks to specialized agents.",
        "role": "orchestrator",
        "model_policy": {"preferred_family": "gemini-pro", "temperature": 0.2},
        "tool_policy": {"allowed_tools": ["plan_decomposition", "route_task", "synthesize_results"]},
        "permission_profile": {"read_workspace": True, "write_workspace": True, "execute_tools": True},
        "memory_policy": {"durable_context": True, "vector_search": True},
        "default_configuration": {"max_subtasks": 20, "timeout_seconds": 3600},
    },
    {
        "id": "def-coder-01",
        "name": "Code Synthesis Agent",
        "slug": "coder",
        "description": "Full-stack code generation, refactoring, lint correction, and test suite execution.",
        "role": "coder",
        "model_policy": {"preferred_family": "claude-sonnet", "temperature": 0.1},
        "tool_policy": {"allowed_tools": ["read_file", "write_to_file", "replace_file_content", "run_command"]},
        "permission_profile": {"read_workspace": True, "write_workspace": True, "execute_tools": True},
        "memory_policy": {"codebase_graph": True},
        "default_configuration": {"lint_on_save": True},
    },
    {
        "id": "def-researcher-01",
        "name": "Research & Literature Agent",
        "slug": "researcher",
        "description": "Deep information retrieval, paper parsing, citation verification, and factual synthesis.",
        "role": "researcher",
        "model_policy": {"preferred_family": "gemini-ultra", "temperature": 0.3},
        "tool_policy": {"allowed_tools": ["search_web", "read_url_content", "query_graph"]},
        "permission_profile": {"read_workspace": True, "write_workspace": False, "execute_tools": True},
        "memory_policy": {"citation_index": True},
        "default_configuration": {"max_citations": 10},
    },
    {
        "id": "def-reviewer-01",
        "name": "Quality & Security Reviewer",
        "slug": "reviewer",
        "description": "Automated code review, security boundary inspection, regression checking, and sign-off verification.",
        "role": "reviewer",
        "model_policy": {"preferred_family": "claude-opus", "temperature": 0.0},
        "tool_policy": {"allowed_tools": ["grep_search", "view_file", "run_command"]},
        "permission_profile": {"read_workspace": True, "write_workspace": False, "execute_tools": False},
        "memory_policy": {"review_standards": True},
        "default_configuration": {"require_diff_checklist": True},
    },
]

_AGENT_ACTIVITY: List[Dict[str, Any]] = [
    {
        "id": "act-orch-01",
        "agent_id": "def-orchestrator-01",
        "action_type": "PLAN_INITIALIZED",
        "message": "Initialized multi-agent DAG for root conversation context.",
        "timestamp": "2026-08-15T10:00:00Z",
        "metadata": {"subtask_count": 4},
    },
    {
        "id": "act-orch-02",
        "agent_id": "def-orchestrator-01",
        "action_type": "ROUTE_DISPATCHED",
        "message": "Dispatched code task to Coder instance.",
        "timestamp": "2026-08-15T10:00:05Z",
        "metadata": {"target_instance": "inst-coder-01"},
    },
    {
        "id": "act-coder-01",
        "agent_id": "def-coder-01",
        "action_type": "TASK_COMPLETED",
        "message": "Successfully synthesized component and ran test suite.",
        "timestamp": "2026-08-15T10:05:00Z",
        "metadata": {"exit_code": 0},
    },
]

_AGENT_INSTANCES: List[Dict[str, Any]] = [
    {
        "id": "inst-orch-01",
        "definition_id": "def-orchestrator-01",
        "conversation_id": "conv-default-01",
        "status": "RUNNING",
        "canonical_model_id": "gemini-1.5-pro",
        "provider_binding_id": "prov-vertex-01",
        "route_lock_id": "lock-orch-01",
        "assigned_task_id": "task-orch-goal-01",
        "current_tool": "plan_decomposition",
        "runtime_metadata": {"uptime_seconds": 3600, "active_turns": 12},
    },
    {
        "id": "inst-coder-01",
        "definition_id": "def-coder-01",
        "conversation_id": "conv-default-01",
        "status": "IDLE",
        "canonical_model_id": "claude-3-5-sonnet",
        "provider_binding_id": "prov-anthropic-01",
        "route_lock_id": "lock-coder-01",
        "assigned_task_id": None,
        "current_tool": None,
        "runtime_metadata": {"uptime_seconds": 3480, "active_turns": 8},
    },
]

_CONVERSATIONS: List[Dict[str, Any]] = [
    {
        "id": "conv-default-01",
        "title": "Core System Architecture Convergence",
        "objective": "Unify agent workspace, definitions, tasks, and workflows into V3 architecture",
        "status": "ACTIVE",
        "plan_version_id": "pv-01",
        "orchestrator_instance_id": "inst-orch-01",
    }
]

_CONVERSATION_EVENTS: List[Dict[str, Any]] = [
    {
        "event_id": "evt-01",
        "conversation_id": "conv-default-01",
        "event_type": "conversation.started",
        "payload": {"objective": "Unify agent workspace, definitions, tasks, and workflows"},
    },
    {
        "event_id": "evt-02",
        "conversation_id": "conv-default-01",
        "event_type": "agent.instance.started",
        "payload": {"instance_id": "inst-orch-01", "role": "orchestrator"},
    },
    {
        "event_id": "evt-03",
        "conversation_id": "conv-default-01",
        "event_type": "task.ready",
        "payload": {"task_id": "task-03", "objective": "Run regression test suite"},
    },
]
