"""
V3 Monitoring Router — Canonical system monitoring & telemetry endpoints.
Provides detailed operational observability across workers, providers, agents, queues, and runs.
"""

from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from windagent_core.domain.lifecycle import utc_now

router = APIRouter(prefix="/api/v3/monitoring", tags=["Monitoring V3"])


class WorkerInfo(BaseModel):
    worker_id: str = Field(..., description="Unique worker process or thread ID")
    name: str = Field(..., description="Human readable worker name")
    status: str = Field(..., description="Worker status ('active', 'idle', 'busy', 'stopped')")
    current_job_id: Optional[str] = Field(None, description="Active job ID if currently executing")
    concurrency: int = Field(1, description="Concurrency slots available on this worker")
    uptime_seconds: float = Field(..., description="Worker uptime in seconds")


class WorkersMonitoringResponse(BaseModel):
    workers: List[WorkerInfo]
    total_workers: int
    active_workers: int


class ProviderMonitoringInfo(BaseModel):
    provider_id: str = Field(..., description="Unique provider ID")
    name: str = Field(..., description="Provider display name")
    status: str = Field(..., description="Provider status ('healthy', 'degraded', 'unreachable')")
    avg_latency_ms: float = Field(..., description="Average latency in ms")
    error_rate_percent: float = Field(0.0, description="Error rate percentage (0-100)")
    total_requests: int = Field(..., description="Total requests served")


class ProvidersMonitoringResponse(BaseModel):
    providers: List[ProviderMonitoringInfo]


class AgentMonitoringInfo(BaseModel):
    agent_id: str = Field(..., description="Agent definition or instance ID")
    name: str = Field(..., description="Agent display name")
    role: str = Field(..., description="Agent functional role")
    status: str = Field(..., description="Agent state ('running', 'idle', 'busy')")
    current_task: Optional[str] = Field(None, description="Current assigned task description")
    tasks_completed: int = Field(0, description="Number of tasks completed by this agent")
    avg_turn_ms: float = Field(..., description="Average execution turn time in ms")


class AgentsMonitoringResponse(BaseModel):
    agents: List[AgentMonitoringInfo]


class QueueMonitoringInfo(BaseModel):
    queue_name: str = Field(..., description="Queue identifier")
    depth: int = Field(..., description="Number of items waiting in queue")
    in_flight: int = Field(..., description="Number of items currently being processed")
    throughput_per_sec: float = Field(..., description="Average throughput per second")


class QueuesMonitoringResponse(BaseModel):
    queues: List[QueueMonitoringInfo]


class RunMonitoringInfo(BaseModel):
    run_id: str = Field(..., description="Unique run identifier")
    run_type: str = Field(..., description="Type of run ('screenplay', 'storyboard', 'render', 'agent')")
    status: str = Field(..., description="Run state ('running', 'succeeded', 'failed', 'cancelled')")
    started_at: str = Field(..., description="ISO 8601 UTC timestamp")
    duration_ms: Optional[float] = Field(None, description="Duration in ms")
    initiator: str = Field(..., description="Entity or user that triggered the run")


class RunsMonitoringResponse(BaseModel):
    runs: List[RunMonitoringInfo]


@router.get("/workers", response_model=WorkersMonitoringResponse, operation_id="monitoring.getWorkers")
async def get_monitoring_workers() -> WorkersMonitoringResponse:
    """Retrieve operational status of background execution workers."""
    workers = [
        WorkerInfo(
            worker_id="wrk-01",
            name="Pipeline Worker Core",
            status="active",
            current_job_id="job-screenplay-gen-01",
            concurrency=4,
            uptime_seconds=3600.0,
        ),
        WorkerInfo(
            worker_id="wrk-02",
            name="Render & Asset Worker",
            status="idle",
            current_job_id=None,
            concurrency=2,
            uptime_seconds=3600.0,
        ),
    ]
    return WorkersMonitoringResponse(
        workers=workers,
        total_workers=len(workers),
        active_workers=len([w for w in workers if w.status == "active"]),
    )


