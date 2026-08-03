"""
Phase 12 — Bounded browser runtime worker (plan 04 §8.2–§8.5).

`BrowserRuntime` is the durable, bounded browser worker for WindAgent. It:

- executes only *typed* operations through `BrowserActionPolicy` (fail closed);
- records redacted evidence for every action via `BrowserEvidenceRecorder`;
- owns one persistent session/profile and a valid profile lock lease;
- classifies health through `BrowserHealthCheck`;
- supports timeout, cancel, worker restart and session reattach without
  losing the session registry / job mapping (job mapping is a separate
  durable record owned by WindAgent).

The runtime never submits a real Flow generation (Phase 14/15) and never
executes raw model-generated browser commands. It is fully testable with a
fake process port — no Chrome or Flow production is required (gate §10).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from windagent_tools.browser.action_policy import (
    BrowserActionPolicy,
    BrowserOperation,
)
from windagent_tools.browser.agent_browser import (
    AgentBrowserClient,
    AgentBrowserConfig,
    AgentBrowserError,
    AgentBrowserProcessPort,
    SubprocessAgentBrowserProcess,
)
from windagent_tools.browser.evidence_capture import (
    BrowserActionEvidence,
    BrowserActionResultState,
    BrowserEvidenceRecorder,
)
from windagent_tools.browser.healthcheck import (
    BrowserHealthCheck,
    BrowserHealthReport,
)
from windagent_tools.browser.session import (
    BrowserProfileLock,
    BrowserSessionMetadata,
    BrowserSessionRegistry,
    BrowserSessionState,
)


class BrowserRuntimeError(RuntimeError):
    """Base error raised by the browser runtime."""


class BrowserActionDeniedError(BrowserRuntimeError):
    """Raised when a typed operation is rejected by the action policy."""


class BrowserActionTimeoutError(BrowserRuntimeError):
    """Raised when a bounded action exceeds its time budget."""


class BrowserSessionNotHealthyError(BrowserRuntimeError):
    """Raised when an operation is requested for an unhealthy session."""


@dataclass(frozen=True)
class BrowserActionResult:
    """Outcome of one bounded action with its evidence record."""

    operation: str
    evidence: BrowserActionEvidence
    captured_text: str = ""
    final_url: str = ""

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "evidence": self.evidence.to_dict(),
            "captured_text_chars": len(self.captured_text),
            "final_url": self.final_url,
        }


ClientFactory = Callable[[AgentBrowserConfig], AgentBrowserClient]


class BrowserRuntime:
    """Bounded, durable browser worker for one persistent session."""

    def __init__(
        self,
        *,
        session_id: str,
        workspace_root: str,
        profile_key: str = "",
        allowed_domains: Sequence[str] = (),
        approved_asset_store: Optional[str] = None,
        config: Optional[AgentBrowserConfig] = None,
        process: Optional[AgentBrowserProcessPort] = None,
        client_factory: Optional[ClientFactory] = None,
        policy: Optional[BrowserActionPolicy] = None,
        health_check: Optional[BrowserHealthCheck] = None,
        lock_lease_seconds: float = 1800.0,
        action_timeout_seconds: float = 60.0,
        clock: Optional[callable] = None,
    ) -> None:
        self.session_id = session_id
        self.workspace_root = workspace_root
        self.profile_key = profile_key
        self._clock = clock or time.time

        self._lock = BrowserProfileLock(
            workspace_root,
            lease_seconds=lock_lease_seconds,
            clock=clock,
        )
        self._registry = BrowserSessionRegistry(
            f"{workspace_root}/artifacts/browser_sessions",
            clock=clock,
        )
        self._policy = policy or BrowserActionPolicy(
            allowed_domains=allowed_domains,
            approved_asset_store=approved_asset_store,
        )
        self._health = health_check or BrowserHealthCheck(
            allowed_domains=allowed_domains,
            clock=clock,
        )
        self._evidence = BrowserEvidenceRecorder(session_id=session_id, clock=clock)

        self._config = config or AgentBrowserConfig(
            session=session_id,
            authenticated=bool(profile_key),
            allowed_domains=tuple(d.lower().strip() for d in allowed_domains),
        )
        self._process = process or SubprocessAgentBrowserProcess()
        self._client_factory = client_factory or (
            lambda cfg: AgentBrowserClient(cfg, process=self._process)
        )
        self._client: Optional[AgentBrowserClient] = None
        self._lease_token = ""
        self._lease_expires_at = 0.0
        self._started = False
        self._started_at = 0.0
        self.action_timeout_seconds = action_timeout_seconds

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> BrowserSessionMetadata:
        """Acquire the profile lock lease and register the session.

        Raises `BrowserProfileLockError` on a lock collision (two workers
        using the same profile).
        """
        token = self._lock.acquire(self.profile_key, worker_id=f"worker:{self.session_id}")
        self._lease_token = token
        self._lease_expires_at = self._clock() + self._lock.lease_seconds

        existing = self._registry.get(self.session_id)
        if existing is None:
            meta = self._registry.register(
                self.session_id,
                profile_key=self.profile_key,
            )
        else:
            meta = self._registry.update_state(
                self.session_id, BrowserSessionState.STARTING
            )
        meta = self._registry.bind_lease(
            self.session_id, token=token, expires_at=self._lease_expires_at
        )
        self._registry.update_state(self.session_id, BrowserSessionState.READY)
        self._client = self._client_factory(self._config)
        self._started = True
        self._started_at = self._clock()
        return meta

    async def stop(self) -> None:
        """Close the browser session and release the profile lock."""
        if self._client is not None:
            with contextlib.suppress(AgentBrowserError, asyncio.TimeoutError):
                await self._client.close()
        self._lock.release(self.profile_key, self._lease_token)
        with contextlib.suppress(Exception):
            self._registry.close(self.session_id)
        self._started = False

    async def reattach(self) -> BrowserSessionMetadata:
        """Reattach to an existing registered session (worker restart path).

        Requires the profile lock lease to be refreshed; the session registry
        and job mapping (owned by WindAgent) survive worker restarts.
        """
        existing = self._registry.get(self.session_id)
        if existing is None:
            raise BrowserRuntimeError(
                f"cannot reattach: session {self.session_id} is not registered"
            )
        token = self._lock.acquire(self.profile_key, worker_id=f"worker:{self.session_id}")
        self._lease_token = token
        self._lease_expires_at = self._clock() + self._lock.lease_seconds
        self._registry.bind_lease(
            self.session_id, token=token, expires_at=self._lease_expires_at
        )
        self._registry.update_state(self.session_id, BrowserSessionState.READY)
        self._client = self._client_factory(self._config)
        self._started = True
        self._started_at = self._clock()
        return self._registry.get(self.session_id)  # type: ignore[return-value]

    def refresh_lease(self) -> bool:
        """Extend the profile lock lease (health check loop hook)."""
        ok = self._lock.refresh(self.profile_key, self._lease_token)
        if ok:
            self._lease_expires_at = self._clock() + self._lock.lease_seconds
            with contextlib.suppress(Exception):
                self._registry.touch_health(self.session_id)
        return ok

    # ------------------------------------------------------------------
    # Bounded actions
    # ------------------------------------------------------------------
    async def execute(
        self,
        operation: BrowserOperation,
        *,
        target: Optional[str] = None,
        screenshot_path: Optional[str] = None,
        workspace_path: Optional[str] = None,
        session_state: Optional[BrowserSessionState] = None,
    ) -> BrowserActionResult:
        """Execute one typed bounded action, fail closed.

        Every step is gated by the action policy; the evidence record is
        written for success, denial, failure, timeout and cancellation alike.
        """
        if not self._started:
            raise BrowserRuntimeError("runtime must be started before executing actions")

        decision = self._policy.evaluate(
            operation,
            target=target,
            workspace_root=self.workspace_root,
            session_state=session_state.value if session_state else None,
        )
        if not decision.allowed:
            self._evidence.finish(
                self._begin_evidence(operation, target),
                BrowserActionResultState.BLOCKED,
                error_class="BrowserActionDeniedError",
            )
            raise BrowserActionDeniedError(
                f"{operation.value} denied: {decision.reason}"
            ) from None

        health = await self.health()
        if health.status.value != "HEALTHY":
            raise BrowserSessionNotHealthyError(
                f"session {self.session_id} is {health.status.value}: {health.reason}"
            )

        action_id = self._begin_evidence(operation, target)
        try:
            captured_text, final_url = await self._dispatch(
                operation,
                target=target,
                screenshot_path=screenshot_path,
                workspace_path=workspace_path,
            )
        except asyncio.TimeoutError:
            self._evidence.finish(
                action_id,
                BrowserActionResultState.TIMED_OUT,
                error_class="BrowserActionTimeoutError",
            )
            raise BrowserActionTimeoutError(
                f"{operation.value} exceeded {self.action_timeout_seconds}s"
            ) from None
        except asyncio.CancelledError:
            self._evidence.finish(
                action_id,
                BrowserActionResultState.CANCELLED,
                error_class="asyncio.CancelledError",
            )
            raise
        except AgentBrowserError as exc:
            self._evidence.finish(
                action_id,
                BrowserActionResultState.FAILED,
                error_class=type(exc).__name__,
            )
            raise BrowserRuntimeError(f"{operation.value} failed: {exc}") from exc

        evidence = self._evidence.finish(
            action_id,
            BrowserActionResultState.SUCCESS,
            screenshot_path=screenshot_path,
        )
        return BrowserActionResult(
            operation=operation.value,
            evidence=evidence,
            captured_text=captured_text,
            final_url=final_url,
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    async def health(self) -> BrowserHealthReport:
        """Classify session health from observable signals (no browser needed
        when the client is a fake; with a real process it queries the live
        session)."""
        meta = self._registry.get(self.session_id)
        process_alive = self._started
        browser_reachable = self._started
        current_url = ""
        if self._client is not None:
            try:
                health_data = await asyncio.wait_for(
                    self._client.session_health(),
                    timeout=min(self.action_timeout_seconds, 10.0),
                )
                current_url = str(health_data.get("url", ""))
                browser_reachable = True
            except (AgentBrowserError, asyncio.TimeoutError, AttributeError):
                browser_reachable = False

        session_state = meta.state if meta else BrowserSessionState.NEW
        return self._health.check(
            process_alive=process_alive,
            browser_reachable=browser_reachable,
            current_url=current_url or None,
            profile_lock_valid=bool(self._lease_token),
            session_state=session_state,
            lease_expires_at=self._lease_expires_at,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _begin_evidence(self, operation: BrowserOperation, target: Optional[str]) -> str:
        return self._evidence.begin(operation.value, target=target)

    async def _dispatch(
        self,
        operation: BrowserOperation,
        *,
        target: Optional[str],
        screenshot_path: Optional[str],
        workspace_path: Optional[str],
    ) -> tuple[str, str]:
        client = self._client
        if client is None:
            raise BrowserRuntimeError("no browser client")

        if operation == BrowserOperation.OPEN_URL:
            capture = await self._with_timeout(
                client.open_and_read(
                    str(target),
                    screenshot_path=screenshot_path,
                    close_session=False,
                )
            )
            return capture.text, capture.final_url

        if operation == BrowserOperation.SNAPSHOT:
            snapshot = await self._with_timeout(client.snapshot())
            return snapshot, ""

        if operation == BrowserOperation.CLICK:
            await self._with_timeout(client.click_target(str(target)))
            return "", ""

        if operation == BrowserOperation.FILL:
            # `target` is the semantic locator; `workspace_path` carries the text.
            await self._with_timeout(client.type_text(str(target), workspace_path or ""))
            return "", ""

        if operation == BrowserOperation.SELECT:
            await self._with_timeout(client.click_target(str(target)))
            return "", ""

        if operation == BrowserOperation.SCREENSHOT:
            await self._with_timeout(
                client.capture_current_page(screenshot_path=screenshot_path)
            )
            return "", ""

        if operation == BrowserOperation.WAIT:
            await self._with_timeout(client.wait_for(str(target)))
            return "", ""

        if operation == BrowserOperation.UPLOAD:
            # Uploads are typed operations over the approved asset store; the
            # policy already verified the path. For Phase 12 (no Flow yet) we
            # assert the approved file exists, then record evidence.
            if workspace_path is None:
                raise BrowserRuntimeError("upload requires an approved asset path")
            if not Path(workspace_path).exists():
                raise BrowserRuntimeError(
                    f"approved upload asset does not exist: {workspace_path}"
                )
            await self._with_timeout(client.wait_for("domcontentloaded", condition="domcontentloaded"))
            return "", ""

        if operation == BrowserOperation.DOWNLOAD:
            if workspace_path is None:
                raise BrowserRuntimeError("download requires a workspace path")
            await self._with_timeout(client.capture_current_page())
            return "", ""

        raise BrowserActionDeniedError(f"unsupported operation {operation.value}")

    async def _with_timeout(self, awaitable):
        return await asyncio.wait_for(awaitable, timeout=self.action_timeout_seconds)


__all__ = [
    "BrowserActionDeniedError",
    "BrowserActionResult",
    "BrowserActionTimeoutError",
    "BrowserRuntime",
    "BrowserRuntimeError",
    "BrowserSessionNotHealthyError",
    "ClientFactory",
]
