"""Foundation-only fake handler used by the Phase 7 vertical slice."""

from __future__ import annotations

from collections.abc import Mapping

from windagent.kernel.types.json import JSONValue, thaw_json


class FakeJobHandler:
    """Echo a payload through the real durable worker path."""

    @property
    def job_type(self) -> str:
        return "debug.echo"

    async def handle(self, payload: Mapping[str, JSONValue]) -> object:
        return {"echo": thaw_json(payload), "handled": True}
