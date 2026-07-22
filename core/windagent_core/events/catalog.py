"""
Standard Event Catalog for WindAgent Architecture V2.
Declares domain event names categorized across 13 bounded namespaces.
"""

class EventCatalog:
    # Task Namespace
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"

    # Session Namespace
    SESSION_CREATED = "session.created"
    SESSION_STARTED = "session.started"
    SESSION_FINISHED = "session.finished"
    SESSION_PAUSED = "session.paused"
    SESSION_RESUMED = "session.resumed"
    SESSION_STOPPED = "session.stopped"
    SESSION_MESSAGE_RECEIVED = "session.message_received"
    SESSION_ASSISTANT_STARTED = "session.assistant_started"
    SESSION_ASSISTANT_DELTA = "session.assistant_delta"
    SESSION_ASSISTANT_COMPLETED = "session.assistant_completed"

    # Planning Namespace
    PLANNING_STARTED = "planning.started"
    PLANNING_FINISHED = "planning.finished"
    PLANNING_REPLAN = "planning.replan"
    PLANNING_CLARIFICATION_REQUEST = "planning.clarification_request"

    # Workflow Namespace
    WORKFLOW_CREATED = "workflow.created"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_UPDATED = "workflow.updated"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_CANCELLED = "workflow.cancelled"

    # Step Namespace
    STEP_STARTED = "step.started"
    STEP_COMPLETED = "step.completed"
    STEP_FAILED = "step.failed"
    STEP_CANCELLED = "step.cancelled"

    # Tool Namespace
    TOOL_PROPOSED = "tool.proposed"
    TOOL_STARTED = "tool.started"
    TOOL_PROGRESS = "tool.progress"
    TOOL_FINISHED = "tool.finished"
    TOOL_ERROR = "tool.error"
    TOOL_AGENT_S3_ACTION_PROPOSED = "tool.agent_s3_action_proposed"

    # Browser Namespace
    BROWSER_SESSION_STARTED = "browser.session_started"
    BROWSER_ACTION_STARTED = "browser.action_started"
    BROWSER_ACTION_COMPLETED = "browser.action_completed"
    BROWSER_NAV_STARTED = "browser.nav_started"
    BROWSER_NAV_COMPLETED = "browser.nav_completed"
    BROWSER_SCREENSHOT_UPDATED = "browser.screenshot_updated"
    BROWSER_CONSOLE = "browser.console"
    BROWSER_ERROR = "browser.error"

    # Model Namespace
    MODEL_REQUEST_STARTED = "model.request_started"
    MODEL_RESPONSE_DELTA = "model.response_delta"
    MODEL_RESPONSE_COMPLETED = "model.response_completed"
    MODEL_REASONING_DELTA = "model.reasoning_delta"

    # Permission Namespace
    PERMISSION_REQUEST = "permission.request"
    PERMISSION_GRANTED = "permission.granted"
    PERMISSION_DENIED = "permission.denied"

    # Verification Namespace
    VERIFICATION_STARTED = "verification.started"
    VERIFICATION_COMPLETED = "verification.completed"
    VERIFICATION_FAILED = "verification.failed"

    # Recovery Namespace
    RECOVERY_STARTED = "recovery.started"
    RECOVERY_COMPLETED = "recovery.completed"

    # Worktree Namespace
    WORKTREE_CREATED = "worktree.created"
    WORKTREE_CHANGED = "worktree.changed"
    WORKTREE_COMMITTED = "worktree.committed"
    WORKTREE_MERGED = "worktree.merged"
    WORKTREE_CONFLICT = "worktree.conflict"
    WORKTREE_REMOVED = "worktree.removed"

    # Provider Namespace
    PROVIDER_STATUS_CHANGED = "provider.status_changed"
    PROVIDER_ERROR = "provider.error"

    # System & Artifact Namespace
    SYSTEM_ERROR = "system.error"
    SYSTEM_HEARTBEAT = "system.heartbeat"
    ARTIFACT_CREATED = "artifact.created"
    TERMINAL_OUTPUT = "system.terminal_output"
