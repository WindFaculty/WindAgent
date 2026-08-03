"""
Phase 12 — Browser health checks (plan 04 §8.5).

The health check classifies the runtime as HEALTHY / DEGRADED / UNHEALTHY /
UNKNOWN by combining five observable signals:

- process alive (worker process responsive);
- browser reachable (browser endpoint/session answers);
- current domain allowed (page is inside the domain allowlist);
- profile lock valid (this worker still holds a valid lease);
- session not in a human-required state.

The check is deterministic and fully offline — it never launches a browser on
its own; it evaluates signals provided by the caller (or by a fake in tests).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from windagent_tools.browser.agent_browser import (
    AgentBrowserPolicyError,
    domain_matches,
    validate_navigation_url,
)
from windagent_tools.browser.session import BrowserSessionState


class BrowserHealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BrowserHealthReport:
    """Immutable health classification for one browser session."""

    status: BrowserHealthStatus
    process_alive: bool = False
    browser_reachable: bool = False
    current_domain_allowed: bool = False
    profile_lock_valid: bool = False
    human_required: bool = False
    current_url: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "process_alive": self.process_alive,
            "browser_reachable": self.browser_reachable,
            "current_domain_allowed": self.current_domain_allowed,
            "profile_lock_valid": self.profile_lock_valid,
            "human_required": self.human_required,
            "current_url": self.current_url,
            "reason": self.reason,
        }


class BrowserHealthCheck:
    """Classifies session health from observable signals (plan 04 §8.5)."""

    def __init__(
        self,
        *,
        allowed_domains: Sequence[str] = (),
        allow_private_network: bool = False,
        clock: Optional[callable] = None,
    ) -> None:
        self.allowed_domains = tuple(
            d.lower().strip() for d in allowed_domains if d.strip()
        )
        self.allow_private_network = allow_private_network
        self._clock = clock or time.time

    # ------------------------------------------------------------------
    def check(
        self,
        *,
        process_alive: bool,
        browser_reachable: bool,
        current_url: Optional[str] = None,
        profile_lock_valid: bool,
        session_state: Optional[BrowserSessionState] = None,
        lease_expires_at: float = 0.0,
    ) -> BrowserHealthReport:
        """Evaluate all signals and classify the session.

        Fail-closed: an empty allowlist means *no* domain is allowed (the
        runtime must be explicitly configured with Flow domains before a
        session can be HEALTHY).
        """
        human_required = session_state in (
            BrowserSessionState.HUMAN_REQUIRED,
        )
        current_domain_allowed = self._domain_allowed(current_url)
        lease_valid = profile_lock_valid and lease_expires_at > self._clock()

        broken = []
        if not process_alive:
            broken.append("worker process is not alive")
        if not browser_reachable:
            broken.append("browser is not reachable")
        if not current_domain_allowed:
            broken.append("current page domain is not allowed")
        if not lease_valid:
            broken.append("profile lock lease is not valid")

        if human_required:
            return BrowserHealthReport(
                status=BrowserHealthStatus.DEGRADED,
                process_alive=process_alive,
                browser_reachable=browser_reachable,
                current_domain_allowed=current_domain_allowed,
                profile_lock_valid=lease_valid,
                human_required=True,
                current_url=current_url or "",
                reason="session requires human action",
            )
        if broken:
            return BrowserHealthReport(
                status=BrowserHealthStatus.UNHEALTHY,
                process_alive=process_alive,
                browser_reachable=browser_reachable,
                current_domain_allowed=current_domain_allowed,
                profile_lock_valid=lease_valid,
                human_required=False,
                current_url=current_url or "",
                reason="; ".join(broken),
            )
        return BrowserHealthReport(
            status=BrowserHealthStatus.HEALTHY,
            process_alive=True,
            browser_reachable=True,
            current_domain_allowed=True,
            profile_lock_valid=True,
            human_required=False,
            current_url=current_url or "",
            reason="all health signals pass",
        )

    # ------------------------------------------------------------------
    def _domain_allowed(self, current_url: Optional[str]) -> bool:
        # Fail closed: an empty allowlist means *no* domain is allowed until
        # the runtime is explicitly configured with Flow domains.
        if not self.allowed_domains:
            return False
        if not current_url:
            return False
        try:
            validate_navigation_url(
                current_url,
                allowed_domains=self.allowed_domains,
                allow_private_network=self.allow_private_network,
            )
        except AgentBrowserPolicyError:
            return False
        return True

    @classmethod
    def domain_ok(cls, hostname: str, pattern: str) -> bool:
        """Expose the domain matcher for selector/contract tests."""
        return domain_matches(hostname, pattern)


__all__ = [
    "BrowserHealthCheck",
    "BrowserHealthReport",
    "BrowserHealthStatus",
]
