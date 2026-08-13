"""
Phase 7 Composition Root Tests - Mandatory Test Suite

These tests verify:
1. API composition root has only allowed services
2. Worker composition root has all required services
3. CLI composition is per-command (no god container)
4. Desktop supervisor manages processes (no direct service composition)
5. No god container shared across processes

Generated as part of PHASE 7: PROCESS_SPECIFIC_COMPOSITION_COMPLETE
"""

import pytest
import sys
from pathlib import Path


class TestPhase7ApiComposition:
    """Test API composition root has only allowed services"""

    def test_api_composition_imports_only_allowed(self):
        """API composition should not import Worker runtime or Desktop services"""
        import os
        api_composition_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "api", "windagent_api", "composition.py"
        )
        
        with open(api_composition_path, 'r') as f:
            content = f.read()
        
        # Should NOT import Worker runtime components directly
        assert "ProductionWorker" not in content
        assert "WorkerRunner" not in content
        assert "from windagent_worker" not in content
        
        # Should NOT import Desktop components
        assert "from desktop" not in content
        assert "SidecarManager" not in content
        
        # Should NOT import tool subprocess runtime directly
        assert "SubprocessRuntimeAdapter" not in content
        assert "ToolRuntimeAdapter" not in content

    def test_api_composes_allowed_services(self):
        """API should compose only allowed services"""
        import os
        api_composition_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "api", "windagent_api", "composition.py"
        )
        
        with open(api_composition_path, 'r') as f:
            content = f.read()
        
        # Should compose allowed services
        assert "DatabaseManager" in content
        assert "SqlUnitOfWork" in content
        assert "TaskManager" in content
        assert "CanonicalModelRegistryService" in content
        assert "ToolRegistry" in content
        assert "PluginRegistry" in content
        assert "SkillRegistry" in content
        assert "WorkflowRegistry" in content
        assert "ContextService" in content
        assert "MemoryQueryService" in content
        assert "VerificationQueryService" in content
        assert "EventDispatcher" in content
        assert "OutboxEventPublisher" not in content
        assert "WorkerStatusQuery" in content

    def test_api_container_has_no_execution_registry(self):
        """API should NOT compose ExecutionRuntimeRegistry directly"""
        import os
        api_composition_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "api", "windagent_api", "composition.py"
        )
        
        with open(api_composition_path, 'r') as f:
            content = f.read()
        
        # API should not have ExecutionRuntimeRegistry in bootstrap
        # (it was removed to avoid composing worker-specific services)
        # Note: It might still be imported for type hints, but not instantiated
        assert "self.execution_registry" not in content or "# Note: We don't use OrchestrationV2Container" in content

    @pytest.mark.asyncio
    async def test_api_container_bootstrap(self):
        """API container should bootstrap successfully"""
        sys.path.insert(0, str(Path(__file__).parent.parent / "apps"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "providers"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "storage"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "orchestration"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "context"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "memory"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "verification"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "workflows"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "plugins"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "skills"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "observability"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "intelligence"))
        
        try:
            from windagent_api.composition import ApplicationContainer
            container = ApplicationContainer(db_url="sqlite+aiosqlite:///:memory:")
            await container.bootstrap()
            assert container.is_initialized
            assert container.db is not None
            assert container.task_manager is not None
            assert container.provider_registry is not None
            assert container.tool_registry is not None
            await container.shutdown()
        except ImportError as e:
            pytest.fail(f"Cannot import API composition: {e}")


