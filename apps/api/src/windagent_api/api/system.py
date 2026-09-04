"""System information surface — the reference Command/Query router flow.

The route only performs: HTTP → validate DTO → QueryBus → response mapper.
Every module router must follow the same discipline (plan section 12); SQL,
provider calls, and business logic are forbidden at this layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from windagent.platform.configuration.settings import Settings
from windagent.platform.modules import (
    InMemoryModuleRegistry,
    ModuleManifest,
    ModuleRegistry,
    QueryRegistration,
)
from windagent.platform.queries import Query, QueryBus, QueryHandler

from windagent_api import __version__ as PACKAGE_VERSION

SYSTEM_MODULE_ID = "api.system"


class GetSystemInfo(Query["SystemInfo"]):
    """Side-effect-free request for the API's runtime self-description."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class SystemInfo:
    """Serializable runtime description returned by the query handler."""

    api_version: str
    environment: str
    version: str
    modules: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "api_version": self.api_version,
            "environment": self.environment,
            "version": self.version,
            "modules": list(self.modules),
        }


@dataclass(slots=True)
class SystemInfoHandler(QueryHandler[GetSystemInfo, SystemInfo]):
    """Resolves runtime identity from composition-owned collaborators."""

    api_version: str
    settings: Settings
    module_registry: ModuleRegistry

    async def handle(self, query: GetSystemInfo) -> SystemInfo:
        return SystemInfo(
            api_version=self.api_version,
            environment=self.settings.environment,
            version=PACKAGE_VERSION,
            modules=tuple(
                descriptor.module_id for descriptor in self.module_registry.all()
            ),
        )


def create_system_router() -> APIRouter:
    """Build the router that dispatches ``GetSystemInfo`` through the bus."""
    router = APIRouter(tags=["system"])

    @router.get("/system/info")
    async def system_info(request: Request) -> JSONResponse:
        query_bus = cast(QueryBus, request.app.state.query_bus)
        info = await query_bus.ask(GetSystemInfo())
        return JSONResponse(info.to_dict())

    return router


def build_system_manifest(
    *,
    api_version: str,
    settings: Settings,
    module_registry: InMemoryModuleRegistry,
) -> ModuleManifest:
    """Compose the app-owned system module contribution."""
    return ModuleManifest(
        id=SYSTEM_MODULE_ID,
        version=PACKAGE_VERSION,
        queries=(
            QueryRegistration(
                GetSystemInfo,
                SystemInfoHandler(
                    api_version=api_version,
                    settings=settings,
                    module_registry=module_registry,
                ),
            ),
        ),
        routers=(create_system_router(),),
    )
