"""WindAgent backend — FastAPI sidecar entry point.

Phase 1: in-memory session/workflow/event state.
Phase 2: SQLite persistence via SQLAlchemy + aiosqlite.
Phase 3: tool executor + PyAutoGUI adapter (production) / MockGuiAdapter (tests).
Phase 4: Qwen3 4B planner via Ollama (with MockModelClient fallback).
Phase 5: sequential workflow runner with Pause / Resume / Stop / Retry.

Run locally:
    cd apps/backend
    uv sync
    # Use mock model client (no Ollama needed):
    WINDAGENT_MODEL_BACKEND=mock uv run uvicorn main:app --port 8765
    # Real Ollama:
    uv run uvicorn main:app --port 8765
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from db.database import Database
from routers import agent_s3, health, models, permissions, sessions, tools, workflow, websocket
from services.agent_s3_adapter import AgentS3Adapter
from services.agent_s3_config import (
    AgentS3Config,
    config_missing_fields,
    load_agent_s3_config,
    package_available,
    validate_or_raise,
)
from services.event_bus import EventBus
from services.event_hooks import make_execution_event_hook, make_jsonl_event_hook
from services.gui_adapter import GuiAdapter, make_default_adapter
from services.gui_grounding import (
    GuiGroundingService,
    MockGuiGroundingService,
)
from services.model_client import ModelClient, OllamaModelClient
from services.permission_service import PermissionService
from services.planner_service import PlannerService
from services.session_service import SessionService
from services.tool_executor import ToolExecutor
from services.workflow_runner import WorkflowRunner
from services.workflow_service import WorkflowService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("windagent.backend")


# ---------- DB config ----------

DB_URL = os.environ.get(
    "WINDAGENT_DB_URL",
    "sqlite+aiosqlite:///./windagent.db",
)


# When set, the GUI adapter is replaced with MockGuiAdapter (tests, CI).
USE_MOCK_GUI = os.environ.get("WINDAGENT_MOCK_GUI", "").lower() in (
    "1", "true", "yes",
)


# Phase 8 prep: which grounding backend to use.
#   "mock"  -> MockGuiGroundingService (default, no Qwen-VL required)
#   "vision" -> VisionModelGroundingService (not implemented; raises)
GROUNDING_BACKEND = os.environ.get("WINDAGENT_GROUNDING_BACKEND", "mock").lower()


# ---------- Model client selection (Phase 4) ----------

# `mock`        -> MockModelClient with canned responses for the two demos.
# `ollama`      -> real OllamaModelClient at WINDAGENT_OLLAMA_URL.
# default       -> ollama (production default).
MODEL_BACKEND = os.environ.get("WINDAGENT_MODEL_BACKEND", "ollama").lower()
OLLAMA_BASE_URL = os.environ.get(
    "WINDAGENT_OLLAMA_URL",
    OllamaModelClient.DEFAULT_BASE_URL,
)
OLLAMA_MODEL = os.environ.get(
    "WINDAGENT_OLLAMA_MODEL",
    OllamaModelClient.DEFAULT_MODEL,
)


def _build_model_client() -> ModelClient:
    """Pick the right ModelClient based on env. Imports MockModelClient
    lazily so the production runtime never imports it."""
    if MODEL_BACKEND == "mock":
        from services.model_client import MockModelClient

        log.info("using MockModelClient (WINDAGENT_MODEL_BACKEND=mock)")
        return MockModelClient()

    if MODEL_BACKEND == "ollama":
        log.info(
            "using OllamaModelClient url=%s model=%s",
            OLLAMA_BASE_URL,
            OLLAMA_MODEL,
        )
        return OllamaModelClient(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL)

    raise ValueError(
        f"unknown WINDAGENT_MODEL_BACKEND={MODEL_BACKEND!r} "
        f"(expected 'mock' or 'ollama')"
    )


def _build_grounding_service() -> GuiGroundingService:
    """Pick the right GuiGroundingService based on env (Phase 8 prep)."""
    if GROUNDING_BACKEND == "mock":
        log.info("using MockGuiGroundingService (WINDAGENT_GROUNDING_BACKEND=mock)")
        return MockGuiGroundingService()
    if GROUNDING_BACKEND == "vision":
        log.info(
            "using VisionModelGroundingService (WINDAGENT_GROUNDING_BACKEND=vision) "
            "— not implemented, will raise on use"
        )
        from services.gui_grounding import VisionModelGroundingService
        return VisionModelGroundingService()
    raise ValueError(
        f"unknown WINDAGENT_GROUNDING_BACKEND={GROUNDING_BACKEND!r} "
        f"(expected 'mock' or 'vision')"
    )


# ---------- Lifespan ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("WindAgent backend starting up (Phase 4 — Qwen planner)")

    db = Database(DB_URL)
    await db.init_models()
    app.state.db = db

    event_bus = EventBus()
    event_bus.add_publisher_hook(make_execution_event_hook(db))

    # Phase 10: also mirror every event to a per-session JSONL file at
    # artifacts/runs/{session_id}/events.jsonl for portable audit log.
    # Default root mirrors ToolExecutor's screenshot root so all run
    # artifacts live under the same directory.
    artifacts_root = Path(os.environ.get(
        "WINDAGENT_ARTIFACTS_ROOT",
        str(Path(__file__).resolve().parent.parent / "artifacts" / "runs"),
    ))
    jsonl_hook = make_jsonl_event_hook(artifacts_root)
    event_bus.add_publisher_hook(jsonl_hook)

    # GUI adapter selection.
    if USE_MOCK_GUI:
        from services.gui_adapter import MockGuiAdapter
        gui: GuiAdapter = MockGuiAdapter()
        log.info("using MockGuiAdapter (WINDAGENT_MOCK_GUI=1)")
    else:
        gui = make_default_adapter()
        log.info("using PyAutoGuiAdapter")

    # Phase 8 prep: GUI grounding service (default mock; vision not impl).
    # Build it before the ToolExecutor so it can be injected.
    grounding_service = _build_grounding_service()

    executor = ToolExecutor(
        event_bus=event_bus,
        db=db,
        gui=gui,
        grounding_service=grounding_service,
    )

    # Phase 4: model client + planner service.
    model_client = _build_model_client()
    planner = PlannerService(client=model_client)

    session_service = SessionService(event_bus=event_bus, db=db)
    workflow_service = WorkflowService(
        event_bus=event_bus, db=db, planner=planner
    )
    permission_service = PermissionService(event_bus=event_bus)
    runner = WorkflowRunner(
        event_bus=event_bus,
        executor=executor,
        session_service=session_service,
        workflow_service=workflow_service,
        permission_service=permission_service,
    )

    app.state.event_bus = event_bus
    app.state.db = db
    app.state.gui = gui
    app.state.model_client = model_client
    app.state.planner_service = planner
    app.state.grounding_service = grounding_service
    app.state.permission_service = permission_service
    app.state.tool_executor = executor
    app.state.session_service = session_service
    app.state.workflow_service = workflow_service
    app.state.workflow_runner = runner

    # ---------- Optional: Agent-S3 integration ----------
    # The backend always loads the Agent-S3 config (cheap; env reads
    # only) but only constructs the adapter when the integration is
    # actually usable. This keeps the upstream ``gui_agents`` package
    # out of the import graph until the operator opts in.
    agent_s3_config: AgentS3Config = load_agent_s3_config()
    agent_s3_adapter: AgentS3Adapter | None = None
    if agent_s3_config.enabled:
        try:
            agent_s3_adapter = AgentS3Adapter(agent_s3_config)
            if agent_s3_adapter.is_available():
                log.info(
                    "agent-s3 enabled (source=%s provider=%s model=%s)",
                    agent_s3_config.source,
                    agent_s3_config.provider,
                    agent_s3_config.model,
                )
            else:
                missing = config_missing_fields(agent_s3_config)
                if missing:
                    log.warning(
                        "agent-s3 enabled but config is incomplete: %s",
                        ", ".join(missing),
                    )
                else:
                    log.warning(
                        "agent-s3 enabled but unavailable "
                        "(source=%s, package_available=%s, external_repo=%s)",
                        agent_s3_config.source,
                        package_available(),
                        agent_s3_config.external_checkout_root is not None,
                    )
        except Exception:  # noqa: BLE001
            log.exception("agent-s3 adapter init failed; continuing without it")
            agent_s3_adapter = None
    else:
        log.info("agent-s3 disabled (set WINDAGENT_AGENT_S3_ENABLED=1 to enable)")
    app.state.agent_s3_config = agent_s3_config
    app.state.agent_s3_adapter = agent_s3_adapter

    log.info("backend ready — db=%s model=%s", DB_URL, MODEL_BACKEND)
    try:
        yield
    finally:
        log.info("WindAgent backend shutting down")
        # Close JSONL handles first so any final in-flight events are
        # flushed before we tear down the rest of the stack.
        try:
            jsonl_hook.close()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            log.exception("error closing jsonl hook")
        await runner.shutdown()
        if hasattr(model_client, "aclose"):
            await model_client.aclose()  # type: ignore[attr-defined]
        await db.dispose()


app = FastAPI(
    title="WindAgent Backend",
    version="0.8.0",
    description="Local Desktop AI Agent — FastAPI sidecar (Phase 8).",
    lifespan=lifespan,
)


# ---------- Routers ----------
app.include_router(health.router)
app.include_router(agent_s3.router)
app.include_router(models.router)
app.include_router(permissions.router)
app.include_router(sessions.router)
app.include_router(workflow.router)
app.include_router(tools.router)
app.include_router(websocket.router)