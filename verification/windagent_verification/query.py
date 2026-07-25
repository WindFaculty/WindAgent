"""Verification query service alias for composition roots.

VerificationQueryService is the async facade over verification domain used by
API/Worker composition roots.
"""
from __future__ import annotations


class VerificationQueryService:
    """Async query service over verification results."""

    def __init__(self) -> None:
        self._results: list = []

    async def list_results(self):  # ponytail: minimal stub
        return list(self._results)

    async def close(self) -> None:
        pass


__all__ = ["VerificationQueryService"]
