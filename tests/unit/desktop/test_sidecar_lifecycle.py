"""
Unit tests for WindAgent Desktop SidecarManager process lifecycle (Phase 13).
"""

import sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent.parent.parent
desktop_dir = root_dir / "apps" / "desktop"
if str(desktop_dir) not in sys.path:
    sys.path.insert(0, str(desktop_dir))

from sidecar_manager import SidecarManager, SidecarStatus


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
