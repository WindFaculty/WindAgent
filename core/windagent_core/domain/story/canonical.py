"""
Canonical Story content base (studio.artifact/v1alpha1).

Every canonical content model:

- is immutable (``frozen=True``) with ``extra="allow"`` so additive compatible
  fields survive round trips within the same schema version;
- declares ``schema_version`` (content-form family) and a stable
  ``artifact_type`` discriminator — these are content-form metadata, NOT
  envelope fields (no ``artifact_id`` / ``content_hash`` / revision / prompt
  provenance at content level; the A envelope owns those);
- serializes deterministically (sorted keys, ``ensure_ascii=False``);
- exposes a presentation-safe ``to_summary()`` for C display.

Cross-cutting rule 7: ``LockedScreenplayPackage`` references immutable
approved artifacts by ``(artifact_id, content_hash, revision_id)``; it never
embeds a mutable in-memory draft as authority.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, ClassVar, Dict

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.story.versions import (
    ARTIFACT_SCHEMA_VERSION,
    canonical_json_bytes,
    validate_artifact_schema_version,
)

__all__ = ["StoryContent", "content_hash_of"]


def content_hash_of(content: Any) -> str:
    """SHA-256 over the canonical serialization of a content value.

    Matches the A envelope hash semantics: stable for the same logical
    content regardless of key insertion order or ASCII escaping.
    """
    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


class StoryContent(BaseModel):
    """Base class for all canonical Story content models."""

    model_config = ConfigDict(frozen=True, extra="allow")

    schema_version: str = Field(default=ARTIFACT_SCHEMA_VERSION)
    artifact_type: str = Field(min_length=1)

    # Presentation-safe summary: models override with a curated field set.
    SUMMARY_FIELDS: ClassVar[tuple[str, ...]] = ()

    def __init__(self, **data: Any) -> None:
        # Fail closed on unknown schema versions at construction time.
        schema_version = data.get("schema_version", ARTIFACT_SCHEMA_VERSION)
        validate_artifact_schema_version(schema_version)
        super().__init__(**data)

    # -- canonical serialization -------------------------------------------
    def to_canonical_dict(self) -> Dict[str, Any]:
        """JSON-compatible canonical dict (sorted keys, UTC ISO timestamps)."""
        return json.loads(self.model_dump_json())

    def canonical_bytes(self) -> bytes:
        """Stable canonical bytes over the full content (schema_version included)."""
        return canonical_json_bytes(self.to_canonical_dict())

    def content_hash(self) -> str:
        """SHA-256 of the canonical serialization (stable for same content)."""
        return content_hash_of(self.to_canonical_dict())

    def serialize(self) -> str:
        """Canonical JSON string (sorted keys, ensure_ascii=False)."""
        return json.dumps(
            json.loads(self.model_dump_json()),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    # -- presentation -------------------------------------------------------
    def to_summary(self) -> Dict[str, Any]:
        """Presentation-safe summary: curated fields, no raw provider text."""
        data = self.to_canonical_dict()
        if self.SUMMARY_FIELDS:
            return {k: data[k] for k in self.SUMMARY_FIELDS if k in data}
        return {
            "artifact_type": data.get("artifact_type"),
            "schema_version": data.get("schema_version"),
        }

    @classmethod
    def deserialize(cls, raw: str) -> "StoryContent":
        data = json.loads(raw)
        return cls.model_validate(data)
