"""Browser Router exposing REST API endpoints to interact with BrowserService."""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services.browser_service import BrowserService

router = APIRouter(prefix="/sessions/{session_id}/browser", tags=["browser"])


def _browser_service(request: Request) -> BrowserService:
    return request.app.state.browser_service


class NavigatePayload(BaseModel):
    url: str = Field(..., min_length=1)


class ClickPayload(BaseModel):
    selector: Optional[str] = None
    x: int = 0
    y: int = 0


class TypePayload(BaseModel):
    text: str
    selector: Optional[str] = None


class ControlPayload(BaseModel):
    control: str = Field(..., description="'agent' or 'user'")


@router.get("")
async def get_browser_state(session_id: UUID, request: Request) -> Dict[str, Any]:
    """Retrieve current browser navigation, status, and screenshot URI."""
    service = _browser_service(request)
    state = service.get_state(str(session_id))
    if not state:
        # Auto-create context if not existing yet
        state = await service.get_or_create_browser(str(session_id))
    return state


@router.get("/screenshot")
async def get_browser_screenshot(session_id: UUID, request: Request) -> FileResponse:
    """Return the raw PNG screenshot of the browser viewport."""
    service = _browser_service(request)
    state = service.get_state(str(session_id))
    if not state:
        state = await service.get_or_create_browser(str(session_id))
    
    path = state.get("screenshot_path")
    if not path or not os.path.exists(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Screenshot not generated yet",
        )
    return FileResponse(path, media_type="image/png")


@router.post("/navigate", status_code=status.HTTP_202_ACCEPTED)
async def browser_navigate(session_id: UUID, payload: NavigatePayload, request: Request) -> Dict[str, Any]:
    """Instruct the session's browser context to navigate to a URL."""
    service = _browser_service(request)
    return await service.navigate(str(session_id), payload.url)


@router.post("/click", status_code=status.HTTP_202_ACCEPTED)
async def browser_click(session_id: UUID, payload: ClickPayload, request: Request) -> Dict[str, Any]:
    """Perform a mouse click at specific coordinates or on a CSS selector."""
    service = _browser_service(request)
    return await service.click(str(session_id), payload.selector, payload.x, payload.y)


@router.post("/type", status_code=status.HTTP_202_ACCEPTED)
async def browser_type(session_id: UUID, payload: TypePayload, request: Request) -> Dict[str, Any]:
    """Type keyboard text into the page."""
    service = _browser_service(request)
    return await service.type_text(str(session_id), payload.text, payload.selector)


@router.post("/control", status_code=status.HTTP_202_ACCEPTED)
async def browser_control(session_id: UUID, payload: ControlPayload, request: Request) -> Dict[str, Any]:
    """Transfer browser control between the agent and human user."""
    if payload.control not in ("agent", "user"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Control mode must be 'agent' or 'user'",
        )
    service = _browser_service(request)
    return await service.set_control(str(session_id), payload.control)


@router.post("/back", status_code=status.HTTP_202_ACCEPTED)
async def browser_back(session_id: UUID, request: Request) -> Dict[str, Any]:
    """Go back in the browser history."""
    service = _browser_service(request)
    return await service.go_back(str(session_id))


@router.post("/forward", status_code=status.HTTP_202_ACCEPTED)
async def browser_forward(session_id: UUID, request: Request) -> Dict[str, Any]:
    """Go forward in the browser history."""
    service = _browser_service(request)
    return await service.go_forward(str(session_id))


@router.post("/reload", status_code=status.HTTP_202_ACCEPTED)
async def browser_reload(session_id: UUID, request: Request) -> Dict[str, Any]:
    """Reload the current browser page."""
    service = _browser_service(request)
    return await service.reload(str(session_id))

import os
