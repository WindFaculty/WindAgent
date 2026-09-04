"""Phase 1 sanity: every declared V2 package is importable."""

from __future__ import annotations

import importlib

LAYERS = [
    "windagent",
    "windagent.kernel",
    "windagent.kernel.ids",
    "windagent.kernel.errors",
    "windagent.kernel.events",
    "windagent.kernel.result",
    "windagent.kernel.time",
    "windagent.kernel.types",
    "windagent.platform",
    "windagent.platform.modules",
    "windagent.platform.commands",
    "windagent.platform.queries",
    "windagent.platform.jobs",
    "windagent.platform.events",
    "windagent.platform.persistence",
    "windagent.platform.persistence.postgres",
    "windagent.platform.artifacts",
    "windagent.platform.realtime",
    "windagent.platform.configuration",
    "windagent.platform.security",
    "windagent.platform.observability",
    "windagent.modules",
    "windagent.modules.identity",
    "windagent.modules.workspace",
    "windagent.modules.model_gateway",
    "windagent.modules.automation",
    "windagent.modules.agent_runtime",
    "windagent.modules.memory",
    "windagent.modules.studio",
    "windagent.modules.production",
    "windagent.modules.live_record",
    "windagent.modules.quality",
    "windagent_api",
    "windagent_worker",
    "windagent_scheduler",
    "windagent_cli",
]


def test_all_declared_packages_import() -> None:
    for name in LAYERS:
        importlib.import_module(name)


def test_workspace_versions_are_consistent() -> None:
    import windagent
    import windagent_api
    import windagent_cli
    import windagent_scheduler
    import windagent_worker

    assert windagent.__version__ == "0.1.0"
    assert (
        windagent_api.__version__
        == windagent_cli.__version__
        == windagent_scheduler.__version__
        == windagent_worker.__version__
        == windagent.__version__
    )
