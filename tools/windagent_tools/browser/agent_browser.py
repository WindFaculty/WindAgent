"""Production subprocess adapter for ``vercel-labs/agent-browser``.

The adapter deliberately uses argv-based subprocess execution instead of a shell.
It validates navigation targets before Chrome is launched, limits returned text,
and supports dependency injection so the browser contract can be tested without
starting Chrome.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
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


class AgentBrowserCommandError(AgentBrowserError):
    """Raised when agent-browser exits non-zero or times out."""


class AgentBrowserPolicyError(AgentBrowserError):
    """Raised when a requested navigation violates the browser policy."""


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

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float,
        env: Mapping[str, str],
    ) -> AgentBrowserCommandResult:
        command = tuple(str(item) for item in argv)
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
            raise AgentBrowserUnavailableError(
                f"agent-browser could not be started: {type(exc).__name__}: {exc}"
            ) from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise AgentBrowserCommandError(
                f"agent-browser timed out after {timeout_seconds:.1f}s"
            ) from exc

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
            raise AgentBrowserCommandError(
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
        raise AgentBrowserPolicyError("Credentials must not be embedded in navigation URLs.")
    hostname = (parts.hostname or "").lower().rstrip(".")
    if not hostname:
        raise AgentBrowserPolicyError("Navigation URL has no hostname.")

    if not allow_private_network:
        if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
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
            raise AgentBrowserPolicyError("Private or non-routable IP navigation is disabled.")

    normalized_domains = tuple(item.lower().strip() for item in allowed_domains if item.strip())
    if normalized_domains and not any(
        domain_matches(hostname, pattern) for pattern in normalized_domains
    ):
        raise AgentBrowserPolicyError(
            f"Navigation host {hostname!r} is outside the configured domain policy."
        )
    return url


@dataclass(frozen=True)
class AgentBrowserConfig:
    binary: str = "agent-browser"
    session: str = "windagent"
    profile: Optional[str] = None
    state_path: Optional[str] = None
    restore: bool = False
    timeout_seconds: float = 60.0
    max_output_chars: int = 100_000
    content_boundaries: bool = True
    containment_mode: str = "native"
    allowed_domains: tuple[str, ...] = ()
    allow_private_network: bool = False
    extra_env: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_session_name(self.session)
        if not self.binary.strip():
            raise AgentBrowserPolicyError("agent-browser binary path cannot be empty.")
        if self.timeout_seconds <= 0:
            raise AgentBrowserPolicyError("Browser timeout must be positive.")
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
        if self.containment_mode == "native" and self.allowed_domains and (
            self.profile or self.state_path or self.restore
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
        allowed_domains: Sequence[str] = (),
        timeout_seconds: Optional[float] = None,
        max_output_chars: Optional[int] = None,
        allow_private_network: Optional[bool] = None,
    ) -> "AgentBrowserConfig":
        merged_env = dict(os.environ)
        merged_env.update({str(key): str(value) for key, value in env.items()})
        resolved_session = session or merged_env.get("AGENT_BROWSER_SESSION", "windagent")
        timeout = timeout_seconds or float(
            merged_env.get("WINDAGENT_BROWSER_TIMEOUT_SECONDS", "60")
        )
        max_output = max_output_chars or int(
            merged_env.get("AGENT_BROWSER_MAX_OUTPUT", "100000")
        )
        configured_domains = tuple(allowed_domains) or _split_csv(
            merged_env.get("AGENT_BROWSER_ALLOWED_DOMAINS")
        )
        return cls(
            binary=merged_env.get("AGENT_BROWSER_BIN", "agent-browser"),
            session=resolved_session,
            profile=merged_env.get("AGENT_BROWSER_PROFILE") or None,
            state_path=merged_env.get("AGENT_BROWSER_STATE") or None,
            restore=_parse_bool(merged_env.get("AGENT_BROWSER_RESTORE"), False),
            timeout_seconds=timeout,
            max_output_chars=max_output,
            content_boundaries=_parse_bool(
                merged_env.get("AGENT_BROWSER_CONTENT_BOUNDARIES"), True
            ),
            containment_mode=merged_env.get(
                "WINDAGENT_BROWSER_CONTAINMENT", "native"
            ).strip().lower(),
            allowed_domains=tuple(item.lower() for item in configured_domains),
            allow_private_network=(
                _parse_bool(merged_env.get("WINDAGENT_BROWSER_ALLOW_PRIVATE_NETWORK"), False)
                if allow_private_network is None
                else allow_private_network
            ),
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
            if upper.startswith("AGENT_BROWSER_"):
                safe[key] = value
                continue
            if any(marker in upper for marker in _SECRET_ENV_MARKERS):
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


class AgentBrowserClient:
    def __init__(
        self,
        config: AgentBrowserConfig,
        process: Optional[AgentBrowserProcessPort] = None,
    ) -> None:
        self.config = config
        self.process = process or SubprocessAgentBrowserProcess()

    async def _run(self, *args: str) -> AgentBrowserCommandResult:
        return await self.process.run(
            [*self.config.command_prefix(), *args],
            timeout_seconds=self.config.timeout_seconds,
            env=self.config.process_env(),
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
                await self._run("screenshot", screenshot_path, "--full")
                screenshot_value = screenshot_path
            return BrowserPageCapture(
                requested_url=url,
                final_url=final_url,
                title=title_result.stdout.strip(),
                text=read_result.stdout[:output_limit],
                screenshot_path=screenshot_value,
            )
        finally:
            if close_session:
                try:
                    await self.close()
                except AgentBrowserError:
                    pass

    async def click_xy(self, x: int, y: int) -> None:
        if x < 0 or y < 0:
            raise AgentBrowserPolicyError("Browser coordinates must be non-negative.")
        await self._run("mouse", "move", str(x), str(y))
        await self._run("mouse", "down", "left")
        await self._run("mouse", "up", "left")

    async def close(self) -> None:
        await self._run("close")


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
