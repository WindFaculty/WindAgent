"""
Phase 16 — Human intervention and account safety (plan 04 §25–§28).

Transforms human challenges into durable, observable, and resumable states:
  - HUMAN_LOGIN_REQUIRED
  - HUMAN_CAPTCHA_REQUIRED
  - HUMAN_ACCOUNT_VERIFICATION_REQUIRED
  - HUMAN_TERMS_ACCEPTANCE_REQUIRED
  - HUMAN_PAYMENT_CONFIRMATION_REQUIRED

Implements takeover pausing, 6-step safe resume protocol without duplicate submits,
audit evidence redaction, and account safety policies (concurrency, backoff, circuit breaker).
"""

from __future__ import annotations

import datetime
import json
import re
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from windagent_tools.google_flow.job_record import FlowJobRegistry, FlowJobStatus
from windagent_tools.google_flow.state_machine import (
    FlowUiObservation,
    FlowUiState,
    FlowUiStateMachine,
)


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FlowHumanState(str, Enum):
    """Typed human states requiring manual intervention (plan 04 §26)."""

    HUMAN_LOGIN_REQUIRED = "HUMAN_LOGIN_REQUIRED"
    HUMAN_CAPTCHA_REQUIRED = "HUMAN_CAPTCHA_REQUIRED"
    HUMAN_ACCOUNT_VERIFICATION_REQUIRED = "HUMAN_ACCOUNT_VERIFICATION_REQUIRED"
    HUMAN_TERMS_ACCEPTANCE_REQUIRED = "HUMAN_TERMS_ACCEPTANCE_REQUIRED"
    HUMAN_PAYMENT_CONFIRMATION_REQUIRED = "HUMAN_PAYMENT_CONFIRMATION_REQUIRED"


class FlowHumanActionStatus(str, Enum):
    """Lifecycle status of a human action record (plan 04 §26)."""

    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


@dataclass
class FlowHumanActionRecord:
    """Durable record for tracking human intervention (plan 04 §26)."""

    human_action_id: str
    session_id: str
    project_id: str
    human_state: FlowHumanState
    reason: str
    detected_at: str
    safe_resume_state: FlowUiState
    redacted_evidence: Dict[str, Any]
    status: FlowHumanActionStatus = FlowHumanActionStatus.PENDING
    generation_id: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "human_action_id": self.human_action_id,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "generation_id": self.generation_id,
            "human_state": self.human_state.value,
            "reason": self.reason,
            "detected_at": self.detected_at,
            "safe_resume_state": self.safe_resume_state.value,
            "redacted_evidence": self.redacted_evidence,
            "status": self.status.value,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "FlowHumanActionRecord":
        """Restore a persisted, typed human-action record."""
        return cls(
            human_action_id=str(raw["human_action_id"]),
            session_id=str(raw["session_id"]),
            project_id=str(raw["project_id"]),
            generation_id=raw.get("generation_id"),
            human_state=FlowHumanState(raw["human_state"]),
            reason=str(raw.get("reason", "")),
            detected_at=str(raw["detected_at"]),
            safe_resume_state=FlowUiState(raw["safe_resume_state"]),
            redacted_evidence=dict(raw.get("redacted_evidence") or {}),
            status=FlowHumanActionStatus(raw.get("status", FlowHumanActionStatus.PENDING.value)),
            resolved_by=raw.get("resolved_by"),
            resolved_at=raw.get("resolved_at"),
        )


class FlowHumanControlError(Exception):
    """Base exception for human control operations."""


class FlowHumanBypassAttemptedError(FlowHumanControlError):
    """Raised when an automated bypass attempt is detected or requested."""


class FlowHumanActionBlockedError(FlowHumanControlError):
    """Raised when an action is attempted on a session paused for human takeover."""


class FlowCircuitBreakerTrippedError(FlowHumanControlError):
    """Raised when a session exceeds the human intervention threshold."""


class FlowRateLimitExceededError(FlowHumanControlError):
    """Raised when automated Flow actions exceed the per-session rate limit."""


class FlowConcurrencyLimitExceededError(FlowHumanControlError):
    """Raised when another automated Flow action already owns the capacity."""


