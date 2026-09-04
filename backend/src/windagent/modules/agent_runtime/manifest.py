"""Module manifest for Agent Runtime (Phase 13).

Discovered automatically by ``PackageModuleDiscovery`` — no bootstrap file
needs to import this module by name except for testing.
"""

from __future__ import annotations

from windagent.platform.modules import (
    CommandRegistration,
    JobRegistration,
    ModuleManifest,
    QueryRegistration,
)

from .api.routes import MODULE_ID, MODULE_VERSION, create_agent_runtime_router
from .application.commands import (
    CompleteTask,
    CreateCheckpoint,
    CreateRun,
    CreateSession,
    CreateTask,
    CreateWorkflow,
    DelegateRun,
    FailTask,
    RecordRunBudgetUsage,
    RequestApproval,
    ResolveApproval,
    RetryTask,
    ScheduleWorkflow,
    TransitionDelegation,
    TransitionRun,
    TransitionSession,
    TransitionStep,
    TransitionTask,
    TransitionWorkflow,
)
from .application.handlers import (
    AgentRunExecuteJobHandler,
    AgentTaskExecuteJobHandler,
    AgentWorkflowStepExecuteJobHandler,
    CompleteTaskHandler,
    CreateCheckpointHandler,
    CreateRunHandler,
    CreateSessionHandler,
    CreateTaskHandler,
    CreateWorkflowHandler,
    DelegateRunHandler,
    FailTaskHandler,
    GetApprovalHandler,
    GetCheckpointHandler,
    GetDelegationHandler,
    GetRunHandler,
    GetSessionHandler,
    GetStepHandler,
    GetTaskHandler,
    GetWorkflowHandler,
    ListApprovalsHandler,
    ListCheckpointsHandler,
    ListDelegationsHandler,
    ListRunsHandler,
    ListSessionsHandler,
    ListStepsHandler,
    ListTasksHandler,
    ListWorkflowsHandler,
    RecordRunBudgetUsageHandler,
    RequestApprovalHandler,
    ResolveApprovalHandler,
    RetryTaskHandler,
    ScheduleWorkflowHandler,
    TransitionDelegationHandler,
    TransitionRunHandler,
    TransitionSessionHandler,
    TransitionStepHandler,
    TransitionTaskHandler,
    TransitionWorkflowHandler,
)
from .application.queries import (
    GetApproval,
    GetCheckpoint,
    GetDelegation,
    GetRun,
    GetSession,
    GetStep,
    GetTask,
    GetWorkflow,
    ListApprovals,
    ListCheckpoints,
    ListDelegations,
    ListRuns,
    ListSessions,
    ListSteps,
    ListTasks,
    ListWorkflows,
)
from .application.runtime import AgentRuntimeServices

AGENT_RUNTIME_JOB_TYPES = (
    "agent_runtime.run.execute",
    "agent_runtime.task.execute",
    "agent_runtime.workflow.step.execute",
)


def build_agent_runtime_manifest(services: AgentRuntimeServices | None = None) -> ModuleManifest:
    return ModuleManifest(
        id=MODULE_ID,
        version=MODULE_VERSION,
        commands=(
            CommandRegistration(CreateSession, CreateSessionHandler(services)),
            CommandRegistration(TransitionSession, TransitionSessionHandler(services)),
            CommandRegistration(CreateRun, CreateRunHandler(services)),
            CommandRegistration(TransitionRun, TransitionRunHandler(services)),
            CommandRegistration(RecordRunBudgetUsage, RecordRunBudgetUsageHandler(services)),
            CommandRegistration(CreateTask, CreateTaskHandler(services)),
            CommandRegistration(TransitionTask, TransitionTaskHandler(services)),
            CommandRegistration(CompleteTask, CompleteTaskHandler(services)),
            CommandRegistration(FailTask, FailTaskHandler(services)),
            CommandRegistration(RetryTask, RetryTaskHandler(services)),
            CommandRegistration(CreateWorkflow, CreateWorkflowHandler(services)),
            CommandRegistration(TransitionWorkflow, TransitionWorkflowHandler(services)),
            CommandRegistration(ScheduleWorkflow, ScheduleWorkflowHandler(services)),
            CommandRegistration(TransitionStep, TransitionStepHandler(services)),
            CommandRegistration(CreateCheckpoint, CreateCheckpointHandler(services)),
            CommandRegistration(RequestApproval, RequestApprovalHandler(services)),
            CommandRegistration(ResolveApproval, ResolveApprovalHandler(services)),
            CommandRegistration(DelegateRun, DelegateRunHandler(services)),
            CommandRegistration(TransitionDelegation, TransitionDelegationHandler(services)),
        ),
        queries=(
            QueryRegistration(GetSession, GetSessionHandler(services)),
            QueryRegistration(ListSessions, ListSessionsHandler(services)),
            QueryRegistration(GetRun, GetRunHandler(services)),
            QueryRegistration(ListRuns, ListRunsHandler(services)),
            QueryRegistration(GetTask, GetTaskHandler(services)),
            QueryRegistration(ListTasks, ListTasksHandler(services)),
            QueryRegistration(GetWorkflow, GetWorkflowHandler(services)),
            QueryRegistration(ListWorkflows, ListWorkflowsHandler(services)),
            QueryRegistration(GetStep, GetStepHandler(services)),
            QueryRegistration(ListSteps, ListStepsHandler(services)),
            QueryRegistration(GetCheckpoint, GetCheckpointHandler(services)),
            QueryRegistration(ListCheckpoints, ListCheckpointsHandler(services)),
            QueryRegistration(GetApproval, GetApprovalHandler(services)),
            QueryRegistration(ListApprovals, ListApprovalsHandler(services)),
            QueryRegistration(GetDelegation, GetDelegationHandler(services)),
            QueryRegistration(ListDelegations, ListDelegationsHandler(services)),
        ),
        jobs=(
            JobRegistration("agent_runtime.run.execute", AgentRunExecuteJobHandler(services)),
            JobRegistration("agent_runtime.task.execute", AgentTaskExecuteJobHandler(services)),
            JobRegistration("agent_runtime.workflow.step.execute", AgentWorkflowStepExecuteJobHandler(services)),
        ),
        routers=(create_agent_runtime_router(),),
        capabilities=(
            "agent_runtime",
            "sessions",
            "runs",
            "planning",
            "tasks",
            "workflows",
            "scheduler",
            "checkpoints",
            "retry",
            "recovery",
            "approvals",
            "delegation",
            "budget",
        ),
    )


manifest = build_agent_runtime_manifest()
