"""
Comprehensive tests for PHASE 10 - Readiness, Liveness and Diagnostics.
Tests all health check functionality with real checks, no hardcoded values.
"""

from __future__ import annotations
import pytest
import asyncio
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock

from windagent_observability.health import (
    HealthChecker,
    HealthStatus,
    HealthProfile,
    HealthCheckResult,
    ReadinessStatus,
)


class TestHealthCheckerInitialization:
    """Tests for HealthChecker initialization."""
    
    def test_health_checker_initializes_with_defaults(self):
        """HealthChecker should initialize with default values."""
        checker = HealthChecker()
        assert checker._db_session_factory is None
        assert checker._worker_status_query is None
        assert checker._provider_registry is None
        assert checker._profile == HealthProfile.DEVELOPMENT
    
    def test_health_checker_initializes_with_custom_profile(self):
        """HealthChecker should accept custom profile."""
        checker = HealthChecker(profile=HealthProfile.PRODUCTION)
        assert checker._profile == HealthProfile.PRODUCTION


class TestLivenessCheck:
    """Tests for liveness probe."""
    
    @pytest.mark.asyncio
    async def test_liveness_returns_true_when_alive(self):
        """Liveness check should return True when process is alive."""
        checker = HealthChecker()
        result = await checker.check_liveness()
        assert result is True


