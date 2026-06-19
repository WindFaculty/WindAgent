"""SQLAlchemy ORM models for the WindAgent backend.

Six tables per ban_ke_hoach.md §2.2:

  chat_sessions   - one row per chat session
  messages        - user/assistant/system messages per session
  workflows       - workflow owned by a session (1:1 in MVP)
  workflow_steps  - ordered steps inside a workflow
  tool_calls      - audit trail of every tool invocation (Phase 3 fills this)
  execution_events- every event envelope ever published (for replay + audit)

UUIDs are stored as String(36) since SQLite has no native UUID type.
JSON payloads are stored as TEXT (SQLite has a JSON affinity but we
keep it as text for simplicity).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------- chat_sessions ----------

class ChatSessionORM(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")

    messages: Mapped[list["MessageORM"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    workflows: Mapped[list["WorkflowORM"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


# ---------- messages ----------

class MessageORM(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id"), nullable=False
    )
    sender: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    session: Mapped[ChatSessionORM] = relationship(back_populates="messages")


Index("ix_messages_session_id_created_at", MessageORM.session_id, MessageORM.created_at)


# ---------- workflows ----------

class WorkflowORM(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    session: Mapped[ChatSessionORM] = relationship(back_populates="workflows")
    steps: Mapped[list["WorkflowStepORM"]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowStepORM.order_index",
    )


# ---------- workflow_steps ----------

class WorkflowStepORM(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    workflow: Mapped[WorkflowORM] = relationship(back_populates="steps")


Index("ix_workflow_steps_workflow_id_order", WorkflowStepORM.workflow_id, WorkflowStepORM.order_index)


# ---------- tool_calls ----------

class ToolCallORM(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    step_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


Index("ix_tool_calls_session_id_created_at", ToolCallORM.session_id, ToolCallORM.created_at)


# ---------- execution_events ----------

class ExecutionEventORM(Base):
    __tablename__ = "execution_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


Index("ix_execution_events_session_id_created_at", ExecutionEventORM.session_id, ExecutionEventORM.created_at)


__all__ = [
    "Base",
    "ChatSessionORM",
    "MessageORM",
    "WorkflowORM",
    "WorkflowStepORM",
    "ToolCallORM",
    "ExecutionEventORM",
]