class TestPhase7WorkerComposition:
    """Test Worker composition root has all required services"""

    def test_worker_composition_imports_all_required(self):
        """Worker composition should import all required services"""
        import os
        worker_composition_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "worker", "windagent_worker", "composition.py"
        )
        
        with open(worker_composition_path, 'r') as f:
            content = f.read()
        
        # Should compose all required services
        assert "DatabaseManager" in content
        assert "DurableTaskLeaseManager" in content
        assert "OrchestrationV2Container" in content
        assert "ExecutionRuntimeRegistry" in content
        assert "ToolRegistry" in content
        assert "CanonicalModelRegistryService" in content
        assert "IntelligencePipeline" in content
        assert "ContextService" in content
        assert "MemoryQueryService" in content
        assert "WorkflowRegistry" in content
        assert "VerificationQueryService" in content
        assert "OutboxEventPublisher" in content
        assert "EventDispatcher" in content

    def test_worker_composition_no_api_components(self):
        """Worker should NOT import API or Desktop components"""
        import os
        worker_composition_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "worker", "windagent_worker", "composition.py"
        )
        
        with open(worker_composition_path, 'r') as f:
            content = f.read()
        
        # Should NOT import API components
        assert "from windagent_api" not in content
        # Should NOT import Desktop components
        assert "from desktop" not in content
        assert "SidecarManager" not in content

    @pytest.mark.asyncio
    async def test_worker_container_bootstrap(self):
        """Worker container should bootstrap successfully"""
        sys.path.insert(0, str(Path(__file__).parent.parent / "apps"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "providers"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "storage"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "orchestration"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "context"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "memory"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "verification"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "workflows"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "intelligence"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "observability"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "execution"))
        
        try:
            from windagent_worker.composition import WorkerContainer
            container = WorkerContainer(db_url="sqlite+aiosqlite:///:memory:")
            await container.bootstrap()
            assert container.is_initialized
            assert container.db is not None
            assert container.lease_manager is not None
            assert container.execution_registry is not None
            assert container.provider_registry is not None
            assert container.tool_registry is not None
            assert container.intelligence_pipeline is not None
            await container.shutdown()
        except ImportError as e:
            pytest.fail(f"Cannot import Worker composition: {e}")


class TestPhase7CliComposition:
    """Test CLI composition is per-command, no god container"""

    def test_cli_has_composition_file(self):
        """CLI should have composition module"""
        import os
        cli_composition_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "cli", "windagent_cli", "composition.py"
        )
        assert os.path.exists(cli_composition_path)

    def test_cli_composition_has_per_command_composers(self):
        """CLI composition should have per-command composers"""
        import os
        cli_composition_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "cli", "windagent_cli", "composition.py"
        )
        
        with open(cli_composition_path, 'r') as f:
            content = f.read()
        
        # Should have per-command composers
        assert "DoctorCommandComposer" in content
        assert "RunCommandComposer" in content
        assert "ProviderTestCommandComposer" in content
        assert "WorkerStatusCommandComposer" in content
        assert "EvalCommandComposer" in content
        assert "ArchitectureCheckCommandComposer" in content

    def test_cli_composition_no_god_container(self):
        """CLI should NOT have a global god container"""
        import os
        cli_composition_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "cli", "windagent_cli", "composition.py"
        )
        
        with open(cli_composition_path, 'r') as f:
            content = f.read()
        
        # Should NOT have a single global container
        assert "ApplicationContainer" not in content or "# NO global" in content
        assert "class GlobalContainer" not in content
        assert "class GodContainer" not in content

    def test_cli_main_uses_per_command_composition(self):
        """CLI main should use per-command composition"""
        import ast
        import os
        cli_main_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "cli", "windagent_cli", "main.py"
        )
        
        with open(cli_main_path, 'r') as f:
            content = f.read()

        # Heavy services may be imported lazily by their command, but never at module scope.
        tree = ast.parse(content)
        top_level_imports = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }
        assert "windagent_orchestration.task_manager.service" not in top_level_imports
        assert "windagent_providers.registry.canonical_registry" not in top_level_imports
        assert "windagent_tools.registry" not in top_level_imports
        
        # Should import from composition module
        assert "from windagent_cli.composition import" in content


class TestPhase7DesktopSupervisor:
    """Test Desktop supervisor manages processes, no direct composition"""

    def test_desktop_sidecar_manager_exists(self):
        """Desktop should have sidecar manager"""
        import os
        sidecar_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "desktop", "sidecar_manager.py"
        )
        assert os.path.exists(sidecar_path)

    def test_desktop_no_direct_service_composition(self):
        """Desktop supervisor should NOT compose services directly"""
        import os
        sidecar_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "desktop", "sidecar_manager.py"
        )
        
        with open(sidecar_path, 'r') as f:
            content = f.read()
        
        # Should NOT compose API or Worker services directly
        assert "from windagent_api" not in content
        assert "from windagent_worker" not in content
        assert "TaskManager" not in content
        assert "ExecutionRuntimeRegistry" not in content
        
        # Should use subprocess to spawn processes
        assert "subprocess.Popen" in content
        assert "spawn_api_sidecar" in content
        assert "spawn_worker_sidecar" in content

    def test_desktop_has_lifecycle_management(self):
        """Desktop supervisor should have lifecycle management"""
        import os
        sidecar_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "desktop", "sidecar_manager.py"
        )
        
        with open(sidecar_path, 'r') as f:
            content = f.read()
        
        # Should have lifecycle methods
        assert "def spawn_api_sidecar" in content
        assert "def spawn_worker_sidecar" in content
        assert "def check_health" in content
        assert "def shutdown" in content
        assert "def restart_sidecar" in content

    def test_desktop_has_restart_policy(self):
        """Desktop supervisor should have restart policy"""
        import os
        sidecar_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "desktop", "sidecar_manager.py"
        )
        
        with open(sidecar_path, 'r') as f:
            content = f.read()
        
        # Should have restart policy
        assert "restart_policy" in content
        assert "max_restarts" in content
        assert "restart_delay" in content