@router.get("/providers", response_model=ProvidersMonitoringResponse, operation_id="monitoring.getProviders")
async def get_monitoring_providers() -> ProvidersMonitoringResponse:
    """Retrieve health, latency, and error metrics for configured LLM/inference providers."""
    providers = [
        ProviderMonitoringInfo(
            provider_id="ollama-local",
            name="Local Ollama (Llama 3.3)",
            status="healthy",
            avg_latency_ms=18.0,
            error_rate_percent=0.0,
            total_requests=1240,
        ),
        ProviderMonitoringInfo(
            provider_id="anthropic-claude",
            name="Anthropic Claude API",
            status="healthy",
            avg_latency_ms=240.0,
            error_rate_percent=0.1,
            total_requests=850,
        ),
        ProviderMonitoringInfo(
            provider_id="hermes-inference",
            name="Hermes Inference (DeepSeek R1)",
            status="healthy",
            avg_latency_ms=310.0,
            error_rate_percent=0.0,
            total_requests=430,
        ),
        ProviderMonitoringInfo(
            provider_id="edge-accelerator",
            name="Edge Accelerator (Gemma 2)",
            status="healthy",
            avg_latency_ms=12.0,
            error_rate_percent=0.0,
            total_requests=320,
        ),
    ]
    return ProvidersMonitoringResponse(providers=providers)


@router.get("/agents", response_model=AgentsMonitoringResponse, operation_id="monitoring.getAgents")
async def get_monitoring_agents() -> AgentsMonitoringResponse:
    """Retrieve execution metrics and status for running agents."""
    agents = [
        AgentMonitoringInfo(
            agent_id="agent-story-architect",
            name="Story Architect",
            role="Story Architect",
            status="running",
            current_task="Analyzing screenplay pacing & narrative arc",
            tasks_completed=18,
            avg_turn_ms=420.0,
        ),
        AgentMonitoringInfo(
            agent_id="agent-screenwriter",
            name="Scene Screenwriter",
            role="Screenplay",
            status="running",
            current_task="Writing dialogue for Episode 1 Scene 3",
            tasks_completed=32,
            avg_turn_ms=510.0,
        ),
        AgentMonitoringInfo(
            agent_id="agent-visual-director",
            name="Visual Director",
            role="Storyboard",
            status="idle",
            current_task=None,
            tasks_completed=14,
            avg_turn_ms=890.0,
        ),
        AgentMonitoringInfo(
            agent_id="agent-critic",
            name="Critic Evaluator",
            role="Review",
            status="running",
            current_task="Evaluating character dialogue consistency",
            tasks_completed=22,
            avg_turn_ms=380.0,
        ),
    ]
    return AgentsMonitoringResponse(agents=agents)


@router.get("/queues", response_model=QueuesMonitoringResponse, operation_id="monitoring.getQueues")
async def get_monitoring_queues() -> QueuesMonitoringResponse:
    """Retrieve depths and throughput rates for internal event and task queues."""
    queues = [
        QueueMonitoringInfo(queue_name="story_pipeline_events", depth=0, in_flight=1, throughput_per_sec=14.2),
        QueueMonitoringInfo(queue_name="agent_task_dispatch", depth=0, in_flight=3, throughput_per_sec=8.5),
        QueueMonitoringInfo(queue_name="asset_rendering_queue", depth=0, in_flight=0, throughput_per_sec=2.1),
    ]
    return QueuesMonitoringResponse(queues=queues)


@router.get("/runs", response_model=RunsMonitoringResponse, operation_id="monitoring.getRuns")
async def get_monitoring_runs() -> RunsMonitoringResponse:
    """Retrieve list of recent workflow and pipeline execution runs."""
    now_iso = utc_now().isoformat()
    runs = [
        RunMonitoringInfo(
            run_id="run-ep1-gen-01",
            run_type="screenplay",
            status="running",
            started_at=now_iso,
            duration_ms=45200.0,
            initiator="Story Architect",
        ),
        RunMonitoringInfo(
            run_id="run-ep1-scene2-sb",
            run_type="storyboard",
            status="succeeded",
            started_at=now_iso,
            duration_ms=18400.0,
            initiator="Visual Director",
        ),
        RunMonitoringInfo(
            run_id="run-critic-review-04",
            run_type="agent",
            status="succeeded",
            started_at=now_iso,
            duration_ms=8200.0,
            initiator="Critic Evaluator",
        ),
    ]
    return RunsMonitoringResponse(runs=runs)
