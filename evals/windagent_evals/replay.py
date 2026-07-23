"""
Deterministic Replay Engine for WindAgent Evals (Phase 11).
Replays recorded trace events and step sequences for offline benchmark evaluation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RecordedEvent:
    """A single recorded event step in execution history."""
    step_id: str
    event_type: str
    payload: Dict[str, Any]
    timestamp: float


@dataclass
class ReplayExecutionRecord:
    """Reconstructed execution state from trace event log."""
    task_id: str
    workflow_name: str
    status: str
    output: str
    used_tools: List[str]
    model_calls: List[Dict[str, Any]]
    total_tokens: int
    cost_usd: float
    total_duration_sec: float
    events: List[RecordedEvent] = field(default_factory=list)


class ReplayEngine:
    """Replays recorded trace logs to regenerate execution records for eval benchmarks."""

    def __init__(self) -> None:
        pass

    def replay_trace(self, trace_events: List[Dict[str, Any]]) -> ReplayExecutionRecord:
        """Reconstructs execution record from event trace."""
        task_id = "unknown_task"
        workflow_name = "default_workflow"
        status = "COMPLETED"
        output = ""
        used_tools = []
        model_calls = []
        total_tokens = 0
        cost_usd = 0.0
        events = []

        for evt in trace_events:
            event_type = evt.get("event_type", "")
            payload = evt.get("payload", {})
            step_id = evt.get("step_id", "step_0")
            ts = evt.get("timestamp", 0.0)

            events.append(RecordedEvent(step_id=step_id, event_type=event_type, payload=payload, timestamp=ts))

            if event_type == "task_started":
                task_id = payload.get("task_id", task_id)
                workflow_name = payload.get("workflow_name", workflow_name)
            elif event_type == "model_call":
                model_calls.append(payload)
                tokens = payload.get("tokens", 0)
                total_tokens += tokens
                cost_usd += payload.get("cost_usd", 0.0)
            elif event_type == "tool_call":
                tool_name = payload.get("tool_name")
                if tool_name and tool_name not in used_tools:
                    used_tools.append(tool_name)
            elif event_type == "task_completed":
                status = "COMPLETED"
                output = payload.get("output", output)
            elif event_type == "task_failed":
                status = "FAILED"
                output = payload.get("error", "Task execution failed")

        duration = events[-1].timestamp - events[0].timestamp if len(events) > 1 else 0.0

        return ReplayExecutionRecord(
            task_id=task_id,
            workflow_name=workflow_name,
            status=status,
            output=output,
            used_tools=used_tools,
            model_calls=model_calls,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            total_duration_sec=duration,
            events=events
        )
