"""Hardcoded intent parser + workflow creator for Phase 1.

Phase 4 will replace the parser with Qwen3 4B via Ollama. Until then this
rule-based fallback supports the two demo scenarios:

  1. "Mở Notepad và gõ Hello"   -> open_app(notepad) + type_text("Hello")
  2. "Mở google.com trên Edge"  -> open_app(edge) + open_url("https://google.com")

Unknown intents produce a 0-step workflow and a warning. The bus still emits
`planning_finished` with `used_fallback=True` so the frontend never hangs.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from db.database import Database
from db.models import WorkflowORM, WorkflowStepORM
from schemas.event import (
    EventEnvelope,
    PlanningFinishedData,
    PlanningStartedData,
    WorkflowCreatedData,
)
from schemas.workflow import Workflow, WorkflowStep
from services.event_bus import EventBus
from services.planner_service import PlanResult, PlannerService


# ---------- Intent parsing (pure, testable) ----------

# Word/phrase variants are kept Vietnamese-friendly while still matching
# the exact demo phrases from docs/mvp_scope.md.
NOTEPAD_RE = re.compile(r"(?i)\b(notepad)\b")
TYPE_RE = re.compile(r"(?i)\b(gõ|type|typing)\b")
EDGE_RE = re.compile(r"(?i)\b(edge|msedge|microsoft\s*edge)\b")
URL_RE = re.compile(r"(?P<url>https?://[^\s,]+|[a-z0-9][a-z0-9\-]*\.[a-z]{2,}[^\s,]*)", re.IGNORECASE)


@dataclass
class IntentDraft:
    steps: List[Dict[str, Any]]
    warning: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not self.steps


def parse_intent(text: str) -> IntentDraft:
    """Pure function: text -> IntentDraft. No I/O, no side effects."""
    text = (text or "").strip()
    if not text:
        return IntentDraft(steps=[], warning="empty message")

    steps: List[Dict[str, Any]] = []
    warnings: List[str] = []

    # ----- Notepad + type pattern -----
    if NOTEPAD_RE.search(text):
        # Find the bit after the type verb as the text payload.
        m = TYPE_RE.search(text)
        typed_payload = ""
        if m:
            tail = text[m.end():].strip(" :,-\"'\u201c\u201d\u2018\u2019")
            # Drop trailing periods
            typed_payload = tail.strip(". \t").strip("\"'\u201c\u201d\u2018\u2019")
        if not typed_payload:
            typed_payload = "Hello"
            warnings.append("no explicit text payload, defaulted to 'Hello'")
        steps.append({
            "name": "Open Notepad",
            "tool_name": "open_app",
            "params": {"app": "notepad"},
        })
        steps.append({
            "name": "Type text",
            "tool_name": "type_text",
            "params": {"text": typed_payload, "method": "paste"},
        })

    # ----- Edge + URL pattern -----
    elif EDGE_RE.search(text):
        m = URL_RE.search(text)
        url = m.group("url") if m else None
        if url and not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
        if not url:
            warnings.append("edge requested but no URL detected")
        else:
            steps.append({
                "name": "Open Edge",
                "tool_name": "open_app",
                "params": {"app": "edge"},
            })
            steps.append({
                "name": "Navigate to URL",
                "tool_name": "open_url",
                "params": {"url": url},
            })

    # ----- Empty steps: prefer collected warnings over catch-all -----
    if not steps and warnings:
        return IntentDraft(steps=[], warning="; ".join(warnings))

    # ----- Catch-all: unknown intent -----
    if not steps:
        return IntentDraft(steps=[], warning=f"no parser rule matched: {text[:60]!r}")

    warning = "; ".join(warnings) if warnings else None
    return IntentDraft(steps=steps, warning=warning)


# ---------- Workflow service ----------

class WorkflowService:
    """Creates and stores workflows; emits planning + workflow_created events."""

    # Default model name used when no PlannerService is wired (Phase 1
    # backward compat — pure rule-based fallback).
    PLANNER_MODEL_NAME = "fallback-rule-based"

    def __init__(
        self,
        event_bus: EventBus,
        db: Optional[Database] = None,
        planner: Optional[PlannerService] = None,
    ) -> None:
        self._bus = event_bus
        self._db = db
        self._workflows: Dict[UUID, Workflow] = {}
        self._by_session: Dict[UUID, UUID] = {}
        self._planner = planner

    async def create_for_message(
        self,
        session_id: UUID,
        message_id: UUID,
        content: str,
    ) -> Workflow:
        """End-to-end: emit planning_started, parse via PlannerService (or
        fallback), emit planning_finished, persist workflow, emit
        workflow_created."""
        start = time.perf_counter()
        await self._bus.publish(
            str(session_id),
            EventEnvelope(
                event="planning_started",
                data=PlanningStartedData(
                    session_id=session_id,
                    message_id=message_id,
                ).model_dump(mode="json"),
            ),
        )

        # Phase 4: route planning through the PlannerService when one
        # is wired. Fall back to parse_intent directly when not (so
        # unit tests don't need a model client).
        if self._planner is not None:
            plan: PlanResult = await self._planner.plan(content)
            steps_data: List[Dict[str, Any]] = plan.steps
            model_name = plan.model or self.PLANNER_MODEL_NAME
            used_fallback = plan.used_fallback
        else:
            draft = parse_intent(content)
            steps_data = list(draft.steps)
            model_name = self.PLANNER_MODEL_NAME
            used_fallback = True

        now = datetime.now(timezone.utc)
        workflow_id = uuid4()
        workflow_steps = [
            WorkflowStep(
                id=uuid4(),
                order=idx + 1,
                name=s["name"],
                tool_name=s["tool_name"],
                params=s["params"],
            )
            for idx, s in enumerate(steps_data)
        ]
        workflow = Workflow(
            workflow_id=workflow_id,
            session_id=session_id,
            created_at=now,
            status="pending",
            steps=workflow_steps,
        )
        self._workflows[workflow_id] = workflow
        self._by_session[session_id] = workflow_id

        latency_ms = int((time.perf_counter() - start) * 1000)

        if self._db is not None:
            async with self._db.session() as s:
                wf_row = WorkflowORM(
                    id=str(workflow_id),
                    session_id=str(session_id),
                    status="pending",
                    created_at=now,
                    updated_at=now,
                )
                s.add(wf_row)
                for st in workflow_steps:
                    s.add(WorkflowStepORM(
                        id=str(st.id),
                        workflow_id=str(workflow_id),
                        order_index=st.order,
                        name=st.name,
                        tool_name=st.tool_name,
                        params_json=json.dumps(st.params, ensure_ascii=False),
                        status=st.status,
                        created_at=now,
                        updated_at=now,
                    ))

        await self._bus.publish(
            str(session_id),
            EventEnvelope(
                event="planning_finished",
                timestamp=now,
                data=PlanningFinishedData(
                    session_id=session_id,
                    message_id=message_id,
                    model=model_name,
                    latency_ms=latency_ms,
                    used_fallback=used_fallback,
                ).model_dump(mode="json"),
            ),
        )

        await self._bus.publish(
            str(session_id),
            EventEnvelope(
                event="workflow_created",
                timestamp=now,
                data=WorkflowCreatedData(
                    session_id=session_id,
                    workflow_id=workflow_id,
                    step_count=len(workflow_steps),
                ).model_dump(mode="json"),
            ),
        )

        return workflow

    async def get_for_session(self, session_id: UUID) -> Optional[Workflow]:
        wid = self._by_session.get(session_id)
        if wid is None:
            return None
        return self._workflows.get(wid)

    async def update_status(
        self,
        session_id: UUID,
        status: str,
        *,
        workflow_id: Optional[UUID] = None,
    ) -> None:
        """Update the WorkflowORM row + in-memory Workflow.status.

        Used by the Phase 5 runner to mark running/completed/failed/etc.
        No-op if the workflow does not exist.
        """
        wid = workflow_id or self._by_session.get(session_id)
        if wid is None:
            return
        wf = self._workflows.get(wid)
        if wf is None:
            return
        now = datetime.now(timezone.utc)
        updated = wf.model_copy(update={"status": status, "updated_at": now})  # type: ignore[arg-type]
        self._workflows[wid] = updated

        if self._db is not None:
            from db.models import WorkflowORM

            async with self._db.session() as s:
                row = await s.get(WorkflowORM, str(wid))
                if row is not None:
                    row.status = status
                    row.updated_at = now

    async def update_step_status(
        self,
        step_id: UUID,
        status: str,
        *,
        workflow_id: Optional[UUID] = None,
    ) -> None:
        """Update a WorkflowStepORM row + in-memory WorkflowStep.status.

        Used by the Phase 5 runner. Walks all workflows (small N) to find
        the step — fine for MVP, replace with index later if needed.
        """
        for wf in self._workflows.values():
            for step in wf.steps:
                if step.id == step_id:
                    now = datetime.now(timezone.utc)
                    new_steps = [
                        s.model_copy(update={"status": status}) if s.id == step_id else s
                        for s in wf.steps
                    ]
                    self._workflows[wf.workflow_id] = wf.model_copy(update={"steps": new_steps})
                    break
            else:
                continue
            break

        if self._db is not None:
            from db.models import WorkflowStepORM

            async with self._db.session() as s:
                row = await s.get(WorkflowStepORM, str(step_id))
                if row is not None:
                    row.status = status
                    row.updated_at = datetime.now(timezone.utc)

    def workflow_count(self) -> int:
        return len(self._workflows)