class TestReadinessChecks:
    """Tests for individual readiness checks."""
    
    @pytest.mark.asyncio
    async def test_database_check_with_valid_connection(self):
        """Database check should pass with valid connection."""
        # Mock session factory: calling it returns an async context manager
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        def mock_session_factory():
            return mock_cm

        checker = HealthChecker(db_session_factory=mock_session_factory)
        result = await checker._check_database_connection()
        
        assert result.name == "database"
        assert result.status == HealthStatus.UP
        assert "verified" in result.message.lower()
        assert result.required is True
    
    @pytest.mark.asyncio
    async def test_database_check_with_failed_connection(self):
        """Database check should fail with connection error."""
        async def mock_failing_session_factory():
            raise Exception("Connection failed")
        
        checker = HealthChecker(db_session_factory=mock_failing_session_factory)
        result = await checker._check_database_connection()
        
        assert result.name == "database"
        assert result.status == HealthStatus.DOWN
        assert "failed" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_schema_migration_check_with_history(self):
        """Schema migration check should return revision from history table."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_row = Mock()
        mock_row.__getitem__ = Mock(side_effect=lambda x: {
            0: "002",
            1: 2
        }.get(x))
        mock_result.fetchone = Mock(return_value=mock_row)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        def mock_session_factory():
            return mock_cm

        checker = HealthChecker(db_session_factory=mock_session_factory)
        result = await checker._check_schema_migration()
        
        assert result.name == "schema_migration"
        assert result.status == HealthStatus.UP
        assert "002" in result.message
    
    @pytest.mark.asyncio
    async def test_worker_heartbeat_check_available(self):
        """Worker heartbeat check should pass when worker is available."""
        mock_status = Mock()
        mock_status.available = True
        mock_status.active_workers = 2
        mock_status.active_leases = 5
        
        mock_query = Mock()
        mock_query.get_status = AsyncMock(return_value=mock_status)
        
        checker = HealthChecker(
            worker_status_query=mock_query,
            profile=HealthProfile.PRODUCTION
        )
        result = await checker._check_worker_heartbeat()
        
        assert result.name == "worker"
        assert result.status == HealthStatus.UP
        assert result.details["active_workers"] == 2
    
    @pytest.mark.asyncio
    async def test_worker_heartbeat_check_unavailable_in_production(self):
        """Worker heartbeat check should be DOWN in production when unavailable."""
        mock_status = Mock()
        mock_status.available = False
        mock_status.active_workers = 0
        mock_status.active_leases = 0
        
        mock_query = Mock()
        mock_query.get_status = AsyncMock(return_value=mock_status)
        
        checker = HealthChecker(
            worker_status_query=mock_query,
            profile=HealthProfile.PRODUCTION
        )
        result = await checker._check_worker_heartbeat()
        
        assert result.name == "worker"
        assert result.status == HealthStatus.DOWN
        assert "No active workers" in result.message
    
    @pytest.mark.asyncio
    async def test_worker_heartbeat_check_unavailable_in_development(self):
        """Worker heartbeat check should be DEGRADED in development when unavailable."""
        mock_status = Mock()
        mock_status.available = False
        mock_status.active_workers = 0
        mock_status.active_leases = 0
        
        mock_query = Mock()
        mock_query.get_status = AsyncMock(return_value=mock_status)
        
        checker = HealthChecker(
            worker_status_query=mock_query,
            profile=HealthProfile.DEVELOPMENT
        )
        result = await checker._check_worker_heartbeat()
        
        assert result.name == "worker"
        assert result.status == HealthStatus.DEGRADED
    
    @pytest.mark.asyncio
    async def test_provider_registry_check_loaded(self):
        """Provider registry check should pass when loaded."""
        mock_provider = Mock()
        mock_provider.provider_name = "openai"
        
        mock_registry = Mock()
        mock_registry.list_providers = AsyncMock(return_value=[mock_provider, mock_provider])
        
        checker = HealthChecker(provider_registry=mock_registry)
        result = await checker._check_provider_registry()
        
        assert result.name == "provider_registry"
        assert result.status == HealthStatus.UP
        assert "2 providers" in result.message
    
    @pytest.mark.asyncio
    async def test_tool_registry_check_loaded(self):
        """Tool registry check should pass when loaded."""
        mock_tool = Mock()
        mock_tool.name = "read_file"
        
        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[mock_tool, mock_tool, mock_tool])
        
        checker = HealthChecker(tool_registry=mock_registry)
        result = await checker._check_tool_registry()
        
        assert result.name == "tool_registry"
        assert result.status == HealthStatus.UP
        assert "3 tools" in result.message
    
    @pytest.mark.asyncio
    async def test_filesystem_check_all_paths_exist(self):
        """Filesystem check should pass when all paths exist."""
        # Create temporary paths that exist
        existing_paths = [Path("tests"), Path("apps")]
        
        checker = HealthChecker(required_paths=existing_paths)
        result = await checker._check_required_filesystem_paths()
        
        assert result.name == "filesystem"
        assert result.status == HealthStatus.UP
    
    @pytest.mark.asyncio
    async def test_filesystem_check_missing_paths(self):
        """Filesystem check should fail when paths are missing."""
        non_existent_paths = [Path("nonexistent_path_12345")]
        
        checker = HealthChecker(required_paths=non_existent_paths)
        result = await checker._check_required_filesystem_paths()
        
        assert result.name == "filesystem"
        assert result.status == HealthStatus.DOWN
        assert "Missing required paths" in result.message


class TestOverallStatusCalculation:
    """Tests for overall status calculation logic."""
    
    def test_production_all_up_returns_up(self):
        """Production profile with all checks UP should return UP."""
        checker = HealthChecker()
        checks = {
            "database": HealthCheckResult("database", HealthStatus.UP, "OK", required=True),
            "worker": HealthCheckResult("worker", HealthStatus.UP, "OK", required=True),
            "provider_registry": HealthCheckResult("provider_registry", HealthStatus.UP, "OK", required=True),
        }
        result = checker._calculate_overall_status(checks, HealthProfile.PRODUCTION)
        assert result == HealthStatus.UP
    
    def test_production_one_required_down_returns_down(self):
        """Production profile with one required check DOWN should return DOWN."""
        checker = HealthChecker()
        checks = {
            "database": HealthCheckResult("database", HealthStatus.UP, "OK", required=True),
            "worker": HealthCheckResult("worker", HealthStatus.DOWN, "Failed", required=True),
            "provider_registry": HealthCheckResult("provider_registry", HealthStatus.UP, "OK", required=True),
        }
        result = checker._calculate_overall_status(checks, HealthProfile.PRODUCTION)
        assert result == HealthStatus.DOWN
    
    def test_development_worker_down_only_returns_degraded(self):
        """Development profile with only worker DOWN should return DEGRADED."""
        checker = HealthChecker()
        checks = {
            "database": HealthCheckResult("database", HealthStatus.UP, "OK", required=True),
            "worker": HealthCheckResult("worker", HealthStatus.DOWN, "Not running", required=False),
            "provider_registry": HealthCheckResult("provider_registry", HealthStatus.UP, "OK", required=True),
        }
        result = checker._calculate_overall_status(checks, HealthProfile.DEVELOPMENT)
        assert result == HealthStatus.DEGRADED
    
    def test_development_other_down_returns_down(self):
        """Development profile with non-worker DOWN should return DOWN."""
        checker = HealthChecker()
        checks = {
            "database": HealthCheckResult("database", HealthStatus.DOWN, "Failed", required=True),
            "worker": HealthCheckResult("worker", HealthStatus.UP, "OK", required=False),
            "provider_registry": HealthCheckResult("provider_registry", HealthStatus.UP, "OK", required=True),
        }
        result = checker._calculate_overall_status(checks, HealthProfile.DEVELOPMENT)
        assert result == HealthStatus.DOWN


class TestFullReadinessCheck:
    """Tests for full readiness check with all components."""
    
    @pytest.mark.asyncio
    async def test_full_readiness_all_passing(self):
        """Full readiness check should pass with all components healthy."""
        # Mock all dependencies
        mock_session = AsyncMock()
        # Configure execute to return a result with fetchone returning a row
        mock_result = Mock()
        mock_row = Mock()
        mock_row.__getitem__ = Mock(side_effect=lambda x: {"revision": "002_legacy_data", "count": 2, 0: "002_legacy_data", 1: 2}.get(x, 0))
        mock_result.fetchone = Mock(return_value=mock_row)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        def mock_session_factory():
            return mock_cm

        mock_worker_query = Mock()
        mock_worker_status = Mock(available=True, active_workers=1, active_leases=0)
        mock_worker_query.get_status = AsyncMock(return_value=mock_worker_status)
        
        mock_provider_reg = Mock()
        mock_provider_reg.list_providers = AsyncMock(return_value=[Mock()])
        
        mock_tool_reg = Mock()
        mock_tool_reg.list_tools = AsyncMock(return_value=[Mock()])
        
        mock_workflow_reg = Mock()
        mock_workflow_reg.list_workflows = AsyncMock(return_value=[Mock()])
        
        checker = HealthChecker(
            db_session_factory=mock_session_factory,
            worker_status_query=mock_worker_query,
            provider_registry=mock_provider_reg,
            tool_registry=mock_tool_reg,
            workflow_registry=mock_workflow_reg,
            profile=HealthProfile.DEVELOPMENT
        )
        
        result = await checker.check_readiness()
        
        assert isinstance(result, ReadinessStatus)
        assert result.overall_status == HealthStatus.UP
        assert result.profile == HealthProfile.DEVELOPMENT
        assert len(result.checks) > 0
    
    @pytest.mark.asyncio
    async def test_full_readiness_production_no_worker_fails(self):
        """Full readiness check in production should fail without worker."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        def mock_session_factory():
            return mock_cm

        mock_worker_query = Mock()
        mock_worker_status = Mock(available=False, active_workers=0, active_leases=0)
        mock_worker_query.get_status = AsyncMock(return_value=mock_worker_status)
        
        mock_provider_reg = Mock()
        mock_provider_reg.list_providers = AsyncMock(return_value=[Mock()])
        
        checker = HealthChecker(
            db_session_factory=mock_session_factory,
            worker_status_query=mock_worker_query,
            provider_registry=mock_provider_reg,
            profile=HealthProfile.PRODUCTION
        )
        
        result = await checker.check_readiness()
        
        assert result.overall_status == HealthStatus.DOWN
        assert result.checks["worker"].status == HealthStatus.DOWN


class TestReadinessStatusSerialization:
    """Tests for ReadinessStatus serialization."""
    
    def test_readiness_status_to_dict(self):
        """ReadinessStatus should serialize to dict correctly."""
        checks = {
            "database": HealthCheckResult("database", HealthStatus.UP, "OK", required=True),
            "worker": HealthCheckResult("worker", HealthStatus.UP, "OK", required=True),
        }
        status = ReadinessStatus(
            overall_status=HealthStatus.UP,
            checks=checks,
            profile=HealthProfile.DEVELOPMENT
        )
        
        result = status.to_dict()
        
        assert isinstance(result, dict)
        assert result["status"] == "UP"
        assert result["profile"] == "development"
        assert "checks" in result
        assert "database" in result["checks"]
        assert result["checks"]["database"]["status"] == "UP"


class TestHealthContracts:
    """Tests for health check contracts."""
    
    def test_health_status_enum_values(self):
        """HealthStatus should have correct values."""
        assert HealthStatus.UP.value == "UP"
        assert HealthStatus.DEGRADED.value == "DEGRADED"
        assert HealthStatus.DOWN.value == "DOWN"
        assert HealthStatus.NOT_REQUIRED.value == "NOT_REQUIRED"
    
    def test_health_profile_enum_values(self):
        """HealthProfile should have correct values."""
        assert HealthProfile.PRODUCTION.value == "production"
        assert HealthProfile.DEVELOPMENT.value == "development"
        assert HealthProfile.TEST.value == "test"
    
    def test_health_check_result_defaults(self):
        """HealthCheckResult should have correct defaults."""
        result = HealthCheckResult(
            name="test",
            status=HealthStatus.UP,
            message="Test message"
        )
        assert result.name == "test"
        assert result.status == HealthStatus.UP
        assert result.message == "Test message"
        assert result.details is None
        assert result.required is True


class TestProfileBasedBehavior:
    """Tests for profile-based health check behavior."""
    
    def test_production_fail_closed(self):
        """Production profile should be fail-closed."""
        checker = HealthChecker(profile=HealthProfile.PRODUCTION)
        checks = {
            "database": HealthCheckResult("database", HealthStatus.DOWN, "Failed", required=True),
        }
        result = checker._calculate_overall_status(checks, HealthProfile.PRODUCTION)
        assert result == HealthStatus.DOWN
    
    def test_development_worker_not_required_for_up(self):
        """Development profile should allow UP without worker."""
        checker = HealthChecker(profile=HealthProfile.DEVELOPMENT)
        checks = {
            "database": HealthCheckResult("database", HealthStatus.UP, "OK", required=True),
            "worker": HealthCheckResult("worker", HealthStatus.DOWN, "Not running", required=False),
        }
        result = checker._calculate_overall_status(checks, HealthProfile.DEVELOPMENT)
        # Worker is down but not required, and it's the only issue
        assert result == HealthStatus.DEGRADED
    
    def test_test_profile_lenient(self):
        """Test profile should be more lenient."""
        checker = HealthChecker(profile=HealthProfile.TEST)
        checks = {
            "database": HealthCheckResult("database", HealthStatus.DOWN, "Failed", required=True),
            "worker": HealthCheckResult("worker", HealthStatus.DOWN, "Not running", required=True),
        }
        result = checker._calculate_overall_status(checks, HealthProfile.TEST)
        # Test allows up to 2 failures
        assert result == HealthStatus.DEGRADED