class FlowHumanControlDetector:
    """Detects human challenge states from UI observations (plan 04 §27.1)."""

    LOGIN_PATTERNS = ("accounts.google.com", "sign in", "login", "choose an account")
    CAPTCHA_PATTERNS = ("recaptcha", "hcaptcha", "turnstile", "verify you are human", "robot test")
    ACCOUNT_VERIF_PATTERNS = ("2-step verification", "security code", "verify your identity", "suspicious activity")
    TERMS_PATTERNS = ("terms of service", "privacy policy", "accept terms", "update to our terms")
    PAYMENT_PATTERNS = ("buy credits", "billing", "add payment method", "subscription", "checkout")

    @classmethod
    def detect(
        self, observation: FlowUiObservation, expected_state: Optional[FlowUiState] = None
    ) -> Optional[FlowHumanState]:
        url_lower = observation.url.lower()
        all_text = " ".join(observation.markers + observation.controls).lower()

        # 1. Login
        if any(p in url_lower or p in all_text for p in self.LOGIN_PATTERNS):
            return FlowHumanState.HUMAN_LOGIN_REQUIRED

        # 2. CAPTCHA
        if any(p in url_lower or p in all_text for p in self.CAPTCHA_PATTERNS):
            return FlowHumanState.HUMAN_CAPTCHA_REQUIRED

        # 3. Account Verification / Challenge
        if any(p in url_lower or p in all_text for p in self.ACCOUNT_VERIF_PATTERNS):
            return FlowHumanState.HUMAN_ACCOUNT_VERIFICATION_REQUIRED

        # 4. Payment / Credits
        if any(p in url_lower or p in all_text for p in self.PAYMENT_PATTERNS):
            return FlowHumanState.HUMAN_PAYMENT_CONFIRMATION_REQUIRED

        # 5. Terms Acceptance
        if any(p in url_lower or p in all_text for p in self.TERMS_PATTERNS):
            return FlowHumanState.HUMAN_TERMS_ACCEPTANCE_REQUIRED

        # 6. Unknown challenge fail-closed: if unexpected URL or markers and not in expected state
        if expected_state and "flow.google.com" not in url_lower and "google.com" in url_lower:
            return FlowHumanState.HUMAN_ACCOUNT_VERIFICATION_REQUIRED

        return None


