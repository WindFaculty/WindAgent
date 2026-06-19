"""Publisher hooks for the EventBus.

Phase 2: mirror every published envelope into the `execution_events`
table so the frontend can replay after reconnect, and we have a full
audit log even after restart.

Phase 10: also mirror every envelope into a per-session JSONL file at
``{root}/{session_id}/events.jsonl`` so the audit trail is portable
(plain text, can be grepped / jq'd) and survives SQLite corruption or
DB schema migration. Both hooks share the same async-publish fan-out
in EventBus; either can fail without affecting the other or the live
WebSocket subscribers.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Dict, Optional, Union
from uuid import uuid4

from db.database import Database
from db.models import ExecutionEventORM
from schemas.event import EventEnvelope


log = logging.getLogger(__name__)


def make_execution_event_hook(db: Database):
    """Return an async hook that writes every event into execution_events."""

    async def hook(session_id: str, envelope: EventEnvelope) -> None:
        # data_json is already JSON-serialisable (envelope built via
        # BaseModel.model_dump(mode="json") which returns JSON-safe types).
        try:
            async with db.session() as s:
                s.add(ExecutionEventORM(
                    id=str(uuid4()),
                    session_id=session_id,
                    event_type=envelope.event,
                    data_json=json.dumps(envelope.data, ensure_ascii=False),
                    created_at=envelope.timestamp or datetime.now(timezone.utc),
                ))
        except Exception:  # noqa: BLE001
            log.exception("failed to persist event %s for session %s", envelope.event, session_id)

    return hook


# ---------------------------------------------------------------------------
# Phase 10: per-session JSONL writer
# ---------------------------------------------------------------------------


# Cap open file handles so a long-running server with thousands of
# sessions doesn't leak fds. Each session handle is opened lazily on the
# first event and reused for subsequent writes. When the cap is hit the
# least-recently-used handle is closed and re-opened on demand.
_JSONL_HANDLE_CAP = 64


class _JsonlWriter:
    """Thread-safe append-only writer for per-session JSONL audit files.

    One file per session_id, located at ``{root}/{session_id}/events.jsonl``.
    Each line is one envelope serialised as JSON. Files are flushed
    after every write so a crash loses at most the in-flight write
    (acceptable for an audit trail; the DB mirror is the durable source
    of truth).
    """

    def __init__(self, root: Path, *, max_open: int = _JSONL_HANDLE_CAP) -> None:
        self._root = Path(root)
        self._max_open = max_open
        self._lock = threading.Lock()
        # LRU: most-recently used at the back.
        self._handles: "OrderedDict[str, IO[str]]" = OrderedDict()

    def _path_for(self, session_id: str) -> Path:
        return self._root / session_id / "events.jsonl"

    def _open(self, session_id: str) -> IO[str]:
        p = self._path_for(session_id)
        # mkdir can raise ValueError on Windows for embedded NULs and
        # OSError for permission/path errors; treat both as "open failed".
        p.parent.mkdir(parents=True, exist_ok=True)
        # newline="" so \n stays literal (we add our own per line).
        return open(p, mode="a", encoding="utf-8", newline="")

    async def write(self, session_id: str, envelope: EventEnvelope) -> None:
        line = json.dumps(
            {
                "event": envelope.event,
                "timestamp": (
                    envelope.timestamp.isoformat()
                    if envelope.timestamp else datetime.now(timezone.utc).isoformat()
                ),
                "data": envelope.data,
            },
            ensure_ascii=False,
        )
        with self._lock:
            fh = self._handles.get(session_id)
            if fh is None:
                if len(self._handles) >= self._max_open:
                    # Evict LRU.
                    evict_id, evict_fh = self._handles.popitem(last=False)
                    try:
                        evict_fh.flush()
                        evict_fh.close()
                    except Exception:  # noqa: BLE001
                        log.warning("jsonl: failed closing evicted handle %s", evict_id)
                try:
                    fh = self._open(session_id)
                except (OSError, ValueError) as exc:
                    # ValueError catches e.g. embedded NUL on Windows.
                    log.error("jsonl: cannot open %s: %s", session_id, exc)
                    return
                self._handles[session_id] = fh
            else:
                # Bump to MRU.
                self._handles.move_to_end(session_id)
            try:
                fh.write(line + "\n")
                fh.flush()
            except OSError as exc:
                log.error("jsonl: write failed for %s: %s", session_id, exc)
                # Drop the handle so the next event retries the open.
                self._handles.pop(session_id, None)
                try:
                    fh.close()
                except Exception:  # noqa: BLE001
                    pass

    def close_all(self) -> None:
        with self._lock:
            for sid, fh in list(self._handles.items()):
                try:
                    fh.flush()
                    fh.close()
                except Exception:  # noqa: BLE001
                    log.warning("jsonl: failed closing handle %s", sid)
            self._handles.clear()


def make_jsonl_event_hook(root: Union[Path, str]):
    """Return an async hook that appends each envelope to a per-session
    JSONL file. ``root`` defaults to ``artifacts/runs`` (matching the
    ToolExecutor screenshot location) but can be overridden via
    ``WINDAGENT_ARTIFACTS_ROOT``.
    """
    writer = _JsonlWriter(Path(root))

    async def hook(session_id: str, envelope: EventEnvelope) -> None:
        await writer.write(session_id, envelope)

    # Expose for tests + lifespan teardown.
    hook.close = writer.close_all  # type: ignore[attr-defined]
    return hook
