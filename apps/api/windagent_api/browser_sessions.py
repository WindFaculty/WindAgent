"""In-memory browser-session bridge used by the desktop UI.

The service owns only browser daemon state and screenshots. Durable WindAgent
sessions remain owned by the canonical V2 session repository. A Chrome profile
is never selected implicitly: callers must explicitly opt in for each browser
session before its first navigation.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Optional
from urllib.parse import urlsplit

from windagent_tools.browser.agent_browser import (
    SOCIAL_PLATFORM_DOMAINS,
    AgentBrowserClient,
    AgentBrowserConfig,
    AgentBrowserError,
    BrowserPageCapture,
    platform_for_url,
)
from windagent_tools.security.permission_engine import PermissionEngine
from windagent_core.security.types import (
    PermissionEvaluationRequest,
    Principal,
    RiskLevel,
)


BrowserControl = Literal["agent", "user"]
_PROFILE_NAME = re.compile(r"^[A-Za-z0-9 _.-]{1,64}$")
_VIEWPORT_WIDTH = 1280
_VIEWPORT_HEIGHT = 800
_MAX_EXTRACTED_CHARS = 100_000


class BrowserSessionError(RuntimeError):
    """A browser-session request could not be completed safely."""


class BrowserSessionConflictError(BrowserSessionError):
    """An action conflicts with the session's existing browser configuration."""


@dataclass(frozen=True)
class BrowserLaunchOptions:
    authenticated: bool = False
    profile: Optional[str] = None


@dataclass
class BrowserState:
    session_id: str
    url: str = "about:blank"
    title: str = "New Tab"
    loading: bool = False
    screenshot_path: Optional[Path] = None
    controlled_by: BrowserControl = "agent"
    extracted_text: str = ""
    error: Optional[str] = None
    authenticated: bool = False
    profile: Optional[str] = None


@dataclass
class _BrowserSession:
    options: BrowserLaunchOptions
    client: AgentBrowserClient
    state: BrowserState
    allowed_domains: tuple[str, ...]
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


ClientFactory = Callable[[AgentBrowserConfig], AgentBrowserClient]


