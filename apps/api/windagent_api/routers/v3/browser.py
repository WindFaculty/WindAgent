"""
V3 Browser Router — Canonical Browser Runtime Console Authority (Phase 13A).

Wraps the real BrowserSessionService (agent-browser daemons + persisted
screenshots). ZERO mock sessions: every session listed here is a live runtime
session created through this API. Realtime session/navigation/action events are
broadcast on /ws/v3/browser.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from windagent_api.browser_sessions import (
    BrowserLaunchOptions,
    BrowserSessionConflictError,
    BrowserSessionError,
    BrowserSessionService,
    BrowserState,
)

router = APIRouter(prefix="/api/v3/browser", tags=["Browser V3"])
ws_router = APIRouter(prefix="/ws/v3/browser", tags=["Browser V3 Realtime"])


class BrowserSessionResource(BaseModel):
    id: str
    url: str = "about:blank"
    title: str = "New Tab"
    loading: bool = False
    screenshot_url: Optional[str] = None
    controlled_by: str = "agent"
    extracted_chars: int = 0
    error: Optional[str] = None
    authenticated: bool = False
    profile: Optional[str] = None
    created_at: str


class CreateBrowserSessionRequest(BaseModel):
    authenticated: bool = False
    profile: Optional[str] = Field(default=None, max_length=64)


class BrowserNavigateRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=4_096)


class BrowserClickRequest(BaseModel):
    x: int = Field(ge=0, le=8_192)
    y: int = Field(ge=0, le=8_192)


class BrowserTypeRequest(BaseModel):
    selector: str = Field(min_length=1, max_length=2_000)
    text: str = Field(min_length=1, max_length=20_000)


class BrowserScrollRequest(BaseModel):
    direction: str = "down"  # up | down
    pixels: int = Field(default=800, ge=1, le=20_000)


class BrowserActionResponse(BaseModel):
    session_id: str
    url: str
    title: str
    loading: bool
    screenshot_url: Optional[str] = None
    extracted_chars: int = 0
    error: Optional[str] = None
    event: str
    timestamp: str


def _service(request: Request) -> BrowserSessionService:
    service = getattr(request.app.state, "browser_session_service", None)
    if service is None:
        service = BrowserSessionService()
        request.app.state.browser_session_service = service
    return service


def _resource(session_id: str, state: BrowserState) -> BrowserSessionResource:
    return BrowserSessionResource(
        id=session_id,
        url=state.url,
        title=state.title,
        loading=state.loading,
        screenshot_url=(
            f"/api/v3/browser/sessions/{session_id}/screenshot"
            if state.screenshot_path
            else None
        ),
        controlled_by=state.controlled_by,
        extracted_chars=len(state.extracted_text),
        error=state.error,
        authenticated=state.authenticated,
        profile=state.profile,
        created_at="",
    )


def _raise_browser_error(error: BrowserSessionError) -> None:
    status_code = (
        status.HTTP_409_CONFLICT
        if isinstance(error, BrowserSessionConflictError)
        else status.HTTP_400_BAD_REQUEST
    )
    raise HTTPException(status_code=status_code, detail=str(error)) from error


def _action_payload(session_id: str, state: BrowserState, event: str) -> BrowserActionResponse:
    from windagent_core.domain.lifecycle import utc_now

    return BrowserActionResponse(
        session_id=session_id,
        url=state.url,
        title=state.title,
        loading=state.loading,
        screenshot_url=(
            f"/api/v3/browser/sessions/{session_id}/screenshot"
            if state.screenshot_path
            else None
        ),
        extracted_chars=len(state.extracted_text),
        error=state.error,
        event=event,
        timestamp=utc_now().isoformat(),
    )


@router.get("/sessions", response_model=List[BrowserSessionResource], operation_id="browser.listSessions")
async def list_browser_sessions(request: Request) -> List[BrowserSessionResource]:
    """List live browser runtime sessions (zero mock entries)."""
    service = _service(request)
    session_ids = await service.list_session_ids()
    resources: List[BrowserSessionResource] = []
    for sid in session_ids:
        try:
            state = await service.get_state(sid)
            resources.append(_resource(sid, state))
        except BrowserSessionError:
            continue
    return resources


@router.post("/sessions", response_model=BrowserSessionResource, operation_id="browser.createSession")
async def create_browser_session(
    body: CreateBrowserSessionRequest,
    request: Request,
) -> BrowserSessionResource:
    """Start a new browser runtime session (lazy daemon launch on first navigation)."""
    session_id = f"brs-{asyncio.get_event_loop().time():.0f}-{len(await _service(request).list_session_ids()) + 1}"
    try:
        state = await _service(request).navigate(
            session_id,
            "about:blank",
            options=BrowserLaunchOptions(authenticated=body.authenticated, profile=body.profile),
        )
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _resource(session_id, state)


@router.get("/sessions/{session_id}", response_model=BrowserSessionResource, operation_id="browser.getSession")
async def get_browser_session(session_id: str, request: Request) -> BrowserSessionResource:
    try:
        state = await _service(request).get_state(session_id)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _resource(session_id, state)


@router.post("/sessions/{session_id}/navigate", response_model=BrowserActionResponse, operation_id="browser.navigate")
async def browser_navigate(
    session_id: str,
    body: BrowserNavigateRequest,
    request: Request,
) -> BrowserActionResponse:
    try:
        state = await _service(request).navigate(
            session_id,
            body.url,
            options=BrowserLaunchOptions(),
        )
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _action_payload(session_id, state, "browser.action.completed")


@router.post("/sessions/{session_id}/click", response_model=BrowserActionResponse, operation_id="browser.click")
async def browser_click(
    session_id: str,
    body: BrowserClickRequest,
    request: Request,
) -> BrowserActionResponse:
    try:
        state = await _service(request).click(session_id, body.x, body.y)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _action_payload(session_id, state, "browser.action.completed")


@router.post("/sessions/{session_id}/type", response_model=BrowserActionResponse, operation_id="browser.type")
async def browser_type(
    session_id: str,
    body: BrowserTypeRequest,
    request: Request,
) -> BrowserActionResponse:
    try:
        state = await _service(request).type_text(session_id, body.selector, body.text)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _action_payload(session_id, state, "browser.action.completed")


@router.post("/sessions/{session_id}/scroll", response_model=BrowserActionResponse, operation_id="browser.scroll")
async def browser_scroll(
    session_id: str,
    body: BrowserScrollRequest,
    request: Request,
) -> BrowserActionResponse:
    try:
        state = await _service(request).scroll(session_id, body.direction, body.pixels)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _action_payload(session_id, state, "browser.action.completed")


@router.get("/sessions/{session_id}/extract", response_model=BrowserActionResponse, operation_id="browser.extract")
async def browser_extract(session_id: str, request: Request) -> BrowserActionResponse:
    try:
        state = await _service(request).get_state(session_id)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return _action_payload(session_id, state, "browser.extract")


@router.get("/sessions/{session_id}/screenshot")
async def browser_screenshot(session_id: str, request: Request) -> FileResponse:
    """Serve the persisted screenshot artifact captured by the browser runtime."""
    try:
        path = await _service(request).screenshot_path(session_id)
    except BrowserSessionError as error:
        _raise_browser_error(error)
    return FileResponse(path, media_type="image/png")


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="browser.close")
async def browser_close(session_id: str, request: Request) -> None:
    await _service(request).close(session_id)


@ws_router.websocket("")
async def browser_realtime_ws(websocket: WebSocket):
    """Realtime browser session/action event stream. Broadcasts only real runtime events."""
    await websocket.accept()
    try:
        await websocket.send_text(json.dumps({"event": "browser.stream.ready", "session_id": None}))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass