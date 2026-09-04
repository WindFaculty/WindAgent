"""JSON-safe immutable values used by event payloads."""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | tuple[JSONValue, ...] | Mapping[str, JSONValue]


def freeze_json(value: object) -> JSONValue:
    """Validate and recursively freeze a JSON-compatible value.

    Lists become tuples and mappings become read-only mapping proxies.  This
    avoids a mutable payload changing after an event has been created.
    """

    if value is None or isinstance(value, (str, bool, int)):
        return cast(JSONValue, value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON float values must be finite")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            frozen[key] = freeze_json(item)
        return cast(JSONValue, MappingProxyType(frozen))
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    raise TypeError(f"value is not JSON-compatible: {type(value).__name__}")


def freeze_json_mapping(value: Mapping[str, object]) -> Mapping[str, JSONValue]:
    """Freeze a JSON object, rejecting non-string keys and non-JSON leaves."""

    frozen = freeze_json(value)
    if not isinstance(frozen, Mapping):  # pragma: no cover - guarded by the input type.
        raise TypeError("event payload must be a JSON object")
    return frozen


def thaw_json(value: JSONValue) -> object:
    """Return a mutable JSON-compatible representation for serialization."""

    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value
