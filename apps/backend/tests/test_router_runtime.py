"""Backend unit and integration tests for Router Runtime, Streaming, Quota Reset, and Adapters."""
from __future__ import annotations

import json
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from db.models import ProviderQuotaSnapshotORM, RouterExecutionLogORM
from services.agent_runtime_adapters import CodingAgent, GUIAgent, WorkflowAgent, ResearchAgent


def test_openai_compatible_stream_completion(client):
    """Test that chat completion with stream: true returns OpenAI-compatible SSE events."""
    payload = {
        "model": "Planner",
        "messages": [
            {"role": "system", "content": "You are a planner"},
            {"role": "user", "content": "Mở Notepad và gõ Hello"}
        ],
        "stream": True
    }
    
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert response.headers.get("content-type") == "text/event-stream; charset=utf-8"

    lines = response.text.split("\n")
    data_lines = [line for line in lines if line.startswith("data: ")]
    
    assert len(data_lines) > 0
    
    # The last chunk should contain [DONE]
    assert data_lines[-1] == "data: [DONE]"

    # Verify formatting of intermediate chunks
    first_chunk_str = data_lines[0].replace("data: ", "").strip()
    first_chunk = json.loads(first_chunk_str)
    assert first_chunk["object"] == "chat.completion.chunk"
    assert "choices" in first_chunk
    assert len(first_chunk["choices"]) > 0
    assert "delta" in first_chunk["choices"][0]


def test_openai_compatible_non_stream_completion(client):
    """Test that chat completion with stream: false returns standard chat completion envelope."""
    payload = {
        "model": "Planner",
        "messages": [
            {"role": "system", "content": "You are a planner"},
            {"role": "user", "content": "Mở Notepad và gõ Hello"}
        ],
        "stream": False
    }
    
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["object"] == "chat.completion"
    assert "choices" in data
    assert len(data["choices"]) > 0
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert "steps" in data["choices"][0]["message"]["content"]


def test_quota_automatic_daily_reset(client, app_state):
    """Test that provider daily quotas reset automatically if the snapshot is from a previous day."""
    db = app_state.db
    quota_service = app_state.model_service.quota_service

    # Create an old snapshot with 0 requests remaining
    async def setup_old_snapshot():
        async with db.session() as session:
            old_time = datetime.now(timezone.utc) - timedelta(days=2)
            snapshot = ProviderQuotaSnapshotORM(
                provider_id="google_ai_studio",
                quota_mode="RPM_RPD",
                rpm_limit=15,
                rpd_limit=1500,
                tpm_limit=1000000,
                remaining_requests_today=0,
                remaining_tokens_today=0,
                remaining_credit=10.0,
                reset_at=None,
                source="test",
                raw_json="{}",
            )
            # Override created_at to old date
            snapshot.created_at = old_time
            session.add(snapshot)
            await session.commit()
            return snapshot.provider_id

    provider_id = asyncio.run(setup_old_snapshot())

    # Execute check_and_reset_provider_quota
    async def run_reset_check():
        await quota_service.check_and_reset_provider_quota(provider_id)
        # Fetch latest snapshot
        return await quota_service.get_latest_quota(provider_id)

    latest_snapshot = asyncio.run(run_reset_check())
    
    assert latest_snapshot is not None
    # Source should show auto_reset and remaining limits should be restored
    assert latest_snapshot.source == "auto_reset"
    assert latest_snapshot.remaining_requests_today == 1500
    assert latest_snapshot.remaining_tokens_today == 1000000


def test_agent_runtime_adapters(client, app_state):
    """Test that all agent runtime adapters successfully route requests and record logs."""
    router_service = app_state.router_service
    db = app_state.db

    # Instantiate adapters
    coder = CodingAgent(router_service)
    gui = GUIAgent(router_service)
    wf = WorkflowAgent(router_service)
    research = ResearchAgent(router_service)

    # We mock or run the calls using the lifespan client database state
    async def run_agents_calls():
        res_coder = await coder.execute_task("Write a quicksort in python", "System context instructions")
        res_gui = await gui.run_step("Click at (250, 400)")
        res_wf = await wf.lookup_memory("Retrieve notepad instructions")
        res_research = await research.scrape_and_parse("https://google.com")
        
        return res_coder, res_gui, res_wf, res_research

    res_coder, res_gui, res_wf, res_research = asyncio.run(run_agents_calls())

    # Verify they returned content (from mock client responses or fallback)
    assert res_coder is not None
    assert res_gui is not None
    assert res_wf is not None
    assert res_research is not None

    # Check execution logs database state to verify logs were persisted for each role
    async def check_logs():
        async with db.session() as session:
            stmt = select(RouterExecutionLogORM)
            res = await session.execute(stmt)
            return res.scalars().all()

    logs = asyncio.run(check_logs())
    roles_logged = [log.role for log in logs]
    
    assert "Coder" in roles_logged
    assert "GUI Agent" in roles_logged
    assert "Memory Agent" in roles_logged
    assert "Researcher" in roles_logged
