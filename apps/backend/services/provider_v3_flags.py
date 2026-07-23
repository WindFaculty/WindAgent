"""Granular Provider V3 cutover flags.

All flags default to false.  They are independent from WINDAGENT_ARCH_V2.
"""

from __future__ import annotations

import os


_PREFIX = "WINDAGENT_PROVIDER_V3_"


def _flag(name: str) -> bool:
    value = os.environ.get(f"{_PREFIX}{name}", "").lower()
    return value in ("1", "true", "yes", "on")


def v3_read_enabled() -> bool:
    return _flag("READ")


def v3_write_enabled() -> bool:
    return _flag("WRITE")


def v3_test_connect_enabled() -> bool:
    return _flag("TEST_CONNECT")


def v3_execute_enabled() -> bool:
    return _flag("EXECUTE")


def v3_route_lock_enabled() -> bool:
    return _flag("ROUTE_LOCK")


def v3_cache_enabled() -> bool:
    return _flag("CACHE")


def flags_summary() -> dict:
    return {
        "read": v3_read_enabled(),
        "write": v3_write_enabled(),
        "test_connect": v3_test_connect_enabled(),
        "execute": v3_execute_enabled(),
        "route_lock": v3_route_lock_enabled(),
        "cache": v3_cache_enabled(),
    }
