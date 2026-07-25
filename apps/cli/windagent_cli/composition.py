"""
CLI Composition Root for WindAgent V2 (PHASE 7).
Provides per-command service composition - each CLI command composes only what it needs.

CLI Composition Strategy (PHASE 7):
- NO global "god container" for all CLI commands
- Each command composes its own required services
- Commands are independent and isolated

Command-specific compositions:
- doctor: Architecture checker, import boundary checker
- architecture-check: Scaffold checker, import boundary checker
- run: TaskManager, Provider registry, Tool registry
- eval: Evaluation service
- provider test: Provider registry, health checker
- worker status: Worker status query

CLI does NOT compose:
- Full API services
- Full Worker services
- Desktop services
"""

from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger("windagent.cli.composition")


class DoctorCommandComposer:
    """Composes services for 'doctor' command."""
    
    def __init__(self):
        self._checker_scripts = []
    
    def add_checker_script(self, script_path: str) -> None:
        self._checker_scripts.append(script_path)
    
    def run_checks(self) -> dict:
        """Runs all diagnostic checks."""
        import subprocess
        import sys
        from pathlib import Path
        
        results = {
            "status": "ALL_SYSTEMS_OPERATIONAL",
            "checks": {}
        }
        
        # Check architecture imports
        root_dir = Path(__file__).resolve().parent.parent.parent.parent
        checker_script = root_dir / "scripts" / "check_architecture_imports.py"
        if checker_script.exists():
            res = subprocess.run([sys.executable, str(checker_script)], 
                               capture_output=True, text=True)
            results["checks"]["import_boundary_check"] = {
                "passed": res.returncode == 0,
                "details": res.stdout + res.stderr if res.returncode != 0 else "Zero import boundary violations"
            }
        
        # Check scaffold
        scaffold_script = root_dir / "scripts" / "scaffold_architecture_v2.py"
        if scaffold_script.exists():
            res = subprocess.run([sys.executable, str(scaffold_script), "--check"],
                               capture_output=True, text=True)
            results["checks"]["scaffold_structure_check"] = {
                "passed": res.returncode == 0,
                "details": res.stdout + res.stderr if res.returncode != 0 else "Scaffold structure OK"
            }
        
        # Check duplicate models
        dup_script = root_dir / "scripts" / "check_duplicate_canonical_models.py"
        if dup_script.exists():
            res = subprocess.run([sys.executable, str(dup_script)],
                               capture_output=True, text=True)
            results["checks"]["duplicate_model_check"] = {
                "passed": res.returncode == 0,
                "details": res.stdout + res.stderr if res.returncode != 0 else "ZERO duplicate models found"
            }
        
        if any(not chk["passed"] for chk in results["checks"].values()):
            results["status"] = "SYSTEM_HEALTH_WARNING"
        
        return results


class RunCommandComposer:
    """Composes services for 'run' command."""
    
    def __init__(self, db_url: str = "sqlite+aiosqlite:///windagent.db"):
        self.db_url = db_url
        self._task_manager = None
        self._provider_registry = None
        self._tool_registry = None
    
    async def bootstrap(self):
        """Bootstraps only services needed for 'run' command."""
        from windagent_storage.database.connection import DatabaseManager
        from windagent_storage.orm.models import BaseORM
        import windagent_storage.orm.v2_orchestration_models
        from windagent_orchestration.task_manager.service import TaskManager
        from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
        from windagent_tools.registry import ToolRegistry
        
        logger.info("Bootstrapping Run command services...")
        
        # Only compose what 'run' needs
        db = DatabaseManager(self.db_url)
        try:
            await db.create_tables(BaseORM.metadata)
        except Exception as ex:
            logger.warning(f"Database table creation warning: {ex}")
        
        self._task_manager = TaskManager(uow_factory=db.session_factory)
        self._provider_registry = CanonicalModelRegistryService()
        self._tool_registry = ToolRegistry()
        
        logger.info("Run command services bootstrapped.")
        return db
    
    async def shutdown(self, db):
        """Shuts down Run command services."""
        if db:
            await db.close()


class ProviderTestCommandComposer:
    """Composes services for 'provider test' command."""
    
    def __init__(self):
        self._provider_registry = None
    
    async def bootstrap(self):
        """Bootstraps only services needed for provider testing."""
        from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
        
        logger.info("Bootstrapping Provider test command services...")
        self._provider_registry = CanonicalModelRegistryService()
        logger.info("Provider test command services bootstrapped.")
    
    async def shutdown(self):
        if self._provider_registry:
            await self._provider_registry.close()


class WorkerStatusCommandComposer:
    """Composes services for 'worker status' command."""
    
    def __init__(self, db_url: str = "sqlite+aiosqlite:///windagent.db"):
        self.db_url = db_url
        self._worker_status_query = None
    
    async def bootstrap(self):
        """Bootstraps only services needed for worker status query."""
        from windagent_storage.database.connection import DatabaseManager
        from windagent_storage.repositories.worker_status import (
            SqlWorkerHeartbeatRepository,
            SqlWorkerStatusQuery,
        )
        
        logger.info("Bootstrapping Worker status command services...")
        
        db = DatabaseManager(self.db_url)
        try:
            await db.create_tables()
        except Exception as ex:
            logger.warning(f"Database setup warning: {ex}")
        
        self._worker_status_query = SqlWorkerStatusQuery(
            SqlWorkerHeartbeatRepository(db.session_factory)
        )
        logger.info("Worker status command services bootstrapped.")
        return db
    
    async def shutdown(self, db):
        if db:
            await db.close()


class EvalCommandComposer:
    """Composes services for 'eval' command."""
    
    def __init__(self):
        self._eval_service = None
    
    async def bootstrap(self):
        """Bootstraps evaluation services."""
        # Eval command uses external evaluation suite
        # No heavy composition needed
        logger.info("Eval command uses external suite - no composition needed.")
    
    async def shutdown(self):
        pass


class ArchitectureCheckCommandComposer:
    """Composes services for 'architecture-check' command."""
    
    def __init__(self):
        pass
    
    async def bootstrap(self):
        """Bootstraps architecture checking services."""
        # Uses scripts, no service composition needed
        logger.info("Architecture check uses scripts - no composition needed.")
    
    async def shutdown(self):
        pass


# Command registry for per-command composition
COMMAND_COMPOSERS = {
    "doctor": DoctorCommandComposer,
    "run": RunCommandComposer,
    "eval": EvalCommandComposer,
    "provider-test": ProviderTestCommandComposer,
    "worker-status": WorkerStatusCommandComposer,
    "architecture-check": ArchitectureCheckCommandComposer,
}
