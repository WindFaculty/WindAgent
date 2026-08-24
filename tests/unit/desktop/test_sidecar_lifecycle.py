"""
Unit tests for WindAgent Desktop SidecarManager process lifecycle (Phase 13).
"""

from sidecar_manager import SidecarManager


def test_sidecar_manager_spawns_and_health_checks():
    mgr = SidecarManager()

    # Spawn API sidecar
    api_status = mgr.spawn_api_sidecar(mock_spawn=True)
    assert api_status.name == "api"
    assert api_status.running is True
    assert api_status.pid is not None

    # Spawn Worker sidecar
    worker_status = mgr.spawn_worker_sidecar(mock_spawn=True)
    assert worker_status.name == "worker"
    assert worker_status.running is True
    assert worker_status.pid is not None

    # Check sidecars health
    health = mgr.check_health()
    assert health["api"] is True
    assert health["worker"] is True

    # Shutdown sidecars
    mgr.shutdown()