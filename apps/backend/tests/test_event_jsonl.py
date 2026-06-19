"""Tests for the per-session JSONL event writer (Phase 10).

Covers:
  - One file per session_id, one JSON object per line.
  - Flushes after every write (file contents visible immediately).
  - LRU eviction when more than max_open sessions are written to.
  - close_all() flushes and closes every handle.
  - Survives OSError on open (logs error, does not raise).
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from schemas.event import EventEnvelope
from services.event_hooks import _JsonlWriter, make_jsonl_event_hook


def _env(event: str, **data) -> EventEnvelope:
    return EventEnvelope(
        event=event,  # type: ignore[arg-type]
        timestamp=datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc),
        data=data,
    )


@pytest.mark.asyncio
async def test_jsonl_writes_one_line_per_event(tmp_path: Path) -> None:
    w = _JsonlWriter(tmp_path)
    sid = "sess-A"
    await w.write(sid, _env("message_received", content="hi"))
    await w.write(sid, _env("step_started", order=1))
    w.close_all()

    p = tmp_path / sid / "events.jsonl"
    assert p.exists()
    lines = p.read_text(encoding="utf-8").rstrip("\n").split("\n")
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event"] == "message_received"
    assert first["data"]["content"] == "hi"
    assert first["timestamp"].startswith("2026-06-19T12:00:00")
    second = json.loads(lines[1])
    assert second["event"] == "step_started"


@pytest.mark.asyncio
async def test_jsonl_separate_files_per_session(tmp_path: Path) -> None:
    w = _JsonlWriter(tmp_path)
    await w.write("sess-A", _env("session_created"))
    await w.write("sess-B", _env("session_created"))
    w.close_all()

    a = (tmp_path / "sess-A" / "events.jsonl").read_text(encoding="utf-8").strip()
    b = (tmp_path / "sess-B" / "events.jsonl").read_text(encoding="utf-8").strip()
    assert a and b
    assert json.loads(a)["data"] == {}


@pytest.mark.asyncio
async def test_jsonl_lru_eviction(tmp_path: Path) -> None:
    # max_open=2 -> writing a third session must evict the oldest handle.
    w = _JsonlWriter(tmp_path, max_open=2)
    await w.write("a", _env("session_created"))
    await w.write("b", _env("session_created"))
    await w.write("c", _env("session_created"))  # evicts "a"
    await w.write("a", _env("step_started"))      # re-opens "a"
    w.close_all()

    # All three files must be present and contain the expected number of lines.
    assert (tmp_path / "a" / "events.jsonl").exists()
    assert (tmp_path / "b" / "events.jsonl").exists()
    assert (tmp_path / "c" / "events.jsonl").exists()
    a_lines = (
        (tmp_path / "a" / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    )
    assert len(a_lines) == 2  # initial + re-open write


@pytest.mark.asyncio
async def test_jsonl_factory_hook_writes_via_async(tmp_path: Path) -> None:
    hook = make_jsonl_event_hook(tmp_path)
    await hook("sess-1", _env("tool_call_started", tool="open_app"))
    await hook("sess-1", _env("tool_call_finished", status="success"))
    hook.close()

    p = tmp_path / "sess-1" / "events.jsonl"
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["data"]["status"] == "success"


@pytest.mark.asyncio
async def test_jsonl_handles_open_failure(tmp_path: Path, caplog) -> None:
    # Force open() to fail by passing a path that contains a NUL.
    bad = _JsonlWriter(tmp_path / "bad\x00name")
    await bad.write("sess-X", _env("error"))
    bad.close_all()
    # We expect a log message, no exception.
    assert any("jsonl" in rec.message for rec in caplog.records)
