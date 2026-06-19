"""Phase 12 — Agent-S3 step orchestrator.

This module wires Agent-S3's raw-action proposals into WindAgent's
existing tool pipeline. It is the **safety boundary** between the
upstream LLM and WindAgent:

  Planner / user
    -> WorkflowRunner (permission gate on ``agent_s3_step``)
      -> ToolExecutor (this orchestrator)
        -> AgentS3Adapter.propose(...)             (raw Python strings)
        -> AgentS3ActionTranslator.translate(...) (whitelist mapping)
        -> mapped tool in allow-list?
              NO  -> return AGENT_S3_UNSAFE_ACTION / _UNSUPPORTED_ACTION
              YES -> validate mapped params via tool_registry
                  -> dry_run?
                      YES -> return translated tool/params only (audit)
                      NO  -> run mapped tool via ToolExecutor._run
        -> emit ``agent_s3_action_proposed`` event
        -> persist audit row (tool_calls via ToolExecutor._emit_and_persist)

The orchestrator NEVER calls ``exec()`` / ``eval()`` / ``compile()`` on
raw strings. The translator only inspects them as text; matched actions
go through WindAgent's standard tool pipeline which has its own Pydantic
validation + permission gate + audit.

State / I/O surface is intentionally narrow:

  ``AgentS3StepExecutor`` is constructed with the Agent-S3 adapter,
  event bus, and an optional GUI adapter (for screenshot capture). The
  runner holds a single instance per session via ``app.state``.

Failure modes are mapped to explicit error codes so the frontend /
audit log can show a stable contract:

  * ``AGENT_S3_DISABLED``             - ``WINDAGENT_AGENT_S3_ENABLED=0``
  * ``AGENT_S3_UNAVAILABLE``          - adapter reported unavailable
  * ``AGENT_S3_ADAPTER_NOT_READY``    - adapter None at lifespan
  * ``AGENT_S3_UNSAFE_ACTION``        - raw action hit a deny pattern
  * ``AGENT_S3_UNSUPPORTED_ACTION``   - translator returned no accepted action
  * ``AGENT_S3_MISCONFIGURED``        - adapter failed at construction
  * ``AGENT_S3_PROPOSE_FAILED``       - upstream predict raised
  * ``AGENT_S3_PARSE_FAILED``         - unexpected translator exception
  * ``MAPPED_TOOL_NOT_WHITELISTED``   - defence-in-depth (should never happen)
  * ``MAPPED_TOOL_INVALID_PARAMS``    - translated params failed Pydantic
  * ``MAPPED_TOOL_EXECUTION_FAILED``  - inner ToolExecutor._run raised
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from uuid import UUID

from services.agent_s3_action_translator import (
    RejectedAction,
    TranslatedAction,
    TranslationResult,
    translate,
)
from services.agent_s3_adapter import AgentS3Adapter, AgentS3Proposal
from services.agent_s3_config import AgentS3Config
from services.event_bus import EventBus
from services.tool_registry import (
    AgentS3StepParams,
    validate_params,
)


log = logging.getLogger(__name__)


# ---------- Mapped tool whitelist ----------
#
# Defence-in-depth: even though the translator maps to specific tool
# names by construction, this set is the explicit allow-list the
# orchestrator re-validates against. Adding a tool here means
# ``agent_s3_step`` is allowed to drive that tool after the outer
# permission gate has approved the meta-action.
AGENT_S3_MAPPED_TOOL_ALLOWLIST = frozenset({
    "click_xy",
    "type_text",
    "hotkey",
    "press_key",
    "scroll",
    "wait",
    "screenshot",
})


# Truncate raw action strings before persisting/auditing so a giant blob
# from the upstream model doesn't bloat the DB.
_RAW_ACTION_AUDIT_MAX_LEN = 400

# Substrings (case-insensitive) we never echo from upstream ``info``.
_SECRET_KEY_NEEDLES = (
    "apikey", "api_key", "secret", "token", "password", "bearer",
)


def _scrub_for_audit(raw: str) -> str:
    """Truncate + strip control chars. NEVER echo API keys."""
    if not raw:
        return ""
    # Replace control chars that would corrupt the JSONL line.
    cleaned = "".join(
        c if (c == "\n" or c == "\t" or 0x20 <= ord(c) < 0x7F or ord(c) > 0xA0)
        else " "
        for c in raw
    )
    if len(cleaned) > _RAW_ACTION_AUDIT_MAX_LEN:
        cleaned = cleaned[:_RAW_ACTION_AUDIT_MAX_LEN] + "...<truncated>"
    return cleaned


def _scrub_info(info: Dict[str, Any]) -> Dict[str, Any]:
    """Strip any accidental secret-shaped fields from upstream ``info``."""
    return {
        k: ("<redacted>" if any(s in k.lower() for s in _SECRET_KEY_NEEDLES) else v)
        for k, v in info.items()
    }


# ---------- Public result shape ----------

class AgentS3StepResult:
    """Lightweight result wrapper returned by ``AgentS3StepExecutor.execute``.

    Mirrors ``ToolExecutor.execute``'s public shape so callers (and the
    wrapping ``ToolExecutor._execute_agent_s3_step``) can convert it
    uniformly. ``status`` is one of ``"success"`` / ``"failed"``.

    The structured fields (``proposal``, ``translation``, ``mapped``)
    are only populated when propose + translate succeeded; downstream
    callers can serialise them into ``tool_call_finished.data.output``
    or the audit log without re-doing the work.
    """

    def __init__(
        self,
        *,
        status: str,
        instruction: str,
        proposal: Optional[AgentS3Proposal] = None,
        translation: Optional[TranslationResult] = None,
        mapped: Optional[TranslatedAction] = None,
        mapped_execution_output: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None,
        duration_ms: int = 0,
        screenshot_path: Optional[str] = None,
        dry_run: bool = False,
    ) -> None:
        self.status = status
        self.instruction = instruction
        self.proposal = proposal
        self.translation = translation
        self.mapped = mapped
        self.mapped_execution_output = mapped_execution_output
        self.error_code = error_code
        self.error_message = error_message
        self.error_type = error_type
        self.duration_ms = duration_ms
        self.screenshot_path = screenshot_path
        self.dry_run = dry_run

    def to_output_dict(self) -> Dict[str, Any]:
        """Serialise into the ``output`` field of a tool_call row."""
        out: Dict[str, Any] = {
            "instruction": self.instruction,
            "dry_run": self.dry_run,
            "screenshot_path": self.screenshot_path,
            "duration_ms": self.duration_ms,
        }
        if self.proposal is not None:
            out["proposal"] = {
                "backend": self.proposal.backend,
                "info": _scrub_info(self.proposal.info),
                "raw_actions": [
                    _scrub_for_audit(a) for a in self.proposal.raw_actions
                ],
            }
        if self.translation is not None:
            out["translation"] = {
                "accepted_count": len(self.translation.accepted),
                "rejected_count": len(self.translation.rejected),
                "rejected": [
                    {
                        "source_line": _scrub_for_audit(r.source_line),
                        "reason": r.reason,
                        "line_number": r.line_number,
                    }
                    for r in self.translation.rejected
                ],
            }
        if self.mapped is not None:
            out["mapped"] = {
                "tool_name": self.mapped.tool_name,
                "params": dict(self.mapped.params),
                "source_line": _scrub_for_audit(self.mapped.source_line),
                "confidence": self.mapped.confidence,
            }
        if self.mapped_execution_output is not None:
            out["mapped_execution"] = dict(self.mapped_execution_output)
        if self.status == "failed":
            out["error"] = {
                "type": self.error_type or "agent_s3_error",
                "code": self.error_code or "AGENT_S3_FAILED",
                "message": self.error_message or "",
            }
        return out


# ---------- Orchestrator ----------

# ``run_mapped_tool`` is a callback that takes (tool_name, params, session_id)
# and runs the inner mapped tool. ``ToolExecutor._run`` matches this shape
# (sync, runs in worker thread). We accept a callable so unit tests can
# inject a fake without spinning up a full ToolExecutor.
RunMappedToolFn = Callable[[str, Dict[str, Any], UUID], Dict[str, Any]]


class AgentS3StepExecutor:
    """Orchestrates one ``agent_s3_step`` invocation.

    Construction is cheap — no I/O. ``execute()`` does all the I/O work
    and returns an ``AgentS3StepResult``.
    """

    def __init__(
        self,
        *,
        config: AgentS3Config,
        adapter: Optional[AgentS3Adapter],
        event_bus: EventBus,
        artifacts_root: Path,
        run_mapped_tool: RunMappedToolFn,
    ) -> None:
        self._cfg = config
        self._adapter = adapter
        self._bus = event_bus
        self._artifacts_root = Path(artifacts_root)
        self._run_mapped_tool = run_mapped_tool
        # GUI adapter is bound later via ``bind_gui_for_screenshot`` to
        # avoid an import cycle at construction time and to keep the
        # orchestrator mockable in unit tests.
        self._gui_for_screenshot = None  # type: ignore[assignment]

    # ---- Public API ----

    async def execute(
        self,
        *,
        session_id: UUID,
        step_id: UUID,
        params: AgentS3StepParams,
    ) -> AgentS3StepResult:
        """Run one agent_s3_step. Never raises — failures are encoded
        into the returned result with ``status="failed"``."""
        start = time.perf_counter()

        # 1. Pre-flight: enabled / adapter ready.
        if not self._cfg.enabled:
            return self._fail(
                params, start,
                code="AGENT_S3_DISABLED",
                type_="config_disabled",
                message=(
                    "Agent-S3 is disabled. Set WINDAGENT_AGENT_S3_ENABLED=1 "
                    "and provide required env vars to enable."
                ),
            )
        if self._adapter is None:
            return self._fail(
                params, start,
                code="AGENT_S3_ADAPTER_NOT_READY",
                type_="adapter_missing",
                message=(
                    "Agent-S3 adapter was not initialised by the lifespan. "
                    "Check backend startup logs."
                ),
            )
        if not self._adapter.is_available():
            return self._fail(
                params, start,
                code="AGENT_S3_UNAVAILABLE",
                type_="adapter_unavailable",
                message=(
                    "Agent-S3 adapter reports unavailable. See "
                    "/agent-s3/health for the reason."
                ),
            )

        # 2. Capture screenshot if requested.
        screenshot_path: Optional[str] = None
        if params.screenshot:
            try:
                screenshot_path = await self._capture_screenshot(session_id)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "agent_s3_step: screenshot failed: %s; "
                    "proceeding without observation",
                    exc,
                )
                screenshot_path = None

        # 3. Call adapter.propose(). The adapter is async; await directly
        #    since ``execute()`` is on the event loop. Upstream predict()
        #    is sync inside the adapter but is bounded by ``timeout_ms``
        #    via the runner's own watchdog + asyncio cancellation.
        observation: Dict[str, Any] = {}
        if screenshot_path:
            observation["screenshot"] = screenshot_path
        try:
            proposal = await self._adapter.propose(params.instruction, observation)
        except Exception as exc:  # noqa: BLE001
            return self._fail(
                params, start,
                code="AGENT_S3_PROPOSE_FAILED",
                type_=type(exc).__name__,
                message=f"Agent-S3 propose() raised: {exc}",
                screenshot_path=screenshot_path,
            )

        if proposal is None:
            # Differentiate "adapter predict raised" (last_error set)
            # from "adapter not available at all" (last_error None).
            # The adapter swallows predict() exceptions internally and
            # records them in ``last_error``; ``propose()`` then returns
            # None. Surface that as a distinct error code so the audit
            # trail shows what really happened.
            last_err = self._adapter.last_error
            if last_err:
                return self._fail(
                    params, start,
                    code="AGENT_S3_PROPOSE_FAILED",
                    type_="predict_returned_none_after_error",
                    message=(
                        f"Agent-S3 adapter set last_error: {last_err!r}"
                    ),
                    screenshot_path=screenshot_path,
                )
            return self._fail(
                params, start,
                code="AGENT_S3_UNAVAILABLE",
                type_="propose_returned_none",
                message=(
                    "Agent-S3 propose() returned None; the adapter is "
                    "unavailable. See /agent-s3/health.last_error."
                ),
                screenshot_path=screenshot_path,
            )

        # 4. Translate raw actions through the whitelist.
        try:
            translation = translate(proposal.raw_actions)
        except Exception as exc:  # noqa: BLE001
            return self._fail(
                params, start,
                code="AGENT_S3_PARSE_FAILED",
                type_=type(exc).__name__,
                message=f"translator raised: {exc}",
                proposal=proposal,
                screenshot_path=screenshot_path,
            )

        # 5. Differentiate translator outcomes.
        if translation.accepted:
            mapped = translation.accepted[0]
        elif translation.rejected:
            first: RejectedAction = translation.rejected[0]
            code = (
                "AGENT_S3_UNSAFE_ACTION"
                if first.reason.startswith("denied:")
                else "AGENT_S3_UNSUPPORTED_ACTION"
            )
            return self._fail(
                params, start,
                code=code,
                type_="translation_rejected",
                message=first.reason,
                proposal=proposal,
                translation=translation,
                screenshot_path=screenshot_path,
            )
        else:
            # Translator returned nothing — should never happen because
            # the input list is non-empty (propose() returned strings).
            return self._fail(
                params, start,
                code="AGENT_S3_UNSUPPORTED_ACTION",
                type_="translation_empty",
                message="translator returned neither accepted nor rejected",
                proposal=proposal,
                translation=translation,
                screenshot_path=screenshot_path,
            )

        # 6. Defence-in-depth: re-validate mapped tool against allow-list.
        if mapped.tool_name not in AGENT_S3_MAPPED_TOOL_ALLOWLIST:
            return self._fail(
                params, start,
                code="MAPPED_TOOL_NOT_WHITELISTED",
                type_="defence_in_depth",
                message=(
                    f"translator mapped to {mapped.tool_name!r} which is "
                    f"not in the agent_s3_step allow-list "
                    f"{sorted(AGENT_S3_MAPPED_TOOL_ALLOWLIST)}."
                ),
                proposal=proposal,
                translation=translation,
                mapped=mapped,
                screenshot_path=screenshot_path,
            )

        # 7. Validate mapped params via Pydantic. If validation fails
        # the LLM hallucinated bad params — fail clean.
        try:
            validate_params(mapped.tool_name, dict(mapped.params))
        except Exception as exc:  # noqa: BLE001
            return self._fail(
                params, start,
                code="MAPPED_TOOL_INVALID_PARAMS",
                type_="validation_error",
                message=(
                    f"translator output for {mapped.tool_name!r} failed "
                    f"Pydantic validation: {exc}"
                ),
                proposal=proposal,
                translation=translation,
                mapped=mapped,
                screenshot_path=screenshot_path,
            )

        # 8. Emit the ``agent_s3_action_proposed`` event so the audit
        # trail has evidence of what the model proposed + what we mapped.
        await self._emit_proposed_event(
            session_id=session_id,
            step_id=step_id,
            instruction=params.instruction,
            mapped=mapped,
            translation=translation,
            dry_run=params.dry_run,
            screenshot_path=screenshot_path,
        )

        # 9. Dry-run path: stop here, no GUI call.
        if params.dry_run:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return AgentS3StepResult(
                status="success",
                instruction=params.instruction,
                proposal=proposal,
                translation=translation,
                mapped=mapped,
                mapped_execution_output={"dry_run": True},
                duration_ms=duration_ms,
                screenshot_path=screenshot_path,
                dry_run=True,
            )

        # 10. Execute the mapped tool via the injected callback. The
        #     callback runs in the executor's worker thread.
        try:
            mapped_output = await asyncio.to_thread(
                self._run_mapped_tool,
                mapped.tool_name,
                dict(mapped.params),
                session_id,
            )
        except Exception as exc:  # noqa: BLE001
            return self._fail(
                params, start,
                code="MAPPED_TOOL_EXECUTION_FAILED",
                type_=type(exc).__name__,
                message=(
                    f"mapped tool {mapped.tool_name!r} raised: {exc}"
                ),
                proposal=proposal,
                translation=translation,
                mapped=mapped,
                screenshot_path=screenshot_path,
            )

        duration_ms = int((time.perf_counter() - start) * 1000)
        return AgentS3StepResult(
            status="success",
            instruction=params.instruction,
            proposal=proposal,
            translation=translation,
            mapped=mapped,
            mapped_execution_output=mapped_output,
            duration_ms=duration_ms,
            screenshot_path=screenshot_path,
            dry_run=False,
        )

    # ---------- Internals ----------

    def bind_gui_for_screenshot(self, gui) -> None:
        """Attach the GUI adapter used by ``_capture_screenshot``.

        Kept as a setter (not a ctor arg) so the orchestrator stays
        independent of the ToolExecutor / GuiAdapter import graph at
        construction time and can be mocked cleanly in tests.
        """
        self._gui_for_screenshot = gui

    async def _capture_screenshot(self, session_id: UUID) -> str:
        """Capture a screenshot via the GUI adapter and return its path.

        Kept narrow so unit tests can replace the GUI adapter without
        touching this method. Raises on failure so the caller can
        proceed without observation.
        """
        if self._gui_for_screenshot is None:
            raise RuntimeError(
                "AgentS3StepExecutor has no GUI adapter bound; "
                "set screenshot=False to skip."
            )
        out_dir = (
            self._artifacts_root / str(session_id) / "agent_s3_screenshots"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        out_path = out_dir / f"shot-{ts}.png"
        result = await asyncio.to_thread(
            self._gui_for_screenshot.screenshot,
            name=out_path.stem,
            out_dir=out_dir,
        )
        return str(result.get("path") or out_path)

    async def _emit_proposed_event(
        self,
        *,
        session_id: UUID,
        step_id: UUID,
        instruction: str,
        mapped: TranslatedAction,
        translation: TranslationResult,
        dry_run: bool,
        screenshot_path: Optional[str],
    ) -> None:
        # Import here to avoid a circular import at module load time.
        from schemas.event import (
            AgentS3ActionProposedData,
            EventEnvelope,
        )

        envelope = EventEnvelope(
            event="agent_s3_action_proposed",
            data=AgentS3ActionProposedData(
                session_id=session_id,
                step_id=step_id,
                instruction=instruction,
                translated_tool=mapped.tool_name,
                translated_params=dict(mapped.params),
                safety_status="accepted",
                rejection_code=None,
                rejected_count=len(translation.rejected),
                dry_run=dry_run,
                screenshot_path=screenshot_path,
            ).model_dump(mode="json"),
        )
        await self._bus.publish(str(session_id), envelope)

    def _fail(
        self,
        params: AgentS3StepParams,
        start: float,
        *,
        code: str,
        type_: str,
        message: str,
        proposal: Optional[AgentS3Proposal] = None,
        translation: Optional[TranslationResult] = None,
        mapped: Optional[TranslatedAction] = None,
        screenshot_path: Optional[str] = None,
    ) -> AgentS3StepResult:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return AgentS3StepResult(
            status="failed",
            instruction=params.instruction,
            proposal=proposal,
            translation=translation,
            mapped=mapped,
            error_code=code,
            error_message=message,
            error_type=type_,
            duration_ms=duration_ms,
            screenshot_path=screenshot_path,
            dry_run=params.dry_run,
        )


__all__ = [
    "AGENT_S3_MAPPED_TOOL_ALLOWLIST",
    "AgentS3StepExecutor",
    "AgentS3StepResult",
    "RunMappedToolFn",
]