"""Automated parity comparator for legacy (V2) vs Provider V3 read/list operations."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List


@dataclass
class ParityResult:
    operation: str
    passed: bool = False
    legacy_result: Any = None
    v3_result: Any = None
    diff: str | None = None
    errors: List[str] = field(default_factory=list)


async def compare_list_models(
    legacy_fn: Callable[[], Awaitable[List[Dict[str, Any]]]],
    v3_fn: Callable[[], Awaitable[List[Dict[str, Any]]]],
) -> ParityResult:
    result = ParityResult(operation="list_models")
    try:
        legacy = await legacy_fn()
    except Exception as exc:
        result.errors.append(f"legacy error: {exc}")
        return result
    try:
        v3 = await v3_fn()
    except Exception as exc:
        result.errors.append(f"v3 error: {exc}")
        return result

    result.legacy_result = legacy
    result.v3_result = v3

    legacy_ids = sorted(m.get("id") for m in legacy)
    v3_ids = sorted(m.get("id") for m in v3)
    if legacy_ids == v3_ids:
        result.passed = True
    else:
        result.diff = f"ids differ: legacy={legacy_ids} v3={v3_ids}"
    return result


async def compare_routing_rules(
    legacy_fn: Callable[[], Awaitable[List[Dict[str, Any]]]],
    v3_fn: Callable[[], Awaitable[List[Dict[str, Any]]]],
) -> ParityResult:
    result = ParityResult(operation="list_routing_rules")
    try:
        legacy = await legacy_fn()
    except Exception as exc:
        result.errors.append(f"legacy error: {exc}")
        return result
    try:
        v3 = await v3_fn()
    except Exception as exc:
        result.errors.append(f"v3 error: {exc}")
        return result

    result.legacy_result = legacy
    result.v3_result = v3

    legacy_roles = sorted(r.get("id") or r.get("role") for r in legacy)
    v3_roles = sorted(r.get("id") or r.get("role") for r in v3)
    if legacy_roles == v3_roles:
        result.passed = True
    else:
        result.diff = f"roles differ: legacy={legacy_roles} v3={v3_roles}"
    return result


async def run_parity_suite(
    suite: Dict[str, tuple[Callable, Callable]],
) -> List[ParityResult]:
    names = {
        "list_models": compare_list_models,
        "list_routing_rules": compare_routing_rules,
    }
    tasks = [
        names[name](legacy_fn, v3_fn)
        for name, (legacy_fn, v3_fn) in suite.items()
        if name in names
    ]
    return list(await asyncio.gather(*tasks))
