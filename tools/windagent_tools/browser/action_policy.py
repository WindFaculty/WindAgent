"""
Phase 12 — Bounded browser action policy (plan 04 §8.4).

The browser worker only ever performs *typed* bounded operations. Raw browser
instructions (arbitrary ``eval``, cookie export, unapproved upload, payment or
terms confirmation, arbitrary filesystem reads, model-invented commands) are
rejected *before* any process/browser call happens.

Allow:
- open URL inside the domain allowlist;
- accessibility snapshot;
- semantic click/fill/select/upload (upload only inside the approved asset
  store);
- screenshot into a controlled workspace path;
- bounded wait;
- download into a controlled workspace path.

Deny / require confirmation:
- arbitrary ``eval``;
- navigation outside the domain allowlist;
- file upload outside the approved asset store;
- payment / terms / destructive confirmation;
- cookie export;
- arbitrary filesystem read;
- commands created by a model that are not typed operations.

The policy is deterministic and fully offline — no network or browser call is
made while evaluating a decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Sequence
from urllib.parse import urlsplit

from windagent_tools.browser.agent_browser import (
    AgentBrowserPolicyError,
    validate_navigation_url,
)

# Operations the runtime may execute. ``deny``-class operations exist so the
# policy can return a *typed* reason instead of silently ignoring a request.
class BrowserOperation(str, Enum):
    OPEN_URL = "open_url"
    SNAPSHOT = "snapshot"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    UPLOAD = "upload"
    SCREENSHOT = "screenshot"
    WAIT = "wait"
    DOWNLOAD = "download"
    # deny-class: never executed, only reported.
    EVAL = "eval"
    COOKIE_EXPORT = "cookie_export"
    FILESYSTEM_READ = "filesystem_read"
    CONFIRM = "confirm"  # payment / terms / destructive confirmation


class BrowserPolicyDecisionCode(str, Enum):
    ALLOW = "allow"
    DENY_OPERATION = "deny_operation"
    DENY_DOMAIN = "deny_domain"
    DENY_UPLOAD_PATH = "deny_upload_path"
    DENY_FILESYSTEM = "deny_filesystem"
    DENY_CREDENTIALS = "deny_credentials"
    REQUIRE_CONFIRMATION = "require_confirmation"


@dataclass(frozen=True)
class BrowserPolicyDecision:
    """Outcome of one bounded action policy evaluation."""

    operation: BrowserOperation
    allowed: bool
    code: BrowserPolicyDecisionCode
    reason: str = ""
    requires_confirmation: bool = False


class BrowserActionPolicy:
    """Deterministic allow/deny policy for bounded browser operations."""

    # Deny-class operations are never executed by the runtime.
    _DENY_OPERATIONS = frozenset(
        {
            BrowserOperation.EVAL,
            BrowserOperation.COOKIE_EXPORT,
            BrowserOperation.FILESYSTEM_READ,
            BrowserOperation.CONFIRM,
        }
    )

    # Operations that read arbitrary filesystem paths are denied entirely.
    _FILESYSTEM_OPERATIONS = frozenset({BrowserOperation.FILESYSTEM_READ})

    # Semantic operations that act on the current page (no navigation target).
    _PAGE_OPERATIONS = frozenset(
        {
            BrowserOperation.SNAPSHOT,
            BrowserOperation.CLICK,
            BrowserOperation.FILL,
            BrowserOperation.SELECT,
            BrowserOperation.SCREENSHOT,
            BrowserOperation.WAIT,
        }
    )

    _CONFIRMATION_MARKERS = re.compile(
        r"(pay|payment|checkout|purchase|billing|subscribe|terms\s*of\s*service|"
        r"accept\s+terms|agree\s+and\s+continue|delete\s+account|permanently\s+delete|"
        r"irreversible)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        allowed_domains: Sequence[str] = (),
        allow_private_network: bool = False,
        approved_asset_store: Optional[str] = None,
        default_deny: bool = True,
    ) -> None:
        self.allowed_domains = tuple(d.lower().strip() for d in allowed_domains if d)
        self.allow_private_network = allow_private_network
        self._approved_asset_store = (
            str(Path(approved_asset_store).resolve())
            if approved_asset_store
            else None
        )
        self.default_deny = default_deny

    # ------------------------------------------------------------------
    # Public evaluation
    # ------------------------------------------------------------------
    def evaluate(
        self,
        operation: BrowserOperation,
        *,
        target: Optional[str] = None,
        workspace_root: Optional[str] = None,
        current_url: Optional[str] = None,
        session_state: Optional[str] = None,
    ) -> BrowserPolicyDecision:
        """Evaluate one bounded action against the policy.

        Fail-closed: any unknown operation, domain violation, credential
        embedded in a URL, or upload outside the approved asset store is
        denied. Payment/terms-style confirmation targets require explicit
        human confirmation.
        """
        if not isinstance(operation, BrowserOperation):
            try:
                operation = BrowserOperation(operation)
            except ValueError:
                return BrowserPolicyDecision(
                    operation=BrowserOperation.CONFIRM,
                    allowed=False,
                    code=BrowserPolicyDecisionCode.DENY_OPERATION,
                    reason=f"unknown operation {operation!r}",
                )

        if operation in self._DENY_OPERATIONS:
            return self._deny(operation, "operation is denied by policy")

        if operation in self._FILESYSTEM_OPERATIONS:
            return self._deny(operation, "arbitrary filesystem reads are denied")

        if operation == BrowserOperation.OPEN_URL:
            return self._evaluate_open_url(target)

        if operation == BrowserOperation.UPLOAD:
            return self._evaluate_upload(target)

        if operation == BrowserOperation.DOWNLOAD:
            return self._evaluate_download(target, workspace_root=workspace_root)

        if operation in self._PAGE_OPERATIONS:
            return self._evaluate_page_operation(
                operation,
                target=target,
                current_url=current_url,
                session_state=session_state,
            )

        # default_deny means an operation not explicitly allowed is denied.
        if self.default_deny:
            return self._deny(operation, "operation is not in the allowlist")

        return BrowserPolicyDecision(
            operation=operation,
            allowed=True,
            code=BrowserPolicyDecisionCode.ALLOW,
        )

    # ------------------------------------------------------------------
    # Per-operation rules
    # ------------------------------------------------------------------
    def _evaluate_open_url(self, target: Optional[str]) -> BrowserPolicyDecision:
        op = BrowserOperation.OPEN_URL
        if not target or not str(target).strip():
            return self._deny(op, "navigation target is empty")
        parts = urlsplit(str(target))
        if parts.username or parts.password:
            return self._deny(
                op,
                "credentials must not be embedded in navigation URLs",
                code=BrowserPolicyDecisionCode.DENY_CREDENTIALS,
            )
        try:
            validate_navigation_url(
                str(target),
                allowed_domains=self.allowed_domains,
                allow_private_network=self.allow_private_network,
            )
        except AgentBrowserPolicyError as exc:
            return BrowserPolicyDecision(
                operation=op,
                allowed=False,
                code=BrowserPolicyDecisionCode.DENY_DOMAIN,
                reason=str(exc),
            )
        return BrowserPolicyDecision(
            operation=op,
            allowed=True,
            code=BrowserPolicyDecisionCode.ALLOW,
        )

    def _evaluate_upload(self, target: Optional[str]) -> BrowserPolicyDecision:
        op = BrowserOperation.UPLOAD
        if self._approved_asset_store is None:
            return self._deny(
                op,
                "no approved asset store is configured; uploads are denied",
                code=BrowserPolicyDecisionCode.DENY_UPLOAD_PATH,
            )
        if not target or not str(target).strip():
            return self._deny(
                op, "upload target is empty", code=BrowserPolicyDecisionCode.DENY_UPLOAD_PATH
            )
        candidate = Path(str(target)).resolve()
        store = Path(self._approved_asset_store)
        try:
            candidate.relative_to(store)
        except ValueError:
            return self._deny(
                op,
                f"upload path {candidate} is outside the approved asset store",
                code=BrowserPolicyDecisionCode.DENY_UPLOAD_PATH,
            )
        if candidate.is_dir():
            return self._deny(
                op, "upload target must be a file", code=BrowserPolicyDecisionCode.DENY_UPLOAD_PATH
            )
        return BrowserPolicyDecision(
            operation=op,
            allowed=True,
            code=BrowserPolicyDecisionCode.ALLOW,
        )

    def _evaluate_download(
        self,
        target: Optional[str],
        *,
        workspace_root: Optional[str],
    ) -> BrowserPolicyDecision:
        op = BrowserOperation.DOWNLOAD
        if not workspace_root:
            return self._deny(op, "download requires a workspace root")
        if not target or not str(target).strip():
            return self._deny(op, "download target is empty")
        root = Path(workspace_root).resolve()
        candidate = (root / str(target)).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return BrowserPolicyDecision(
                operation=op,
                allowed=False,
                code=BrowserPolicyDecisionCode.DENY_FILESYSTEM,
                reason=f"download path {candidate} is outside the workspace root",
            )
        return BrowserPolicyDecision(
            operation=op,
            allowed=True,
            code=BrowserPolicyDecisionCode.ALLOW,
        )

    def _evaluate_page_operation(
        self,
        operation: BrowserOperation,
        *,
        target: Optional[str],
        current_url: Optional[str],
        session_state: Optional[str],
    ) -> BrowserPolicyDecision:
        # A payment/terms style target is never auto-confirmed.
        if target and self._CONFIRMATION_MARKERS.search(str(target)):
            return BrowserPolicyDecision(
                operation=operation,
                allowed=False,
                code=BrowserPolicyDecisionCode.REQUIRE_CONFIRMATION,
                reason=(
                    "target matches payment/terms/destructive patterns; "
                    "human confirmation required"
                ),
                requires_confirmation=True,
            )
        if operation == BrowserOperation.CLICK and not (target and str(target).strip()):
            return self._deny(operation, "click target is empty")
        if operation == BrowserOperation.FILL and not (target and str(target).strip()):
            return self._deny(operation, "fill target is empty")
        if operation == BrowserOperation.SELECT and not (target and str(target).strip()):
            return self._deny(operation, "select target is empty")
        return BrowserPolicyDecision(
            operation=operation,
            allowed=True,
            code=BrowserPolicyDecisionCode.ALLOW,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _deny(
        self,
        operation: BrowserOperation,
        reason: str,
        *,
        code: BrowserPolicyDecisionCode = BrowserPolicyDecisionCode.DENY_OPERATION,
    ) -> BrowserPolicyDecision:
        return BrowserPolicyDecision(
            operation=operation,
            allowed=False,
            code=code,
            reason=reason,
        )

    def operation_allowlist(self) -> list[str]:
        """Stable, sorted list of operations the policy allows."""
        allowed = {
            BrowserOperation.OPEN_URL,
            BrowserOperation.SNAPSHOT,
            BrowserOperation.CLICK,
            BrowserOperation.FILL,
            BrowserOperation.SELECT,
            BrowserOperation.UPLOAD,
            BrowserOperation.SCREENSHOT,
            BrowserOperation.WAIT,
            BrowserOperation.DOWNLOAD,
        }
        return sorted(op.value for op in allowed)


__all__ = [
    "BrowserActionPolicy",
    "BrowserOperation",
    "BrowserPolicyDecision",
    "BrowserPolicyDecisionCode",
]
