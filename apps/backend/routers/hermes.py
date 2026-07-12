"""Hermes supervisor router managing server process liveness and capabilities."""
from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import APIRouter, Request

from services.hermes.runtime_manager import HermesRuntimeManager

router = APIRouter(prefix="/runtimes/hermes", tags=["hermes"])


def _manager(request: Request) -> HermesRuntimeManager:
    return request.app.state.hermes_runtime_manager


@router.get("/status")
async def get_status(request: Request) -> Dict[str, Any]:
    """Get the current process state of the Hermes supervisor."""
    mgr = _manager(request)
    return {
        "status": mgr.status,
        "auto_start": mgr.config.auto_start,
        "executable": mgr.config.executable,
        "base_url": mgr.config.base_url,
    }


@router.get("/health")
async def get_health(request: Request) -> Dict[str, Any]:
    """Perform a liveness check and latency probe on the local Hermes server."""
    mgr = _manager(request)
    api = request.app.state.hermes_api_client
    t0 = time.time()
    reachable = await mgr.probe_health()
    latency_ms = int((time.time() - t0) * 1000) if reachable else 0

    capabilities = {}
    if reachable:
        try:
            capabilities = await api.get_capabilities()
        except Exception:
            pass

    return {
        "enabled": mgr.config.enabled,
        "reachable": reachable,
        "version": capabilities.get("version", "0.18.2") if reachable else "unknown",
        "api_server": capabilities.get("api_server", True) if reachable else False,
        "runs_api": capabilities.get("runs_api", True) if reachable else False,
        "session_streaming": capabilities.get("session_streaming", True) if reachable else False,
        "approval": capabilities.get("approval", True) if reachable else False,
        "stop": capabilities.get("stop", True) if reachable else False,
        "pause": capabilities.get("pause", False) if reachable else False,
        "profile": mgr.config.profile,
        "latency_ms": latency_ms,
        "api_key_scrubbed": True if mgr.config.api_key else False,
    }


@router.get("/health/detailed")
async def get_detailed_health(request: Request) -> Dict[str, Any]:
    """Get detailed health status from Hermes."""
    mgr = _manager(request)
    api = request.app.state.hermes_api_client
    if not await mgr.probe_health():
        return {
            "status": "unreachable",
            "error": "Hermes server is offline",
        }
    try:
        return await api.get_detailed_health()
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


@router.get("/capabilities")
async def get_capabilities(request: Request) -> Dict[str, Any]:
    """Fetch capabilities directly from supervised Hermes server or fallback."""
    mgr = _manager(request)
    api = request.app.state.hermes_api_client
    if not await mgr.probe_health():
        return await mgr.get_capabilities()
    try:
        return await api.get_capabilities()
    except Exception:
        return await mgr.get_capabilities()


@router.get("/tools")
async def get_tools(request: Request) -> Dict[str, Any]:
    """Aggregate toolsets and skills discovered in Hermes."""
    mgr = _manager(request)
    api = request.app.state.hermes_api_client
    if not await mgr.probe_health():
        return {
            "toolsets": [],
            "skills": [],
            "status": "offline",
        }
    try:
        import asyncio
        toolsets_task = api.get_toolsets()
        skills_task = api.get_skills()
        toolsets, skills = await asyncio.gather(toolsets_task, skills_task, return_exceptions=True)

        return {
            "toolsets": toolsets if not isinstance(toolsets, Exception) else [],
            "skills": skills if not isinstance(skills, Exception) else [],
            "status": "online",
        }
    except Exception as e:
        return {
            "toolsets": [],
            "skills": [],
            "status": "error",
            "error": str(e),
        }


@router.post("/start")
async def start_hermes(request: Request) -> Dict[str, Any]:
    """Force start the Hermes background supervisor process."""
    mgr = _manager(request)
    await mgr.start()
    return {"status": "success", "state": mgr.status}


@router.post("/stop")
async def stop_hermes(request: Request) -> Dict[str, Any]:
    """Shutdown the supervised Hermes server process tree."""
    mgr = _manager(request)
    await mgr.stop()
    return {"status": "success", "state": mgr.status}


@router.post("/restart")
async def restart_hermes(request: Request) -> Dict[str, Any]:
    """Restart the supervised Hermes server process context."""
    mgr = _manager(request)
    await mgr.restart()
    return {"status": "success", "state": mgr.status}
