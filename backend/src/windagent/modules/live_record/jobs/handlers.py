"""Live Record job handlers (ADAPT + harden — native engine remains in desktop sidecar)."""

from __future__ import annotations

from typing import Any

from ..application.runtime import LiveRecordServices


class _Handler:
    def __init__(self, services: LiveRecordServices | None = None) -> None:
        self._services = services


class DirectorHeartbeatJobHandler(_Handler):
    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id", "")) if isinstance(payload, dict) else ""
        return {"session_id": session_id, "status": "HEARTBEAT_OK"}


class SegmentFinalizeJobHandler(_Handler):
    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        segment_id = str(payload.get("segment_id", "")) if isinstance(payload, dict) else ""
        return {"segment_id": segment_id, "status": "FINALIZED"}
