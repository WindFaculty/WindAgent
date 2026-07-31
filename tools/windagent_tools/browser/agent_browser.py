"""Production subprocess adapter for ``vercel-labs/agent-browser``.

The adapter deliberately uses argv-based subprocess execution instead of a shell.
It validates navigation targets before Chrome is launched, limits returned text,
and supports dependency injection so the browser contract can be tested without
starting Chrome.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import ipaddress
import json
import logging
import os
import re
import socket
import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Sequence
from urllib.parse import urlsplit


SOCIAL_PLATFORM_DOMAINS: dict[str, tuple[str, ...]] = {
    "facebook": ("facebook.com", "*.facebook.com", "fb.watch"),
    "youtube": ("youtube.com", "*.youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com", "*.tiktok.com"),
}

_SESSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SECRET_ENV_MARKERS = ("API_KEY", "AUTH_TOKEN", "ACCESS_TOKEN", "SECRET", "PASSWORD")


class AgentBrowserError(RuntimeError):
    """Base error raised by the agent-browser process adapter."""


class AgentBrowserUnavailableError(AgentBrowserError):
    """Raised when the configured binary cannot be started."""


class AgentBrowserProcessStartError(AgentBrowserUnavailableError):
    """Raised when the configured executable exists but cannot be launched."""


class AgentBrowserTimeoutError(AgentBrowserError):
    """Raised when one browser CLI command exceeds its time budget."""


class AgentBrowserNonZeroExitError(AgentBrowserError):
    """Raised when agent-browser exits with a non-zero status."""


class AgentBrowserCommandError(AgentBrowserNonZeroExitError):
    """Backward-compatible name for command failures."""


class AgentBrowserPolicyError(AgentBrowserError):
    """Raised when a requested navigation violates the browser policy."""


def is_retryable_browser_error(error: BaseException) -> bool:
    """Classify only transient adapter failures as safe to retry."""
    return isinstance(error, (AgentBrowserProcessStartError, AgentBrowserTimeoutError))


@dataclass(frozen=True)
class AgentBrowserCommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    parsed: Any = None


class AgentBrowserProcessPort(Protocol):
    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float,
        env: Mapping[str, str],
    ) -> AgentBrowserCommandResult:
        """Execute one agent-browser command."""


class SubprocessAgentBrowserProcess:
    """Runs agent-browser without invoking a command shell."""

    _REAP_TIMEOUT_SECONDS = 3.0

    @staticmethod
    async def _terminate(process: asyncio.subprocess.Process) -> None:
        """Terminate a child and reap it, including during task cancellation."""
        if (
            process.returncode is None
            and sys.platform == "win32"
            and getattr(process, "pid", None)
        ):
            # agent-browser starts Chrome as a child daemon. Killing only the
            # CLI leaves that daemon alive (and its inherited pipes open), so
            # terminate the verified process tree on Windows.
            with contextlib.suppress(OSError, asyncio.TimeoutError):
                killer = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(killer.wait(), timeout=3)
        elif process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
        # A browser daemon can inherit the CLI stdout/stderr pipe. Waiting on
        # ``communicate`` after killing its parent can then block until Chrome
        # exits, so reap only the direct child with a hard upper bound.
        with contextlib.suppress(
            ProcessLookupError, asyncio.TimeoutError, asyncio.CancelledError
        ):
            await asyncio.wait_for(
                process.wait(),
                timeout=SubprocessAgentBrowserProcess._REAP_TIMEOUT_SECONDS,
            )
        # On Windows ProactorEventLoop, a killed child whose browser descendant
        # inherited stdio can leave pipe transports alive after ``wait``. Close
        # the private transport while the event loop is still running so Python
        # does not emit unclosed-transport warnings at shutdown.
        transport = getattr(process, "_transport", None)
        if transport is not None:
            with contextlib.suppress(Exception):
                transport.close()

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float,
        env: Mapping[str, str],
    ) -> AgentBrowserCommandResult:
        command = tuple(str(item) for item in argv)
        # Resolve Windows .cmd wrapper to actual executable
        if sys.platform == "win32" and command[0].lower().endswith(".cmd"):
            import shutil

            resolved = shutil.which(command[0])
            if resolved and resolved.lower().endswith(".cmd"):
                try:
                    with open(resolved, "r") as f:
                        content = f.read()
                    import re
                    import os

                    # Match %~dp0...exe pattern
                    match = re.search(r'%~dp0([^"\s]+\.exe)', content)
                    if match:
                        exe_rel = match.group(1).replace("/", "\\")
                        exe_path = os.path.join(os.path.dirname(resolved), exe_rel)
                        if os.path.exists(exe_path):
                            command = (exe_path,) + command[1:]
                        else:
                            # Fallback: search in node_modules
                            match2 = re.search(r'"([^"]+\.exe)"', content)
                            if match2:
                                command = (match2.group(1),) + command[1:]
                    else:
                        match2 = re.search(r'"([^"]+\.exe)"', content)
                        if match2:
                            command = (match2.group(1),) + command[1:]
                except Exception:
                    pass
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=dict(env),
            )
        except FileNotFoundError as exc:
            raise AgentBrowserUnavailableError(
                f"agent-browser binary not found: {command[0]}"
            ) from exc
        except OSError as exc:
            raise AgentBrowserProcessStartError(
                f"agent-browser could not be started: {type(exc).__name__}: {exc}"
            ) from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            await self._terminate(process)
            raise AgentBrowserTimeoutError(
                f"agent-browser timed out after {timeout_seconds:.1f}s"
            ) from exc
        except asyncio.CancelledError:
            # ``communicate`` cancellation does not terminate a child process.
            # Reap it here so task cancellation cannot leak a CLI child.
            await self._terminate(process)
            raise

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
        parsed = _parse_json_output(stdout)
        result = AgentBrowserCommandResult(
            argv=command,
            returncode=process.returncode or 0,
            stdout=stdout,
            stderr=stderr,
            parsed=parsed,
        )
        if result.returncode != 0:
            detail = stderr or stdout or "no diagnostic output"
            raise AgentBrowserNonZeroExitError(
                f"agent-browser exited {result.returncode}: {detail[-2000:]}"
            )
        return result


def _parse_json_output(text: str) -> Any:
    if not text:
        return None
    candidates = [text]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        candidates.append(lines[-1])
    first_object = text.find("{")
    last_object = text.rfind("}")
    if first_object >= 0 and last_object > first_object:
        candidates.append(text[first_object : last_object + 1])
    first_array = text.find("[")
    last_array = text.rfind("]")
    if first_array >= 0 and last_array > first_array:
        candidates.append(text[first_array : last_array + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _parse_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: Optional[str]) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


def _validate_session_name(value: str) -> str:
    if not _SESSION_PATTERN.fullmatch(value):
        raise AgentBrowserPolicyError(
            "Browser session must match [A-Za-z0-9._-] and be at most 64 characters."
        )
    return value


def domain_matches(hostname: str, pattern: str) -> bool:
    host = hostname.lower().rstrip(".")
    candidate = pattern.lower().strip().rstrip(".")
    if candidate.startswith("*."):
        base = candidate[2:]
        return host == base or host.endswith(f".{base}")
    return host == candidate


def platform_for_url(url: str) -> Optional[str]:
    hostname = (urlsplit(url).hostname or "").lower()
    for platform, patterns in SOCIAL_PLATFORM_DOMAINS.items():
        if any(domain_matches(hostname, pattern) for pattern in patterns):
            return platform
    return None


def validate_navigation_url(
    url: str,
    *,
    allowed_domains: Sequence[str],
    allow_private_network: bool,
) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise AgentBrowserPolicyError("Only http and https navigation is permitted.")
    if parts.username or parts.password:
        raise AgentBrowserPolicyError(
            "Credentials must not be embedded in navigation URLs."
        )
    hostname = (parts.hostname or "").lower().rstrip(".")
    if not hostname:
        raise AgentBrowserPolicyError("Navigation URL has no hostname.")

    if not allow_private_network:
        if (
            hostname == "localhost"
            or hostname.endswith(".localhost")
            or hostname.endswith(".local")
        ):
            raise AgentBrowserPolicyError("Private or local navigation is disabled.")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address and (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise AgentBrowserPolicyError(
                "Private or non-routable IP navigation is disabled."
            )
        if address is None:
            try:
                addr_info = socket.getaddrinfo(hostname, None)
                for family, socktype, proto, canonname, sockaddr in addr_info:
                    ip_str = sockaddr[0]
                    try:
                        resolved_ip = ipaddress.ip_address(ip_str)
                        if (
                            resolved_ip.is_private
                            or resolved_ip.is_loopback
                            or resolved_ip.is_link_local
                            or resolved_ip.is_multicast
                            or resolved_ip.is_reserved
                            or resolved_ip.is_unspecified
                        ):
                            raise AgentBrowserPolicyError(
                                f"DNS resolution for host {hostname!r} resolved to private or non-routable IP {ip_str!r}."
                            )
                    except ValueError:
                        continue
            except socket.gaierror:
                pass

    normalized_domains = tuple(
        item.lower().strip() for item in allowed_domains if item.strip()
    )
    if normalized_domains and not any(
        domain_matches(hostname, pattern) for pattern in normalized_domains
    ):
        raise AgentBrowserPolicyError(
            f"Navigation host {hostname!r} is outside the configured domain policy."
        )
    return url


class BrowserAuditLogger:
    """Sanitized logger for browser audit trail events."""

    _SENSITIVE_KEYS = {
        "cookie",
        "cookies",
        "token",
        "auth_token",
        "access_token",
        "api_key",
        "secret",
        "password",
        "authorization",
        "bearer",
        "pass",
        "pwd",
        "private_key",
        "session_token",
    }

    _URL_SECRET_REGEX = re.compile(
        r"([?&](?:token|api_key|auth|auth_token|access_token|secret|password|key|cred|credential)=)[^&]+",
        re.IGNORECASE,
    )

    def __init__(self, logger_name: str = "windagent.browser.audit") -> None:
        self.logger = logging.getLogger(logger_name)

    @classmethod
    def sanitize_url_string(cls, text: str) -> str:
        if isinstance(text, str) and ("?" in text or "&" in text):
            return cls._URL_SECRET_REGEX.sub(r"\1[REDACTED]", text)
        return text

    @classmethod
    def sanitize_dict(cls, data: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for k, v in data.items():
            key_lower = str(k).lower()
            if any(marker in key_lower for marker in cls._SENSITIVE_KEYS):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = cls.sanitize_dict(v)
            elif isinstance(v, list):
                sanitized[k] = [
                    cls.sanitize_dict(item)
                    if isinstance(item, dict)
                    else (cls.sanitize_url_string(item) if isinstance(item, str) else item)
                    for item in v
                ]
            elif isinstance(v, str):
                sanitized[k] = cls.sanitize_url_string(v)
            else:
                sanitized[k] = v
        return sanitized

    def log_event(
        self, event_type: str, session: str, details: dict[str, Any]
    ) -> dict[str, Any]:
        sanitized_details = self.sanitize_dict(details)
        record = {
            "event_type": event_type,
            "session": session,
            "timestamp": time.time(),
            "details": sanitized_details,
        }
        self.logger.info(
            "BrowserAudit: %s | Session: %s | %s", event_type, session, sanitized_details
        )
        return record


@dataclass(frozen=True)
class AgentBrowserConfig:
    binary: str = "agent-browser"
    session: str = "windagent"
    authenticated: bool = False
    profile: Optional[str] = None
    state_path: Optional[str] = None
    restore: bool = False
    timeout_seconds: float = 60.0
    retry_attempts: int = 2
    retry_backoff_seconds: float = 0.25
    cleanup_timeout_seconds: float = 8.0
    max_output_chars: int = 100_000
    content_boundaries: bool = True
    containment_mode: str = "native"
    allowed_domains: tuple[str, ...] = ()
    allow_private_network: bool = False
    headless: bool = True
    extra_env: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_session_name(self.session)
        if not self.binary.strip():
            raise AgentBrowserPolicyError("agent-browser binary path cannot be empty.")
        if self.timeout_seconds <= 0:
            raise AgentBrowserPolicyError("Browser timeout must be positive.")
        if self.retry_attempts < 1 or self.retry_attempts > 4:
            raise AgentBrowserPolicyError(
                "Browser retry attempts must be between 1 and 4."
            )
        if self.retry_backoff_seconds < 0 or self.retry_backoff_seconds > 10:
            raise AgentBrowserPolicyError(
                "Browser retry backoff must be between 0 and 10 seconds."
            )
        if self.cleanup_timeout_seconds <= 0 or self.cleanup_timeout_seconds > 30:
            raise AgentBrowserPolicyError(
                "Browser cleanup timeout must be between 0 and 30 seconds."
            )
        if self.max_output_chars < 1_000 or self.max_output_chars > 2_000_000:
            raise AgentBrowserPolicyError(
                "Browser max output must be between 1,000 and 2,000,000 characters."
            )
        if self.containment_mode not in {"native", "preflight"}:
            raise AgentBrowserPolicyError(
                "Browser containment mode must be 'native' or 'preflight'."
            )
        if self.profile and self.state_path:
            raise AgentBrowserPolicyError(
                "Configure either AGENT_BROWSER_PROFILE or AGENT_BROWSER_STATE, not both."
            )
        if (self.profile or self.state_path or self.restore) and not self.authenticated:
            raise AgentBrowserPolicyError(
                "Using a Chrome profile or saved state requires explicit authenticated=true."
            )
        if (
            self.containment_mode == "native"
            and self.allowed_domains
            and (self.profile or self.state_path or self.restore)
        ):
            raise AgentBrowserPolicyError(
                "agent-browser native domain containment cannot be combined with "
                "profile/state restore. Use preflight containment for an authenticated "
                "session, or remove profile/state options."
            )

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str],
        *,
        session: Optional[str] = None,
        authenticated: Optional[bool] = None,
        profile: Optional[str] = None,
        allowed_domains: Sequence[str] = (),
        timeout_seconds: Optional[float] = None,
        max_output_chars: Optional[int] = None,
        allow_private_network: Optional[bool] = None,
    ) -> "AgentBrowserConfig":
        merged_env = dict(os.environ)
        merged_env.update({str(key): str(value) for key, value in env.items()})
        resolved_session = session or merged_env.get(
            "AGENT_BROWSER_SESSION", "windagent"
        )
        resolved_authenticated = (
            _parse_bool(merged_env.get("WINDAGENT_BROWSER_AUTHENTICATED"), False)
            if authenticated is None
            else authenticated
        )
        resolved_profile = (
            profile if profile is not None else merged_env.get("AGENT_BROWSER_PROFILE")
        )
        timeout = timeout_seconds or float(
            merged_env.get("WINDAGENT_BROWSER_TIMEOUT_SECONDS", "60")
        )
        retry_attempts = int(merged_env.get("WINDAGENT_BROWSER_RETRY_ATTEMPTS", "2"))
        retry_backoff = float(
            merged_env.get("WINDAGENT_BROWSER_RETRY_BACKOFF_SECONDS", "0.25")
        )
        cleanup_timeout = float(
            merged_env.get("WINDAGENT_BROWSER_CLEANUP_TIMEOUT_SECONDS", "8")
        )
        max_output = max_output_chars or int(
            merged_env.get("AGENT_BROWSER_MAX_OUTPUT", "100000")
        )
        configured_domains = tuple(allowed_domains) or _split_csv(
            merged_env.get("AGENT_BROWSER_ALLOWED_DOMAINS")
        )
        headless = merged_env.get("WINDAGENT_BROWSER_HEADLESS", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        return cls(
            binary=merged_env.get("AGENT_BROWSER_BIN", "agent-browser"),
            session=resolved_session,
            authenticated=resolved_authenticated,
            profile=resolved_profile or None,
            state_path=merged_env.get("AGENT_BROWSER_STATE") or None,
            restore=_parse_bool(merged_env.get("AGENT_BROWSER_RESTORE"), False),
            timeout_seconds=timeout,
            retry_attempts=retry_attempts,
            retry_backoff_seconds=retry_backoff,
            cleanup_timeout_seconds=cleanup_timeout,
            max_output_chars=max_output,
            content_boundaries=_parse_bool(
                merged_env.get("AGENT_BROWSER_CONTENT_BOUNDARIES"), True
            ),
            containment_mode=merged_env.get("WINDAGENT_BROWSER_CONTAINMENT", "native")
            .strip()
            .lower(),
            allowed_domains=tuple(item.lower() for item in configured_domains),
            allow_private_network=(
                _parse_bool(
                    merged_env.get("WINDAGENT_BROWSER_ALLOW_PRIVATE_NETWORK"), False
                )
                if allow_private_network is None
                else allow_private_network
            ),
            headless=headless,
            extra_env={str(key): str(value) for key, value in env.items()},
        )

    def command_prefix(self) -> list[str]:
        args = [self.binary, "--session", self.session]
        if self.profile:
            args.extend(["--profile", self.profile])
        if self.state_path:
            args.extend(["--state", self.state_path])
        if self.restore:
            args.append("--restore")
        if self.content_boundaries:
            args.append("--content-boundaries")
        if not self.headless:
            args.append("--headed")
        args.extend(["--max-output", str(self.max_output_chars)])
        if self.containment_mode == "native" and self.allowed_domains:
            args.extend(["--allowed-domains", ",".join(self.allowed_domains)])
        return args

    def process_env(self) -> dict[str, str]:
        merged = dict(os.environ)
        merged.update({str(key): str(value) for key, value in self.extra_env.items()})
        safe: dict[str, str] = {}
        for key, value in merged.items():
            upper = key.upper()
            if any(marker in upper for marker in _SECRET_ENV_MARKERS):
                continue
            if upper.startswith("AGENT_BROWSER_") or upper.startswith("WINDAGENT_BROWSER_"):
                safe[key] = value
                continue
            safe[key] = value
        return safe


@dataclass(frozen=True)
class BrowserPageCapture:
    requested_url: str
    final_url: str
    title: str
    text: str
    screenshot_path: Optional[str] = None


@dataclass(frozen=True)
class BrowserBenchmark:
    """A lightweight, repeatable measurement for one rendered-page capture."""

    open_and_read_ms: float
    runner_peak_memory_bytes: int
    content_chars: int
    final_url: str


class AgentBrowserClient:
    """High-level browser primitives backed by one named agent-browser session."""

    _SEMANTIC_LOCATORS = {
        "alt",
        "label",
        "placeholder",
        "role",
        "testid",
        "text",
        "title",
    }

    def __init__(
        self,
        config: AgentBrowserConfig,
        process: Optional[AgentBrowserProcessPort] = None,
    ) -> None:
        self.config = config
        self.process = process or SubprocessAgentBrowserProcess()

    async def _run(
        self,
        *args: str,
        retryable: bool = True,
    ) -> AgentBrowserCommandResult:
        """Run one idempotent CLI command with bounded exponential backoff.

        Only launch/timeout failures are retried. A policy rejection and a non-zero
        CLI result are deterministic for the same input and must reach the caller.
        """
        attempts = self.config.retry_attempts if retryable else 1
        for attempt in range(1, attempts + 1):
            try:
                return await self.process.run(
                    [*self.config.command_prefix(), *args],
                    timeout_seconds=self.config.timeout_seconds,
                    env=self.config.process_env(),
                )
            except (AgentBrowserProcessStartError, AgentBrowserTimeoutError):
                if attempt == attempts:
                    raise
                delay = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
                if delay:
                    await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    async def _cleanup_session(self) -> None:
        """Close a daemon session promptly without masking the original failure."""
        with contextlib.suppress(AgentBrowserError, asyncio.TimeoutError):
            await asyncio.wait_for(
                self._run("close", retryable=False),
                timeout=self.config.cleanup_timeout_seconds,
            )

    async def open_and_read(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        max_chars: Optional[int] = None,
        screenshot_path: Optional[str] = None,
        close_session: bool = True,
    ) -> BrowserPageCapture:
        validate_navigation_url(
            url,
            allowed_domains=self.config.allowed_domains,
            allow_private_network=self.config.allow_private_network,
        )
        if wait_until not in {"load", "domcontentloaded", "networkidle", "none"}:
            raise AgentBrowserPolicyError(
                "wait_until must be load, domcontentloaded, networkidle, or none."
            )
        output_limit = max_chars or self.config.max_output_chars
        output_limit = max(1_000, min(output_limit, self.config.max_output_chars))
        cleaned_after_failure = False
        try:
            await self._run("open", url)
            if wait_until != "none":
                await self._run("wait", "--load", wait_until)
            title_result = await self._run("get", "title")
            url_result = await self._run("get", "url")
            final_url = (url_result.stdout or url).strip()
            validate_navigation_url(
                final_url,
                allowed_domains=self.config.allowed_domains,
                allow_private_network=self.config.allow_private_network,
            )
            read_result = await self._run("read")
            screenshot_value = None
            if screenshot_path:
                await self._run("screenshot", "--full", screenshot_path)
                screenshot_value = screenshot_path
            return BrowserPageCapture(
                requested_url=url,
                final_url=final_url,
                title=title_result.stdout.strip(),
                text=read_result.stdout[:output_limit],
                screenshot_path=screenshot_value,
            )
        except BaseException:
            # An interrupted tool call must never retain a daemon/Chrome session.
            cleaned_after_failure = True
            await self._cleanup_session()
            raise
        finally:
            if close_session and not cleaned_after_failure:
                await self._cleanup_session()

    async def click_xy(self, x: int, y: int) -> None:
        if x < 0 or y < 0:
            raise AgentBrowserPolicyError("Browser coordinates must be non-negative.")
        await self._run("mouse", "move", str(x), str(y), retryable=False)
        await self._run("mouse", "down", "left", retryable=False)
        await self._run("mouse", "up", "left", retryable=False)

    async def type_text(self, selector: str, text: str) -> None:
        """Type text into a selector or accessibility reference."""
        clean_selector = selector.strip()
        if not clean_selector:
            raise AgentBrowserPolicyError("Browser type selector cannot be empty.")
        if not text:
            raise AgentBrowserPolicyError("Browser text cannot be empty.")
        await self._run("type", clean_selector, text, retryable=False)

    async def set_viewport(self, width: int, height: int) -> None:
        """Set the viewport used by screenshot-coordinate interactions."""
        if not 320 <= width <= 4_096 or not 240 <= height <= 4_096:
            raise AgentBrowserPolicyError(
                "Browser viewport must be between 320x240 and 4096x4096."
            )
        await self._run("set", "viewport", str(width), str(height), retryable=False)

    async def capture_current_page(
        self,
        *,
        max_chars: Optional[int] = None,
        screenshot_path: Optional[str] = None,
    ) -> BrowserPageCapture:
        """Read and optionally screenshot the already-open page without closing it."""
        output_limit = max_chars or self.config.max_output_chars
        output_limit = max(1_000, min(output_limit, self.config.max_output_chars))
        title_result = await self._run("get", "title")
        url_result = await self._run("get", "url")
        final_url = url_result.stdout.strip()
        if not final_url:
            raise AgentBrowserPolicyError("Browser session has no active page URL.")
        validate_navigation_url(
            final_url,
            allowed_domains=self.config.allowed_domains,
            allow_private_network=self.config.allow_private_network,
        )
        read_result = await self._run("read")
        screenshot_value = None
        if screenshot_path:
            await self._run("screenshot", "--full", screenshot_path)
            screenshot_value = screenshot_path
        return BrowserPageCapture(
            requested_url=final_url,
            final_url=final_url,
            title=title_result.stdout.strip(),
            text=read_result.stdout[:output_limit],
            screenshot_path=screenshot_value,
        )

    async def go_back(self) -> None:
        await self._run("back", retryable=False)

    async def go_forward(self) -> None:
        await self._run("forward", retryable=False)

    async def reload(self) -> None:
        await self._run("reload", retryable=False)

    async def snapshot(self) -> str:
        """Return the accessibility snapshot containing stable ``@ref`` targets."""
        return (await self._run("snapshot")).stdout

    async def click_target(self, target: str, *, locator: str = "ref") -> None:
        """Click a snapshot reference, CSS selector, or semantic locator.

        ``ref`` targets must be an ``@e…`` accessibility reference returned by
        :meth:`snapshot`; semantic locators are delegated to ``agent-browser find``.
        Coordinate clicking is deliberately kept separate as a legacy fallback.
        """
        clean_target = target.strip()
        if not clean_target:
            raise AgentBrowserPolicyError("Browser click target cannot be empty.")
        if locator == "ref":
            if not clean_target.startswith("@"):
                raise AgentBrowserPolicyError(
                    "Snapshot-reference clicks must use an @ref returned by snapshot."
                )
            await self._run("click", clean_target, retryable=False)
            return
        if locator == "css":
            await self._run("click", clean_target, retryable=False)
            return
        if locator not in self._SEMANTIC_LOCATORS:
            allowed = ", ".join(sorted(self._SEMANTIC_LOCATORS))
            raise AgentBrowserPolicyError(
                f"Unsupported semantic locator {locator!r}; use one of: {allowed}."
            )
        await self._run("find", locator, clean_target, "click", retryable=False)

    async def scroll(self, direction: str, pixels: int = 800) -> None:
        if direction not in {"up", "down", "left", "right"}:
            raise AgentBrowserPolicyError(
                "Scroll direction must be up, down, left, or right."
            )
        if pixels < 1 or pixels > 20_000:
            raise AgentBrowserPolicyError("Scroll pixels must be between 1 and 20,000.")
        await self._run("scroll", direction, str(pixels), retryable=False)

    async def wait_for(
        self,
        target: str,
        *,
        condition: str = "selector",
    ) -> None:
        clean_target = target.strip()
        if not clean_target:
            raise AgentBrowserPolicyError("Browser wait target cannot be empty.")
        if condition == "selector":
            await self._run("wait", clean_target)
            return
        if condition == "text":
            await self._run("wait", "--text", clean_target)
            return
        if condition == "url":
            await self._run("wait", "--url", clean_target)
            return
        if condition == "javascript":
            await self._run("wait", "--fn", clean_target)
            return
        if condition in {"load", "domcontentloaded", "networkidle"}:
            await self._run("wait", "--load", condition)
            return
        raise AgentBrowserPolicyError(
            "Wait condition must be selector, text, url, javascript, load, "
            "domcontentloaded, or networkidle."
        )

    async def read_attribute(self, selector: str, attribute: str) -> str:
        if not selector.strip() or not attribute.strip():
            raise AgentBrowserPolicyError("Selector and attribute are required.")
        return (
            await self._run("get", "attr", attribute.strip(), selector.strip())
        ).stdout

    async def list_links(self, *, limit: int = 100) -> list[dict[str, str]]:
        if limit < 1 or limit > 1_000:
            raise AgentBrowserPolicyError("Link limit must be between 1 and 1,000.")
        expression = (
            "JSON.stringify([...document.querySelectorAll('a[href]')]"
            f".slice(0,{limit}).map(a=>({{text:(a.innerText||a.textContent||'').trim(),href:a.href}})))"
        )
        result = await self._run("eval", expression)
        parsed = result.parsed
        if not isinstance(parsed, list):
            return []
        links: list[dict[str, str]] = []
        for item in parsed:
            if isinstance(item, dict) and isinstance(item.get("href"), str):
                links.append(
                    {
                        "text": str(item.get("text", "")),
                        "href": item["href"],
                    }
                )
        return links

    async def collect_paginated(
        self,
        next_target: str,
        *,
        locator: str = "ref",
        max_pages: int = 5,
    ) -> list[str]:
        """Read pages until the rendered DOM repeats or the page cap is reached."""
        if max_pages < 1 or max_pages > 50:
            raise AgentBrowserPolicyError(
                "Pagination max_pages must be between 1 and 50."
            )
        pages: list[str] = []
        seen: set[str] = set()
        for index in range(max_pages):
            content = (await self._run("read")).stdout[: self.config.max_output_chars]
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if digest in seen:
                break
            seen.add(digest)
            pages.append(content)
            if index + 1 < max_pages:
                await self.click_target(next_target, locator=locator)
                await self.wait_for("domcontentloaded", condition="domcontentloaded")
        return pages

    async def collect_infinite_scroll(
        self,
        *,
        max_scrolls: int = 5,
        pixels: int = 1_200,
        settle_ms: int = 400,
    ) -> list[str]:
        """Collect distinct rendered DOM states while advancing an infinite feed."""
        if max_scrolls < 1 or max_scrolls > 50:
            raise AgentBrowserPolicyError(
                "Infinite-scroll max_scrolls must be between 1 and 50."
            )
        if settle_ms < 0 or settle_ms > 30_000:
            raise AgentBrowserPolicyError(
                "Infinite-scroll settle_ms must be between 0 and 30,000."
            )
        pages: list[str] = []
        seen: set[str] = set()
        for index in range(max_scrolls):
            content = (await self._run("read")).stdout[: self.config.max_output_chars]
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if digest in seen:
                break
            seen.add(digest)
            pages.append(content)
            if index + 1 < max_scrolls:
                await self.scroll("down", pixels)
                if settle_ms:
                    await self._run("wait", str(settle_ms))
        return pages

    async def extract_video_transcript(self) -> str:
        """Extract visible transcript segments only; no platform-protection bypass."""
        expression = (
            "JSON.stringify([...document.querySelectorAll("
            "'ytd-transcript-segment-renderer, [data-testid*=transcript], [class*=transcript]') ]"
            ".map(e=>(e.innerText||e.textContent||'').trim()).filter(Boolean))"
        )
        result = await self._run("eval", expression)
        if isinstance(result.parsed, list):
            return "\n".join(str(item) for item in result.parsed)[
                : self.config.max_output_chars
            ]
        return ""

    async def inspect_network(self, *, clear: bool = False) -> Any:
        args = ["network", "requests"]
        if clear:
            args.append("--clear")
        result = await self._run(*args)
        return result.parsed if result.parsed is not None else result.stdout

    async def start_har(self) -> None:
        await self._run("network", "har", "start", retryable=False)

    async def stop_har(self, output_path: str) -> str:
        if not output_path.strip():
            raise AgentBrowserPolicyError("HAR output path cannot be empty.")
        await self._run("network", "har", "stop", output_path, retryable=False)
        return output_path

    async def session_health(self) -> dict[str, Any]:
        """Return safe session diagnostics without exposing cookie values."""
        url_result = await self._run("get", "url")
        cookies_result = await self._run("cookies", "get")
        cookies = cookies_result.parsed
        if isinstance(cookies, dict):
            cookie_items = cookies.get("cookies", [])
        else:
            cookie_items = cookies if isinstance(cookies, list) else []
        return {
            "session": self.config.session,
            "url": url_result.stdout.strip(),
            "cookie_count": len(cookie_items),
            "has_cookies": bool(cookie_items),
        }

    async def open_many_and_read(
        self,
        urls: Sequence[str],
        *,
        wait_until: str = "domcontentloaded",
        max_chars: Optional[int] = None,
    ) -> list[BrowserPageCapture]:
        if not urls:
            raise AgentBrowserPolicyError(
                "At least one URL is required for a browser session."
            )
        captures: list[BrowserPageCapture] = []
        try:
            for url in urls:
                captures.append(
                    await self.open_and_read(
                        url,
                        wait_until=wait_until,
                        max_chars=max_chars,
                        close_session=False,
                    )
                )
            return captures
        finally:
            await self._cleanup_session()

    async def benchmark_open_and_read(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        max_chars: Optional[int] = None,
    ) -> BrowserBenchmark:
        """Measure capture latency and Python runner peak memory for a fixed URL."""
        tracing_was_active = tracemalloc.is_tracing()
        if not tracing_was_active:
            tracemalloc.start()
        try:
            started = time.perf_counter()
            capture = await self.open_and_read(
                url,
                wait_until=wait_until,
                max_chars=max_chars,
                close_session=True,
            )
            _, peak = tracemalloc.get_traced_memory()
            return BrowserBenchmark(
                open_and_read_ms=(time.perf_counter() - started) * 1000,
                runner_peak_memory_bytes=peak,
                content_chars=len(capture.text),
                final_url=capture.final_url,
            )
        finally:
            if not tracing_was_active:
                tracemalloc.stop()

    async def close(self) -> None:
        await self._run("close", retryable=False)


def resolve_workspace_artifact_path(workspace_root: str, relative_path: str) -> Path:
    root = Path(workspace_root).resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AgentBrowserPolicyError(
            "Browser artifact path must remain inside the workspace root."
        ) from exc
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate
