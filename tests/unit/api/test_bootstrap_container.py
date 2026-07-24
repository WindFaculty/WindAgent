import sys
import pytest
from pathlib import Path

backend_dir = str(Path(__file__).resolve().parents[3] / "apps" / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from bootstrap.container import ApplicationContainer
from bootstrap.validation import validate_application_container


def test_container_validation_missing_dependency():
    """Container validation fails closed when a required dependency is missing."""
    container = ApplicationContainer(
        db=None,  # missing
        event_bus=None,
        session_service=None,
        permission_service=None,
        planner_service=None,
        route_lock_service=None,
        workflow_service=None,
        workflow_runner=None,
        orchestration_container=None,
        recovery_service=None,
    )
    with pytest.raises(ValueError, match="missing in ApplicationContainer"):
        validate_application_container(container)


def test_container_validation_success():
    """Container validation passes when all required ports are bound."""
    class DummyPort:
        pass

    container = ApplicationContainer(
        db=DummyPort(),
        event_bus=DummyPort(),
        session_service=DummyPort(),
        permission_service=DummyPort(),
        planner_service=DummyPort(),
        route_lock_service=DummyPort(),
        workflow_service=DummyPort(),
        workflow_runner=DummyPort(),
        orchestration_container=DummyPort(),
        recovery_service=DummyPort(),
    )
    assert validate_application_container(container) is True
