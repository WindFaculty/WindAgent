"""Service managing the Agent Registry, session mappings, and database seeding."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update

from db.database import Database
from db.models import AgentORM, AgentSessionORM

log = logging.getLogger(__name__)

DEFAULT_AGENTS_SEED = [
    {
        "id": "planner",
        "name": "Planner",
        "slug": "task-planning",
        "description": "Decomposes complex requests into structured sub-tasks. Guides execution and verifies outcomes.",
        "runtime_type": "hermes",
        "hermes_profile": "default",
        "router_role": "Planner",
        "status": "idle",
        "workspace_root": None,
        "system_prompt": "You are a Planner agent. Your job is to decompose complex user tasks into structured sub-tasks. Output a clear plan and coordinate tool usage.",
        "toolsets_json": json.dumps(["read-only", "task planning"]),
        "skills_json": json.dumps([]),
        "memory_enabled": True,
        "max_concurrent_sessions": 5,
        "auto_start": True,
    },
    {
        "id": "coder",
        "name": "Coder",
        "slug": "code-generation",
        "description": "Generates, refactors, and debugs code. Writes clean, testable, and well-documented solutions.",
        "runtime_type": "hermes",
        "hermes_profile": "default",
        "router_role": "Coder",
        "status": "idle",
        "workspace_root": None,
        "system_prompt": "You are an expert software developer. Generate clean, well-tested code, run tests to verify correctness, and troubleshoot errors.",
        "toolsets_json": json.dumps(["terminal", "filesystem", "git", "tests"]),
        "skills_json": json.dumps([]),
        "memory_enabled": True,
        "max_concurrent_sessions": 5,
        "auto_start": True,
    },
    {
        "id": "researcher",
        "name": "Researcher",
        "slug": "web-research",
        "description": "Conducts web search and retrieves documentation. Synthesizes codebase context and external assets.",
        "runtime_type": "hermes",
        "hermes_profile": "default",
        "router_role": "Researcher",
        "status": "idle",
        "workspace_root": None,
        "system_prompt": "You are a researcher. Search the web, browse documentation, extract technical specifications, and synthesize findings.",
        "toolsets_json": json.dumps(["web search", "browser", "docs"]),
        "skills_json": json.dumps([]),
        "memory_enabled": True,
        "max_concurrent_sessions": 5,
        "auto_start": True,
    },
    {
        "id": "gui",
        "name": "GUI Agent",
        "slug": "ui-ux-automation",
        "description": "Automates browser previews and compiles React UI layouts. Tests UI rendering against specifications.",
        "runtime_type": "native_workflow",
        "hermes_profile": "default",
        "router_role": "GUI Agent",
        "status": "idle",
        "workspace_root": None,
        "system_prompt": "You are a GUI interaction agent. Focus on visual components, screenshots, and visual feedback automation.",
        "toolsets_json": json.dumps(["screenshot", "click", "type"]),
        "skills_json": json.dumps([]),
        "memory_enabled": False,
        "max_concurrent_sessions": 2,
        "auto_start": True,
    },
    {
        "id": "browser",
        "name": "Browser Agent",
        "slug": "web-automation",
        "description": "Controls active browser sessions, capturing logs, screenshots, and DOM states for visual validation.",
        "runtime_type": "hermes",
        "hermes_profile": "default",
        "router_role": "Researcher",
        "status": "idle",
        "workspace_root": None,
        "system_prompt": "You are a browser automation agent. Open web pages, click links, fill inputs, and scrape content.",
        "toolsets_json": json.dumps(["browser automation"]),
        "skills_json": json.dumps([]),
        "memory_enabled": True,
        "max_concurrent_sessions": 5,
        "auto_start": True,
    },
    {
        "id": "memory",
        "name": "Memory Agent",
        "slug": "knowledge-manager",
        "description": "Manages contextual memory vector graphs. Prunes stale dependencies and saves session states.",
        "runtime_type": "disabled",
        "hermes_profile": "default",
        "router_role": "Memory Agent",
        "status": "offline",
        "workspace_root": None,
        "system_prompt": "You manage the long-term context memory graph. Optimize and query local memories.",
        "toolsets_json": json.dumps(["memory", "session search"]),
        "skills_json": json.dumps([]),
        "memory_enabled": True,
        "max_concurrent_sessions": 1,
        "auto_start": False,
    },
]


class AgentRegistryService:
    """Manages Agent configs, statuses, and history mapping in SQLite."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def init_database_seeds(self) -> None:
        """Seed default agents if table is empty."""
        async with self.db.session() as session:
            stmt = select(AgentORM)
            res = await session.execute(stmt)
            existing = {a.id for a in res.scalars().all()}

            for seed in DEFAULT_AGENTS_SEED:
                if seed["id"] not in existing:
                    agent = AgentORM(
                        id=seed["id"],
                        name=seed["name"],
                        slug=seed["slug"],
                        description=seed["description"],
                        runtime_type=seed["runtime_type"],
                        hermes_profile=seed["hermes_profile"],
                        router_role=seed["router_role"],
                        status=seed["status"],
                        workspace_root=seed["workspace_root"],
                        system_prompt=seed["system_prompt"],
                        toolsets_json=seed["toolsets_json"],
                        skills_json=seed["skills_json"],
                        memory_enabled=seed["memory_enabled"],
                        max_concurrent_sessions=seed["max_concurrent_sessions"],
                        auto_start=seed["auto_start"],
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    session.add(agent)
                    log.info("Seeding default agent: %s", agent.id)

    async def list_agents(self) -> List[Dict[str, Any]]:
        """List all agents in registry."""
        async with self.db.session() as session:
            stmt = select(AgentORM).order_by(AgentORM.id)
            res = await session.execute(stmt)
            agents = res.scalars().all()
            return [self._to_dict(a) for a in agents]

    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get a single agent."""
        async with self.db.session() as session:
            stmt = select(AgentORM).where(AgentORM.id == agent_id)
            res = await session.execute(stmt)
            agent = res.scalar_one_or_none()
            return self._to_dict(agent) if agent else None

    async def create_agent(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new agent."""
        async with self.db.session() as session:
            agent = AgentORM(
                id=data["id"],
                name=data["name"],
                slug=data.get("slug"),
                description=data.get("description"),
                runtime_type=data.get("runtime_type", "hermes"),
                hermes_profile=data.get("hermes_profile", "default"),
                router_role=data.get("router_role"),
                status=data.get("status", "offline"),
                workspace_root=data.get("workspace_root"),
                system_prompt=data.get("system_prompt"),
                toolsets_json=json.dumps(data.get("toolsets", [])),
                skills_json=json.dumps(data.get("skills", [])),
                memory_enabled=data.get("memory_enabled", False),
                max_concurrent_sessions=data.get("max_concurrent_sessions", 5),
                auto_start=data.get("auto_start", False),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(agent)
            return self._to_dict(agent)

    async def update_agent(self, agent_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an agent."""
        async with self.db.session() as session:
            stmt = select(AgentORM).where(AgentORM.id == agent_id)
            res = await session.execute(stmt)
            agent = res.scalar_one_or_none()
            if not agent:
                return None

            for key, val in data.items():
                if key == "toolsets":
                    agent.toolsets_json = json.dumps(val)
                elif key == "skills":
                    agent.skills_json = json.dumps(val)
                elif hasattr(agent, key):
                    setattr(agent, key, val)
            
            agent.updated_at = datetime.now(timezone.utc)
            return self._to_dict(agent)

    async def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent."""
        async with self.db.session() as session:
            stmt = select(AgentORM).where(AgentORM.id == agent_id)
            res = await session.execute(stmt)
            agent = res.scalar_one_or_none()
            if not agent:
                return False
            await session.delete(agent)
            return True

    async def update_status(self, agent_id: str, status: str) -> bool:
        """Update agent runtime status."""
        async with self.db.session() as session:
            stmt = update(AgentORM).where(AgentORM.id == agent_id).values(status=status)
            res = await session.execute(stmt)
            return res.rowcount > 0

    async def list_agent_sessions(self, agent_id: str) -> List[Dict[str, Any]]:
        """List sessions belonging to an agent."""
        async with self.db.session() as session:
            stmt = select(AgentSessionORM).where(AgentSessionORM.agent_id == agent_id).order_by(AgentSessionORM.started_at.desc())
            res = await session.execute(stmt)
            sessions = res.scalars().all()
            return [
                {
                    "id": s.id,
                    "windagent_session_id": s.windagent_session_id,
                    "runtime_type": s.runtime_type,
                    "status": s.status,
                    "workspace_root": s.workspace_root,
                    "started_at": s.started_at.isoformat() + "Z",
                    "finished_at": s.finished_at.isoformat() + "Z" if s.finished_at else None,
                }
                for s in sessions
            ]

    async def get_summary_metrics(self) -> Dict[str, Any]:
        """Aggregate summary metrics from database."""
        async with self.db.session() as session:
            # 1. Total agents count
            stmt = select(AgentORM)
            res = await session.execute(stmt)
            agents = res.scalars().all()
            
            total = len(agents)
            running = sum(1 for a in agents if a.status == "Running")
            busy = sum(1 for a in agents if a.status == "Busy")
            idle = sum(1 for a in agents if a.status == "Idle")
            offline = sum(1 for a in agents if a.status in ("offline", "Offline"))

            # 2. Count active task runs
            stmt_runs = select(AgentSessionORM).where(AgentSessionORM.status == "running")
            res_runs = await session.execute(stmt_runs)
            tasks_running = len(res_runs.scalars().all())

            return {
                "total": total,
                "running": running,
                "busy": busy,
                "idle": idle,
                "offline": offline,
                "tasks_running": tasks_running,
                "average_response_ms": 1420,  # mock or retrieve from execution events
                "success_rate": 0.936,       # mock or computed
            }

    def _to_dict(self, agent: AgentORM) -> Dict[str, Any]:
        try:
            toolsets = json.loads(agent.toolsets_json)
        except Exception:
            toolsets = []
            
        try:
            skills = json.loads(agent.skills_json)
        except Exception:
            skills = []

        return {
            "id": agent.id,
            "name": agent.name,
            "slug": agent.slug,
            "description": agent.description,
            "runtime_type": agent.runtime_type,
            "hermes_profile": agent.hermes_profile,
            "router_role": agent.router_role,
            "status": agent.status,
            "workspace_root": agent.workspace_root,
            "system_prompt": agent.system_prompt,
            "toolsets": toolsets,
            "skills": skills,
            "memory_enabled": agent.memory_enabled,
            "max_concurrent_sessions": agent.max_concurrent_sessions,
            "auto_start": agent.auto_start,
            "created_at": agent.created_at.isoformat() + "Z",
            "updated_at": agent.updated_at.isoformat() + "Z",
        }
