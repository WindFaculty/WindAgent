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


@fake_app.post("/v1/runs")
async def start_run(req: Request):
    body = await req.json()
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    # Emit a small scripted flow: tool started -> progress -> completed -> run completed.
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
