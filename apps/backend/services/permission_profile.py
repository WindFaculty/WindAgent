"""Phase 6 — Permission profile evaluation (ban_ke_hoach §10).

Three profiles gate a coding agent's shell actions:

  Safe       — read-only + local edits; anything risky is blocked.
  Standard   — local edits/build/test/commit auto; install/push/
               destructive need explicit user approval.
  Autonomous — everything auto-approved (operator trust).

Profiles are evaluated per *tool call / shell command*, not per agent
type. This classifier is consulted by the Hermes bridge when a run emits
an `approval.request`: under Standard it lets the request bubble up to
the user; under Autonomous it auto-grants; under Safe it auto-denies
destructive/high-risk actions.

The shell classifier is intentionally narrow: it covers the commands
named in §10 (install, wide lockfile change, multi-file delete, out-of-
workspace access, push/PR/merge, destructive). Nothing here shells out —
it only inspects the command string, so it is safe to unit-test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

# Profiles accepted by AgentInstanceORM.permission_profile.
PROFILES = ("Safe", "Standard", "Autonomous")

# Risk classes §10 maps to "needs approval".
_APPROVE_PATTERNS: List[re.Pattern[str]] = [
    # package install
    re.compile(r"(^|\s)(npm|pnpm|yarn|bun|pip|pip3|poetry|uv|cargo|go)\s+install", re.I),
    re.compile(r"(^|\s)apt(-get)?\s+install", re.I),
    re.compile(r"(^|\s)brew\s+install", re.I),
    # git push / pr / merge to shared branches
    re.compile(r"(^|\s)git\s+push", re.I),
    re.compile(r"(^|\s)git\s+(pr|mr|merge)", re.I),
    re.compile(r"(^|\s)gh\s+pr", re.I),
    # multi-file / forced deletion
    re.compile(r"(^|\s)(rm\s+.*-[rf]|rm\s+-[rf])", re.I),
    re.compile(r"(^|\s)git\s+clean\s+-[a-z]*[fd]", re.I),
    # destructive / force
    re.compile(r"(^|\s)git\s+(reset\s+--hard|checkout\s+\.|push\s+-[a-z]*f)", re.I),
    re.compile(r"(^|\s)(drop|truncate|delete)\s+", re.I),
    re.compile(r"(^|\s):\(\)\s*\{", re.I),  # fork bomb-ish
]

# High-risk / always-blocked under Safe (and blocked outright under any
# profile if it targets shared state destructively).
_BLOCKED_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"(^|\s)git\s+push\s+-[a-z]*f", re.I),       # force-push
    re.compile(r"(^|\s)git\s+(push\s+.*--delete|branch\s+-[dD])", re.I),
    re.compile(r"(^|\s)(rm\s+-rf\s+/(usr|etc|home|var|System)|mkfs)", re.I),
    re.compile(r"(^|\s)chmod\s+-R\s+777\s+/", re.I),
]


@dataclass
class Decision:
    action: str  # "allow" | "needs_approval" | "blocked"
    reason: str


def _matches(patterns: List[re.Pattern[str]], command: str) -> bool:
    return any(p.search(command) for p in patterns)


def classify_command(profile: str, command: str) -> Decision:
    """Classify a shell command under a permission profile.

    profile defaults to Standard when unknown (fail-safe, not fail-open).
    """
    profile = profile if profile in PROFILES else "Standard"
    command = (command or "").strip()

    if _matches(_BLOCKED_PATTERNS, command):
        return Decision("blocked", "destructive or protected operation")

    if profile == "Autonomous":
        return Decision("allow", "autonomous profile auto-approves")

    if profile == "Safe":
        # Safe allows only benign local work; everything risky is blocked.
        if _matches(_APPROVE_PATTERNS, command):
            return Decision("blocked", "Safe profile forbids risky command")
        return Decision("allow", "Safe profile allows benign command")

    # Standard: risky commands need user approval, rest auto-allowed.
    if _matches(_APPROVE_PATTERNS, command):
        return Decision("needs_approval", "Standard profile requires approval")
    return Decision("allow", "Standard profile auto-allows")