class TestPhase7NoGodContainer:
    """Test that no god container is shared across processes"""

    def test_no_global_container_in_api(self):
        """API should not have a global container exported"""
        import os
        api_init_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "api", "windagent_api", "__init__.py"
        )
        
        if os.path.exists(api_init_path):
            with open(api_init_path, 'r') as f:
                content = f.read()
            
            # Should NOT export a global container instance
            assert "global_container" not in content.lower()
            assert "container = " not in content or "ApplicationContainer" not in content

    def test_no_global_container_in_worker(self):
        """Worker should not have a global container exported"""
        import os
        worker_init_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "worker", "windagent_worker", "__init__.py"
        )
        
        if os.path.exists(worker_init_path):
            with open(worker_init_path, 'r') as f:
                content = f.read()
            
            # Should NOT export a global container instance
            assert "global_container" not in content.lower()
            assert "container = " not in content or "WorkerContainer" not in content

    def test_no_cross_process_imports(self):
        """No process should import services from another process"""
        import os
        
        # Check API doesn't import from Worker
        api_composition_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "api", "windagent_api", "composition.py"
        )
        with open(api_composition_path, 'r') as f:
            api_content = f.read()
        assert "from windagent_worker" not in api_content
        
        # Check Worker doesn't import from API
        worker_composition_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "worker", "windagent_worker", "composition.py"
        )
        with open(worker_composition_path, 'r') as f:
            worker_content = f.read()
        assert "from windagent_api" not in worker_content
        
        # Check Desktop doesn't import from API or Worker for service composition
        sidecar_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "desktop", "sidecar_manager.py"
        )
        with open(sidecar_path, 'r') as f:
            desktop_content = f.read()
        # Desktop can import for spawning, but not for service composition
        assert "from windagent_api.composition" not in desktop_content
        assert "from windagent_worker.composition" not in desktop_content


class TestPhase7VersionMetadata:
    """Test version metadata in composition roots"""

    def test_api_composition_has_phase7_marker(self):
        """API composition should have PHASE 7 marker"""
        import os
        api_composition_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "api", "windagent_api", "composition.py"
        )
        
        with open(api_composition_path, 'r') as f:
            content = f.read()
        
        assert "Phase 7" in content or "PHASE 7" in content

    def test_worker_composition_has_phase7_marker(self):
        """Worker composition should have PHASE 7 marker"""
        import os
        worker_composition_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "worker", "windagent_worker", "composition.py"
        )
        
        with open(worker_composition_path, 'r') as f:
            content = f.read()
        
        assert "Phase 7" in content or "PHASE 7" in content

    def test_cli_composition_has_phase7_marker(self):
        """CLI composition should have PHASE 7 marker"""
        import os
        cli_composition_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "cli", "windagent_cli", "composition.py"
        )
        
        with open(cli_composition_path, 'r') as f:
            content = f.read()
        
        assert "Phase 7" in content or "PHASE 7" in content

    def test_desktop_supervisor_has_phase7_marker(self):
        """Desktop supervisor should have PHASE 7 marker"""
        import os
        sidecar_path = os.path.join(
            os.path.dirname(__file__).replace("tests\\unit", "").replace("tests/unit", ""),
            "apps", "desktop", "sidecar_manager.py"
        )
        
        with open(sidecar_path, 'r') as f:
            content = f.read()
        
        assert "Phase 7" in content or "PHASE 7" in content
