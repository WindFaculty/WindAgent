"""Phase 8 canonical error envelope contracts, including module routers."""

from __future__ import annotations

from typing import Literal, cast

import httpx
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from windagent.kernel.errors.domain import DomainError
from windagent.platform.commands import Command, CommandBus
from windagent.platform.configuration.settings import Settings
from windagent.platform.modules import CommandRegistration, ModuleManifest
from windagent_api.app import create_app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
PRODUCTION_DATABASE_URL = "postgresql+asyncpg://localhost:5432/windagent_v2"


class EchoRequest(BaseModel):
    value: int


class BoomCommand(Command[None]):
    __slots__ = ()


class CrashCommand(Command[None]):
    __slots__ = ()


class BoomHandler:
    async def handle(self, command: BoomCommand) -> None:
        raise DomainError(
            "boom happened", code="conflict", context={"resource": "demo"}
        )


class CrashHandler:
    async def handle(self, command: CrashCommand) -> None:
        raise RuntimeError("secret internals leaked")


def _boom_router() -> APIRouter:
    router = APIRouter()

    @router.post("/boom")
    async def boom(request: Request) -> JSONResponse:
        command_bus = cast(CommandBus, request.app.state.command_bus)
        await command_bus.dispatch(BoomCommand())
        return JSONResponse({"ok": True})

    @router.post("/crash")
    async def crash(request: Request) -> JSONResponse:
        command_bus = cast(CommandBus, request.app.state.command_bus)
        await command_bus.dispatch(CrashCommand())
        return JSONResponse({"ok": True})

    @router.post("/echo")
    async def echo(request: Request, body: EchoRequest) -> JSONResponse:
        command_bus = cast(CommandBus, request.app.state.command_bus)
        await command_bus.dispatch(BoomCommand())
        return JSONResponse({"echo": body.value})

    return router


def _app(
    *, environment: Literal["development", "test", "production"] = "test"
) -> FastAPI:
    manifest = ModuleManifest(
        id="test.boom",
        version="0",
        commands=(
            CommandRegistration(BoomCommand, BoomHandler()),
            CommandRegistration(CrashCommand, CrashHandler()),
        ),
        routers=(_boom_router(),),
    )
    return create_app(
        Settings(
            environment=environment,
            database_url=(
                TEST_DATABASE_URL
                if environment == "test"
                else PRODUCTION_DATABASE_URL
            ),
        ),
        manifests=(manifest,),
    )


async def test_module_router_mounts_under_the_canonical_prefix() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()), base_url="http://v2.test"
    ) as client:
        response = await client.post("/api/v4/boom")
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "conflict"
    assert body["error"]["message"] == "boom happened"
    assert body["error"]["context"] == {"resource": "demo"}


async def test_unexpected_exceptions_produce_a_generic_500() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=_app(environment="production"), raise_app_exceptions=False
        ),
        base_url="http://v2.test",
    ) as client:
        response = await client.post("/api/v4/crash")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "secret internals" not in response.text


async def test_unexpected_exceptions_expose_details_outside_production() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(), raise_app_exceptions=False),
        base_url="http://v2.test",
    ) as client:
        response = await client.post("/api/v4/crash")
    assert response.status_code == 500
    assert "secret internals" in response.json()["error"]["context"]["detail"]


async def test_handler_arguments_are_validated_as_transport_errors() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()), base_url="http://v2.test"
    ) as client:
        response = await client.post("/api/v4/echo", json={"unexpected": 1})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