class FlowAccountSafetyPolicy:
    """Account safety enforcement and evidence redaction (plan 04 §27.4)."""

    # Sensitive key/value regex patterns for redaction
    SENSITIVE_PATTERNS = [
        re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)"),  # email
        re.compile(r"(cookie|session|token|auth|bearer|password|secret|key)=\S+", re.IGNORECASE),
        re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),  # credit card numbers
    ]

    def __init__(
        self,
        max_interventions_per_session: int = 3,
        rate_limit_per_minute: int = 10,
        max_concurrency: int = 1,
        max_backoff_seconds: float = 300.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if max_interventions_per_session < 1:
            raise ValueError("max_interventions_per_session must be >= 1")
        if rate_limit_per_minute < 1:
            raise ValueError("rate_limit_per_minute must be >= 1")
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self.max_interventions_per_session = max_interventions_per_session
        self.rate_limit_per_minute = rate_limit_per_minute
        self.max_concurrency = max_concurrency
        self.max_backoff_seconds = max_backoff_seconds
        self._clock = clock or time.time
        self.session_intervention_counts: Dict[str, int] = {}
        self.session_action_timestamps: Dict[str, List[float]] = {}
        self._active_operation_tokens: Dict[str, str] = {}

    def record_intervention(self, session_id: str) -> int:
        count = self.session_intervention_counts.get(session_id, 0) + 1
        self.session_intervention_counts[session_id] = count
        if count > self.max_interventions_per_session:
            raise FlowCircuitBreakerTrippedError(
                f"Session '{session_id}' exceeded max human interventions limit "
                f"({count} > {self.max_interventions_per_session}). Circuit breaker tripped."
            )
        return count

    def calculate_backoff(self, attempt: int, base_seconds: float = 2.0) -> float:
        backoff = base_seconds * (2 ** max(0, attempt - 1))
        return min(backoff, self.max_backoff_seconds)

    def reserve_automated_action(self, session_id: str, operation_token: str) -> None:
        """Reserve bounded browser capacity before an automated action.

        A caller may nest operations under the *same* token (for example a
        generator calling a navigator).  A distinct token is always a
        competing operation and is subject to the concurrency limit.
        """
        active_token = self._active_operation_tokens.get(session_id)
        if active_token == operation_token:
            return
        if active_token is not None or len(self._active_operation_tokens) >= self.max_concurrency:
            raise FlowConcurrencyLimitExceededError(
                "automated Flow action denied: account concurrency limit "
                f"({self.max_concurrency}) is already in use"
            )

        now = self._clock()
        timestamps = [
            timestamp
            for timestamp in self.session_action_timestamps.get(session_id, [])
            if now - timestamp < 60.0
        ]
        if len(timestamps) >= self.rate_limit_per_minute:
            raise FlowRateLimitExceededError(
                "automated Flow action denied: session rate limit "
                f"({self.rate_limit_per_minute}/minute) exceeded"
            )
        timestamps.append(now)
        self.session_action_timestamps[session_id] = timestamps
        self._active_operation_tokens[session_id] = operation_token

    def release_automated_action(self, session_id: str, operation_token: str) -> None:
        """Release a matching capacity reservation; never release another owner."""
        if self._active_operation_tokens.get(session_id) == operation_token:
            del self._active_operation_tokens[session_id]

    def assert_no_automated_bypass(self, action_name: str) -> None:
        """Fail closed if an action attempts automated challenge solving or credit buying."""
        name_lower = action_name.lower()
        forbidden_terms = (
            "solve_captcha",
            "ocr_captcha",
            "auto_login",
            "auto_buy_credits",
            "auto_accept_terms",
            "rotate_proxy",
            "spoof_fingerprint",
        )
        if any(term in name_lower for term in forbidden_terms):
            raise FlowHumanBypassAttemptedError(
                f"Automated action '{action_name}' violates account safety policy (zero bypass rule)."
            )

    @classmethod
    def redact_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Redacts sensitive credentials, cookies, tokens, and email addresses."""
        redacted: Dict[str, Any] = {}
        for key, val in data.items():
            if any(s in key.lower() for s in ("cookie", "token", "auth", "secret", "password", "session")):
                redacted[key] = "[REDACTED_SECRET]"
            elif isinstance(val, str):
                cleaned = val
                for pattern in cls.SENSITIVE_PATTERNS:
                    cleaned = pattern.sub("[REDACTED]", cleaned)
                redacted[key] = cleaned
            elif isinstance(val, dict):
                redacted[key] = cls.redact_dict(val)
            elif isinstance(val, list):
                redacted[key] = [
                    cls.redact_dict(item) if isinstance(item, dict) else item for item in val
                ]
            else:
                redacted[key] = val
        return redacted


class FlowHumanControlManager:
    """Manages human intervention lifecycle and safe resume protocol (plan 04 §27.2–§27.3)."""

    def __init__(
        self,
        safety_policy: Optional[FlowAccountSafetyPolicy] = None,
        *,
        state_dir: Optional[str] = None,
    ) -> None:
        self.safety_policy = safety_policy or FlowAccountSafetyPolicy()
        self._state_dir = Path(state_dir).resolve() if state_dir else None
        self._path = (
            self._state_dir / "flow_human_actions.json"
            if self._state_dir is not None
            else None
        )
        if self._state_dir is not None:
            self._state_dir.mkdir(parents=True, exist_ok=True)
        self.active_records = self._load_records()
        self.paused_sessions: Set[str] = {
            record.session_id
            for record in self.active_records.values()
            if record.status == FlowHumanActionStatus.PENDING
        }
        # Keep the circuit breaker effective across process restarts.  A
        # terminal record still represents a prior account intervention.
        for record in self.active_records.values():
            current_count = self.safety_policy.session_intervention_counts.get(
                record.session_id, 0
            )
            self.safety_policy.session_intervention_counts[record.session_id] = (
                current_count + 1
            )
        # (session, token) -> nesting depth.  The same operation may call
        # navigation, while another token is a competing browser action.
        self._automation_depths: Dict[tuple[str, str], int] = {}

    @property
    def state_path(self) -> Optional[Path]:
        """Persistence path, exposed for diagnostics and verification only."""
        return self._path

    def _load_records(self) -> Dict[str, FlowHumanActionRecord]:
        if self._path is None or not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("root must be an object")
            records = raw.get("records", raw)
            if not isinstance(records, dict):
                raise ValueError("records must be an object")
            return {
                action_id: FlowHumanActionRecord.from_dict(record)
                for action_id, record in records.items()
                if isinstance(action_id, str) and isinstance(record, dict)
            }
        except (OSError, ValueError, KeyError) as exc:
            # A missing/unreadable audit record must not silently unpause a
            # browser session; the operator needs to repair the state first.
            raise FlowHumanControlError(
                f"unable to load durable human-control state: {exc}"
            ) from exc

    def _save_records(self) -> None:
        if self._path is None:
            return
        payload = {
            "schema_version": 1,
            "records": {
                action_id: record.to_dict()
                for action_id, record in sorted(self.active_records.items())
            },
        }
        temporary_path = self._path.with_suffix(".tmp")
        try:
            temporary_path.write_text(
                json.dumps(payload, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(self._path)
        except OSError as exc:
            raise FlowHumanControlError(
                f"unable to persist durable human-control state: {exc}"
            ) from exc

    def list_records(self) -> list[FlowHumanActionRecord]:
        """Return stable-ordered human action records for operator review."""
        return sorted(
            self.active_records.values(),
            key=lambda record: (record.detected_at, record.human_action_id),
        )

    def get_record(self, human_action_id: str) -> Optional[FlowHumanActionRecord]:
        return self.active_records.get(human_action_id)

    def begin_automated_action(self, session_id: str, operation_token: str) -> None:
        """Assert takeover is clear and reserve bounded browser capacity."""
        self.assert_session_active(session_id)
        key = (session_id, operation_token)
        depth = self._automation_depths.get(key, 0)
        if depth == 0:
            self.safety_policy.reserve_automated_action(session_id, operation_token)
        self._automation_depths[key] = depth + 1

    def end_automated_action(self, session_id: str, operation_token: str) -> None:
        """Release a reservation created by :meth:`begin_automated_action`."""
        key = (session_id, operation_token)
        depth = self._automation_depths.get(key, 0)
        if depth <= 1:
            self._automation_depths.pop(key, None)
            self.safety_policy.release_automated_action(session_id, operation_token)
        else:
            self._automation_depths[key] = depth - 1

    def create_or_get_human_action(
        self,
        *,
        session_id: str,
        project_id: str,
        human_state: FlowHumanState,
        reason: str,
        safe_resume_state: FlowUiState,
        raw_evidence: Dict[str, Any],
        generation_id: Optional[str] = None,
    ) -> FlowHumanActionRecord:
        """Idempotently record a takeover request for one blocked operation."""
        for record in self.active_records.values():
            if (
                record.status == FlowHumanActionStatus.PENDING
                and record.session_id == session_id
                and record.project_id == project_id
                and record.generation_id == generation_id
                and record.human_state == human_state
            ):
                return record
        return self.create_human_action(
            session_id=session_id,
            project_id=project_id,
            human_state=human_state,
            reason=reason,
            safe_resume_state=safe_resume_state,
            raw_evidence=raw_evidence,
            generation_id=generation_id,
        )

    def create_human_action(
        self,
        session_id: str,
        project_id: str,
        human_state: FlowHumanState,
        reason: str,
        safe_resume_state: FlowUiState,
        raw_evidence: Dict[str, Any],
        generation_id: Optional[str] = None,
    ) -> FlowHumanActionRecord:
        """Pause session scheduler and create durable human action record (plan 04 §27.2)."""
        # Check circuit breaker
        self.safety_policy.record_intervention(session_id)

        redacted_evidence = FlowAccountSafetyPolicy.redact_dict(raw_evidence)
        action_id = f"ha_{uuid.uuid4().hex[:12]}"

        record = FlowHumanActionRecord(
            human_action_id=action_id,
            session_id=session_id,
            project_id=project_id,
            generation_id=generation_id,
            human_state=human_state,
            reason=reason,
            detected_at=_utc_now_iso(),
            safe_resume_state=safe_resume_state,
            redacted_evidence=redacted_evidence,
            status=FlowHumanActionStatus.PENDING,
        )

        self.active_records[action_id] = record
        self.paused_sessions.add(session_id)
        self._save_records()
        return record

    def assert_session_active(self, session_id: str) -> None:
        """Raises exception if session is currently paused for human takeover."""
        if session_id in self.paused_sessions:
            raise FlowHumanActionBlockedError(
                f"Session '{session_id}' is paused for human intervention. Automated actions are blocked."
            )

    def get_takeover_instructions(self, human_action_id: str) -> Dict[str, Any]:
        """Provides user-facing takeover instructions without exposing secrets (plan 04 §27.2)."""
        record = self.get_record(human_action_id)
        if not record:
            raise FlowHumanControlError(f"Human action '{human_action_id}' not found.")

        instructions = {
            "human_action_id": record.human_action_id,
            "session_id": record.session_id,
            "project_id": record.project_id,
            "human_state": record.human_state.value,
            "reason": record.reason,
            "user_action_required": self._get_user_action_prompt(record.human_state),
            "status": record.status.value,
        }
        return instructions

    def _get_user_action_prompt(self, state: FlowHumanState) -> str:
        prompts = {
            FlowHumanState.HUMAN_LOGIN_REQUIRED: "Please log in to your Google account in the browser session.",
            FlowHumanState.HUMAN_CAPTCHA_REQUIRED: "Please solve the CAPTCHA challenge presented in the browser.",
            FlowHumanState.HUMAN_ACCOUNT_VERIFICATION_REQUIRED: "Please complete 2-factor or identity verification.",
            FlowHumanState.HUMAN_TERMS_ACCEPTANCE_REQUIRED: "Please review and accept the terms of service in the browser.",
            FlowHumanState.HUMAN_PAYMENT_CONFIRMATION_REQUIRED: "Please manage subscription/payment details manually.",
        }
        return prompts.get(state, "Manual action required in browser session.")

    def execute_safe_resume(
        self,
        human_action_id: str,
        resolved_by: str,
        current_observation: FlowUiObservation,
        expected_project_id: str,
        job_registry: Optional[FlowJobRegistry] = None,
        project_verifier: Optional[Callable[[str, FlowUiObservation], bool]] = None,
    ) -> Dict[str, Any]:
        """6-step safe resume protocol (plan 04 §27.3).

        Steps:
          1. Health check (UI is reachable, not in error)
          2. Confirm challenge cleared (no human state detected)
          3. Confirm account & project match expectation
          4. Reconcile active job (never re-submit blindly)
          5. Resume from safe_resume_state
          6. Record audit record
        """
        record = self.get_record(human_action_id)
        if not record:
            raise FlowHumanControlError(f"Human action '{human_action_id}' not found.")

        if record.status != FlowHumanActionStatus.PENDING:
            raise FlowHumanControlError(f"Human action '{human_action_id}' is already {record.status.value}.")

        # Step 1: Health check.  A blank or explicit Flow error page is not a
        # safe location from which to resume an account-bound action.  A
        # generic-but-reachable page remains eligible for the subsequent
        # challenge/project checks because providers can change page labels.
        if not current_observation.url:
            raise FlowHumanControlError("Resume failed: Browser observation has empty URL.")
        observed_state = FlowUiStateMachine().classify(current_observation)
        if observed_state == FlowUiState.ERROR:
            raise FlowHumanControlError(
                f"Resume failed: Browser health check reached {observed_state.value}."
            )

        # Step 2: Confirm challenge cleared
        detected_challenge = FlowHumanControlDetector.detect(current_observation)
        if detected_challenge is not None:
            raise FlowHumanControlError(
                f"Resume failed: Challenge '{detected_challenge.value}' is still active."
            )

        # Step 3: Confirm project / account match
        if expected_project_id and record.project_id != expected_project_id:
            raise FlowHumanControlError(
                f"Resume failed: Project ID mismatch ('{record.project_id}' != '{expected_project_id}')."
            )
        if project_verifier is not None and not project_verifier(
            record.project_id, current_observation
        ):
            raise FlowHumanControlError(
                "Resume failed: current browser page does not verify the expected project."
            )

        # Step 4: Reconcile active job if attached
        reconciled_job_status: Optional[str] = None
        if record.generation_id and job_registry:
            job = job_registry.get(record.generation_id)
            if job and job.status == FlowJobStatus.SUBMITTING:
                # Reconcile to avoid duplicate submit
                reconciled_job_status = FlowJobStatus.UNKNOWN_REQUIRES_RECONCILIATION.value
                job_registry.mark(record.generation_id, FlowJobStatus.UNKNOWN_REQUIRES_RECONCILIATION)

        # Step 5: Resume state transition & unpause session
        record.status = FlowHumanActionStatus.RESOLVED
        record.resolved_by = resolved_by
        record.resolved_at = _utc_now_iso()
        self.paused_sessions.discard(record.session_id)
        self._save_records()

        # Step 6: Record audit log
        audit_record = {
            "human_action_id": record.human_action_id,
            "session_id": record.session_id,
            "project_id": record.project_id,
            "generation_id": record.generation_id,
            "resolved_by": record.resolved_by,
            "resolved_at": record.resolved_at,
            "resumed_at_state": record.safe_resume_state.value,
            "reconciled_job_status": reconciled_job_status,
            "project_verified": project_verifier is not None,
            "duplicate_submit_prevented": True,
        }
        return audit_record
