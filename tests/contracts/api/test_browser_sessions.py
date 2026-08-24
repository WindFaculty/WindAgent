"""Tests for the V2 browser bridge without launching Chrome."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from windagent_api.browser_sessions import (
    BrowserLaunchOptions,
    BrowserSessionConflictError,
    BrowserSessionService,
)
from windagent_api.routers.v2_browser import router
from windagent_tools.browser.agent_browser import BrowserPageCapture


class FakeBrowserClient:
    def __init__(self, config):
        self.config = config
        self.url = "about:blank"
        self.closed = False
        self.clicks: list[tuple[int, int]] = []
        self.viewport: tuple[int, int] | None = None

    async def set_viewport(self, width: int, height: int) -> None:
        self.viewport = (width, height)

    async def open_and_read(self, url: str, **kwargs) -> BrowserPageCapture:
        self.url = url
        screenshot_path = kwargs.get("screenshot_path")
        if screenshot_path:
            Path(screenshot_path).touch()
        return BrowserPageCapture(
            requested_url=url,
            final_url=url,
            title="TikTok test page",
            text="public video metadata",
            screenshot_path=screenshot_path,
        )

    async def capture_current_page(self, **kwargs) -> BrowserPageCapture:
        screenshot_path = kwargs.get("screenshot_path")
        if screenshot_path:
            Path(screenshot_path).touch()
        return BrowserPageCapture(
            requested_url=self.url,
            final_url=self.url,
            title="TikTok test page",
            text="public video metadata after interaction",
            screenshot_path=screenshot_path,
        )

    async def click_xy(self, x: int, y: int) -> None:
        self.clicks.append((x, y))

    async def type_text(self, selector: str, text: str) -> None:
        self.url = f"{self.url}#{selector}:{text}"

    async def scroll(self, direction: str, pixels: int) -> None:
        self.url = f"{self.url}#{direction}:{pixels}"

    async def go_back(self) -> None:
        self.url = "https://www.tiktok.com/previous"

    async def go_forward(self) -> None:
        self.url = "https://www.tiktok.com/next"

    async def reload(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


class FakeClientFactory:
    def __init__(self):
        self.clients: list[FakeBrowserClient] = []

    def __call__(self, config):
        client = FakeBrowserClient(config)
        self.clients.append(client)
        return client


@pytest.mark.asyncio
async def test_browser_service_requires_explicit_profile_opt_in_and_keeps_content(
    tmp_path,
):
    factory = FakeClientFactory()
    service = BrowserSessionService(
        screenshot_root=tmp_path,
        client_factory=factory,
    )

    with pytest.raises(Exception, match="explicit authenticated"):
        await service.navigate(
            "session-1",
            "https://www.tiktok.com/vi-VN/",
            options=BrowserLaunchOptions(profile="Default"),
        )

    state = await service.navigate(
        "session-1",
        "https://www.tiktok.com/vi-VN/",
        options=BrowserLaunchOptions(authenticated=True, profile="Default"),
    )

    assert state.authenticated is True
    assert state.profile == "Default"
    assert state.extracted_text == "public video metadata"
    assert state.screenshot_path and state.screenshot_path.is_file()
    assert factory.clients[0].viewport == (1280, 800)
    assert factory.clients[0].config.containment_mode == "preflight"
    assert "*.tiktok.com" in factory.clients[0].config.allowed_domains


@pytest.mark.asyncio
async def test_browser_service_allows_click_only_under_user_control(tmp_path):
    factory = FakeClientFactory()
    service = BrowserSessionService(screenshot_root=tmp_path, client_factory=factory)
    await service.navigate(
        "session-2",
        "https://example.com/",
        options=BrowserLaunchOptions(),
    )

    with pytest.raises(BrowserSessionConflictError, match="Take user control"):
        await service.click("session-2", 50, 75)

    await service.set_control("session-2", "user")
    state = await service.click("session-2", 50, 75)

    assert state.extracted_text.endswith("after interaction")
    assert factory.clients[0].clicks == [(50, 75)]


def test_browser_router_returns_state_screenshot_and_controlled_click(tmp_path):
    factory = FakeClientFactory()
    app = FastAPI()
    app.include_router(router)
    app.state.browser_session_service = BrowserSessionService(
        screenshot_root=tmp_path,
        client_factory=factory,
    )

    with TestClient(app) as client:
        initial = client.get("/api/v2/browser/sessions/session-3")
        assert initial.status_code == 200
        assert initial.json()["url"] == "about:blank"

        navigated = client.post(
            "/api/v2/browser/sessions/session-3/navigate",
            json={"url": "https://www.tiktok.com/vi-VN/", "authenticated": True},
        )
        assert navigated.status_code == 200
        payload = navigated.json()
        assert payload["profile"] == "Default"
        assert payload["content_chars"] == len("public video metadata")
        assert payload["screenshot_url"].endswith("/session-3/screenshot")

        screenshot = client.get(payload["screenshot_url"])
        assert screenshot.status_code == 200

        denied = client.post(
            "/api/v2/browser/sessions/session-3/click", json={"x": 10, "y": 20}
        )
        assert denied.status_code == 409

        control = client.post(
            "/api/v2/browser/sessions/session-3/control",
            json={"controlled_by": "user"},
        )
        assert control.status_code == 200
        clicked = client.post(
            "/api/v2/browser/sessions/session-3/click", json={"x": 10, "y": 20}
        )
        assert clicked.status_code == 200
        assert clicked.json()["extracted_text"].endswith("after interaction")

        scrolled = client.post(
            "/api/v2/browser/sessions/session-3/scroll",
            json={"direction": "down", "pixels": 800},
        )
        assert scrolled.status_code == 200
        assert scrolled.json()["url"].endswith("#down:800")
