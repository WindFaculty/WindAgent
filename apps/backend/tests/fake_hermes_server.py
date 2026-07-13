"""Fake Hermes API Server for contract tests.

Implements the subset of the Runs API the WindAgent bridge uses:
  POST /v1/runs                -> start run, return run_id
  GET  /v1/runs/{run_id}       -> status
  POST /v1/runs/{run_id}/stop  -> stop
  POST /v1/runs/{run_id}/approval -> approve/deny
  GET  /v1/runs/{run_id}/events -> SSE stream of tool + completion events
  GET  /v1/capabilities        -> capability flags

Run it behind httpx in tests via ASGITransport so no socket is needed.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

fake_app = FastAPI()

# run_id -> {"status": ..., "events": [...]}
_RUNS: Dict[str, dict] = {}


@fake_app.get("/health")
async def health():
    return {"status": "healthy"}


@fake_app.get("/health/detailed")
async def health_detailed():
    return {
        "status": "healthy",
        "uptime_s": 3600,
        "database": "connected",
        "services": {
            "runs_api": "ok",
            "capabilities": "ok"
        }
    }


@fake_app.get("/v1/capabilities")
async def capabilities():
    return {
        "version": "0.18.2",
        "api_server": True,
        "runs_api": True,
        "session_streaming": True,
        "approval": True,
        "stop": True,
        "pause": False,
    }


@fake_app.get("/v1/models")
async def models():
    return {
        "models": [
            {"id": "coder", "name": "Coder Model"},
            {"id": "planner", "name": "Planner Model"}
        ]
    }


@fake_app.get("/v1/toolsets")
async def toolsets():
    return {
        "toolsets": ["terminal", "web_browser", "file_editor"]
    }


@fake_app.get("/v1/skills")
async def skills():
    return {
        "skills": ["python_coding", "internet_search"]
    }


_SESSIONS: Dict[str, list] = {}


@fake_app.post("/api/sessions")
async def create_api_session(req: Request):
    body = await req.json()
    sid = body.get("session_id")
    _SESSIONS[sid] = [
        {"sender": "user", "content": "Hello Hermes", "created_at": "2026-07-10T12:00:00Z"},
        {"sender": "assistant", "content": "Hello! How can I help you today?", "created_at": "2026-07-10T12:01:00Z"}
    ]
    return {"status": "created", "session_id": sid}


@fake_app.get("/api/sessions/{session_id}/messages")
async def get_api_session_messages(session_id: str):
    msgs = _SESSIONS.get(session_id, [])
    return msgs


@fake_app.post("/v1/runs")
async def start_run(req: Request):
    body = await req.json()
    print("Fake Hermes start_run body:", body)
    msg = body.get("input") or body.get("message") or body.get("user_message") or ""
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    
    if "delete" in msg.lower() or "approval" in msg.lower():
        events = [
            {"event": "approval.request", "id": "cmd_1", "tool": "terminal", "command": "rm -rf /"},
            {"event": "tool.started", "tool": "terminal", "preview": "rm -rf /"},
            {"event": "tool.completed", "tool": "terminal", "duration": 0.5},
            {"event": "run.completed", "run_id": run_id},
        ]
    elif "browser" in msg.lower():
        events = [
            {"event": "browser_navigation_started", "url": "https://google.com"},
            {"event": "browser_navigation_completed", "url": "https://google.com", "title": "Google", "loading": False},
            {"event": "run.completed", "run_id": run_id},
        ]
    else:
        events = [
            {"event": "tool.started", "tool": "terminal", "preview": "ls -la"},
            {"event": "tool.progress", "tool": "terminal", "progress": "scanning"},
            {"event": "tool.completed", "tool": "terminal", "duration": 1.2},
            {"event": "assistant.delta", "delta": "Done."},
            {"event": "run.completed", "run_id": run_id},
        ]
    _RUNS[run_id] = {"status": "running", "events": events, "approved": None}
    return {"run_id": run_id, "status": "running"}


@fake_app.get("/v1/runs/{run_id}")
async def get_run(run_id: str):
    rec = _RUNS.get(run_id, {})
    return {"run_id": run_id, "status": rec.get("status", "unknown")}


@fake_app.post("/v1/runs/{run_id}/stop")
async def stop_run(run_id: str):
    if run_id in _RUNS:
        _RUNS[run_id]["status"] = "cancelled"
    return {"run_id": run_id, "status": "cancelled"}


@fake_app.post("/v1/runs/{run_id}/approval")
async def approval(run_id: str, req: Request):
    body = await req.json()
    if run_id in _RUNS:
        _RUNS[run_id]["approved"] = body.get("choice")
    return {"run_id": run_id, "choice": body.get("choice")}


@fake_app.get("/v1/runs/{run_id}/events")
async def events(run_id: str):
    rec = _RUNS.get(run_id, {})

    async def gen():
        for ev in rec.get("events", []):
            yield f"event: {ev['event']}\ndata: {__import__('json').dumps(ev)}\n\n"
            await asyncio.sleep(0.01)

    return StreamingResponse(gen(), media_type="text/event-stream")
