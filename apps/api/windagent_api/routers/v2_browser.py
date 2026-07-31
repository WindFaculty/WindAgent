"""Browser endpoints for the desktop Agent Workspace.

The router is deliberately separate from the durable Sessions router because
browser daemons and screenshots are process-local resources. Its session id is
the owning V2 session id, so the desktop can consistently reconnect to a page.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from windagent_api.browser_sessions import (
    BrowserLaunchOptions,
    BrowserSessionConflictError,
    BrowserSessionError,
    BrowserSessionService,
    BrowserState,
)


router = APIRouter(prefix="/api/v2/browser/sessions", tags=["Browser V2"])


class BrowserNavigateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4_096)
    authenticated: bool = False
    profile: Optional[str] = Field(default=None, max_length=64)


class BrowserClickRequest(BaseModel):
    x: int = Field(ge=0, le=4_096)
    y: int = Field(ge=0, le=4_096)


class BrowserTypeRequest(BaseModel):
    selector: str = Field(min_length=1, max_length=2_000)
    text: str = Field(min_length=1, max_length=20_000)


class BrowserScrollRequest(BaseModel):
    direction: Literal["up", "down"] = "down"
    pixels: int = Field(default=800, ge=1, le=20_000)


class BrowserControlRequest(BaseModel):
    controlled_by: Literal["agent", "user"]


class BrowserStateResponse(BaseModel):
    session_id: str
    url: str
    title: str
    loading: bool
    screenshot_url: Optional[str] = None
    controlled_by: Literal["agent", "user"]
    extracted_text: str = ""
    content_chars: int = 0
    error: Optional[str] = None
    authenticated: bool = False
    profile: Optional[str] = None


def _service(request: Request) -> BrowserSessionService:
    service = getattr(request.app.state, "browser_session_service", None)
    if service is None:
        service = BrowserSessionService()
        request.app.state.browser_session_service = service
    return service


def _response(state: BrowserState) -> BrowserStateResponse:
    return BrowserStateResponse(
        session_id=state.session_id,
        url=state.url,
        title=state.title,
        loading=state.loading,
        screenshot_url=(
            f"/api/v2/browser/sessions/{state.session_id}/screenshot"
            if state.screenshot_path
            else None
        ),
        controlled_by=state.controlled_by,
        extracted_text=state.extracted_text,
        content_chars=len(state.extracted_text),
        error=state.error,
        authenticated=state.authenticated,
        profile=state.profile,
    )


def _raise_browser_error(error: BrowserSessionError) -> None:
    status_code = (
        status.HTTP_409_CONFLICT
        if isinstance(error, BrowserSessionConflictError)
        else status.HTTP_400_BAD_REQUEST
    )
    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.get("/{session_id}", response_model=BrowserStateResponse)
async def get_browser_state(session_id: str, request: Request) -> BrowserStateResponse:
    return _response(await _service(request).get_state(session_id))


@router.post("/{session_id}/navigate", response_model=BrowserStateResponse)
async def navigate_browser(
    session_id: str,
    body: BrowserNavigateRequest,
    request: Request,
) -> BrowserStateResponse:
    try:
        state = await _service(request).navigate(
            session_id,
            body.url,
            options=BrowserLaunchOptions(
                authenticated=body.authenticated,
                profile=body.profile,
            ),
        )
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _response(state)


@router.post("/{session_id}/click", response_model=BrowserStateResponse)
async def click_browser(
    session_id: str, body: BrowserClickRequest, request: Request
) -> BrowserStateResponse:
    try:
        state = await _service(request).click(session_id, body.x, body.y)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _response(state)


@router.post("/{session_id}/type", response_model=BrowserStateResponse)
async def type_browser(
    session_id: str, body: BrowserTypeRequest, request: Request
) -> BrowserStateResponse:
    try:
        state = await _service(request).type_text(session_id, body.selector, body.text)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _response(state)


@router.post("/{session_id}/scroll", response_model=BrowserStateResponse)
async def scroll_browser(
    session_id: str, body: BrowserScrollRequest, request: Request
) -> BrowserStateResponse:
    try:
        state = await _service(request).scroll(session_id, body.direction, body.pixels)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _response(state)


@router.post("/{session_id}/control", response_model=BrowserStateResponse)
async def control_browser(
    session_id: str, body: BrowserControlRequest, request: Request
) -> BrowserStateResponse:
    try:
        state = await _service(request).set_control(session_id, body.controlled_by)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _response(state)


@router.post("/{session_id}/back", response_model=BrowserStateResponse)
async def go_back_browser(session_id: str, request: Request) -> BrowserStateResponse:
    try:
        state = await _service(request).go_back(session_id)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _response(state)


@router.post("/{session_id}/forward", response_model=BrowserStateResponse)
async def go_forward_browser(session_id: str, request: Request) -> BrowserStateResponse:
    try:
        state = await _service(request).go_forward(session_id)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _response(state)


@router.post("/{session_id}/reload", response_model=BrowserStateResponse)
async def reload_browser(session_id: str, request: Request) -> BrowserStateResponse:
    try:
        state = await _service(request).reload(session_id)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _response(state)


@router.get("/{session_id}/screenshot")
async def get_browser_screenshot(session_id: str, request: Request) -> FileResponse:
    try:
        path = await _service(request).screenshot_path(session_id)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return FileResponse(path, media_type="image/png")


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def close_browser(session_id: str, request: Request) -> None:
    await _service(request).close(session_id)
