import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.hermes.event_mapper import HermesEventTranslator
from services.hermes.api_client import HermesApiClient
from services.hermes.config import HermesConfig
from services.hermes.runtime_manager import HermesRuntimeManager
from services.hermes.session_bridge import HermesSessionBridge
from schemas.event import EventEnvelope


@pytest.mark.asyncio
async def test_event_translator_progress_and_error():
    # 1. Test tool.progress mapping
    env = HermesEventTranslator.translate(
        {"event": "tool.progress", "tool": "terminal", "progress": "Compiling source code..."},
        windagent_session_id="session_123",
        sequence=1,
    )
    assert env is not None
    assert env.event == "tool_call_progress"
    assert env.data["tool_name"] == "terminal"
    assert env.data["progress"] == "Compiling source code..."

    # 2. Test run.failed mapping
    env_failed = HermesEventTranslator.translate(
        {"event": "run.failed", "run_id": "run_999", "error": "Execution timeout expired"},
        windagent_session_id="session_123",
        sequence=2,
    )
    assert env_failed is not None
    assert env_failed.event == "session_finished"
    assert env_failed.data["final_status"] == "failed"
    assert env_failed.data["error"]["message"] == "Execution timeout expired"


@pytest.mark.asyncio
async def test_hermes_client_sse_crash_handling():
    # Arrange
    config = HermesConfig(enabled=True, base_url="http://127.0.0.1:8642")
    api_client = HermesApiClient(config)
    event_bus_mock = MagicMock()
    event_bus_mock.publish = AsyncMock()
    
    db_mock = MagicMock()
    
    bridge = HermesSessionBridge(
        db=db_mock,
        client=api_client,
        event_bus=event_bus_mock,
    )

    # Mock stream_run_events to raise an exception
    async def mock_stream_run_events(run_id):
        # Yield one valid event, then raise ReadError
        yield {"event": "tool.started", "tool": "terminal", "preview": "ls"}
        raise httpx.ReadError("Connection to Hermes server interrupted")

    with patch.object(api_client, "stream_run_events", side_effect=mock_stream_run_events):
        # Act
        await bridge._stream_run("windagent_sess_1", "hermes_run_1")

    # Assert
    # Verify that the crash was handled and an "error" EventEnvelope was published
    assert event_bus_mock.publish.call_count >= 2
    
    # Check that error event is published
    calls = event_bus_mock.publish.mock_calls
    error_published = False
    for call in calls:
        args = call[1]
        if len(args) == 2 and isinstance(args[1], EventEnvelope):
            env = args[1]
            if env.event == "error":
                error_published = True
                assert "Hermes event stream crashed" in env.data["message"]
                
    assert error_published, "Expected an error event to be published upon SSE crash"


@pytest.mark.asyncio
async def test_hermes_crash_and_restart_reconciliation():
    # Arrange
    config = HermesConfig(enabled=True, base_url="http://127.0.0.1:8642")
    runtime_manager = HermesRuntimeManager(config, event_bus=None)

    # Mock health probe to throw ConnectError
    async def mock_health_error(*args, **kwargs):
        raise httpx.ConnectError("Connection refused by Hermes")

    # Act
    with patch("httpx.AsyncClient.get", side_effect=mock_health_error):
        is_healthy = await runtime_manager.probe_health()

    # Assert
    assert is_healthy is False, "Expected health check to return False when server is unreachable"