class BrowserSessionService:
    """Serializes UI actions against a persistent named agent-browser session."""

    def __init__(
        self,
        *,
        screenshot_root: Optional[Path] = None,
        client_factory: Optional[ClientFactory] = None,
        permission_engine: Optional[PermissionEngine] = None,
    ) -> None:
        self._screenshot_root = screenshot_root or (
            Path(tempfile.gettempdir()) / "windagent-browser"
        )
        self._client_factory = client_factory or AgentBrowserClient
        self._permission_engine = permission_engine or PermissionEngine()
        self._sessions: dict[str, _BrowserSession] = {}
        self._sessions_lock = asyncio.Lock()

    @staticmethod
    def _browser_session_name(session_id: str) -> str:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
        return f"windagent-ui-{digest}"

    @staticmethod
    def _allowed_domains(url: str) -> tuple[str, ...]:
        platform = platform_for_url(url)
        if platform and platform in SOCIAL_PLATFORM_DOMAINS:
            return SOCIAL_PLATFORM_DOMAINS[platform]
        hostname = urlsplit(url).hostname
        if not hostname:
            return ()
        hostname = hostname.lower()
        return (hostname, f"*.{hostname}")

    @staticmethod
    def _validate_options(options: BrowserLaunchOptions) -> BrowserLaunchOptions:
        profile = options.profile.strip() if options.profile else None
        if profile and not options.authenticated:
            raise BrowserSessionError(
                "Chrome profile requires explicit authenticated=true."
            )
        if profile and not _PROFILE_NAME.fullmatch(profile):
            raise BrowserSessionError(
                "Chrome profile must be a profile name, not a filesystem path."
            )
        if options.authenticated:
            return BrowserLaunchOptions(
                authenticated=True, profile=profile or "Default"
            )
        return BrowserLaunchOptions()

    def _make_client(
        self,
        session_id: str,
        options: BrowserLaunchOptions,
        allowed_domains: tuple[str, ...],
    ) -> AgentBrowserClient:
        binary = os.environ.get("AGENT_BROWSER_BIN")
        if not binary:
            binary = (
                shutil.which("agent-browser.cmd")
                or shutil.which("agent-browser")
                or "agent-browser"
            )
        config = AgentBrowserConfig(
            binary=binary,
            session=self._browser_session_name(session_id),
            authenticated=options.authenticated,
            profile=options.profile,
            timeout_seconds=float(
                os.environ.get("WINDAGENT_BROWSER_TIMEOUT_SECONDS", "60")
            ),
            retry_attempts=int(os.environ.get("WINDAGENT_BROWSER_RETRY_ATTEMPTS", "2")),
            retry_backoff_seconds=float(
                os.environ.get("WINDAGENT_BROWSER_RETRY_BACKOFF_SECONDS", "0.25")
            ),
            cleanup_timeout_seconds=float(
                os.environ.get("WINDAGENT_BROWSER_CLEANUP_TIMEOUT_SECONDS", "8")
            ),
            max_output_chars=_MAX_EXTRACTED_CHARS,
            containment_mode="preflight" if options.authenticated else "native",
            allowed_domains=allowed_domains,
            headless=os.environ.get("WINDAGENT_BROWSER_HEADLESS", "").strip().lower()
            in {"1", "true", "yes"},
        )
        return self._client_factory(config)

    async def _get_or_create(
        self,
        session_id: str,
        options: BrowserLaunchOptions,
        url: str,
    ) -> _BrowserSession:
        safe_options = self._validate_options(options)
        allowed_domains = self._allowed_domains(url)
        async with self._sessions_lock:
            existing = self._sessions.get(session_id)
            if existing is not None:
                if existing.options != safe_options:
                    raise BrowserSessionConflictError(
                        "Chrome-profile settings cannot change in an active browser "
                        "session. Close the browser session before changing them."
                    )
                if existing.allowed_domains != allowed_domains:
                    # Native domain containment is fixed at browser launch. A
                    # new host therefore gets a fresh daemon while retaining
                    # the same logical WindAgent session and explicit profile
                    # consent; this prevents the old host's allow-list from
                    # silently expanding.
                    async with existing.lock:
                        try:
                            await existing.client.close()
                        except AgentBrowserError:
                            pass
                        existing.client = self._make_client(
                            session_id, safe_options, allowed_domains
                        )
                        existing.allowed_domains = allowed_domains
                return existing
            state = BrowserState(
                session_id=session_id,
                authenticated=safe_options.authenticated,
                profile=safe_options.profile,
            )
            record = _BrowserSession(
                options=safe_options,
                client=self._make_client(session_id, safe_options, allowed_domains),
                state=state,
                allowed_domains=allowed_domains,
            )
            self._sessions[session_id] = record
            return record

    def _screenshot_path(self, session_id: str) -> Path:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        directory = self._screenshot_root / digest
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "current.png"

    @staticmethod
    def _apply_capture(
        state: BrowserState, capture: BrowserPageCapture
    ) -> BrowserState:
        state.url = capture.final_url
        state.title = capture.title or capture.final_url
        state.extracted_text = capture.text
        state.screenshot_path = (
            Path(capture.screenshot_path) if capture.screenshot_path else None
        )
        state.loading = False
        state.error = None
        return state

    @staticmethod
    def _mark_failure(state: BrowserState, error: BaseException) -> None:
        state.loading = False
        state.error = str(error)

    async def get_state(self, session_id: str) -> BrowserState:
        record = self._sessions.get(session_id)
        if record is None:
            return BrowserState(session_id=session_id)
        async with record.lock:
            return BrowserState(**record.state.__dict__)

    async def navigate(
        self,
        session_id: str,
        url: str,
        *,
        options: BrowserLaunchOptions,
    ) -> BrowserState:
        decision = self._permission_engine.evaluate_request(
            PermissionEvaluationRequest(
                principal=Principal(id="local-desktop-user", roles=["user"]),
                action="open_url",
                target=url,
                risk_level=RiskLevel.HIGH,
                context={
                    "workspace_root": os.getcwd(),
                    # This endpoint represents a direct navigation submitted
                    # from the local user's Browser Panel.
                    "user_approved": True,
                    "is_destructive": False,
                },
            )
        )
        if not decision.is_allowed:
            raise BrowserSessionError(f"Permission denied: {decision.human_reason}")
        record = await self._get_or_create(session_id, options, url)
        async with record.lock:
            record.state.loading = True
            try:
                await record.client.set_viewport(_VIEWPORT_WIDTH, _VIEWPORT_HEIGHT)
                capture = await record.client.open_and_read(
                    url,
                    wait_until="domcontentloaded",
                    max_chars=_MAX_EXTRACTED_CHARS,
                    screenshot_path=str(self._screenshot_path(session_id)),
                    close_session=False,
                )
                return BrowserState(
                    **self._apply_capture(record.state, capture).__dict__
                )
            except (AgentBrowserError, ValueError) as exc:
                self._mark_failure(record.state, exc)
                raise BrowserSessionError(str(exc)) from exc

    async def _capture_after_action(self, record: _BrowserSession) -> BrowserState:
        capture = await record.client.capture_current_page(
            max_chars=_MAX_EXTRACTED_CHARS,
            screenshot_path=str(self._screenshot_path(record.state.session_id)),
        )
        return BrowserState(**self._apply_capture(record.state, capture).__dict__)

    async def click(self, session_id: str, x: int, y: int) -> BrowserState:
        record = self._sessions.get(session_id)
        if record is None:
            raise BrowserSessionConflictError(
                "Navigate before interacting with the browser."
            )
        async with record.lock:
            if record.state.controlled_by != "user":
                raise BrowserSessionConflictError(
                    "Take user control before clicking the browser preview."
                )
            record.state.loading = True
            try:
                await record.client.click_xy(x, y)
                return await self._capture_after_action(record)
            except (AgentBrowserError, ValueError) as exc:
                self._mark_failure(record.state, exc)
                raise BrowserSessionError(str(exc)) from exc

    async def type_text(
        self, session_id: str, selector: str, text: str
    ) -> BrowserState:
        record = self._sessions.get(session_id)
        if record is None:
            raise BrowserSessionConflictError(
                "Navigate before typing into the browser."
            )
        async with record.lock:
            record.state.loading = True
            try:
                await record.client.type_text(selector, text)
                return await self._capture_after_action(record)
            except (AgentBrowserError, ValueError) as exc:
                self._mark_failure(record.state, exc)
                raise BrowserSessionError(str(exc)) from exc

    async def scroll(
        self, session_id: str, direction: Literal["up", "down"], pixels: int
    ) -> BrowserState:
        record = self._sessions.get(session_id)
        if record is None:
            raise BrowserSessionConflictError("Navigate before scrolling the browser.")
        async with record.lock:
            if record.state.controlled_by != "user":
                raise BrowserSessionConflictError(
                    "Take user control before scrolling the browser preview."
                )
            record.state.loading = True
            try:
                await record.client.scroll(direction, pixels)
                return await self._capture_after_action(record)
            except (AgentBrowserError, ValueError) as exc:
                self._mark_failure(record.state, exc)
                raise BrowserSessionError(str(exc)) from exc

    async def _history_action(self, session_id: str, action: str) -> BrowserState:
        record = self._sessions.get(session_id)
        if record is None:
            raise BrowserSessionConflictError("Navigate before using browser history.")
        async with record.lock:
            record.state.loading = True
            try:
                await getattr(record.client, action)()
                return await self._capture_after_action(record)
            except (AgentBrowserError, ValueError) as exc:
                self._mark_failure(record.state, exc)
                raise BrowserSessionError(str(exc)) from exc

    async def go_back(self, session_id: str) -> BrowserState:
        return await self._history_action(session_id, "go_back")

    async def go_forward(self, session_id: str) -> BrowserState:
        return await self._history_action(session_id, "go_forward")

    async def reload(self, session_id: str) -> BrowserState:
        return await self._history_action(session_id, "reload")

    async def set_control(
        self, session_id: str, controlled_by: BrowserControl
    ) -> BrowserState:
        record = self._sessions.get(session_id)
        if record is None:
            raise BrowserSessionConflictError(
                "Navigate before changing browser control."
            )
        async with record.lock:
            record.state.controlled_by = controlled_by
            return BrowserState(**record.state.__dict__)

    async def screenshot_path(self, session_id: str) -> Path:
        record = self._sessions.get(session_id)
        if record is None or record.state.screenshot_path is None:
            raise BrowserSessionConflictError("No browser screenshot is available.")
        async with record.lock:
            path = record.state.screenshot_path
            if path is None or not path.is_file():
                raise BrowserSessionConflictError("No browser screenshot is available.")
            return path

    async def close(self, session_id: str) -> None:
        async with self._sessions_lock:
            record = self._sessions.pop(session_id, None)
        if record is None:
            return
        async with record.lock:
            try:
                await record.client.close()
            except AgentBrowserError:
                pass
            if record.state.screenshot_path:
                record.state.screenshot_path.unlink(missing_ok=True)

    async def close_all(self) -> None:
        session_ids = list(self._sessions)
        for session_id in session_ids:
            await self.close(session_id)
