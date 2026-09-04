"""Versioned API transport."""

from collections.abc import Iterable
from typing import cast

from fastapi import APIRouter

API_VERSION = "v4"
API_PREFIX = f"/api/{API_VERSION}"


def build_api_router(module_routers: Iterable[object]) -> APIRouter:
    """Mount module-owned routers under the single canonical prefix.

    The API deliberately has no dual mounts and no legacy router tree
    (plan section 12): every module route must appear under ``/api/v4``.
    """
    router = APIRouter(prefix=API_PREFIX)
    for module_router in module_routers:
        router.include_router(cast(APIRouter, module_router))
    return router
