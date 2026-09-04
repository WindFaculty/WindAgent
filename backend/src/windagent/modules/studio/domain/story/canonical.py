"""Canonical Story content base (studio.artifact/v1alpha1).

Every canonical content model is immutable, declares ``schema_version`` and
``artifact_type``, serializes deterministically (sorted keys), and exposes a
presentation-safe ``to_summary()``.  The envelope owns identity/hash/revision;
content models never carry ``artifact_id`` or ``content_hash``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..errors import StudioValidationError

ARTIFACT_SCHEMA_VERSION = "studio.artifact/v1alpha1"


def canonical_json_bytes(content: Any) -> bytes:
    return json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")


def content_hash_of(content: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


def validate_artifact_schema_version(value: str) -> None:
    if value != ARTIFACT_SCHEMA_VERSION:
        raise StudioValidationError(
            f"Unsupported artifact schema version {value!r}; expected {ARTIFACT_SCHEMA_VERSION!r}.",
            context={"schema_version": value},
        )


class StoryContent(BaseModel):
    """Base class for all canonical Story content models."""

    model_config = ConfigDict(frozen=True, extra="allow")

    schema_version: str = Field(default=ARTIFACT_SCHEMA_VERSION)
    artifact_type: str = Field(min_length=1)

    SUMMARY_FIELDS: ClassVar[tuple[str, ...]] = ()

    def __init__(self, **data: Any) -> None:
        schema_version = data.get("schema_version", ARTIFACT_SCHEMA_VERSION)
        if isinstance(schema_version, str):
            validate_artifact_schema_version(schema_version)
        super().__init__(**data)

    def to_canonical_dict(self) -> dict[str, Any]:
        return json.loads(self.model_dump_json())  # type: ignore[no-any-return]

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_canonical_dict())

    def content_hash(self) -> str:
        return content_hash_of(self.to_canonical_dict())

    def serialize(self) -> str:
        return json.dumps(
            json.loads(self.model_dump_json()),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def to_summary(self) -> dict[str, Any]:
        data = self.to_canonical_dict()
        if self.SUMMARY_FIELDS:
            return {k: data[k] for k in self.SUMMARY_FIELDS if k in data}
        return {
            "artifact_type": data.get("artifact_type"),
            "schema_version": data.get("schema_version"),
        }

    @classmethod
    def deserialize(cls, raw: str) -> StoryContent:
        data: dict[str, Any] = json.loads(raw)
        return cls.model_validate(data)


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "StoryContent",
    "canonical_json_bytes",
    "content_hash_of",
    "validate_artifact_schema_version",
]
