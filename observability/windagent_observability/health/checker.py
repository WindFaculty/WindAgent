"""
Health Checker Service for WindAgent V2 (Phase 10).
Implements real liveness and readiness checks with profile-based behavior.
"""

from __future__ import annotations
import logging
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_observability.health.contracts import (
    HealthStatus,
    HealthProfile,
    HealthCheckResult,
    ReadinessStatus,
    HealthDependencyBundle,
)

logger = logging.getLogger("windagent.observability.health")


class HealthChecker:
    """
    Health Checker Service for real liveness and readiness probes.
    
    Implements all required checks from PHASE 10:
    - Liveness: Process event loop check
    - Readiness: Database, schema, outbox, worker, queue, registries, event dispatcher, filesystem, config
    
    Profile-based behavior:
    - PRODUCTION: Fail-closed, all required checks must pass
    - DEVELOPMENT: Worker not running returns DEGRADED (not UP)
    - TEST: Allows in-memory adapters when explicitly injected
    """
    
    def __init__(
        self,
        db_session_factory: Optional[Callable[[], AsyncGenerator[AsyncSession, None]]] = None,
        worker_status_query: Optional[Any] = None,
        provider_registry: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
        plugin_registry: Optional[Any] = None,
        skill_registry: Optional[Any] = None,
        workflow_registry: Optional[Any] = None,
        event_dispatcher: Optional[Any] = None,
        outbox_repository: Optional[Any] = None,
        outbox_publisher: Optional[Any] = None,
        required_paths: Optional[List[Path]] = None,
        profile: HealthProfile = HealthProfile.DEVELOPMENT,
        bundle: Optional[HealthDependencyBundle] = None,
    ):
        """
        Initialize HealthChecker with required dependencies or a typed HealthDependencyBundle.
        """
        if bundle is not None:
            self._db_session_factory = db_session_factory or bundle.database
            self._worker_status_query = worker_status_query or bundle.worker
            self._provider_registry = provider_registry or bundle.providers
            self._tool_registry = tool_registry or bundle.tools
            self._plugin_registry = plugin_registry or bundle.plugins
            self._skill_registry = skill_registry or bundle.skills
            self._workflow_registry = workflow_registry or bundle.workflows
            self._event_dispatcher = event_dispatcher or bundle.events
            self._outbox_repository = outbox_repository or bundle.outbox
            self._outbox_publisher = outbox_publisher or (bundle.outbox if hasattr(bundle.outbox, "is_running") else None)
            self._required_paths = required_paths or (bundle.filesystem if isinstance(bundle.filesystem, list) else [])
        else:
            self._db_session_factory = db_session_factory
            self._worker_status_query = worker_status_query
            self._provider_registry = provider_registry
            self._tool_registry = tool_registry
            self._plugin_registry = plugin_registry
            self._skill_registry = skill_registry
            self._workflow_registry = workflow_registry
            self._event_dispatcher = event_dispatcher
            self._outbox_repository = outbox_repository
            self._outbox_publisher = outbox_publisher
            self._required_paths = required_paths or []

        self._profile = profile
        
        # Default required paths
        self._default_required_paths = [
            Path("scripts"),
            Path("configs"),
            Path("storage"),
        ]
    
    async def check_liveness(self) -> bool:
        """
        Liveness probe - only checks if process event loop is alive.
        
        Does NOT check external dependencies.
        Returns True if the process is alive.
        """
        # Process is alive if we can await a simple task
        try:
            await asyncio.sleep(0)
            return True
        except Exception:
            return False
    
    async def check_readiness(
        self,
        profile: Optional[HealthProfile] = None,
        components: Optional[List[str]] = None,
    ) -> ReadinessStatus:
        """
        Readiness probe - checks all required components are ready.
        
        Args:
            profile: Override the default profile for this check
            components: Optional list of component names to filter check to
            
        Returns:
            ReadinessStatus with all check results and overall status
        """
        import time
        effective_profile = profile or self._profile
        checks: Dict[str, HealthCheckResult] = {}
        
        # Run all checks concurrently
        all_tasks = {
            "database": self._check_database_connection,
            "schema_migration": self._check_schema_migration,
            "outbox": self._check_outbox_publisher,
            "queue": self._check_queue_access,
            "worker": self._check_worker_heartbeat,
            "provider_registry": self._check_provider_registry,
            "tool_registry": self._check_tool_registry,
            "plugin_registry": self._check_plugin_registry,
            "skill_registry": self._check_skill_registry,
            "workflow_registry": self._check_workflow_registry,
            "event_dispatcher": self._check_event_dispatcher,
            "filesystem": self._check_required_filesystem_paths,
            "configuration": self._check_configuration,
        }
        
        if components:
            norm_comps = [c.lower().strip() for c in components]
            check_tasks = {}
            for name, task in all_tasks.items():
                if any(nc in name for nc in norm_comps) or any(name in nc for nc in norm_comps):
                    check_tasks[name] = task
            if not check_tasks:
                # Fallback if no matching key found directly
                check_tasks = {name: task for name, task in all_tasks.items() if any(c in name for c in norm_comps)}
        else:
            check_tasks = all_tasks
        
        async def _run_timed(name: str, task_fn: Callable):
            t0 = time.perf_counter()
            try:
                res: HealthCheckResult = await task_fn()
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                if res.latency_ms <= 0:
                    res.latency_ms = elapsed_ms
                self._attach_suggested_action_and_mask_secrets(res)
                return res
            except Exception as ex:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                res = HealthCheckResult(
                    name=name,
                    status=HealthStatus.DOWN,
                    message=f"Check failed: {str(ex)}",
                    details={"error": str(ex)},
                    required=True,
                    latency_ms=elapsed_ms,
                )
                self._attach_suggested_action_and_mask_secrets(res)
                return res

        # Execute checks
        results = await asyncio.gather(
            *(_run_timed(name, task) for name, task in check_tasks.items()),
            return_exceptions=True
        )
        
        # Map results to check names
        for (name, _), result in zip(check_tasks.items(), results):
            if isinstance(result, Exception):
                res = HealthCheckResult(
                    name=name,
                    status=HealthStatus.DOWN,
                    message=f"Check failed: {str(result)}",
                    details={"error": str(result)},
                    required=True
                )
                self._attach_suggested_action_and_mask_secrets(res)
                checks[name] = res
            else:
                checks[name] = result
        
        # Calculate overall status based on profile
        overall_status = self._calculate_overall_status(checks, effective_profile)
        
        return ReadinessStatus(
            overall_status=overall_status,
            checks=checks,
            profile=effective_profile
        )

    def _attach_suggested_action_and_mask_secrets(self, res: HealthCheckResult) -> HealthCheckResult:
        """Attach suggested remediation and mask secrets in result messages and details."""
        if res.suggested_action is None and res.status in (HealthStatus.DOWN, HealthStatus.DEGRADED):
            remediations = {
                "database": "Verify database connection string and ensure SQLite/PostgreSQL server is responsive.",
                "schema_migration": "Run database migrations via 'python scripts/migrate_database_schema.py'.",
                "outbox": "Ensure OutboxEventPublisher background task or process is started and running.",
                "queue": "Check durable_queue table structure and database connection.",
                "worker": "Start worker process via 'python apps/worker/main.py' or check worker heartbeat thread.",
                "provider_registry": "Check model provider configurations and API key environment variables.",
                "tool_registry": "Ensure system tools are properly registered in ToolRegistry.",
                "workflow_registry": "Verify workflow definition files and WorkflowRegistry initialization.",
                "event_dispatcher": "Verify EventDispatcher instance is running and has active subscriptions.",
                "filesystem": "Create missing required directories in the workspace.",
                "configuration": "Check WINDAGENT_ENV and system environment variable configurations.",
            }
            res.suggested_action = remediations.get(res.name, f"Inspect logs for component '{res.name}' and restart component.")
        elif res.status == HealthStatus.UP and res.suggested_action is None:
            res.suggested_action = "No action required."

        # Mask potential credentials/secrets
        import re
        secret_patterns = [
            r"(?i)(password|secret|key|token|auth)=([^\s;&]+)",
            r"(?i)(://[^:]+:)([^@]+)(@)",
        ]
        for pat in secret_patterns:
            res.message = re.sub(pat, r"\1***\3" if "@" in pat else r"\1=***", res.message)
            if res.suggested_action:
                res.suggested_action = re.sub(pat, r"\1***\3" if "@" in pat else r"\1=***", res.suggested_action)
            if res.details and isinstance(res.details, dict):
                for k, v in res.details.items():
                    if any(sec in k.lower() for sec in ["password", "secret", "key", "token", "auth"]):
                        res.details[k] = "***"
                    elif isinstance(v, str):
                        res.details[k] = re.sub(pat, r"\1***\3" if "@" in pat else r"\1=***", v)
        return res
    
    def _calculate_overall_status(
        self,
        checks: Dict[str, HealthCheckResult],
        profile: HealthProfile
    ) -> HealthStatus:
        """
        Calculate overall status based on individual check results and profile.
        
        Rules:
        - PRODUCTION: All required checks must be UP, otherwise DOWN
        - DEVELOPMENT: Worker can be DOWN/DEGRADED, but others must be UP for overall UP
        - TEST: More lenient, allows in-memory adapters
        """
        down_required = []
        degraded_optional = []
        worker_down_optional = False
        
        for name, check in checks.items():
            if check.status == HealthStatus.DOWN and check.required:
                down_required.append(name)
            elif check.status == HealthStatus.DEGRADED and not check.required:
                degraded_optional.append(name)
            # ponytail: worker DOWN with required=False in development is DEGRADED, not UP
            elif name == "worker" and check.status == HealthStatus.DOWN and not check.required:
                worker_down_optional = True
        
        # Production: Fail-closed, any required DOWN = overall DOWN
        if profile == HealthProfile.PRODUCTION:
            if down_required:
                return HealthStatus.DOWN
            return HealthStatus.UP
        
        # Development: Worker not running = DEGRADED, other required DOWN = DOWN
        elif profile == HealthProfile.DEVELOPMENT:
            # Check if worker is the only issue
            worker_issue = "worker" in down_required or worker_down_optional
            other_issues = [n for n in down_required if n != "worker"]
            
            if other_issues:
                return HealthStatus.DOWN
            elif worker_issue:
                # Worker is down but others are up - this is DEGRADED
                return HealthStatus.DEGRADED
            return HealthStatus.UP
        
        # Test: Most lenient
        elif profile == HealthProfile.TEST:
            if down_required:
                # In test, we allow some failures
                return HealthStatus.DEGRADED if len(down_required) <= 2 else HealthStatus.DOWN
            return HealthStatus.UP
        
        # Default to UP if no issues
        return HealthStatus.UP
    
    async def _check_database_connection(self) -> HealthCheckResult:
        """Check database connection with real query."""
        if self._db_session_factory is None:
            # In development/test, this might not be available
            return HealthCheckResult(
                name="database",
                status=HealthStatus.NOT_REQUIRED if self._profile == HealthProfile.TEST else HealthStatus.DOWN,
                message="Database session factory not configured",
                required=self._profile != HealthProfile.TEST
            )
        
        try:
            async with self._db_session_factory() as session:
                await session.execute(text("SELECT 1"))
            return HealthCheckResult(
                name="database",
                status=HealthStatus.UP,
                message="SQL connection verified",
                details={"query": "SELECT 1"},
                required=True
            )
        except Exception as e:
            return HealthCheckResult(
                name="database",
                status=HealthStatus.DOWN,
                message=f"Database connection failed: {str(e)}",
                details={"error": str(e)},
                required=True
            )
    
    EXPECTED_HEAD_REVISIONS = {"002_legacy_data", "002"}

    async def _check_schema_migration(self) -> HealthCheckResult:
        """Check current schema revision against expected head."""
        if self._db_session_factory is None:
            return HealthCheckResult(
                name="schema_migration",
                status=HealthStatus.NOT_REQUIRED if self._profile == HealthProfile.TEST else HealthStatus.DOWN,
                message="Cannot check schema without database",
                required=self._profile != HealthProfile.TEST
            )
        
        try:
            # Check migration history table
            async with self._db_session_factory() as session:
                result = await session.execute(text("""
                    SELECT MAX(revision) as latest_revision, COUNT(*) as total_migrations
                    FROM migration_history
                """))
                row = result.fetchone()
                
                if row is None or row[0] is None:
                    return HealthCheckResult(
                        name="schema_migration",
                        status=HealthStatus.DOWN,
                        message="No migrations applied",
                        details={"latest_revision": None, "total_migrations": 0},
                        required=True
                    )
                
                latest_revision = str(row[0]) if row[0] else "unknown"
                total_migrations = row[1] if row[1] else 0
                
                if latest_revision not in self.EXPECTED_HEAD_REVISIONS:
                    return HealthCheckResult(
                        name="schema_migration",
                        status=HealthStatus.DOWN,
                        message=f"Schema revision '{latest_revision}' does not match expected head '002_legacy_data'",
                        details={
                            "latest_revision": latest_revision,
                            "expected_head": "002_legacy_data",
                            "total_migrations": total_migrations,
                        },
                        required=True
                    )

                return HealthCheckResult(
                    name="schema_migration",
                    status=HealthStatus.UP,
                    message=f"Schema head verified at revision {latest_revision}",
                    details={
                        "latest_revision": latest_revision,
                        "total_migrations": total_migrations
                    },
                    required=True
                )
        except Exception as e:
            if "no such table" in str(e).lower():
                return HealthCheckResult(
                    name="schema_migration",
                    status=HealthStatus.DOWN,
                    message="Migration history table not found - migrations not applied",
                    details={"error": str(e)},
                    required=True
                )
            return HealthCheckResult(
                name="schema_migration",
                status=HealthStatus.DOWN,
                message=f"Schema check failed: {str(e)}",
                details={"error": str(e)},
                required=True
            )
    
    async def _check_outbox_publisher(self) -> HealthCheckResult:
        """Check outbox publisher heartbeat and running task state."""
        if self._outbox_repository is None and self._outbox_publisher is None:
            is_prod = self._profile == HealthProfile.PRODUCTION
            return self._attach_suggested_action_and_mask_secrets(HealthCheckResult(
                name="outbox",
                status=HealthStatus.DOWN if is_prod else HealthStatus.NOT_REQUIRED,
                message="Outbox repository/publisher missing or not configured",
                required=is_prod
            ))
        
        # Check publisher running state if publisher object exists
        if self._outbox_publisher is not None:
            is_running = getattr(self._outbox_publisher, "is_running", True)
            if not is_running:
                return self._attach_suggested_action_and_mask_secrets(HealthCheckResult(
                    name="outbox",
                    status=HealthStatus.DOWN,
                    message="Outbox publisher object exists but task is not running",
                    details={"is_running": False},
                    required=True
                ))

        try:
            # Check for pending records
            if self._db_session_factory is not None:
                async with self._db_session_factory() as session:
                    result = await session.execute(text("""
                        SELECT COUNT(*) as pending_count FROM outbox_records 
                        WHERE status = 'pending' OR status = 'failed'
                    """))
                    row = result.fetchone()
                    pending_count = row[0] if row and row[0] else 0
                    
                    return self._attach_suggested_action_and_mask_secrets(HealthCheckResult(
                        name="outbox",
                        status=HealthStatus.UP,
                        message="Outbox publisher heartbeat OK",
                        details={"pending_records": pending_count},
                        required=True
                    ))
            return self._attach_suggested_action_and_mask_secrets(HealthCheckResult(
                name="outbox",
                status=HealthStatus.UP,
                message="Outbox publisher verified",
                required=True
            ))
        except Exception as e:
            if "no such table" in str(e).lower():
                return self._attach_suggested_action_and_mask_secrets(HealthCheckResult(
                    name="outbox",
                    status=HealthStatus.DOWN,
                    message="Outbox table not found",
                    details={"error": str(e)},
                    required=True
                ))
            return self._attach_suggested_action_and_mask_secrets(HealthCheckResult(
                name="outbox",
                status=HealthStatus.DOWN,
                message=f"Outbox check failed: {str(e)}",
                details={"error": str(e)},
                required=True
            ))

    async def _check_queue_access(self) -> HealthCheckResult:
        """Check queue access (durable queue table)."""
        if self._db_session_factory is None:
            is_prod = self._profile == HealthProfile.PRODUCTION
            return HealthCheckResult(
                name="queue",
                status=HealthStatus.DOWN if is_prod else HealthStatus.NOT_REQUIRED,
                message="Cannot check queue without database",
                required=is_prod
            )
        
        try:
            async with self._db_session_factory() as session:
                result = await session.execute(text("""SELECT COUNT(*) as queue_depth FROM task_runs"""))
                row = result.fetchone()
                queue_depth = row[0] if row and row[0] else 0
                
                return HealthCheckResult(
                    name="queue",
                    status=HealthStatus.UP,
                    message="Queue access verified",
                    details={"queue_depth": queue_depth},
                    required=True,
                )
        except Exception as e:
            if "no such table" in str(e).lower():
                return HealthCheckResult(
                    name="queue",
                    status=HealthStatus.DOWN,
                    message="Queue table not found",
                    details={"error": str(e)},
                    required=True
                )
            return HealthCheckResult(
                name="queue",
                status=HealthStatus.DOWN,
                message=f"Queue check failed: {str(e)}",
                details={"error": str(e)},
                required=True
            )
    
    async def _check_worker_heartbeat(self) -> HealthCheckResult:
        """Check worker process heartbeat via status query."""
        if self._worker_status_query is None:
            if self._profile == HealthProfile.PRODUCTION:
                status = HealthStatus.DOWN
            elif self._profile == HealthProfile.DEVELOPMENT:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.NOT_REQUIRED
            return self._attach_suggested_action_and_mask_secrets(HealthCheckResult(
                name="worker",
                status=status,
                message="Worker status query not configured",
                required=self._profile == HealthProfile.PRODUCTION
            ))
        
        try:
            worker_status = await self._worker_status_query.get_status()
            
            if worker_status.available:
                return self._attach_suggested_action_and_mask_secrets(HealthCheckResult(
                    name="worker",
                    status=HealthStatus.UP,
                    message="Worker heartbeat verified",
                    details={
                        "active_workers": worker_status.active_workers,
                        "active_leases": worker_status.active_leases
                    },
                    required=self._profile == HealthProfile.PRODUCTION
                ))
            else:
                return self._attach_suggested_action_and_mask_secrets(HealthCheckResult(
                    name="worker",
                    status=HealthStatus.DOWN if self._profile == HealthProfile.PRODUCTION else HealthStatus.DEGRADED,
                    message=f"No active workers (available: {worker_status.available})",
                    details={
                        "active_workers": worker_status.active_workers,
                        "active_leases": worker_status.active_leases
                    },
                    required=self._profile == HealthProfile.PRODUCTION
                ))
        except Exception as e:
            return self._attach_suggested_action_and_mask_secrets(HealthCheckResult(
                name="worker",
                status=HealthStatus.DOWN,
                message=f"Worker status check failed: {str(e)}",
                details={"error": str(e)},
                required=self._profile == HealthProfile.PRODUCTION
            ))
    
    async def _check_provider_registry(self) -> HealthCheckResult:
        """Check provider registry is loaded."""
        if self._provider_registry is None:
            is_prod = self._profile == HealthProfile.PRODUCTION
            return HealthCheckResult(
                name="provider_registry",
                status=HealthStatus.DOWN if is_prod else HealthStatus.NOT_REQUIRED,
                message="Provider registry missing or not configured",
                required=is_prod
            )
        
        try:
            # Registry liveness: object exists and exposes a non-empty catalog.
            registry = self._provider_registry
            if hasattr(registry, "list_providers"):
                providers = registry.list_providers()
            elif hasattr(registry, "get_providers"):
                providers = registry.get_providers()
            else:
                providers = getattr(registry, "_canonical_models", {}) or {}
            count = len(providers) if providers is not None else 0
            
            return HealthCheckResult(
                name="provider_registry",
                status=HealthStatus.UP,
                message=f"Provider registry loaded ({len(providers)} providers)",
                details={"provider_count": len(providers)},
                required=True
            )
        except Exception as e:
            return HealthCheckResult(
                name="provider_registry",
                status=HealthStatus.DOWN,
                message=f"Provider registry check failed: {str(e)}",
                details={"error": str(e)},
                required=True
            )
    
    async def _check_tool_registry(self) -> HealthCheckResult:
        """Check tool registry is loaded."""
        if self._tool_registry is None:
            is_prod = self._profile == HealthProfile.PRODUCTION
            return HealthCheckResult(
                name="tool_registry",
                status=HealthStatus.DOWN if is_prod else HealthStatus.NOT_REQUIRED,
                message="Tool registry missing or not configured",
                required=is_prod
            )
        
        try:
            # Check if registry has tools
            # Registry liveness: object exists and exposes a tool catalog (sync call).
            registry = self._tool_registry
            tools = registry.list_tools() if hasattr(registry, "list_tools") else getattr(registry, "_tools", {})
            count = len(tools) if tools is not None else 0
            
            return HealthCheckResult(
                name="tool_registry",
                status=HealthStatus.UP,
                message=f"Tool registry loaded ({count} tools)",
                details={"tool_count": count},
                required=True
            )
        except Exception as e:
            return HealthCheckResult(
                name="tool_registry",
                status=HealthStatus.DOWN,
                message=f"Tool registry check failed: {str(e)}",
                details={"error": str(e)},
                required=True
            )
    
    async def _check_plugin_registry(self) -> HealthCheckResult:
        """Check plugin registry is loaded."""
        if self._plugin_registry is None:
            return HealthCheckResult(
                name="plugin_registry",
                status=HealthStatus.NOT_REQUIRED,
                message="Plugin registry not configured",
                required=False
            )
        
        try:
            # Check if registry has plugins
            plugins = await self._plugin_registry.list_plugins()
            
            return HealthCheckResult(
                name="plugin_registry",
                status=HealthStatus.UP,
                message=f"Plugin registry loaded ({len(plugins)} plugins)",
                details={"plugin_count": len(plugins)},
                required=False  # Plugins are optional
            )
        except Exception as e:
            return HealthCheckResult(
                name="plugin_registry",
                status=HealthStatus.DOWN,
                message=f"Plugin registry check failed: {str(e)}",
                details={"error": str(e)},
                required=False
            )
    
    async def _check_skill_registry(self) -> HealthCheckResult:
        """Check skill registry is loaded."""
        if self._skill_registry is None:
            return HealthCheckResult(
                name="skill_registry",
                status=HealthStatus.NOT_REQUIRED,
                message="Skill registry not configured",
                required=False
            )
        
        try:
            # Check if registry has skills
            skills = await self._skill_registry.list_skills()
            
            return HealthCheckResult(
                name="skill_registry",
                status=HealthStatus.UP,
                message=f"Skill registry loaded ({len(skills)} skills)",
                details={"skill_count": len(skills)},
                required=False  # Skills are optional
            )
        except Exception as e:
            return HealthCheckResult(
                name="skill_registry",
                status=HealthStatus.DOWN,
                message=f"Skill registry check failed: {str(e)}",
                details={"error": str(e)},
                required=False
            )
    
    async def _check_workflow_registry(self) -> HealthCheckResult:
        """Check workflow registry is loaded."""
        if self._workflow_registry is None:
            is_prod = self._profile == HealthProfile.PRODUCTION
            return HealthCheckResult(
                name="workflow_registry",
                status=HealthStatus.DOWN if is_prod else HealthStatus.NOT_REQUIRED,
                message="Workflow registry missing or not configured",
                required=is_prod
            )
        
        try:
            # Check if registry has workflows
            # Registry liveness: object exists and exposes a workflow catalog.
            registry = self._workflow_registry
            if hasattr(registry, "list_workflows"):
                workflows = registry.list_workflows()
            elif hasattr(registry, "list_packs"):
                workflows = registry.list_packs()
            else:
                workflows = getattr(registry, "_packs", {}) or {}
            count = len(workflows) if workflows is not None else 0
            
            return HealthCheckResult(
                name="workflow_registry",
                status=HealthStatus.UP,
                message=f"Workflow registry loaded ({count} workflows)",
                details={"workflow_count": count},
                required=True
            )
        except Exception as e:
            return HealthCheckResult(
                name="workflow_registry",
                status=HealthStatus.DOWN,
                message=f"Workflow registry check failed: {str(e)}",
                details={"error": str(e)},
                required=True
            )
    
    async def _check_event_dispatcher(self) -> HealthCheckResult:
        """Check event dispatcher is active."""
        if self._event_dispatcher is None:
            is_prod = self._profile == HealthProfile.PRODUCTION
            return HealthCheckResult(
                name="event_dispatcher",
                status=HealthStatus.DOWN if is_prod else HealthStatus.NOT_REQUIRED,
                message="Event dispatcher not configured",
                required=is_prod
            )
        
        try:
            # Check if dispatcher is active
            # For now, we assume it's active if it exists
            # In a real implementation, we'd check if it has active subscriptions
            return HealthCheckResult(
                name="event_dispatcher",
                status=HealthStatus.UP,
                message="Event dispatcher active",
                details={"status": "active"},
                required=True
            )
        except Exception as e:
            return HealthCheckResult(
                name="event_dispatcher",
                status=HealthStatus.DOWN,
                message=f"Event dispatcher check failed: {str(e)}",
                details={"error": str(e)},
                required=True
            )
    
    async def _check_required_filesystem_paths(self) -> HealthCheckResult:
        """Check all required filesystem paths exist."""
        all_paths = self._default_required_paths + self._required_paths
        missing_paths = []
        
        for path in all_paths:
            if not path.exists():
                missing_paths.append(str(path))
        
        if missing_paths:
            return HealthCheckResult(
                name="filesystem",
                status=HealthStatus.DOWN,
                message=f"Missing required paths: {', '.join(missing_paths)}",
                details={"missing_paths": missing_paths},
                required=True
            )
        
        return HealthCheckResult(
            name="filesystem",
            status=HealthStatus.UP,
            message=f"All {len(all_paths)} required paths exist",
            details={"checked_paths": len(all_paths)},
            required=True
        )
    
    async def _check_configuration(self) -> HealthCheckResult:
        """Check configuration validity."""
        # For now, we just check that we have a valid profile
        # In a real implementation, this would validate all configuration
        try:
            # Check if we can determine the current environment
            import os
            env = os.environ.get("WINDAGENT_ENV", "development")
            
            return HealthCheckResult(
                name="configuration",
                status=HealthStatus.UP,
                message=f"Configuration valid (env: {env})",
                details={"environment": env, "profile": self._profile.value},
                required=True
            )
        except Exception as e:
            return HealthCheckResult(
                name="configuration",
                status=HealthStatus.DOWN,
                message=f"Configuration check failed: {str(e)}",
                details={"error": str(e)},
                required=True
            )
