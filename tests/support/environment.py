"""Environment / clock / deterministic-ID helpers.

Root conftest imports these to provide:

* ``isolated_env`` — hermetic env vars per test (TMPDIR, DATABASE_URL, etc.)
* ``deterministic_ids`` — short stable IDs for tests that need them
* ``fake_clock`` — monotonic clock that can be advanced deterministically
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


def isolated_tmp_env(monkeypatch, tmp_path: Path) -> dict[str, str]:
    """Set ``TMPDIR/TEMP/TMP`` to ``tmp_path`` and return the mapping.

    Required by ADR 0006 A5: tests must not write to the source tree.
    """
    env = {
        "TMPDIR": str(tmp_path),
        "TEMP": str(tmp_path),
    }
    if os.name == "nt":
        env["TMP"] = str(tmp_path)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return env


def deterministic_id(prefix: str = "test") -> str:
    """Return a short deterministic-looking ID (still unique per call)."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class FakeClock:
    """Monotonic fake clock that can be advanced without real sleep."""

    _now: float = 0.0

    def time(self) -> float:
        return self._now

    def monotonic(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def sleep(self, seconds: float) -> None:
        """Advance the clock — does NOT block."""
        self.advance(seconds)


def install_fake_clock(monkeypatch) -> FakeClock:
    """Monkey-patch ``time.time`` / ``time.monotonic`` to use a ``FakeClock``.

    Use sparingly — only for tests that would otherwise use ``time.sleep``.
    Most tests should use ``tests.support.waiting.poll_until`` instead.
    """
    clock = FakeClock(_now=time.monotonic())
    monkeypatch.setattr(time, "monotonic", clock.monotonic)
    monkeypatch.setattr(time, "time", clock.time)
    return clock
