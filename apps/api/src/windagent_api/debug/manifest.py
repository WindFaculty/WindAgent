"""App-owned manifest wiring debug handlers into the buses."""

from __future__ import annotations

from windagent.platform.jobs import DurableJobQueue
from windagent.platform.modules import (
    CommandRegistration,
    ModuleManifest,
    QueryRegistration,
)

from windagent_api import __version__ as PACKAGE_VERSION

from .contracts import CancelDebugJob, GetDebugJob, SubmitDebugJob
from .handlers import (
    CancelDebugJobHandler,
    GetDebugJobHandler,
    SubmitDebugJobHandler,
)

DEBUG_MODULE_ID = "api.debug"


def build_debug_manifest(queue: DurableJobQueue) -> ModuleManifest:
    """Register debug commands and queries; the router is mounted explicitly.

    The debug surface intentionally stays outside ``/api/v4`` (it is an
    unauthenticated development tool), so its router is mounted by the
    composition root instead of traveling with this manifest.
    """
    return ModuleManifest(
        id=DEBUG_MODULE_ID,
        version=PACKAGE_VERSION,
        commands=(
            CommandRegistration(SubmitDebugJob, SubmitDebugJobHandler(queue)),
            CommandRegistration(CancelDebugJob, CancelDebugJobHandler(queue)),
        ),
        queries=(QueryRegistration(GetDebugJob, GetDebugJobHandler(queue)),),
    )
