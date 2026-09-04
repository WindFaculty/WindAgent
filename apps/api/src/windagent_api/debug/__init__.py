"""App-owned debug transport for the Phase 7 fake-job vertical slice.

The debug surface deliberately bypasses ``/api/v4``: it is an unauthenticated
development tool, mounted only when a queue is explicitly injected, and it is
removed once Phase 9 provides an authenticated transport.  Even so, its
routes obey the Phase 8 discipline: HTTP → DTO → Command/QueryBus → mapper.
"""

from .contracts import (
    CancelDebugJob,
    GetDebugJob,
    SubmitDebugJob,
    SubmitDebugJobResult,
)
from .handlers import (
    CancelDebugJobHandler,
    GetDebugJobHandler,
    SubmitDebugJobHandler,
)
from .manifest import build_debug_manifest
from .routes import DebugJobRequest, create_debug_jobs_router

__all__ = [
    "CancelDebugJob",
    "CancelDebugJobHandler",
    "DebugJobRequest",
    "GetDebugJob",
    "GetDebugJobHandler",
    "SubmitDebugJob",
    "SubmitDebugJobHandler",
    "SubmitDebugJobResult",
    "build_debug_manifest",
    "create_debug_jobs_router",
]
