"""Hermes supervisor router managing server process liveness and capabilities."""
from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import APIRouter, Request

from services.hermes.runtime_manager import HermesRuntimeManager

router = APIRouter(prefix="/hermes", tags=["hermes"])


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
    t0 = time.time()
    reachable = await mgr.probe_health()
    latency_ms = int((time.time() - t0) * 1000) if reachable else 0

    capabilities = {}
    if reachable:
        capabilities = await mgr.get_capabilities()

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
