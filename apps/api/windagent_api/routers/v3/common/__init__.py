"""
Common V3 API Foundation Contracts and Utilities.
"""

from windagent_api.routers.v3.common.problems import (
    ApiProblem,
    ApiProblemException,
    api_problem_exception_handler,
)
from windagent_api.routers.v3.common.resource import ResourceBase
from windagent_api.routers.v3.common.pagination import PageInfo, CursorPage
from windagent_api.routers.v3.common.concurrency import (
    ExpectedVersionMutation,
    VersionConflictError,
    check_optimistic_concurrency,
)
from windagent_api.routers.v3.common.correlation import (
    CorrelationIdMiddleware,
    get_correlation_id,
    set_correlation_id,
)
from windagent_api.routers.v3.common.idempotency import (
    IdempotencyRecord,
    IdempotencyConflictError,
    IdempotencyStore,
    GLOBAL_IDEMPOTENCY_STORE,
)
from windagent_api.routers.v3.common.commands import CommandReceipt
from windagent_api.routers.v3.common.events import EventEnvelope

__all__ = [
    "ApiProblem",
    "ApiProblemException",
    "api_problem_exception_handler",
    "ResourceBase",
    "PageInfo",
    "CursorPage",
    "ExpectedVersionMutation",
    "VersionConflictError",
    "check_optimistic_concurrency",
    "CorrelationIdMiddleware",
    "get_correlation_id",
    "set_correlation_id",
    "IdempotencyRecord",
    "IdempotencyConflictError",
    "IdempotencyStore",
    "GLOBAL_IDEMPOTENCY_STORE",
    "CommandReceipt",
    "EventEnvelope",
]
