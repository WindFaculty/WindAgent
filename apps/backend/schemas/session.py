"""Schemas for chat sessions and messages."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


SessionStatus = Literal["idle", "planning", "pending", "running", "paused", "completed", "failed", "cancelled", "interrupted"]
MessageSender = Literal["user", "assistant", "system"]


class ChatSession(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    status: SessionStatus = "idle"


class CreateSessionRequest(BaseModel):
    agent_id: Optional[str] = None
    workspace_root: Optional[str] = None
    title: Optional[str] = None


class CreateSessionResponse(BaseModel):
    session_id: UUID
    created_at: datetime
    status: SessionStatus = "idle"


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class Message(BaseModel):
    id: UUID
    session_id: UUID
    sender: MessageSender
    content: str
    created_at: datetime