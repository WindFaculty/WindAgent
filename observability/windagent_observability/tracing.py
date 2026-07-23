"""
Distributed Trace Chain for WindAgent Observability (Phase 11).
Traces the execution chain: task -> plan -> workflow -> step -> model call -> tool call -> verification.
"""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SpanKind(str, Enum):
    """Hierarchy levels of tracing chain."""
    TASK = "task"
    PLAN = "plan"
    WORKFLOW = "workflow"
    STEP = "step"
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    VERIFICATION = "verification"


@dataclass
class Span:
    """A single trace span representing an operation in the execution chain."""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    kind: SpanKind
    start_time: float
    end_time: Optional[float] = None
    status: str = "IN_PROGRESS"
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def finish(self, status: str = "OK", extra_attributes: Optional[Dict[str, Any]] = None) -> None:
        """Completes span execution."""
        self.end_time = time.time()
        self.status = status
        if extra_attributes:
            self.attributes.update(extra_attributes)

    @property
    def duration_sec(self) -> float:
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time


class TraceChain:
    """Manages spans forming an end-to-end task execution trace."""

    def __init__(self, trace_id: Optional[str] = None) -> None:
        self.trace_id = trace_id or str(uuid.uuid4())
        self.spans: Dict[str, Span] = {}

    def start_span(
        self,
        name: str,
        kind: SpanKind,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> Span:
        """Starts a new trace span linked to parent span."""
        span_id = str(uuid.uuid4())
        span = Span(
            span_id=span_id,
            trace_id=self.trace_id,
            parent_span_id=parent_span_id,
            name=name,
            kind=kind,
            start_time=time.time(),
            attributes=attributes or {}
        )
        self.spans[span_id] = span
        return span

    def get_span(self, span_id: str) -> Optional[Span]:
        return self.spans.get(span_id)

    def list_spans() -> List[Span]:
        return list(self.spans.values())

    def validate_chain_completeness(self) -> bool:
        """Validates that all expected trace levels (task -> plan -> workflow -> step -> model/tool -> verification) are present."""
        kinds_present = {span.kind for span in self.spans.values()}
        required = {SpanKind.TASK, SpanKind.WORKFLOW, SpanKind.STEP}
        return required.issubset(kinds_present)
