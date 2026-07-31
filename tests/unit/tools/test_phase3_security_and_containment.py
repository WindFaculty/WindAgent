"""Phase 3 Security, Containment, and Audit test suite."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
import pytest

from windagent_core.contracts.tools import ToolInvocation
from windagent_core.security.types import Principal
from windagent_tools.base import ToolExecutionContext
from windagent_tools.browser import (
    BrowserAuditLogger,
    BrowserStateManager,
    ClickXYTool,
    OpenURLTool,
    AgentBrowserConfig,
)
from windagent_tools.browser.agent_browser import AgentBrowserCommandResult


class TestBrowserAuditLogger:
    """Test secret redaction and structured audit log recording."""

    def test_audit_logger_redacts_sensitive_keys(self):
        logger = BrowserAuditLogger()
        raw_details = {
            "requested_url": "https://example.com/login",
            "cookie": "session_id=secret123",
            "auth_token": "bearer-xyz",
            "nested": {
                "API_KEY": "sk-test-12345",
                "safe_field": "value",
            },
            "credentials": [
                {"password": "my_password", "user": "alice"}
            ]
        }
        record = logger.log_event("navigation", "test-session", raw_details)
        details = record["details"]

        assert details["requested_url"] == "https://example.com/login"
        assert details["cookie"] == "[REDACTED]"
        assert details["auth_token"] == "[REDACTED]"
        assert details["nested"]["API_KEY"] == "[REDACTED]"
        assert details["nested"]["safe_field"] == "value"
        assert details["credentials"][0]["password"] == "[REDACTED]"
        assert details["credentials"][0]["user"] == "alice"


class TestProfileCopyIsolation:
    """Test isolated Chrome profile copying and cleanup."""

    def test_create_and_cleanup_isolated_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BrowserStateManager(workspace_root=tmpdir)
            
            # Create a fake source profile directory
            src_profile = Path(tmpdir) / "source_chrome_profile"
            src_profile.mkdir()
            (src_profile / "Preferences").write_text('{"profile": "user_data"}', encoding="utf-8")

            # Create isolated copy
            isolated_path = manager.create_isolated_profile_copy(src_profile)

            assert isolated_path.exists()
            assert "windagent_profile_" in str(isolated_path)
            assert (isolated_path / "Preferences").exists()

            # Clean up isolated copy
            cleaned = manager.cleanup_isolated_profile(isolated_path)
            assert cleaned is True
            assert not isolated_path.exists()


class TestPerUserPermissionAndAuditBinding:
    """Test principal identity binding and audit event logging in tools."""

    @pytest.mark.asyncio
    async def test_open_url_binds_principal_and_audits(self, tmp_path):
        logged_events = []

        class DummyAuditLogger:
            def log_event(self, event_type, session, details):
                logged_events.append((event_type, session, details))
                return {"event_type": event_type, "details": details}

        tool = OpenURLTool(
            client_factory=lambda config: FakeClient(config)
        )
        tool._audit_logger = DummyAuditLogger()

        principal = Principal(id="user_123", roles=["analyst"], permissions=["external_network"])
        invocation = ToolInvocation(
            id="call-1",
            tool_name="open_url",
            params={"url": "https://example.com"},
        )
        ctx = ToolExecutionContext(
            session_id="session-1",
            principal=principal,
            workspace_root=str(tmp_path),
            user_approved=True,
            env_vars={},
        )

        res = await tool.execute(invocation, ctx)
        assert res.success is True
        assert len(logged_events) == 1
        event_type, session, details = logged_events[0]
        assert event_type == "open_url"
        assert details["principal_id"] == "user_123"

    @pytest.mark.asyncio
    async def test_click_xy_binds_principal_and_audits(self, tmp_path):
        logged_events = []

        class DummyAuditLogger:
            def log_event(self, event_type, session, details):
                logged_events.append((event_type, session, details))
                return {"event_type": event_type, "details": details}

        tool = ClickXYTool(
            client_factory=lambda config: FakeClient(config)
        )
        tool._audit_logger = DummyAuditLogger()

        principal = Principal(id="user_456", roles=["analyst"], permissions=[])
        invocation = ToolInvocation(
            id="call-2",
            tool_name="click_xy",
            params={"target": "@ref-123"},
        )
        ctx = ToolExecutionContext(
            session_id="session-2",
            principal=principal,
            workspace_root=str(tmp_path),
            user_approved=True,
            env_vars={},
        )

        res = await tool.execute(invocation, ctx)
        assert res.success is True
        assert len(logged_events) == 1
        event_type, session, details = logged_events[0]
        assert event_type == "click_xy"
        assert details["principal_id"] == "user_456"
        assert details["target"] == "@ref-123"


class FakeClient:
    def __init__(self, config: AgentBrowserConfig):
        self.config = config

    async def open_and_read(self, url, **kwargs):
        from windagent_tools.browser.agent_browser import BrowserPageCapture
        return BrowserPageCapture(
            requested_url=url,
            final_url=url,
            title="Fake Page",
            text="Rendered Content",
        )

    async def click_target(self, target, **kwargs):
        pass

    async def snapshot(self):
        return "@ref-123"

    async def session_health(self):
        return {"has_cookies": False}

    async def close(self):
        pass
